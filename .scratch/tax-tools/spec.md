Status: ready-for-agent

# Specification: Multi-Brokerage 1099 Aggregator & NY Credit Card Sales Tax Calculator

## Problem Statement

Tax season requires consolidating complex financial data across disparate institutions:
1. **Investment Reporting (1099 Forms)**: Investors with multiple brokerage accounts (Schwab, Fidelity, Robinhood, Webull, Vanguard, Chase, etc.) receive separate consolidated 1099 PDF statements, each dozens to hundreds of pages long. Manually extracting summary figures (Form 8949 Part I Short-Term Boxes A/B/C, Part II Long-Term Boxes D/E/F, wash sales, proceeds, cost basis) and Form 1099-INT interest (specifically distinguishing federal-only taxable interest from New York State tax-exempt U.S. Treasury interest) is slow, tedious, and prone to costly transcription errors.
2. **Itemized Deduction (Sales Tax vs. State Income Tax)**: Taxpayers filing IRS Schedule A who deduct actual state and local general sales taxes paid—or need documentation for New York State use tax / itemized deductions—face credit card activity statements that only record gross settled transaction totals. Credit card statements do not itemize sales tax. Furthermore, spending includes exempt purchases (groceries, medicine, MTA/transit), out-of-state travel, card payments, and refunds. Manually categorizing hundreds of credit card transactions to isolate taxable spend and reverse-calculate New York sales tax paid is nearly impossible without automation.
3. **Summary Table Usability & Copy Efficiency**: In the 1099 Interactive Summary Table Preview:
   - Copy-to-clipboard buttons rendered via `st.html` do not work because modern Streamlit sanitizes and strips `<script>` tags by default unless explicitly permitted (`unsafe_allow_javascript=True`) and clipboard APIs require accessible user interaction contexts.
   - The current copy buttons and clipboard badge layout are oversized, adding visual clutter and consuming valuable table cell real estate across dense 18-column financial grids.
   - Inline cell click-to-copy is needed: clicking any table cell copies its value to the clipboard via delegated document listeners, with momentary green confirmation feedback, without using inline `onclick` handlers (which would double-fire with delegated listeners).
   - Column labels like `ST Net Gain/(Loss)` and `LT Net Gain/(Loss)` are overly long, forcing horizontal scrolling on standard screens.
   - The overall table typography is slightly too large for compact financial overview tables, and secondary institutional metadata (`Clearing Firm`) occupies prominent early column position instead of being placed at the right-most edge of the table.
4. **Interactive Summary Table Column Sorting Regression**:
   - The original Streamlit `st.dataframe` preview supported sorting table rows by clicking column headers. When the preview table was transitioned to custom HTML (`render_summary_table_html`) to support copy buttons, section dividers, and semantic shading, column header click sorting was lost. Users can no longer sort by clicking column headers to quickly rank accounts by Proceeds, Net Gain/Loss, or Interest.
5. **Sample Corpus Contains Real Taxpayer Identifiers**:
   - The `Sample 1099-INT/`, `Sample Form 1099/`, and `Sample Activity Statements/` directories hold real consolidated tax documents rather than synthetic fixtures. They embed the account holder's full legal name, street address, ZIP, masked taxpayer identification number (`***-**-0381`), roughly twenty brokerage, bank, and card account numbers, a second individual's name, personal mobile numbers, and dozens of third-party payment handles. These files are tracked in git.
   - `detect_account_number` also carried the account holder's first name in a hard-coded denylist of first words to reject, alongside an institution location code and assorted English words. The parser therefore only worked on documents belonging to one particular person, and the name was committed to source.
   - Household-level financial figures (property basis, mortgage interest, depreciation schedule, dues, and insurance) lived in `docs/tax/TAX_KNOWLEDGE_BASE_2025.md`, which belongs to a separate personal-finance project rather than a code repository.

## Solution

A local, deterministic tax assistant delivering two dedicated tools accessible via a unified local web UI and command-line interface:
1. **1099 Tax Aggregator**: Ingests multiple consolidated 1099 PDFs simultaneously, deterministically targets and parses the summary tables (bypassing trade-by-trade logs in seconds without runtime AI or external API costs), captures brokerage names and account numbers directly from document text (with filename fallback for unrecognized brokerage brands), validates mathematical integrity, and exports a clean, ready-to-file multi-tab Excel workbook (`1099_Tax_Summary.xlsx`).
2. **NY Sales Tax Calculator**: Ingests annual credit card activity CSV/Excel statements from various banks (Chase, Amex, Citi, Capital One, etc.), normalizes differing schemas, filters out payments and fees, nets refunds with negative tax impact, applies deterministic keyword/category classification to separate exempt purchases (unprepared groceries, healthcare, transit) from taxable goods/dining, treats ambiguous transactions as taxable, reverse-calculates New York sales tax using the user-selected county jurisdiction (defaulting to NYC 8.875%), and exports an audit-ready multi-tab Excel workbook (`NY_Sales_Tax_Report.xlsx`).
3. **Optimized Interactive Summary Table Preview**:
   - Fixes clipboard copying by enabling JavaScript execution (`unsafe_allow_javascript=True` in `st.html`) and supporting a resilient clipboard fallback (`navigator.clipboard.writeText` with legacy `document.execCommand('copy')` fallback) so that clicking reliably copies sanitized numbers into the user's OS clipboard across all browsers and local web environments.
   - Re-architects copy buttons to be ultra-compact, lightweight, and low-profile (e.g. subtle hover/inline mini-icon or compact button with unobtrusive tooltip), preventing layout bloat and preserving tight cell real estate.
   - Streamlines column headers: shortens `ST Net Gain/(Loss)` to `ST Net` and `LT Net Gain/(Loss)` to `LT Net`.
   - Decreases preview table typography size by 1 pt (reducing from ~14px / 0.875rem to ~12.5px–13px / 0.8rem or equivalent `calc()` adjustment) for a crisp, high-density financial ledger presentation.
   - Reorders columns to place `Clearing Firm` at the right-most edge of the table (just before or after `Parity Status`), prioritizing critical tax amounts and account identifiers up front.
4. **Client-Side Interactive Column Header Sorting**:
   - Re-establishes column header click-to-sort functionality in `render_summary_table_html` using client-side JavaScript.
   - Each column header (`<th>`) acts as an interactive sorting trigger with pointer cursors, hover feedback, and visual direction indicators (`⇅` neutral, `▲` ascending, `▼` descending).
   - Handles smart numeric/currency parsing (stripping `$`, commas, and interpreting negatives/parentheses) for accurate mathematical sorting of capital gains, cost basis, proceeds, wash sales, and interest figures.
   - Sorts string columns (`Brokerage Name`, `Account #`, `Clearing Firm`, `Parity Status`) alphabetically.
   - Operates entirely in the browser DOM by reordering table rows, maintaining all one-click copy buttons, section dividers, wash-sale highlights, and zero-group background shading without triggering Streamlit server reruns.

Each tool operates independently, generates its own separate workbook, and keeps all financial documents 100% offline and secure.

---

## User Stories

1. As a taxpayer with multiple brokerage accounts, I want to upload several consolidated 1099 PDFs in a single batch, so that I do not have to process brokerages one by one.
2. As a taxpayer, I want the 1099 parser to run locally and deterministically without runtime LLM calls, so that my sensitive financial data remains completely private and large multi-hundred-page PDFs process within seconds at zero cost.
3. As an investor using the Form 8949 summary reporting method, I want the 1099 tool to extract aggregate Proceeds, Cost Basis, Wash Sale Disallowance (Box 1g / Code W), other adjustments, and Net Gain/Loss for Short-Term Box A, Box B, and Box C, so that I can directly populate Form 8949 Part I.
4. As an investor using the Form 8949 summary reporting method, I want the 1099 tool to extract aggregate Proceeds, Cost Basis, Wash Sale Disallowance (Box 1g / Code W), other adjustments, and Net Gain/Loss for Long-Term Box D, Box E, and Box F, so that I can directly populate Form 8949 Part II.
5. As an investor with U.S. government debt investments, I want the 1099 tool to parse Form 1099-INT and distinctly separate Box 1 (Ordinary Interest) from Box 3 (U.S. Savings Bonds and Treasury Obligations), so that I can properly claim the subtraction modification on New York Form IT-201.
6. As an investor with dividend-bearing securities, I want the 1099 tool to parse Form 1099-DIV to report Box 1a (Total Ordinary Dividends), Box 1b (Qualified Dividends), and Section 199A Dividends, so that I can complete Schedule B and Form 1040 dividend reporting.
7. As a taxpayer, I want the tool to extract the brokerage entity name directly from document text and headers across all major brokerages and clearing firms (BBAE, dSpac, Fennel, Fidelity, Firstrade, Public, Robinhood, Schwab, SoFi, Tradier, Vanguard, WeBull, Wells Fargo/WellsTrade, Chase, Apex Clearing, DriveWealth, National Financial Services), so that each record is accurately labeled without manual data entry.
8. As a taxpayer, I want the tool to fall back to extracting the brokerage name from the PDF filename if and only if the recognizable brokerage brand cannot be detected within the document text, so that unusual or unbranded clearing statements are still correctly identified.
9. As a taxpayer, I want the tool to extract the account number directly from the 1099 document header preserving the institution's masking format (e.g. `***-1234`), so that my summary sheet can be audited against original statements.
10. As a taxpayer, I want the tool to perform mathematical parity assertions (`Proceeds - Cost Basis + Adjustments == Net Gain/Loss`) on every parsed 1099-B category, so that I am alerted immediately if a brokerage statement has scanning artifacts or reconciliation discrepancies.
11. As a taxpayer, I want the 1099 tool to output a dedicated Excel workbook (`1099_Tax_Summary.xlsx`) featuring an IRS Schedule D/8949 aggregate summary tab, a per-brokerage breakdown tab, and an interest/dividends ledger tab, so that I can hand the workbook directly to my CPA or key values into tax preparation software.
12. As a credit card holder with accounts across multiple financial institutions, I want to upload annual CSV and Excel activity exports from Chase, Amex, Citi, Capital One, Bank of America, Discover, and others in a single batch, so that all my annual spending is aggregated in one place.
13. As a credit card holder, I want the tool to automatically detect and map differing bank CSV header schemas into a unified transaction format, so that I do not need to manually edit column names before processing.
14. As a taxpayer, I want the credit card tool to automatically filter out payments, balance transfers, interest charges, card fees, and statement credits from total spend, so that non-purchase transactions do not inflate my calculated spending or tax.
15. As a taxpayer who received merchant returns and refunds, I want negative transaction amounts to reverse-calculate a negative sales tax paid, so that my net sales tax deduction accurately reflects actual net expenditures.
16. As a New York taxpayer, I want the tool to automatically classify purchases at supermarkets, grocery stores, pharmacies, medical/dental offices, transit/MTA, utilities, and rent as sales-tax-exempt, so that untaxed purchases are not erroneously assigned sales tax.
17. As a New York taxpayer, I want transactions at restaurants, bars, prepared food delivery, electronics, entertainment, and general retail to be classified as fully taxable, so that qualifying sales tax is captured.
18. As a taxpayer, I want ambiguous merchants (e.g. Amazon, department stores, general merchandise) to be classified as taxable by default, so that sales tax on everyday retail purchases is not omitted.
19. As a traveler, I want out-of-state hotel lodging, airfare, and foreign transactions to be excluded from New York sales tax calculation, so that out-of-jurisdiction taxes are not erroneously claimed as New York sales tax.
20. As a New York City resident, I want New York City's combined 8.875% sales tax rate to be applied by default, so that I get accurate calculations out of the box without manual rate configuration.
21. As a resident of another New York county, I want a selectable dropdown of all 62 New York counties with their official local tax rates, so that the calculator accurately computes sales tax for any New York jurisdiction.
22. As a taxpayer, I want the sales tax calculation to use the exact reverse tax formula ($\text{Sales Tax} = \text{Amount} \times \frac{r}{1 + r}$), so that the calculated sales tax represents the actual tax embedded in the gross settled amount.
23. As a taxpayer preparing for potential tax audit, I want the sales tax tool to output a dedicated Excel workbook (`NY_Sales_Tax_Report.xlsx`) containing an executive KPI summary tab, an itemized ledger tab with classification reasons and formulas, and a category audit tab, so that I have complete audit-ready backup documentation.
24. As a user, I want a modern, responsive local web dashboard built with Streamlit featuring two separate tabs and separate processing buttons for each tool, so that I can run either tool independently and download separate output files.
25. As a power user, I want command-line interface scripts for both tools, so that I can run batch jobs or automate workflows directly from the terminal.
26. As a taxpayer preparing my tax return, I want the Interactive Summary Table Preview to append the last 4 characters of the account number to the Brokerage Name (e.g. `BBAE -3240`), so that I can immediately distinguish between multiple accounts held at the same brokerage.
27. As a taxpayer copying values from the Interactive Summary Table Preview, I want to click any table cell to instantly copy its value to the clipboard, so that I can paste them straight into tax software.
28. As a taxpayer reading the summary preview table, I want the click-to-copy interaction to be compact and non-intrusive, so that the table remains tight and easy to read.
29. As a taxpayer scanning short-term and long-term capital gains, I want the net gain/loss columns labeled simply as `ST Net` and `LT Net`, so that the column headers are concise and fit neatly without awkward word wrapping.
30. As a taxpayer viewing dense multi-brokerage financial rows, I want the summary table font size reduced by 1 pt, so that more data fits comfortably in the viewport without crowding.
31. As a taxpayer focused on tax numbers, I want the `Clearing Firm` column moved to the far right of the table, so that it does not push essential financial figures off to the right.
32. As a taxpayer reviewing investment summaries across numerous brokerages, I want thickened visual dividers before the Short-Term (ST) and Long-Term (LT) sections, so that I can easily identify where each section begins.
33. As a taxpayer scanning multi-brokerage data, I want semantic column groups (Short-Term, Long-Term, and Interest) to be shaded with a light grey background whenever all values in that specific group are zero for a given row, so that inactive sections fade into the background and I can focus exclusively on figures requiring attention.
34. As an investor reviewing multi-brokerage statements, I want to click any column header in the Interactive Summary Table Preview to sort rows ascending or descending, so that I can quickly identify my largest proceeds, largest gains/losses, or highest interest amounts.
35. As a taxpayer sorting financial figures, I want currency and numeric columns to sort numerically rather than alphabetically, so that negative amounts, zero values, and larger dollar numbers sort mathematically accurately.
36. As a taxpayer, I want visual sort direction indicators (neutral ⇅, ascending ▲, descending ▼) displayed in the table headers, so that I always know which column is actively sorted and in which direction.
37. As a user interacting with the preview table, I want column header sorting to execute purely in the browser without server reruns, so that sorting is instant and does not disrupt copy buttons, section dividers, or row highlights.
38. As a taxpayer whose 1099 statements are processed by this tool, I want account-number detection to decide on the *shape* of a candidate rather than on whether it recognises my name, so that the parser works on any taxpayer's documents instead of only the ones it was developed against.
39. As a maintainer reviewing this repository, I want no real taxpayer name, address, taxpayer identification number, or account number present in the source, the tests, the sample documents, or the filenames, so that the repository carries no identifying information about the person who built it.
40. As a maintainer, I want the sample corpus to keep exercising the parser's real code paths (Form 8949 summaries, Box 1 interest, treasury interest, wash sales, bank dialect detection) after redaction, so that sanitizing the fixtures does not quietly reduce test coverage.

---

## Implementation Decisions

### Module Architecture
The system will be organized into decoupled core modules, shared utilities, and interface layers:
- **1099 Ingestion Engine**: Deterministic document parser utilizing fast text/table extraction to locate and scrape summary sections (Form 8949 Summary, 1099-B, 1099-INT, 1099-DIV). Includes a brokerage signature dictionary and regex matchers for targeted brokerages.
- **1099 Reconciliation & Aggregation Engine**: Validates extracted figures, cross-checks arithmetic consistency, aggregates totals across all processed accounts, and formats data models for reporting.
- **Credit Card Activity Normalizer**: Auto-detects bank file signatures and schema dialects across major issuers, standardizing columns into Date, Description, Amount, Source Bank, and Source Account.
- **NY Sales Tax Classifier & Calculator**: Applies a tiered rules engine for exclusions, geographic filters, exempt matchers, and reverse tax math.
- **Excel Report Generator**: Builds formatted `.xlsx` workbooks (`1099_Tax_Summary.xlsx` and `NY_Sales_Tax_Report.xlsx`).
- **Interactive Summary Table Formatting & Preview Components**:
  - **Working Clipboard Execution**: In Streamlit's web rendering, pass `unsafe_allow_javascript=True` to `st.html(..., unsafe_allow_javascript=True)` so that embedded `<script>` blocks execute. The copy function should incorporate a robust clipboard handler that attempts `navigator.clipboard.writeText(...)` and gracefully falls back to a temporary offscreen `textarea` with `document.execCommand('copy')` if modern permissions or non-secure contexts require it.
  - **Inline Cell Click-to-Copy**: Every data cell is clickable; clicking the cell text copies its value to the clipboard via a single delegated document listener. This avoids the double-fire problem from inline `onclick` handlers (which would fire copy on every re-render). Blank cells are not clickable. Momentary visual feedback (green checkmark) confirms the copy.
  - **Concise Header Renaming**: Rename `ST Net Gain/(Loss)` to `ST Net` and `LT Net Gain/(Loss)` to `LT Net` across table definition, semantic grouping configuration, and rendered headers.
  - **Font Size Reduction**: Reduce table typography by 1 pt (setting table text to `0.8125rem` / ~13px or `10pt` equivalent down from `0.875rem` / ~14px), with proportional reductions for header cells and badges.
  - **Higher Contrast Semantic Shading**: Deepen the contrast between shaded inactive (all-zero) and unshaded active cells by utilizing a more distinct darker muted tone (e.g. `#DEE2E6` / `#E2E6EA` background with `#495057` / `#6c757d` text) against crisp unshaded active cells, making zero groups immediately obvious at a glance.
  - **Column Reordering**: Reorder the columns in `build_1099_summary_df` so that `Clearing Firm` is moved to the far right (placed right after `Parity Status` or as the second-to-last column before `Parity Status`), placing primary tax metrics (`ST Proceeds`, `ST Basis`, `ST Wash Sale`, `ST Net`, `LT Proceeds`, `LT Basis`, `LT Wash Sale`, `LT Net`, `Total Proceeds`, `Total Cost Basis`, `Total Wash Sale`, `Total Net Gain/(Loss)`, `Ordinary Interest`, `US Treasury Interest`) immediately after `Brokerage Name` and `Account #`.
  - **Interactive Column Header Sorting**:
    - Add sort headers with visual sort indicator icons (`⇅` by default, toggling to `▲` for ascending and `▼` for descending).
    - Style table headers with `cursor: pointer; user-select: none;` and subtle hover feedback.
    - Implement client-side sorting logic within the embedded `<script>`:
      - Distinguish between numeric/currency columns and string columns.
      - Parse and normalize currency strings (stripping `$`, commas, whitespace, handling negative signs and parentheses `(100.00)` -> `-100.00`, and treating `-` or blanks as 0) to ensure mathematical numeric sorting rather than lexical string sorting.
      - Reorder existing table rows in the DOM (`tbody.appendChild(...)`) so that all inline copy click handlers, `data-copy` attributes, section dividers, wash-sale highlights, and zero-group shading remain completely intact and active.
      - Sort completely in the browser DOM with zero Streamlit server reruns or latency.

### Architectural Decisions
- **Zero Runtime AI Dependency**: Parsing and calculations execute 100% locally and deterministically.
- **Client-Side Clipboard & Zero Rerun Overhead**: Clipboard copying and table sorting occur purely within the browser DOM without triggering Streamlit server lifecycle reruns.
- **Backward Compatibility & Test Integrity**: Existing programmatic models and exporters remain synchronized while preview presentation models reflect the updated column ordering, concise names, and sorting capabilities.
- **Shape-Based Extraction Over Identity Matching**: Field extractors classify candidates structurally, never by recognising a specific person. `detect_account_number` accepts a candidate only when it carries a digit or an explicit mask character (`*`), which rejects recipient names, cross-reference prose (`Account No. SEE BOX 1`), and institution location codes (`OH4-7214`) without naming any of them. A denylist of known names would silently fail on every other taxpayer's documents and would itself leak an identifier into source.
- **Format-Preserving Placeholders**: Sample-corpus redaction must preserve the *shape* of each value it replaces — digit count, separator layout, and letter/digit mix — because the parser's regexes branch on those shapes (for example `[A-Z]{2}\d-\d{6}` is accepted where `[A-Z]{2}\d-\d{4}` is rejected, and `NNNNNNNN` alphanumerics are matched by the Apex `<BranchAccount>` pattern). A placeholder that changes shape would silently reroute a fixture down a different code path and reduce coverage.
- **Two-Tier PDF Redaction**: The sample corpus contains two mechanically distinct PDF encodings and needs different treatment for each:
  - *Plain-text PDFs* (simple fonts, text stored as literal strings): each string's bytes are its own character codes, so redaction rewrites string bodies in place.
  - *Subset-font PDFs* (`/Type0` with embedded subsets, text stored as 2-byte glyph indices): visible text exists only via the font's `ToUnicode` CMap. Redaction decodes glyphs to characters through that CMap, redacts, then re-encodes using glyph indices the subset already contains. A replacement character with no glyph in the subset cannot be rendered and falls back to a space.
  - Whole-string token matching is required in addition to substring matching, because tight layouts draw the street number, street name, unit designator, and the recipient's first and last name as *separate* text runs. Matching whole decoded strings catches these without touching words that merely contain the same letters (`THIS`, `THE`, `BALANCE`).
- **Sample Filenames Carry No Account Numbers**: Filenames embed account identifiers, so they are renamed to drop them. Where a filename's numeric suffix is load-bearing — bank dialect detection derives an account label from the filename — the slot is retained with a synthetic value rather than removed, so the feature stays covered.

### Sample Corpus

**This repository does not ship sample documents. You must supply your own.**

The parser's end-to-end tests read real consolidated tax documents and real bank
exports from three directories:

| Directory | Expected contents |
| --- | --- |
| `Sample Form 1099/` | Form 1099-B / 1099-DIV consolidated PDFs from your brokerages |
| `Sample 1099-INT/` | Form 1099-INT PDFs from your banks and mortgage servicers |
| `Sample Activity Statements/` | Annual activity CSV or Excel exports from your card issuers and banks |

Drop your own files in and run the suite:

```bash
python -m pytest tests/ -q
```

**Tests that need the corpus skip themselves when it is absent**, so a fresh
checkout still reports green rather than failing. Concretely, the bank-dialect
detection, bank-export ingestion, multi-statement batch processing, pipeline
end-to-end, 1099 statement extraction, 1099-INT extraction, CLI single-file
execution, and in-app upload-flow tests are all skipped until you provide files.
Everything that does not require a real document — tax and exclusion rules,
reverse-tax math, parity assertions, formatting, clipboard and sorting behaviour
in a real browser, and the Excel exporters — runs regardless.

Two things to know when naming your files:

- **Brokerage detection reads the filename as a fallback.** If a brand cannot be
  identified from the document text, the tool parses the filename. Prefix files
  with the brokerage or clearing firm (for example `Vanguard`, `Fidelity`,
  `Schwab`, `Chase`, `BBAE`) so detection succeeds even on unusual statements.
- **Bank dialect detection derives the account label from the filename**, so
  include the issuer and, if you want the label to carry a suffix, the account
  identifier in the name (for example `Chase Sapphire Preferred Card 1234.csv`).

Because the corpus is yours, keep it out of version control. `.gitignore` already
excludes `Sample Form 1099/`, `Sample 1099-INT/`, and `Sample Activity
Statements/`, so `git add -A` cannot sweep your tax documents into a commit.

- **Household financials live outside the repository**: `docs/tax/` is gitignored. The tax knowledge base describes one household's full financial position and belongs to a separate personal-finance project.
- **Machine-local artifacts are never tracked**: Windows `.lnk` shortcuts embed the absolute path of the machine that created them (for example `D:\Documents\...`) and are broken for every other user, so they are gitignored. `Run_Tax_Assistant.bat` is portable instead, resolving its own directory via `%~dp0`.
- **Third-party payment handles are out of scope**: Counterparty Zelle, PayPal, and Cash App handles and the payee's name are left intact. They are other people's identifiers rather than the account holder's, and removing them would gut the fixture's value for transaction-classification work.
- **Redaction of the working tree does not redact git history**: Every sample file has been tracked since the initial commit, so the original identifiers remain reachable in prior revisions. Removing them from history requires a history rewrite or a freshly initialized repository; see Further Notes.

---

## Testing Decisions

### What Makes a Good Test
Tests must verify observable external behavior and contracts rather than internal private implementation details:
- **Table Structure & Column Order Contract**: Assert that `build_1099_summary_df` produces the updated column names `ST Net` and `LT Net` instead of the old verbose titles, and that `Clearing Firm` is positioned at the far right of the dataframe column list.
- **Clipboard Sanitization & HTML Attributes**: Assert that target columns (`Brokerage Name`, `Account #`, `ST Proceeds`, `ST Basis`, `ST Wash Sale`, `LT Proceeds`, `LT Basis`, `LT Wash Sale`) contain compact cell click triggers with valid `data-copy` attributes containing sanitized numerical values (no `$`, negative preserved).
- **CSS & Typography Specifications**: Assert that the rendered table HTML stylesheet contains the reduced font sizing (~1pt lower) and compact cell click trigger dimensions.
- **JavaScript & Script Execution Safety**: Assert that `render_summary_table_html` outputs self-contained client-side script code compatible with `st.html(..., unsafe_allow_javascript=True)`.
- **Column Header Sort Contract**: Assert that header cells (`<th>`) include sortable indicators/classes, pointer styles in CSS, and that the client-side sorting script includes column sorting handlers, currency parsing, and DOM row reordering logic.
- **Name-Independent Extraction Contract**: Assert that `detect_account_number` rejects recipient names drawn from a set of names the parser has never seen (including non-Latin scripts), rejects cross-reference prose, rejects institution location codes, and still finds a genuine account number elsewhere in the same document. A test that only exercises the developer's own name cannot detect the regression it exists to prevent.
- **Redacted-Corpus Coverage Contract**: Assert that every sample PDF still yields a non-empty parse, that account numbers are still recovered from document text (and not merely from filenames), and that Form 8949 parity still holds — confirming redaction preserved the fixture's value.
- **End-to-End Regression Suite**: Verify all existing 1099 parsing, sales tax calculations, and Excel export suites continue to pass without disruption.

---

## Out of Scope

- Modifying the underlying Excel export workbook column headers or sheet schemas (unless specifically requested; the request targets the interactive summary table preview).
- Trade-by-trade Form 8949 line extraction.
- External online clipboard services or cloud sync.

---

## Further Notes

- Streamlit's `st.html` requires `unsafe_allow_javascript=True` to execute `<script>` elements. Adding this flag directly resolves the inert copy buttons.
- The user requested ticket proposals for approval before implementation.
- Personal identifiers in the sample corpus: the real values were the account holder's name and a second individual's name, the street address and city/ZIP, masked TIN `***-**-0381`, roughly twenty brokerage/bank/card account numbers, and personal mobile numbers. These are now replaced by the placeholders `JOHN DOE` / `JANE DOE`, `123 HAPPY STREET`, `SPRINGFIELD NY 10001`, `***-**-0000`, sequential `9AA1xxxx` / `9000xxxx` / `NNN-NNNNNN` account numbers, and `123-456-7890`.
- Payer federal identification numbers on 1099 forms (`94-1737782`, `46-4364776`, `23-2019846`, and similar) are *institution* EINs rather than personal identifiers and were deliberately left intact, as were IRS form legends mentioning "social security number" and merchant or institution hotlines.
- Subset-font redaction could not be assumed to produce readable placeholder text, since a replacement character is only renderable if the subset already embedded its glyph. In practice all seven subset-font documents did embed the needed glyphs for `JOHN DOE` and `123 HAPPY STREET`, so the corpus is uniformly readable rather than partly blanked.
