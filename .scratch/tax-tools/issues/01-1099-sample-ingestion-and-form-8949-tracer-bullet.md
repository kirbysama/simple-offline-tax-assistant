# 01: 1099 Sample Ingestion & Form 8949 Summary Tracer Bullet

**What to build:** 
A vertical tracer-bullet pipeline that prompts the user for representative 1099 PDF samples from their brokerages, ingests native consolidated 1099 PDF statements, extracts the brokerage entity name directly from document text/headers (falling back to the PDF filename if unrecognized), extracts the masked account number, targets and parses the Form 8949 summary tables (Boxes A, B, C, D, E, F: Proceeds, Cost Basis, Wash Sales / Adjustments, Net Gain/Loss) without scanning trade-by-trade lines, validates arithmetic integrity (`Proceeds - Cost Basis + Adjustments == Net Gain/Loss`), and outputs a working, formatted `1099_Tax_Summary.xlsx` workbook accompanied by automated end-to-end tests against sample documents.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Prompts user to supply sample 1099 PDFs in a designated samples directory (e.g. `samples/1099/`) to calibrate layout patterns.
- [x] Ingests native 1099 PDFs deterministically via local PDF parsing without runtime AI or external API calls.
- [x] Extracts the recognizable brokerage brand from document text/headers (with clearing firm noted if applicable).
- [x] Falls back to extracting the brokerage name from the PDF filename if and only if the brokerage brand is not identified within the document text.
- [x] Extracts the account number directly from the document header, preserving original masking.
- [x] Fast-targets the Form 8949 summary sections and extracts aggregate totals for Part I Short-Term (Boxes A, B, C) and Part II Long-Term (Boxes D, E, F).
- [x] Asserts mathematical parity (`Proceeds - Cost Basis + Adjustments == Net Gain/Loss`) on all extracted categories.
- [x] Exports an initial Excel workbook (`1099_Tax_Summary.xlsx`) with Form 8949 Summary and Brokerage Breakdown tabs.
- [x] Includes automated end-to-end tests verifying extraction accuracy against sample 1099 PDFs.

## Answer

Implemented vertical tracer-bullet pipeline for 1099 PDF ingestion, summary extraction across Box A-F categories, arithmetic parity verification, and openpyxl-based multi-tab Excel export (`1099_Tax_Summary.xlsx`):
1. **Sample Ingestion**: Located and parsed all 14 sample 1099 PDFs in `Sample Form 1099` (covering 23 account statements across BBAE, DSpac, Fennel, Fidelity, Firstrade, Public, Robinhood, Schwab, SoFi, Tradier, Vanguard, WeBull, WellsTrade, and Chase).
2. **Brokerage & Clearing Detection**: Document text headers take priority, with fallback to filename brand if unbranded (e.g. generic IRS instructions in SoFi, Redbridge/Apex in BBAE/DSpac). Clearing firms (Apex Clearing, DriveWealth, NFS, Robinhood Securities, Vanguard Marketing, J.P. Morgan) are captured.
3. **Account Masking**: Preserves account number format directly from document headers.
4. **Form 8949 Fast-Targeting**: Targets summary tables for Part I (Boxes A, B, C) and Part II (Boxes D, E, F) bypassing trade-by-trade lines.
5. **Parity Assertions**: `Proceeds - Cost Basis + Adjustments == Net Gain/Loss` validated across all 23 account statements with 100% validity.
6. **Excel Output**: Generated `1099_Tax_Summary.xlsx` with Form 8949 Summary and Brokerage Breakdown tabs.
7. **Test Coverage**: 10 automated unit and end-to-end tests in `tests/test_1099_parser.py` and `tests/test_excel_exporter.py` passing cleanly (100% pass rate).

