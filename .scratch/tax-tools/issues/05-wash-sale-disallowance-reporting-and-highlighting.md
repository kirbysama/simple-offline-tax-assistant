# 05: Wash Sale Disallowance Reporting & Red Highlighting in Web UI and Excel

**What to build:** 
A vertical tracer-bullet feature that tracks Form 1099-B Box 1g Wash Sale Disallowance across all Form 8949 categories (Part I Boxes A-C, Part II Boxes D-F) and brokerage accounts, notes accounts where wash sales occurred and their exact disallowed amounts, and highlights these disallowances in red font and fill across both the generated Excel workbook (`1099_Tax_Summary.xlsx`) and the interactive web UI dashboard.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Ingests and isolates Form 1099-B Box 1g Wash Sale Disallowances across individual Form 8949 categories and per-brokerage statements in `tax_tools.models` and `tax_tools.parser_1099`.
- [x] Tracks wash sales without breaking mathematical parity assertions (`Proceeds - Cost Basis + Adjustments == Net Gain/Loss`).
- [x] Displays a dedicated metric and summary column for Wash Sale Disallowance in the Streamlit web dashboard (`app.py`).
- [x] Formats and highlights cells/rows with disallowed wash sales in red in the web dashboard summary table and expanded schedule view.
- [x] Applies soft red fill (`#FFC7CE`) and bold dark red font (`#9C0006`) to wash sale cells in the "Form 8949 Summary" tab of `1099_Tax_Summary.xlsx` whenever wash sales are present.
- [x] Adds a dedicated "Wash Sale Disallowed (1g)" column in the "Brokerage Breakdown" tab of `1099_Tax_Summary.xlsx`, styled with red highlighting for accounts with non-zero wash sales.
- [x] Leaves categories and accounts with zero wash sales unhighlighted.
- [x] Includes automated tests covering models, Excel red highlighting inspection, parser wash sale extraction, and web UI summary table generation.
