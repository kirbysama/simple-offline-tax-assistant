"""Tests for Credit Card Activity Normalizer, NY Sales Tax Classifier & Calculator."""

import os
from pathlib import Path
import pytest
import openpyxl

from tax_tools.sales_tax_models import (
    TransactionTreatment,
    BankDialect,
    NY_COUNTY_RATES,
    get_tax_rate_for_county,
    NormalizedTransaction,
    SalesTaxReport,
)
from tax_tools.activity_normalizer import ActivityNormalizer
from tax_tools.sales_tax_calculator import SalesTaxCalculator
from tax_tools.sales_tax_exporter import SalesTaxExcelExporter


SAMPLE_DIR = Path("Sample Activity Statements")

# The activity-statement corpus is not distributed with this repository, because
# real bank exports carry account identifiers, counterparty payment handles and
# merchant detail that stay identifying even after the account holder's name and
# address are redacted. Supply your own exports to exercise these tests; see the
# "Sample Corpus" section of .scratch/tax-tools/spec.md.
HAVE_SAMPLE_ACTIVITY = SAMPLE_DIR.is_dir()
needs_sample_activity = pytest.mark.skipif(
    not HAVE_SAMPLE_ACTIVITY,
    reason="Sample Activity Statements/ not present; supply your own bank exports",
)


@needs_sample_activity
class TestBankSchemaDetectionAndNormalization:
    """Test auto-detection and normalization across bank dialects."""

    def test_detect_chase_credit_card(self):
        normalizer = ActivityNormalizer()
        path = SAMPLE_DIR / "Chase Freedom Card 9012_Activity 2025.CSV"
        dialect, bank, account = normalizer.detect_dialect(path)
        assert dialect == BankDialect.CHASE_CREDIT
        assert bank == "Chase"
        assert "9012" in account

    def test_detect_chase_checking(self):
        normalizer = ActivityNormalizer()
        path = SAMPLE_DIR / "Chase Personal Checking 9099_Activity 2025.CSV"
        dialect, bank, account = normalizer.detect_dialect(path)
        assert dialect == BankDialect.CHASE_CHECKING
        assert bank == "Chase"
        assert "9099" in account

    def test_detect_amex(self):
        normalizer = ActivityNormalizer()
        path = SAMPLE_DIR / "Amex Blue Cash Everyday Activity 2025.csv"
        dialect, bank, account = normalizer.detect_dialect(path)
        assert dialect == BankDialect.AMEX
        assert "American Express" in bank or "Amex" in bank
        assert "Blue Cash" in account

    def test_detect_citi(self):
        normalizer = ActivityNormalizer()
        path = SAMPLE_DIR / "Citi Double Cash Activity 2025.CSV"
        dialect, bank, account = normalizer.detect_dialect(path)
        assert dialect == BankDialect.CITI
        assert "Citi" in bank
        assert "Double Cash" in account

    def test_detect_discover(self):
        normalizer = ActivityNormalizer()
        path = SAMPLE_DIR / "Discover-Transactions-2025.csv"
        dialect, bank, account = normalizer.detect_dialect(path)
        assert dialect == BankDialect.DISCOVER
        assert "Discover" in bank

    def test_ingest_chase_credit_card_records(self):
        normalizer = ActivityNormalizer()
        path = SAMPLE_DIR / "Chase Freedom Card 9012_Activity 2025.CSV"
        txs = normalizer.parse_file(path)
        assert len(txs) > 0
        # In Chase, sales were negative in raw CSV, should be normalized to positive amounts
        walmart = next(t for t in txs if "WALMART" in t.description)
        assert walmart.amount > 0
        assert round(walmart.amount, 2) == 98.89

    def test_ingest_amex_records(self):
        normalizer = ActivityNormalizer()
        path = SAMPLE_DIR / "Amex Blue Cash Everyday Activity 2025.csv"
        txs = normalizer.parse_file(path)
        assert len(txs) > 0
        # Check grocery spend
        supermarket = next(t for t in txs if "GOOD SUPERMARKET" in t.description)
        assert supermarket.amount == 11.49


class TestExclusionFiltering:
    """Test automatic exclusion of non-spend items (payments, transfers, fees)."""

    def test_exclude_card_payments(self):
        calculator = SalesTaxCalculator()
        # Chase autopay
        t1 = NormalizedTransaction(
            date="2025-12-22",
            description="AUTOMATIC PAYMENT - THANK",
            amount=19.99,
            raw_amount=19.99,
            source_bank="Chase",
            source_account="1122",
            memo="",
        )
        classified = calculator.classify_transaction(t1)
        assert classified.treatment == TransactionTreatment.EXCLUDED_PAYMENT

        # Amex autopay
        t2 = NormalizedTransaction(
            date="2025-12-22",
            description="AUTOPAY PAYMENT - THANK YOU",
            amount=14.10,
            raw_amount=-14.10,
            source_bank="Amex",
            source_account="Everyday",
        )
        classified2 = calculator.classify_transaction(t2)
        assert classified2.treatment == TransactionTreatment.EXCLUDED_PAYMENT

    def test_exclude_annual_membership_fee(self):
        calculator = SalesTaxCalculator()
        t = NormalizedTransaction(
            date="2025-05-01",
            description="ANNUAL MEMBERSHIP FEE",
            amount=95.00,
            raw_amount=-95.00,
            source_bank="Chase",
            source_account="5464",
            category="Fees & Adjustments",
        )
        classified = calculator.classify_transaction(t)
        assert classified.treatment == TransactionTreatment.EXCLUDED_FEE


class TestRefundHandling:
    """Test merchant refund sign preservation and negative sales tax reverse calculation."""

    def test_chase_return_negative_sales_tax(self):
        calculator = SalesTaxCalculator(county_rate=0.08875)
        # Brandsmart return
        t = NormalizedTransaction(
            date="2025-05-05",
            description="BRANDSMART USA",
            amount=-183.74,  # normalized negative spend for return
            raw_amount=183.74,
            source_bank="Chase",
            source_account="5464",
            category="Shopping",
            is_refund=True,
        )
        classified = calculator.classify_transaction(t)
        assert classified.treatment == TransactionTreatment.REFUND
        assert classified.amount < 0
        assert classified.sales_tax < 0
        assert classified.pre_tax_amount < 0
        assert round(classified.pre_tax_amount + classified.sales_tax, 2) == classified.amount

    def test_amex_refund_handling(self):
        calculator = SalesTaxCalculator(county_rate=0.08875)
        t = NormalizedTransaction(
            date="2025-09-08",
            description="TELEFLORACOM        LOS ANGELES",
            amount=-15.00,
            raw_amount=-15.00,
            source_bank="Amex",
            source_account="Everyday",
            is_refund=True,
        )
        classified = calculator.classify_transaction(t)
        assert classified.treatment == TransactionTreatment.REFUND
        assert classified.sales_tax < 0
        assert round(classified.pre_tax_amount + classified.sales_tax, 2) == classified.amount


class TestExemptAndTaxableClassification:
    """Test classification rules for exempt items vs taxable goods and dining."""

    def test_exempt_groceries(self):
        calculator = SalesTaxCalculator()
        merchants = [
            "TRADER JOE'S #543",
            "WHOLE FOODS MARKET",
            "GOOD SUPERMARKET INC SPRINGFIELD",
            "STOP & SHOP #509 MASPETH",
            "ALDI 73011 NANUET",
            "GOLDEN HARVEST FARMS Valatie",
            "KEY FOOD SUPERMARKET",
        ]
        for m in merchants:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=m,
                amount=50.00,
                raw_amount=50.00,
                source_bank="Chase",
                source_account="1122",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXEMPT, f"Failed for {m}"
            assert res.sales_tax == 0.0

    def test_exempt_transit_and_tolls(self):
        calculator = SalesTaxCalculator()
        transit_items = [
            "E-Z*PASSNY REBILL STATEN ISLAND NY",
            "MTA*METROCARD",
            "MTA OMNY PAY",
            "PATH COMMUTER RAIL",
        ]
        for item in transit_items:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=item,
                amount=20.00,
                raw_amount=20.00,
                source_bank="Citi",
                source_account="Double Cash",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXEMPT, f"Failed for {item}"
            assert res.sales_tax == 0.0

    def test_exempt_medical_and_prescriptions(self):
        calculator = SalesTaxCalculator()
        medical_items = [
            "CVS PHARMACY #1024",
            "WALGREENS #3421",
            "DUANE READE 1422",
            "DENTAL ASSOCIATES OF NY",
        ]
        for item in medical_items:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=item,
                amount=35.00,
                raw_amount=35.00,
                source_bank="Chase",
                source_account="1122",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXEMPT, f"Failed for {item}"
            assert res.sales_tax == 0.0

    def test_exempt_utilities_and_education(self):
        calculator = SalesTaxCalculator()
        utility_items = [
            ("CON EDISON OF NY", "Bills & Utilities"),
            ("NATIONAL GRID NY", "Bills & Utilities"),
            ("PSEG LONG ISLAND", "Bills & Utilities"),
            ("OPC*ALBANY MED T&F", "Education"),
        ]
        for desc, cat in utility_items:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=desc,
                amount=100.00,
                raw_amount=100.00,
                source_bank="Chase",
                source_account="1122",
                category=cat,
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXEMPT, f"Failed for {desc}"
            assert res.sales_tax == 0.0

    def test_fintech_and_p2p_transfers_excluded(self):
        calculator = SalesTaxCalculator()
        fintech_descriptions = [
            "PAYPAL *WAYOFTHEWEA",
            "PAYPAL *NEWMAN307",
            "PAYPAL INST XFER TRENTKENNEDY01",
            "ROBINHOOD DEBITS 90000200",
            "Online RealTime payment to Robinhood Securities",
            "Robinhood Funds",
            "WU DIGITAL 800-325-6000",
            "WUVISAAFT 800-325-6000 CO",
            "CASHAPP*TRANSFER",
            "CASH APP*MO BHARMAL Oakland CA",
            "Cash App* payment transfer",
            "SoFi Banking Deposit",
            "SoFi Money XFER",
            "Payroll Deposit",
            "DEPOSIT(S) MOBILE",
            "XFER TO CHECKING",
            "ATM WITHDRAWAL CHASE",
            "Withdrawal at Teller",
            "Fennel Financial Fennel Fin ST-U1Y6X7K6N8E8",
            "FENNEL FIN TRANSFER",
        ]
        for desc in fintech_descriptions:
            t = NormalizedTransaction(
                date="2025-05-01",
                description=desc,
                amount=75.00,
                raw_amount=75.00,
                source_bank="Chase",
                source_account="1999",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXCLUDED_TRANSFER, f"Failed for {desc}"
            assert res.pre_tax_amount == 0.0
            assert res.sales_tax == 0.0

    def test_motor_fuel_and_gas_stations_exempt(self):
        calculator = SalesTaxCalculator()
        gas_descriptions = [
            "FUEL 4 #1024",
            "EXXONMOBIL 48102341",
            "EXXON GAS STATION",
            "QUICK CHEK #124",
            "QUICKCHEK CONVENIENCE",
            "VALERO CORNER STORE",
            "FUEL HUB WEST COXSACKINY",
            "DELTA GAS",
            "DELTA SERVICE STATION",
            "SUNOCO GAS STATION",
            "BP SERVICE STATION",
            "GULF OIL STATION 101",
            "GULF SERVICE",
            "Local Gas Station",
        ]
        for desc in gas_descriptions:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=desc,
                amount=45.00,
                raw_amount=45.00,
                source_bank="Discover",
                source_account="Discover",
                category="Gasoline",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXEMPT, f"Failed for {desc}"
            assert res.pre_tax_amount == 0.0
            assert res.sales_tax == 0.0

    def test_municipal_parking_parknyc_exempt(self):
        calculator = SalesTaxCalculator()
        parking_descriptions = [
            "PARKNYC",
            "PARKNYC APP PAYMENT",
            "PARK NYC METER",
        ]
        for desc in parking_descriptions:
            t = NormalizedTransaction(
                date="2025-07-01",
                description=desc,
                amount=15.00,
                raw_amount=15.00,
                source_bank="Citi",
                source_account="Double Cash",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXEMPT, f"Failed for {desc}"
            assert res.pre_tax_amount == 0.0
            assert res.sales_tax == 0.0

    def test_sf_match_residency_fee_exempt_education(self):
        calculator = SalesTaxCalculator()
        residency_items = [
            "SF MATCH RESIDENCY FEE",
            "SFMATCH APPLICATION",
            "SF MATCH",
        ]
        for desc in residency_items:
            t = NormalizedTransaction(
                date="2025-08-01",
                description=desc,
                amount=350.00,
                raw_amount=350.00,
                source_bank="Chase",
                source_account="5464",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXEMPT, f"Failed for {desc}"
            assert res.category == "Education & Residency" or "Education" in res.category
            assert res.pre_tax_amount == 0.0
            assert res.sales_tax == 0.0

    def test_taxable_dining_and_entertainment(self):
        calculator = SalesTaxCalculator(county_rate=0.08875)
        taxable_items = [
            ("SQ *WIZARD BURGER", "Food & Drink"),
            ("SQ *HARVEST SMOKEHOUSE Valatie NY", "Food & Drink"),
            ("STARBUCKS STORE #1234", "Food & Drink"),
            ("DOORDASH*CHIPOTLE", "Food & Drink"),
            ("Spotify P3D07FBD43", "Entertainment"),
            ("CROWN COINS CASINO", "Entertainment"),
        ]
        for desc, cat in taxable_items:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=desc,
                amount=50.00,
                raw_amount=50.00,
                source_bank="Chase",
                source_account="1122",
                category=cat,
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.TAXABLE, f"Failed for {desc}"
            assert res.sales_tax > 0.0

    def test_ambiguous_merchants_default_to_taxable(self):
        calculator = SalesTaxCalculator(county_rate=0.08875)
        ambiguous = [
            "AMZN Mktp US*2K48J",
            "TARGET 00021312",
            "BEST BUY #1028",
            "HOME DEPOT #1204",
            "MACY'S HERALD SQUARE",
        ]
        for m in ambiguous:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=m,
                amount=100.00,
                raw_amount=100.00,
                source_bank="Chase",
                source_account="1122",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.TAXABLE, f"Failed for {m}"
            assert res.sales_tax > 0.0

    def test_new_miscategorizations_taxable(self):
        calculator = SalesTaxCalculator(county_rate=0.08875)
        taxable_items = [
            ("76 Gas & Mart", "Shopping"),
            ("McDonalds #4321", "Food & Drink"),
            ("Zola Registry", "Shopping"),
            ("Zola.com Wedding", "Shopping"),
            ("SQ aka Square payment", "Shopping"),
            ("SQ *COFFEE SHOP", "Food & Drink"),
            ("Amazon Marketplace", "Shopping"),
            ("amazon.com order", "Shopping"),
            ("Amazon* Prime", "Shopping"),
            ("French Bistro", "Food & Drink"),
            ("Corner Cafes NYC", "Food & Drink"),
            ("Local Cafe Brooklyn", "Food & Drink"),
            ("Italian Caffe", "Food & Drink"),
            ("Mint Mobile Plan", "Bills & Utilities"),
            ("Verizon Wireless", "Bills & Utilities"),
            ("AT&T Mobility", "Bills & Utilities"),
            ("ATT * Wireless", "Bills & Utilities"),
            ("Harbor Freight Tools", "Shopping"),
            ("Jetblue Airways", "Travel"),
            ("United Airlines", "Travel"),
            ("Hyatt Regency", "Travel"),
            ("Hilton Garden Inn", "Travel"),
            ("Apple Store", "Electronics"),
            ("Samsung Electronics", "Shopping"),
        ]
        for desc, cat in taxable_items:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=desc,
                amount=100.00,
                raw_amount=100.00,
                source_bank="Chase",
                source_account="1122",
                category=cat,
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.TAXABLE, f"Failed for {desc}"
            assert res.sales_tax > 0.0

    def test_out_of_state_and_foreign_excluded(self):
        calculator = SalesTaxCalculator()
        oos_items = [
            "SP SUPERBOBA 7788635366 CAN",
            "RESTAURANT IN PARIS FRA",
            "HOTEL IN MEXICO MEX",
            "STORE IN BERLIN DEU",
            "INTERNATIONAL TRANSACTION LUX",
        ]
        for item in oos_items:
            t = NormalizedTransaction(
                date="2025-06-01",
                description=item,
                amount=250.00,
                raw_amount=250.00,
                source_bank="Discover",
                source_account="Discover",
            )
            res = calculator.classify_transaction(t)
            assert res.treatment == TransactionTreatment.EXCLUDED_OUT_OF_STATE, f"Failed for {item}"
            assert res.sales_tax == 0.0


class TestReverseSalesTaxMath:
    """Test exact reverse sales tax math: Tax = Amount * r / (1 + r)."""

    def test_exact_nyc_reverse_tax(self):
        calculator = SalesTaxCalculator(county_rate=0.08875)
        # Suppose a purchase with pre-tax $100.00 has 8.875% tax -> $8.88, total = $108.88
        pre_tax, tax = calculator.compute_reverse_tax(108.88)
        assert pre_tax == 100.00
        assert tax == 8.88
        assert round(pre_tax + tax, 2) == 108.88

    def test_county_rates_coverage(self):
        assert len(NY_COUNTY_RATES) >= 62
        nyc_rate = get_tax_rate_for_county("New York City")
        assert nyc_rate == 0.08875
        albany_rate = get_tax_rate_for_county("Albany")
        assert albany_rate == 0.08000
        erie_rate = get_tax_rate_for_county("Erie")
        assert erie_rate == 0.08750
        nassau_rate = get_tax_rate_for_county("Nassau")
        assert nassau_rate == 0.08625


class TestBatchProcessingAndExcelExport:
    """Test end-to-end multi-statement processing and 3-tab Excel generation."""

    @needs_sample_activity
    def test_process_all_sample_activity_statements(self, tmp_path):
        calculator = SalesTaxCalculator(county_name="New York City (8.875%)")
        sample_files = list(SAMPLE_DIR.glob("*.csv")) + list(SAMPLE_DIR.glob("*.CSV"))
        assert len(sample_files) >= 5

        report = calculator.process_files(sample_files)
        assert report.total_transactions > 0
        assert report.total_spend_analyzed > 0
        assert report.total_taxable > 0
        assert report.total_sales_tax_paid > 0
        assert report.total_exempt > 0
        assert report.total_excluded > 0

        # Export Excel
        exporter = SalesTaxExcelExporter()
        out_path = tmp_path / "NY_Sales_Tax_Report.xlsx"
        exporter.export(report, str(out_path))

        assert out_path.exists()
        wb = openpyxl.load_workbook(str(out_path))
        sheet_names = wb.sheetnames
        assert "Deduction Summary" in sheet_names
        assert "Itemized Ledger" in sheet_names
        assert "Category Audit Trail" in sheet_names

        # Verify KPI values in Deduction Summary sheet
        ws_sum = wb["Deduction Summary"]
        assert ws_sum["A1"].value == "NEW YORK SALES TAX ITEMIZATION SUMMARY"
        assert ws_sum["B5"].value == 0.08875

        # Verify Itemized Ledger has 911 rows (1 header + 910 data)
        ws_ledger = wb["Itemized Ledger"]
        assert ws_ledger.max_row == report.total_transactions + 1

        # Verify Category Audit Trail
        ws_cat = wb["Category Audit Trail"]
        assert ws_cat["A1"].value == "CATEGORY & INSTITUTION AUDIT TRAIL"

    def test_excel_activity_input_ingestion(self, tmp_path):
        """Test ingesting activity from a .xlsx file."""
        from tax_tools.activity_normalizer import ActivityNormalizer

        # Create a sample .xlsx activity file
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Transactions"
        ws.append(["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"])
        ws.append(["12/15/2025", "12/15/2025", "WHOLE FOODS MARKET", "Groceries", "Sale", "-75.50", ""])
        ws.append(["12/10/2025", "12/10/2025", "STARBUCKS", "Food & Drink", "Sale", "-6.50", ""])
        ws.append(["12/01/2025", "12/01/2025", "AUTOMATIC PAYMENT - THANK", "", "Payment", "82.00", ""])

        xlsx_path = tmp_path / "Chase_Freedom_Activity.xlsx"
        wb.save(str(xlsx_path))

        normalizer = ActivityNormalizer()
        txs = normalizer.parse_file(xlsx_path)
        assert len(txs) == 3

        calc = SalesTaxCalculator()
        classified = [calc.classify_transaction(t) for t in txs]
        assert classified[0].treatment == TransactionTreatment.EXEMPT
        assert classified[1].treatment == TransactionTreatment.TAXABLE
        assert classified[2].treatment == TransactionTreatment.EXCLUDED_PAYMENT

    @needs_sample_activity
    def test_run_sales_tax_pipeline_end_to_end(self, tmp_path):
        from tax_tools.sales_tax_pipeline import run_sales_tax_pipeline
        out_excel = tmp_path / "Pipeline_Report.xlsx"
        report = run_sales_tax_pipeline(
            input_dir=str(SAMPLE_DIR),
            county_name="Albany (8.000%)",
            output_excel=str(out_excel),
        )
        assert report.county == "Albany (8.000%)"
        assert report.tax_rate == 0.08
        assert out_excel.exists()

