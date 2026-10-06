# ADR 0001: Deterministic Summary-Targeted 1099 Parsing and Verification

## Context
Investors receive annual consolidated 1099 PDF statements ranging from 10 to 100+ pages from multiple brokerage firms. Processing every individual trade transaction line-by-line is slow, costly if sent to cloud LLMs, and introduces privacy issues for sensitive financial data. Furthermore, taxpayers reporting capital gains using the IRS Form 8949 summary method only require aggregate totals for Boxes A, B, C, D, E, and F.

## Decision
1. **Local and Deterministic Execution**: Use local Python parsing (`pdfplumber` and `pypdf`) without external API calls or runtime AI.
2. **Summary Table Fast-Targeting**: Identify and target summary sections ("Form 8949 Summary", "Summary of Proceeds", "1099-B Summary") by page headers and table anchor words, bypassing hundreds of individual transaction pages.
3. **Brokerage Discovery with Filename Fallback**: Detect the customer brokerage brand and clearing firm first from document text/headers, and fallback to extracting the brokerage name from the PDF filename if and only if unbranded or absent in document text.
4. **Strict Mathematical Parity Validation**: Validate `Proceeds - Cost Basis + Adjustments == Net Gain/Loss` for each reported category and flag any discrepancy greater than \$0.01.
5. **Decoupled Excel Generation**: Produce a clean, audit-ready multi-tab Excel workbook (`1099_Tax_Summary.xlsx`) featuring an aggregate Form 8949 Summary tab and a per-brokerage Breakdown tab.

## Consequences
- Fast parsing (sub-second per document).
- Sensitive financial data remains 100% offline.
- Immediate detection and reporting of scanning or reconciliation discrepancies.
