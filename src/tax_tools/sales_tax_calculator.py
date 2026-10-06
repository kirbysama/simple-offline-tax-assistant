"""Deterministic NY Sales Tax Classifier and Reverse Calculator."""

import re
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple, Union

from tax_tools.activity_normalizer import ActivityNormalizer
from tax_tools.sales_tax_models import (
    DEFAULT_COUNTY,
    DEFAULT_TAX_RATE,
    NormalizedTransaction,
    SalesTaxReport,
    TransactionTreatment,
    get_tax_rate_for_county,
)


class SalesTaxCalculator:
    """Classifies transactions and reverse-calculates New York sales tax paid."""

    def __init__(self, county_name: str = DEFAULT_COUNTY, county_rate: Optional[float] = None):
        self.county_name = county_name
        self.tax_rate = county_rate if county_rate is not None else get_tax_rate_for_county(county_name)
        self.normalizer = ActivityNormalizer()

    def compute_reverse_tax(self, amount: float) -> Tuple[float, float]:
        """Reverse calculate pre-tax base amount and sales tax embedded in settled amount.
        
        Formula:
            Sales Tax = Amount * (r / (1 + r))
            Pre-Tax Base = Amount / (1 + r)
        Enforces exact cent parity: Pre-Tax Base + Sales Tax = Amount.
        Works for both positive amounts and negative refunds.
        """
        if amount == 0.0 or self.tax_rate == 0.0:
            return 0.0, 0.0

        r = self.tax_rate
        pre_tax = round(amount / (1.0 + r), 2)
        sales_tax = round(amount - pre_tax, 2)
        return pre_tax, sales_tax

    def classify_transaction(self, tx: NormalizedTransaction) -> NormalizedTransaction:
        """Apply multi-tier deterministic classification rules to a single transaction."""
        desc = tx.description.strip()
        desc_upper = desc.upper()
        cat = (tx.category or "").strip()
        cat_upper = cat.upper()
        memo_upper = (tx.memo or "").upper()

        tx.tax_rate = self.tax_rate

        # -------------------------------------------------------------
        # Tier 1: Non-Spend Exclusion Filter (Payments, Transfers, Fees)
        # -------------------------------------------------------------
        # Payments
        payment_keywords = [
            "AUTOMATIC PAYMENT",
            "AUTOPAY",
            "DIRECTPAY",
            "PAYMENT - THANK",
            "PAYMENT THANK YOU",
            "ONLINE PAYMENT",
            "CHASE CREDIT CRD AUTOPAY",
            "MOBILE PAYMENT",
            "EBILL PAYMENT",
            "BILL PAYMENT",
            "PAYMENT RECEIVED",
            "THANK YOU - MOBILE",
            "THANK YOU - WEB",
            "AUTO-PMT",
            "LOAN_PMT",
        ]
        if any(kw in desc_upper for kw in payment_keywords) or cat_upper == "PAYMENT" or "PAYMENTS AND CREDITS" in cat_upper:
            # Note: Do not exclude if it's a merchant refund
            if not tx.is_refund:
                tx.treatment = TransactionTreatment.EXCLUDED_PAYMENT
                tx.classification_reason = "Non-spend: card payment or autopay adjustment"
                tx.pre_tax_amount = 0.0
                tx.sales_tax = 0.0
                return tx

        # Transfers & Banking Adjustments
        transfer_keywords = [
            "BALANCE TRANSFER",
            "ACCT_XFER",
            "INST XFER",
            "XFER",
            "CHASE_TO_PARTNERFI",
            "PARTNERFI_TO_CHASE",
            "WIRE TRANSFER",
            "CHECK_DEPOSIT",
            "DEPOSIT",
            "DEPOSITS",
            "QUICKPAY",
            "ZELLE",
            "ATM",
            "WITHDRAWAL",
            "PAYPAL",
            "ROBINHOOD",
            "WU DIGITAL",
            "WUVISAAFT",
            "CASHAPP",
            "CASH APP",
            "CASH APP*",
            "SOFI",
            "FENNEL",
        ]
        if any(kw in desc_upper for kw in transfer_keywords) or cat_upper in ("ACCT_XFER", "ACH_DEBIT", "ACH_CREDIT"):
            tx.treatment = TransactionTreatment.EXCLUDED_TRANSFER
            tx.classification_reason = "Non-spend: account transfer or banking adjustment"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # Annual Fees & Finance Charges
        fee_keywords = [
            "ANNUAL MEMBERSHIP FEE",
            "ANNUAL FEE",
            "MEMBERSHIP FEE",
            "LATE FEE",
            "OVERLIMIT FEE",
            "FEE CHARGED",
            "FOREIGN TRANSACTION FEE",
            "INTEREST CHARGE",
            "FINANCE CHARGE",
            "PURCHASE INTEREST",
        ]
        if any(kw in desc_upper for kw in fee_keywords) or "FEES & ADJUSTMENTS" in cat_upper:
            tx.treatment = TransactionTreatment.EXCLUDED_FEE
            tx.classification_reason = "Non-spend: card annual fee or finance interest charge"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # -------------------------------------------------------------
        # Tier 2: Merchant Refund / Return Handler
        # -------------------------------------------------------------
        if tx.is_refund or tx.amount < 0:
            pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
            tx.treatment = TransactionTreatment.REFUND
            tx.is_refund = True
            tx.pre_tax_amount = pre_tax
            tx.sales_tax = sales_tax
            tx.classification_reason = f"Merchant return/refund: negative sales tax offset at {self.tax_rate*100:.3f}%"
            return tx

        # -------------------------------------------------------------
        # Tier 3: Geographic Exclusion Filter (Foreign Only)
        # Note: Airlines, hotels, and general travel are treated as taxable.
        # -------------------------------------------------------------
        foreign_indicators = [" CAN", " LUX", " MEX", " GBR", " FRA", " DEU", " CAN ", " LUX "]
        is_foreign = any(ind in desc_upper for ind in foreign_indicators) or "INTERNATIONAL" in desc_upper

        if is_foreign:
            tx.treatment = TransactionTreatment.EXCLUDED_OUT_OF_STATE
            tx.category = "Out-of-State / Foreign"
            tx.classification_reason = "Geographic exclusion: foreign transaction"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # -------------------------------------------------------------
        # Tier 4: Priority Taxable Retail Overrides (Brands, Phones, Marketplaces)
        # Prevents substring collisions like Amazon Marketplace matching 'MARKET' in groceries.
        # -------------------------------------------------------------
        priority_taxable_keywords = [
            "76",
            "MCDONALD",
            "ZOLA",
            "ZOLA.COM",
            "SQ *",
            "SQ*",
            "SQ AKA SQUARE",
            "SQUARE",
            "AMAZON",
            "AMAZON.COM",
            "AMAZON*",
            "BISTRO",
            "CAFE",
            "CAFES",
            "CAFFE",
            "TOOLS",
            "MINT MOBILE",
            "VERIZON",
            "AT&T",
            "ATT *",
            "T-MOBILE",
            "TMOBILE",
            "APPLE",
            "SAMSUNG",
            "GOOGLE PIXEL",
            "MOTOROLA",
            "AIRLINE",
            "DELTA AIR",
            "UNITED AIR",
            "AMERICAN AIR",
            "JETBLUE",
            "SOUTHWEST AIR",
            "AIRWAYS",
            "FRONTIER AIR",
            "SPIRIT AIR",
            "ALASKA AIR",
            "HOTEL",
            "MOTEL",
            "MARRIOTT",
            "HILTON",
            "HYATT",
            "SHERATON",
            "WESTIN",
            "AIRBNB",
            "VRBO",
            "RESORT",
        ]
        if any(kw in desc_upper for kw in priority_taxable_keywords):
            pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
            tx.treatment = TransactionTreatment.TAXABLE
            tx.pre_tax_amount = pre_tax
            tx.sales_tax = sales_tax
            # Categorize appropriately
            if any(kw in desc_upper for kw in ["CAFE", "CAFES", "CAFFE", "BISTRO", "MCDONALD"]):
                tx.category = "Dining & Food Service"
                tx.classification_reason = f"Taxable: restaurant/cafe food service at {self.tax_rate*100:.3f}%"
            elif any(kw in desc_upper for kw in ["AIRLINE", "DELTA AIR", "UNITED AIR", "AMERICAN AIR", "JETBLUE", "SOUTHWEST AIR", "AIRWAYS", "HOTEL", "MOTEL", "MARRIOTT", "HILTON", "HYATT", "SHERATON", "WESTIN", "AIRBNB", "VRBO", "RESORT"]):
                tx.category = "Travel & Lodging"
                tx.classification_reason = f"Taxable: airline travel or lodging accommodation at {self.tax_rate*100:.3f}%"
            elif any(kw in desc_upper for kw in ["MINT MOBILE", "VERIZON", "AT&T", "ATT *", "T-MOBILE", "TMOBILE", "APPLE", "SAMSUNG", "GOOGLE PIXEL", "MOTOROLA"]):
                tx.category = "Telecommunications & Hardware"
                tx.classification_reason = f"Taxable: telecommunications service or hardware at {self.tax_rate*100:.3f}%"
            else:
                tx.category = "General Retail & Merchandise"
                tx.classification_reason = f"Taxable: retail merchandise or marketplace purchase at {self.tax_rate*100:.3f}%"
            return tx

        # -------------------------------------------------------------
        # Tier 5: Tax-Exempt Purchases (NY Tax Law § 1115)
        # -------------------------------------------------------------
        # 5A: Groceries & Unprepared Food
        grocery_keywords = [
            "SUPERMARKET",
            "GROCERY",
            "GROCERIES",
            "TRADER JOE",
            "WHOLE FOODS",
            "STOP & SHOP",
            "ALDI",
            "KEY FOOD",
            "FAIRWAY",
            "WEGMANS",
            "FOODTOWN",
            "C-TOWN",
            "H MART",
            "HMART",
            "GOOD SUPERMARKET",
            "GOLDEN HARVEST FARMS",
            "MORTON WILLIAMS",
            "PRODUCE",
            "MARKET",
            "BAKERY",
            "BUTCHER",
            "FISH MARKET",
            "TNT LIQUIDATORS",
        ]
        if cat_upper in ("GROCERIES", "SUPERMARKETS", "MERCHANDISE & SUPPLIES-GROCERIES") or any(
            kw in desc_upper for kw in grocery_keywords
        ):
            tx.treatment = TransactionTreatment.EXEMPT
            tx.category = "Groceries & Supermarkets"
            tx.classification_reason = "Exempt under NY Tax Law § 1115(a)(1): unprepared food for home consumption"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # 4B: Commuter Transit, Tolls & Municipal Parking
        transit_keywords = [
            "MTA",
            "OMNY",
            "METROCARD",
            "PATH",
            "E-Z*PASS",
            "EZPASS",
            "METRO-NORTH",
            "LIRR",
            "LONG ISLAND RAIL ROAD",
            "NJ TRANSIT",
            "BRIDGE AND TUNNEL",
            "FERRY",
            "PORT AUTHORITY",
            "SUBWAY",
            "COMMUTER",
            "PARKNYC",
            "PARK NYC",
        ]
        if any(kw in desc_upper for kw in transit_keywords):
            tx.treatment = TransactionTreatment.EXEMPT
            tx.category = "Commuter Transit, Tolls & Parking"
            tx.classification_reason = "Exempt: public commuter transportation, bridge/highway tolls, or municipal parking"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # 4C: Prescriptions & Medical
        medical_keywords = [
            "PHARMACY",
            "CVS",
            "WALGREENS",
            "DUANE READE",
            "RITE AID",
            "PRESCRIPTION",
            "HOSPITAL",
            "DENTAL",
            "DOCTOR",
            "MEDICAL",
            "CLINIC",
            "HEALTH",
            "URGENT CARE",
            "OPTOMETRY",
            "QUEST DIAGNOSTICS",
            "LABCORP",
            "DR JEN NATURAL",
            "MEDICINE",
        ]
        if cat_upper in ("MEDICAL", "HEALTHCARE", "PHARMACIES") or any(kw in desc_upper for kw in medical_keywords):
            tx.treatment = TransactionTreatment.EXEMPT
            tx.category = "Medical & Prescriptions"
            tx.classification_reason = "Exempt under NY Tax Law § 1115(a)(3): prescription drugs and medical care"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # 5D: Motor Fuel & Gas Stations (NY Tax Law § 1115 / Excise Tax Treated)
        gas_keywords = [
            "FUEL 4",
            "EXXON",
            "QUICK CHEK",
            "QUICKCHEK",
            "VALERO",
            "FUEL HUB",
            "GAS STATION",
            "SERVICE STATION",
            "GULF",
        ]
        # Match 'GAS' as a whole word or in common station phrases to prevent false positives
        is_gas_word = bool(re.search(r"\bGAS\b", desc_upper))
        is_delta_gas = "DELTA" in desc_upper and any(term in desc_upper for term in ["GAS", "SERVICE", "FUEL", "STATION"])
        if cat_upper in ("GASOLINE", "GAS") or any(kw in desc_upper for kw in gas_keywords) or is_gas_word or is_delta_gas:
            tx.treatment = TransactionTreatment.EXEMPT
            tx.category = "Motor Fuel & Gas Stations"
            tx.classification_reason = "Exempt under NY Tax Law § 1115: motor fuel and service station purchases"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # 4E: Utilities, Rent & Education (excluding taxable phone companies)
        education_keywords = [
            "SF MATCH",
            "SFMATCH",
        ]
        utility_keywords = [
            "CON ED",
            "CONEDISON",
            "NATIONAL GRID",
            "NGRID",
            "PSEG",
            "SPECTRUM",
            "OPTIMUM",
            "TUITION",
            "ALBANY MED T&F",
            "COLLEGE",
            "UNIVERSITY",
            "RENT",
            "ELECTRIC",
            "GAS UTILITY",
            "WATER UTILITY",
        ]
        if any(kw in desc_upper for kw in education_keywords):
            tx.treatment = TransactionTreatment.EXEMPT
            tx.category = "Education & Residency"
            tx.classification_reason = "Exempt: medical residency matching program and educational examination fee"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # Ensure phone companies/manufacturers in Bills & Utilities category are not exempted
        phone_keywords = [
            "MINT MOBILE",
            "VERIZON",
            "AT&T",
            "ATT *",
            "T-MOBILE",
            "TMOBILE",
            "APPLE",
            "SAMSUNG",
            "GOOGLE PIXEL",
            "MOTOROLA",
        ]
        is_phone = any(kw in desc_upper for kw in phone_keywords)

        if not is_phone and (cat_upper in ("UTILITIES", "EDUCATION") or (cat_upper == "BILLS & UTILITIES" and not is_phone) or any(kw in desc_upper for kw in utility_keywords)):
            tx.treatment = TransactionTreatment.EXEMPT
            tx.category = "Utilities, Rent & Education"
            tx.classification_reason = "Exempt: residential utilities, tuition, or rental housing"
            tx.pre_tax_amount = 0.0
            tx.sales_tax = 0.0
            return tx

        # -------------------------------------------------------------
        # Tier 5: Taxable Purchases (Dining, Travel, Telecom, Retail)
        # -------------------------------------------------------------
        # 5A: Dining, Restaurants, Cafes & Food Delivery (NY Tax Law § 1105(d))
        dining_keywords = [
            "RESTAURANT",
            "CAFE",
            "CAFES",
            "CAFFE",
            "COFFEE",
            "STARBUCKS",
            "DUNKIN",
            "MCDONALD",
            "BURGER",
            "PIZZA",
            "BAR",
            "PUB",
            "GRILL",
            "DINER",
            "DOORDASH",
            "UBEREATS",
            "GRUBHUB",
            "SEAMLESS",
            "CAVIAR",
            "SMOKEHOUSE",
            "BISTRO",
            "TAVERN",
            "SUSHI",
            "WIZARD BURGER",
            "PEQUENO",
        ]
        if cat_upper in ("FOOD & DRINK", "DINING", "RESTAURANTS") or any(kw in desc_upper for kw in dining_keywords):
            pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
            tx.treatment = TransactionTreatment.TAXABLE
            tx.category = "Dining & Food Service"
            tx.pre_tax_amount = pre_tax
            tx.sales_tax = sales_tax
            tx.classification_reason = f"Taxable under NY Tax Law § 1105(d): restaurant dining and prepared food at {self.tax_rate*100:.3f}%"
            return tx

        # 5B: Travel, Airlines & Lodging
        travel_keywords = [
            "AIRLINE",
            "DELTA AIR",
            "UNITED AIR",
            "AMERICAN AIR",
            "JETBLUE",
            "SOUTHWEST AIR",
            "AIRWAYS",
            "FRONTIER AIR",
            "SPIRIT AIR",
            "ALASKA AIR",
            "HOTEL",
            "MOTEL",
            "MARRIOTT",
            "HILTON",
            "HYATT",
            "SHERATON",
            "WESTIN",
            "AIRBNB",
            "VRBO",
            "RESORT",
        ]
        if cat_upper in ("TRAVEL", "TRAVEL & AIRFARE") or any(kw in desc_upper for kw in travel_keywords):
            pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
            tx.treatment = TransactionTreatment.TAXABLE
            tx.category = "Travel & Lodging"
            tx.pre_tax_amount = pre_tax
            tx.sales_tax = sales_tax
            tx.classification_reason = f"Taxable: airline travel or lodging accommodation at {self.tax_rate*100:.3f}%"
            return tx

        # 5C: Phone Companies & Hardware Manufacturers
        if is_phone or any(kw in desc_upper for kw in phone_keywords):
            pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
            tx.treatment = TransactionTreatment.TAXABLE
            tx.category = "Telecommunications & Hardware"
            tx.pre_tax_amount = pre_tax
            tx.sales_tax = sales_tax
            tx.classification_reason = f"Taxable: telecommunications service or hardware at {self.tax_rate*100:.3f}%"
            return tx

        # 5D: Retail Brands, Online Marketplaces & Square / POS
        retail_keywords = [
            "76",
            "ZOLA",
            "ZOLA.COM",
            "SQ *",
            "SQ*",
            "SQUARE",
            "AMAZON",
            "AMAZON.COM",
            "AMAZON*",
            "TOOLS",
        ]
        if any(kw in desc_upper for kw in retail_keywords):
            pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
            tx.treatment = TransactionTreatment.TAXABLE
            tx.category = "General Retail & Merchandise"
            tx.pre_tax_amount = pre_tax
            tx.sales_tax = sales_tax
            tx.classification_reason = f"Taxable: retail merchandise or marketplace purchase at {self.tax_rate*100:.3f}%"
            return tx

        # 5E: Entertainment & Digital Subscriptions
        entertainment_keywords = [
            "SPOTIFY",
            "NETFLIX",
            "HULU",
            "DISNEY",
            "HBO",
            "APPLE STORE",
            "BEST BUY",
            "B&H PHOTO",
            "MICRO CENTER",
            "CINEMA",
            "THEATRE",
            "BROADWAY",
            "TICKETMASTER",
            "CASINO",
            "CROWN COINS",
            "CROWNSCOINCASINO",
            "GOING.COM",
            "GOOGLE *GOOGLE ONE",
        ]
        if cat_upper in ("ENTERTAINMENT", "ELECTRONICS") or any(kw in desc_upper for kw in entertainment_keywords):
            pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
            tx.treatment = TransactionTreatment.TAXABLE
            tx.category = "Entertainment & Digital Services"
            tx.pre_tax_amount = pre_tax
            tx.sales_tax = sales_tax
            tx.classification_reason = f"Taxable: entertainment, digital subscriptions, or electronics at {self.tax_rate*100:.3f}%"
            return tx

        # -------------------------------------------------------------
        # Tier 6: Ambiguous Retail Merchant Default (Spec Requirement)
        # -------------------------------------------------------------
        pre_tax, sales_tax = self.compute_reverse_tax(tx.amount)
        tx.treatment = TransactionTreatment.TAXABLE
        tx.category = "General Retail & Merchandise"
        tx.pre_tax_amount = pre_tax
        tx.sales_tax = sales_tax
        tx.classification_reason = f"Taxable (Ambiguity Default): retail merchandise reverse-calculated at {self.tax_rate*100:.3f}%"
        return tx

    def process_files(self, file_inputs: List[Union[str, Path, BinaryIO]]) -> SalesTaxReport:
        """Ingest, normalize, and classify transactions across multiple bank statement files."""
        all_txs: List[NormalizedTransaction] = []

        for f_inp in file_inputs:
            txs = self.normalizer.parse_file(f_inp)
            for t in txs:
                classified = self.classify_transaction(t)
                all_txs.append(classified)

        # Sort transactions chronologically
        all_txs.sort(key=lambda x: x.date, reverse=True)

        return SalesTaxReport(
            county=self.county_name,
            tax_rate=self.tax_rate,
            transactions=all_txs,
        )
