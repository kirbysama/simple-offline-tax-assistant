# 03: Credit Card Ingestion & NY Sales Tax Calculator

**What to build:**
A standalone credit card spending analyzer that accepts annual CSV and Excel activity statements from multiple banks (Chase, Amex, Citi, Capital One, Discover, Bank of America, Apple Card, etc.), auto-detects and normalizes varying bank schemas, excludes non-spend items (payments, transfers, interest, fees, credits), handles refunds with negative sales tax offsets, applies deterministic keyword and category classification to separate exempt transactions (unprepared food/groceries, prescriptions/medical, MTA/transit, utilities) from taxable goods, defaults ambiguous merchants to taxable per specification, reverse-calculates New York sales tax at the selected county rate (defaulting to NYC 8.875%), and exports an audit-ready multi-tab `NY_Sales_Tax_Report.xlsx` workbook accompanied by automated tests.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Ingests annual CSV and Excel activity files from multiple banks concurrently.
- [x] Auto-detects issuer file schema dialects (Chase, Amex, Citi, Capital One, Discover, BofA, Apple Card, Generic) and normalizes columns into Date, Description, Amount, Source Bank, and Source Account.
- [x] Automatically identifies and excludes payments (e.g. "Payment Thank You"), balance transfers, interest charges, annual card fees, and financial adjustments from spend.
- [x] Handles merchant returns/refunds by preserving sign and calculating negative sales tax paid to accurately offset deductions.
- [x] Classifies exempt transactions: unprepared groceries/supermarkets (Trader Joe's, Whole Foods, Key Food, etc.), pharmacies/medical (CVS, Walgreens prescriptions, dental), commuter transit (MTA, subways, PATH, commuter rail), and utilities/rent.
- [x] Classifies taxable transactions: restaurants, bars, food delivery, electronics, home goods, entertainment, and general retail.
- [x] Defaults ambiguous merchants (e.g. Amazon, department stores, general retailers) to taxable per specification.
- [x] Excludes out-of-state hotel lodging, airfare, and foreign currency transactions from New York sales tax.
- [x] Computes exact reverse sales tax using $\text{Sales Tax} = \text{Amount} \times \frac{r}{1 + r}$ with configurable county rate defaulting to New York City (8.875%).
- [x] Exports a complete 3-tab Excel workbook (`NY_Sales_Tax_Report.xlsx`): Tab 1 Deduction Summary KPI cards; Tab 2 Itemized Transaction Ledger; Tab 3 Category Breakdown & Audit Trail.
- [x] Comprehensive automated tests verifying bank schema detection, exclusion filtering, exempt/taxable categorization, refund handling, and reverse tax math.

## Answer
Implemented the complete deterministic Credit Card Ingestion and NY Reverse Sales Tax Calculator:
- `ActivityNormalizer`: Dialect auto-detection (Chase Credit/Checking, Amex, Citi, Discover, Capital One, BofA, Apple Card, Generic) with sign and date normalization across CSV and Excel formats.
- `SalesTaxCalculator`: Multi-tier deterministic classification (non-spend exclusions, refunds with negative sales tax, geographic exclusions, exempt spend, taxable dining/entertainment, and ambiguous retail default) with exact cent-parity reverse tax math across all 62 NY counties.
- `SalesTaxExcelExporter`: Audit-ready 3-tab workbook generator with executive KPI cards, itemized ledger with statutory audit notes, and category/card audit trails.
- `sales_tax_pipeline.py`: Batch runner and scriptable CLI.
- 23 automated tests verifying all functionality, achieving 100% test pass rate across 910 sample transactions and synthesized edge cases.

