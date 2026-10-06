# 02: Multi-Brokerage Coverage & Interest / Dividends Schedule

**What to build:**
Expands the 1099 aggregator across all 14 targeted brokerages and clearing firms (BBAE, dSpac, Fennel, Fidelity, Firstrade, Public, Robinhood, Schwab, SoFi, Tradier, Vanguard, WeBull, Wells Fargo/WellsTrade, Chase, and clearing houses Apex, DriveWealth, NFS). Parses Form 1099-INT with distinct separation between Box 1 (Ordinary Interest) and Box 3 (U.S. Savings Bonds and Treasury Obligations for NY Form IT-201 state subtraction), plus Box 8 (Tax-Exempt Interest). Parses Form 1099-DIV (Box 1a Ordinary Dividends, Box 1b Qualified Dividends, and Section 199A Dividends). Aggregates multi-brokerage figures into a complete 3-tab `1099_Tax_Summary.xlsx` workbook backed by extensive tests.

**Blocked by:** 01: 1099 Sample Ingestion & Form 8949 Summary Tracer Bullet

**Status:** resolved

- [x] Implements robust header/table extraction signatures for all 14 brokerages: BBAE, dSpac, Fennel, Fidelity, Firstrade, Public, Robinhood, Schwab, SoFi, Tradier, Vanguard, WeBull, Wells Fargo/WellsTrade, Chase.
- [x] Handles clearing house statements (Apex Clearing, DriveWealth, National Financial Services) pairing introducing broker brand with custodian.
- [x] Extracts Form 1099-INT values, isolating Box 1 (Ordinary Interest) from Box 3 (U.S. Treasury and Savings Bonds obligations) and Box 8 (Tax-Exempt Interest).
- [x] Extracts Form 1099-DIV values, isolating Box 1a (Total Ordinary Dividends), Box 1b (Qualified Dividends), and Section 199A Dividends.
- [x] Generates the complete 3-tab Excel workbook (`1099_Tax_Summary.xlsx`): Tab 1 Form 8949/Schedule D Summary; Tab 2 Brokerage Breakdown; Tab 3 Interest & Dividend Schedule.
- [x] Comprehensive unit and integration test suite asserting extraction accuracy across all covered brokerage layouts.

## Answer

Expanded the 1099 parser and Excel reporter to fully cover all 14 targeted brokerages and clearing firms, parsing Form 1099-INT and Form 1099-DIV schedules, isolating NY State tax-exempt U.S. Treasury obligations, and generating the complete 3-tab `1099_Tax_Summary.xlsx` workbook:

1. **Data Models (`src/tax_tools/models.py`)**:
   - Added `Form1099INT` (isolating `box_1_interest`, `box_3_us_treasury` for NY IT-201 line 28 / S-102 subtraction, and `box_8_tax_exempt`). Includes additive aggregation.
   - Added `Form1099DIV` (isolating `box_1a_ordinary_dividends`, `box_1b_qualified_dividends`, and `box_5_section_199a`). Includes additive aggregation.
   - Integrated both models into `BrokerageAccountStatement` and `AggregationReport` (`aggregate_int`, `aggregate_div`).

2. **Parser Signatures (`src/tax_tools/parser_1099.py`)**:
   - Implemented `parse_general_int_and_div` and `parse_robinhood_int_and_div` covering all 14 brokerage and custodian layouts (Apex Clearing firms BBAE, DSpac, Fennel, Firstrade, Public, Tradier, WeBull, plus Vanguard, WellsTrade, Fidelity, Charles Schwab, Chase, and SoFi).
   - Added clearing firm signatures for Wells Fargo Clearing Services, Webull Financial, and SoFi Bank alongside Apex Clearing, DriveWealth, NFS, Robinhood Securities, JP Morgan, Charles Schwab, and Vanguard Marketing.
   - Extracted per-account 1099-INT and 1099-DIV figures for multi-account statements (such as Robinhood's 10 sub-accounts in a single consolidated PDF).

3. **3-Tab Excel Workbook (`src/tax_tools/excel_exporter.py`)**:
   - Implemented Tab 3: "Interest & Dividend Schedule" displaying per-account breakdown of 1099-INT (Box 1, Box 3, Box 8, Total) and 1099-DIV (Box 1a, Box 1b, Box 5) alongside brokerage brand, clearing firm, account number, and source file.
   - Added aggregate totals row with double-underline accounting border and highlight fill.
   - Added legal and tax guidance callout notes detailing New York State Form IT-201 line 28 (S-102 subtraction modification) for Box 3 Treasury interest and Federal Schedule B/Form 1040 line mappings.

4. **Testing Suite (`tests/test_1099_parser.py`, `tests/test_excel_exporter.py`)**:
   - Added 10 new unit and end-to-end tests validating INT/DIV model arithmetic, specific statement extractions (SoFi, WellsTrade, Fidelity, Vanguard, Schwab, Chase, Robinhood multi-account), clearing firm pairings, and NY Treasury subtraction isolation.
   - All 43 tests pass (100% pass rate).
