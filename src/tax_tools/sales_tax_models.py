"""Data models for Credit Card Ingestion and NY Sales Tax Calculation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class TransactionTreatment(str, Enum):
    """Classification treatment of a financial transaction for NY Sales Tax."""
    TAXABLE = "Taxable"
    EXEMPT = "Exempt"
    REFUND = "Refund"
    EXCLUDED_PAYMENT = "Excluded - Payment"
    EXCLUDED_FEE = "Excluded - Fee"
    EXCLUDED_TRANSFER = "Excluded - Transfer"
    EXCLUDED_OUT_OF_STATE = "Excluded - Out of State"


class BankDialect(str, Enum):
    """Recognized bank CSV/Excel schema dialect."""
    CHASE_CREDIT = "Chase Credit Card"
    CHASE_CHECKING = "Chase Checking / Banking"
    AMEX = "American Express"
    CITI = "Citi Double Cash / Credit"
    DISCOVER = "Discover"
    CAPITAL_ONE = "Capital One"
    BOFA = "Bank of America"
    APPLE_CARD = "Apple Card"
    GENERIC = "Generic CSV / Excel"


# All 62 New York Counties and standard combined sales tax rates (State 4% + Local + MCTD where applicable)
NY_COUNTY_RATES: Dict[str, float] = {
    "New York City (8.875%)": 0.08875,
    "Albany (8.000%)": 0.08000,
    "Allegany (8.500%)": 0.08500,
    "Bronx (NYC) (8.875%)": 0.08875,
    "Broome (8.000%)": 0.08000,
    "Cattaraugus (8.500%)": 0.08500,
    "Cayuga (8.000%)": 0.08000,
    "Chautauqua (8.000%)": 0.08000,
    "Chemung (8.000%)": 0.08000,
    "Chenango (8.000%)": 0.08000,
    "Clinton (8.000%)": 0.08000,
    "Columbia (8.000%)": 0.08000,
    "Cortland (8.000%)": 0.08000,
    "Delaware (8.000%)": 0.08000,
    "Dutchess (8.125%)": 0.08125,
    "Erie (8.750%)": 0.08750,
    "Essex (8.000%)": 0.08000,
    "Franklin (8.000%)": 0.08000,
    "Fulton (8.000%)": 0.08000,
    "Genesee (8.000%)": 0.08000,
    "Greene (8.000%)": 0.08000,
    "Hamilton (8.000%)": 0.08000,
    "Herkimer (8.250%)": 0.08250,
    "Jefferson (8.000%)": 0.08000,
    "Kings (Brooklyn - NYC) (8.875%)": 0.08875,
    "Lewis (8.000%)": 0.08000,
    "Livingston (8.000%)": 0.08000,
    "Madison (8.000%)": 0.08000,
    "Monroe (8.000%)": 0.08000,
    "Montgomery (8.000%)": 0.08000,
    "Nassau (8.625%)": 0.08625,
    "New York (Manhattan - NYC) (8.875%)": 0.08875,
    "Niagara (8.000%)": 0.08000,
    "Oneida (8.750%)": 0.08750,
    "Onondaga (8.000%)": 0.08000,
    "Ontario (7.500%)": 0.07500,
    "Orange (8.125%)": 0.08125,
    "Orleans (8.000%)": 0.08000,
    "Oswego (8.000%)": 0.08000,
    "Otsego (8.000%)": 0.08000,
    "Putnam (8.375%)": 0.08375,
    "Queens (NYC) (8.875%)": 0.08875,
    "Rensselaer (8.000%)": 0.08000,
    "Richmond (Staten Island - NYC) (8.875%)": 0.08875,
    "Rockland (8.375%)": 0.08375,
    "Saratoga (7.000%)": 0.07000,
    "Schenectady (8.000%)": 0.08000,
    "Schoharie (8.000%)": 0.08000,
    "Schuyler (8.000%)": 0.08000,
    "Seneca (8.000%)": 0.08000,
    "St. Lawrence (8.000%)": 0.08000,
    "Steuben (8.000%)": 0.08000,
    "Suffolk (8.625%)": 0.08625,
    "Sullivan (8.500%)": 0.08500,
    "Tioga (8.000%)": 0.08000,
    "Tompkins (8.000%)": 0.08000,
    "Ulster (8.000%)": 0.08000,
    "Warren (7.000%)": 0.07000,
    "Washington (7.000%)": 0.07000,
    "Wayne (8.000%)": 0.08000,
    "Westchester (8.375%)": 0.08375,
    "Wyoming (8.000%)": 0.08000,
    "Yates (8.000%)": 0.08000,
}

DEFAULT_COUNTY = "New York City (8.875%)"
DEFAULT_TAX_RATE = 0.08875



def get_tax_rate_for_county(county_name: str) -> float:
    """Resolve tax rate from county name or partial key; defaults to NYC rate."""
    if not county_name:
        return DEFAULT_TAX_RATE
    if county_name in NY_COUNTY_RATES:
        return NY_COUNTY_RATES[county_name]
    
    clean = county_name.strip().lower()
    if "city" in clean or "nyc" in clean or "manhattan" in clean or "brooklyn" in clean or "queens" in clean:
        return DEFAULT_TAX_RATE
        
    for k, v in NY_COUNTY_RATES.items():
        if clean in k.lower():
            return v
            
    return DEFAULT_TAX_RATE


@dataclass
class NormalizedTransaction:
    """Standardized representation of a single credit card or banking transaction."""
    date: str
    description: str
    amount: float  # Normalized: positive = spend/purchase, negative = refund/credit
    raw_amount: float
    source_bank: str
    source_account: str
    treatment: TransactionTreatment = TransactionTreatment.TAXABLE
    category: str = "General Retail"
    pre_tax_amount: float = 0.0
    sales_tax: float = 0.0
    tax_rate: float = 0.0
    classification_reason: str = ""
    is_refund: bool = False
    memo: str = ""

    @property
    def is_excluded(self) -> bool:
        """True if non-spend or out-of-state exclusion."""
        return self.treatment in (
            TransactionTreatment.EXCLUDED_PAYMENT,
            TransactionTreatment.EXCLUDED_FEE,
            TransactionTreatment.EXCLUDED_TRANSFER,
            TransactionTreatment.EXCLUDED_OUT_OF_STATE,
        )

    @property
    def is_taxable(self) -> bool:
        """True if transaction incurs sales tax (or negative tax for refunds)."""
        return self.treatment in (TransactionTreatment.TAXABLE, TransactionTreatment.REFUND)


@dataclass
class CategorySummary:
    """Summary metrics aggregated by spend category."""
    category: str
    treatment: str
    transaction_count: int = 0
    gross_amount: float = 0.0
    taxable_amount: float = 0.0
    sales_tax_paid: float = 0.0
    pct_of_total_tax: float = 0.0


@dataclass
class CardSummary:
    """Summary metrics aggregated by banking card/account."""
    source_bank: str
    source_account: str
    transaction_count: int = 0
    gross_amount: float = 0.0
    taxable_amount: float = 0.0
    sales_tax_paid: float = 0.0


@dataclass
class SalesTaxReport:
    """Consolidated annual New York sales tax report across all statements."""
    county: str = DEFAULT_COUNTY
    tax_rate: float = DEFAULT_TAX_RATE
    transactions: List[NormalizedTransaction] = field(default_factory=list)

    @property
    def total_transactions(self) -> int:
        return len(self.transactions)

    @property
    def spend_transactions(self) -> List[NormalizedTransaction]:
        """Transactions representing actual goods/services (excluding payments/fees/transfers)."""
        return [
            t for t in self.transactions
            if t.treatment not in (
                TransactionTreatment.EXCLUDED_PAYMENT,
                TransactionTreatment.EXCLUDED_FEE,
                TransactionTreatment.EXCLUDED_TRANSFER,
            )
        ]

    @property
    def total_gross_spend(self) -> float:
        """Total gross spending on goods and services (net of refunds)."""
        return round(sum(t.amount for t in self.spend_transactions), 2)

    @property
    def total_spend_analyzed(self) -> float:
        """Alias for total_gross_spend."""
        return self.total_gross_spend


    @property
    def total_excluded(self) -> float:
        """Sum of non-spend exclusions (payments, fees, transfers)."""
        return round(
            sum(
                t.amount for t in self.transactions
                if t.treatment in (
                    TransactionTreatment.EXCLUDED_PAYMENT,
                    TransactionTreatment.EXCLUDED_FEE,
                    TransactionTreatment.EXCLUDED_TRANSFER,
                )
            ),
            2,
        )

    @property
    def total_exempt(self) -> float:
        """Total spend on tax-exempt items (groceries, medicine, transit, utilities)."""
        return round(
            sum(t.amount for t in self.transactions if t.treatment == TransactionTreatment.EXEMPT),
            2,
        )

    @property
    def total_out_of_state(self) -> float:
        """Total spend on out-of-state lodging, flights, and foreign charges."""
        return round(
            sum(t.amount for t in self.transactions if t.treatment == TransactionTreatment.EXCLUDED_OUT_OF_STATE),
            2,
        )

    @property
    def total_taxable(self) -> float:
        """Total gross taxable spend subject to sales tax (net of refunds)."""
        return round(sum(t.amount for t in self.transactions if t.is_taxable), 2)

    @property
    def total_pre_tax(self) -> float:
        """Total calculated pre-tax base amount for taxable transactions."""
        return round(sum(t.pre_tax_amount for t in self.transactions if t.is_taxable), 2)

    @property
    def total_sales_tax_paid(self) -> float:
        """Total reverse-calculated New York sales tax paid."""
        return round(sum(t.sales_tax for t in self.transactions if t.is_taxable), 2)

    @property
    def category_summaries(self) -> List[CategorySummary]:
        """Aggregate breakdown grouped by transaction category."""
        groups: Dict[str, CategorySummary] = {}
        for t in self.transactions:
            cat = t.category or "Other"
            if cat not in groups:
                groups[cat] = CategorySummary(
                    category=cat,
                    treatment=t.treatment.value,
                )
            entry = groups[cat]
            entry.transaction_count += 1
            entry.gross_amount = round(entry.gross_amount + t.amount, 2)
            if t.is_taxable:
                entry.taxable_amount = round(entry.taxable_amount + t.amount, 2)
                entry.sales_tax_paid = round(entry.sales_tax_paid + t.sales_tax, 2)

        total_tax = self.total_sales_tax_paid
        result = list(groups.values())
        for cs in result:
            if total_tax > 0 and cs.sales_tax_paid > 0:
                cs.pct_of_total_tax = round((cs.sales_tax_paid / total_tax) * 100, 1)
        result.sort(key=lambda x: (x.sales_tax_paid, x.gross_amount), reverse=True)
        return result

    @property
    def card_summaries(self) -> List[CardSummary]:
        """Aggregate breakdown grouped by bank and card account."""
        groups: Dict[str, CardSummary] = {}
        for t in self.spend_transactions:
            key = f"{t.source_bank} - {t.source_account}"
            if key not in groups:
                groups[key] = CardSummary(
                    source_bank=t.source_bank,
                    source_account=t.source_account,
                )
            entry = groups[key]
            entry.transaction_count += 1
            entry.gross_amount = round(entry.gross_amount + t.amount, 2)
            if t.is_taxable:
                entry.taxable_amount = round(entry.taxable_amount + t.amount, 2)
                entry.sales_tax_paid = round(entry.sales_tax_paid + t.sales_tax, 2)

        result = list(groups.values())
        result.sort(key=lambda x: x.gross_amount, reverse=True)
        return result
