# 04: Unified Streamlit Web Dashboard & CLI

**What to build:**
A unified local web application built with Streamlit providing independent interactive interfaces for both tools, plus standalone CLI command entrypoints. Tab 1 hosts the 1099 Tax Aggregator (multi-PDF drag-and-drop, "Process 1099s" button, interactive summary preview table, and single-click download of `1099_Tax_Summary.xlsx`). Tab 2 hosts the NY Sales Tax Calculator (multi-CSV/Excel drag-and-drop, county selector dropdown with NYC 8.875% default, "Calculate NY Sales Tax" button, live KPI metric cards, and single-click download of `NY_Sales_Tax_Report.xlsx`). Ensures the two tools operate completely separately with dedicated file output downloads.

**Blocked by:** 02: Multi-Brokerage Coverage & Interest / Dividends Schedule, 03: Credit Card Ingestion & NY Sales Tax Calculator

**Status:** resolved

- [x] Develops Streamlit application with dual-tab interface (`app.py`).
- [x] Tab 1 (1099 Aggregator): Multi-PDF drag-and-drop file uploader, "Process 1099s" trigger, interactive summary table preview (Brokerage Name, Account #, Gains/Losses, Ordinary Interest, US Treasury Interest), and single-click download button for `1099_Tax_Summary.xlsx`.
- [x] Tab 2 (NY Sales Tax): Multi-file CSV/Excel uploader, New York county selector dropdown (covering all 62 NY counties with rates, defaulting to New York City at 8.875%), "Calculate NY Sales Tax" trigger, real-time KPI metric cards (Total Spend, Excluded, Exempt, Taxable, Total NY Sales Tax Paid), and single-click download button for `NY_Sales_Tax_Report.xlsx`.
- [x] Ensures the two tools operate completely independently with separate processing triggers and downloads as requested.
- [x] Provides clean standalone CLI entrypoints (`python tax_1099_parser.py ...` and `python ny_sales_tax_calculator.py ...`) for batch command-line execution.
- [x] End-to-end integration and smoke tests for the web UI and CLI commands.

## Answer

Implemented the unified Streamlit web dashboard and standalone CLI command entrypoints for both tools:

1. **Streamlit Web Application (`app.py`)**:
   - Built dual-tab interactive interface with `st.tabs(["📑 1099 Tax Aggregator", "💳 NY Sales Tax Calculator"])`.
   - **Tab 1 (1099 Aggregator)**:
     - Drag-and-drop multi-PDF uploader (`st.file_uploader`) supporting concurrent ingestion of multi-brokerage consolidated 1099 PDFs.
     - "Process 1099s" primary trigger button plus convenience "Load Sample 1099s" button.
     - Interactive summary preview table (`Brokerage Name`, `Account #`, `Clearing Firm`, `Proceeds`, `Cost Basis`, `Gains/Losses`, `Ordinary Interest`, `US Treasury Interest`, `Parity Status`).
     - Real-time KPI metrics for Statements Parsed, Parity Status, Net Capital Gain/(Loss), Ordinary Interest, and NY IT-201 S-102 tax-exempt U.S. Treasury Interest.
     - Single-click download button for `1099_Tax_Summary.xlsx`.
     - Expandable views for IRS Form 8949 (Boxes A-F, Short/Long totals) and Form 1099-INT / 1099-DIV distribution schedules.
   - **Tab 2 (NY Sales Tax Calculator)**:
     - Multi-file CSV/Excel activity statement uploader (`st.file_uploader`).
     - New York county dropdown selector covering all 62 NY counties with statutory combined sales tax rates, defaulting to `New York City (8.875%)`.
     - "Calculate NY Sales Tax" primary trigger button plus convenience "Load Sample Statements" button.
     - Real-time KPI metric cards: `Total Spend`, `Excluded`, `Exempt`, `Taxable`, and `Total NY Sales Tax Paid`.
     - Single-click download button for `NY_Sales_Tax_Report.xlsx`.
     - Interactive category audit breakdown and searchable itemized transaction ledger preview.
   - **Dual-Tool Independence**: Complete isolation in `st.session_state` (`1099_*` vs `sales_tax_*`), ensuring neither tool wipes or conflicts with the other's processing state or download buffers.

2. **Standalone Command-Line Interfaces**:
   - `tax_1099_parser.py`: Batch command-line runner (`python tax_1099_parser.py [-i DIR|FILES] [-o OUT.xlsx] [-q]`). Supports directory scanning, individual PDF file arguments, terminal summary tables, parity assertions, and Excel export.
   - `ny_sales_tax_calculator.py`: Batch command-line runner (`python ny_sales_tax_calculator.py [-i DIR|FILES] [-c COUNTY] [-o OUT.xlsx] [-q] [--list-counties]`). Supports bank activity normalization, reverse tax calculations across any NY county rate, terminal execution summaries, and Excel export.

3. **Integration and Smoke Testing (`tests/test_cli_and_app.py`)**:
   - Added 14 unit and integration tests covering helper formatting, in-memory Excel generation, CLI argument parsing, single-file CLI executions, error handling, and Streamlit `AppTest` end-to-end simulations.
   - Total test suite expanded to 57 automated tests, all passing with a 100% pass rate.
