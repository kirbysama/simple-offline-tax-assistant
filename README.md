# Simple Offline Tax Assistant

Two local tools for turning a year of financial statements into numbers you can
hand to a preparer:

1. **1099 Aggregator** — reads consolidated Form 1099 PDFs and extracts the
   Form 8949 summary figures, interest, and dividends into one Excel workbook.
2. **NY Sales Tax Calculator** — reads credit card and bank activity exports and
   reverse-calculates the New York sales tax you actually paid, for an
   itemized-deduction claim.

Everything runs locally. No API keys, no network calls, no LLM in the parse path.

> **This tool extracts a subset of what is on your 1099s.** See
> [What it extracts](#what-it-extracts-from-your-1099s) for the exact list, and
> [Adding an extraction](#adding-an-extraction) for how to extend it. It is a
> starting point for your return, not a complete transcription of the forms.

## Install

```bash
git clone https://github.com/kirbysama/simple-offline-tax-assistant.git
cd simple-offline-tax-assistant

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

pip install -e .
```

Optional, for the browser-based clipboard and copy tests:

```bash
pip install -e ".[browser-tests]"
playwright install chromium
```

## Quick start

```bash
# Web dashboard (both tools, two tabs)
python -m streamlit run app.py

# Command line
python tax_1099_parser.py "path/to/statements" -o 1099_Tax_Summary.xlsx
python ny_sales_tax_calculator.py "path/to/activity" --county "New York City (8.875%)"
```

## What it extracts from your 1099s

The 1099 Aggregator reads the **summary-reporting method** of Form 1099-B, plus
the interest and dividend schedules. Specifically:

| Form | Boxes read | What you get |
| --- | --- | --- |
| Form 8949 summary | A, B, C (short-term) and D, E, F (long-term) | Proceeds, cost basis, adjustments, wash sale disallowed, net gain/loss |
| Form 1099-INT | 1, 3, 8 | Ordinary interest; US Treasury / Savings Bond interest; tax-exempt interest |
| Form 1099-DIV | 1a, 1b, 5 | Ordinary dividends; qualified dividends; Section 199A dividends |

Per account it also records the brokerage, clearing firm, account number, tax
year, and source filename, and it flags duplicate statements and any row where
`proceeds − cost basis + adjustments ≠ net gain/loss`.

Box 3 on the 1099-INT is read specifically so you can make the New York
IT-201 S-102 subtraction for Treasury obligations.

### What it does not extract

This is the important part:

- **No trade-by-trade Form 8949 lines.** Only the broker's summary figures are
  read. If you file using the detailed method, or you need per-lot basis, you
  still need the transaction-level data.
- **Wash sales are not computed.** The tool reads the broker's already-reported
  wash-sale disallowance (Box 1g / Code W). It does not apply the 30-day rule
  itself, so it will not catch a wash sale your broker missed.
- **Most boxes are not read.** 1099-INT has boxes 2–15a; 1099-DIV has boxes 2–14.
  Only the ones in the table above are extracted.
- **No other tax forms.** No 1099-R, 1099-DA, 1098, 1099-K, 1095, K-1, or
  consolidated brokerage 1099 that only reports covered-versus-noncovered detail
  in a layout this parser has not seen.

Everything else on the page — descriptions, CUSIPs, dates, quantities, per-sale
proceeds — is ignored.

## Sales tax calculator

Reads `.csv`, `.xlsx`, and `.xls` activity exports, auto-detects the bank's
column layout, then classifies each transaction through a tiered rules engine:

- excludes non-spend: card payments, balance transfers, interest, annual fees,
  late fees, statement credits, and P2P / fintech transfers
- nets merchant refunds as negative sales tax
- excludes out-of-state and foreign purchases
- classifies NY Tax Law §1115 exempt purchases (groceries and unprepared food,
  prescription drugs, MTA and transit, utilities)
- applies priority-taxable overrides for brands, phones, and marketplaces so a
  keyword like `MARKET` cannot mis-file a grocery purchase
- defaults ambiguous merchants to taxable

Sales tax is recovered with the reverse formula:

```
tax = gross × rate / (1 + rate)
```

All 63 New York jurisdictions are selectable — the 62 counties plus New York
City, which has no county of its own — and New York City at 8.875% is the
default. Output is `NY_Sales_Tax_Report.xlsx` with a `Deduction Summary` tab, an
`Itemized Ledger` carrying the classification reason for every row, and a
`Category Audit Trail` tab.

## Sample documents

**No sample tax documents are included in this repository**, by choice. Real
consolidated 1099 PDFs and bank exports stay identifying even after names and
account numbers are redacted, because the trade detail, income amounts, and
counterparty payment handles are untouched.

To run the full test suite, supply your own:

| Directory | Contents |
| --- | --- |
| `Sample Form 1099/` | Form 1099-B / 1099-DIV consolidated PDFs |
| `Sample 1099-INT/` | Form 1099-INT PDFs |
| `Sample Activity Statements/` | Annual activity exports from your banks |

Drop your files in and run:

```bash
python -m pytest tests/ -q
```

Tests that need documents skip themselves when the directories are absent, so a
fresh clone still reports green. All three directories are gitignored, so your
tax documents cannot be swept into a commit by `git add -A`.

Two filename conventions matter, because the parsers read filenames:

- **Brokerage detection falls back to the filename** when the brand cannot be
  found in the document text. Prefix with the institution —
  `Vanguard 2025 Form 1099.pdf`, `Fidelity Consolidated.pdf`.
- **Bank dialect detection derives the account label from the filename** —
  `Chase Sapphire Preferred Card 1234.csv`.

## Adding an extraction

If you need a box that is not in the table above, this is a normal small code
change and the repository is set up for it. Clone it and ask your coding agent
to add the field — it needs to touch four places:

1. **`src/tax_tools/models.py`** — add the field to `Form1099INT`,
   `Form1099DIV`, or `Form8949Box`.
2. **`src/tax_tools/parser_1099.py`** — add a regex to the relevant
   `parse_*` function. The existing ones are small, commented, and each targets
   one layout, so a new issuer is usually a handful of lines.
3. **`src/tax_tools/excel_exporter.py`** — surface it in the relevant sheet.
4. **`tests/`** — add a case; supply a sample PDF under `Sample Form 1099/` to
   assert against.

A worked request looks like:

> Read Form 1099-INT box 4 (early withdrawal penalty) and add it as a column in
> the Interest & Dividend Schedule.

The parser is deliberately deterministic and regex-driven, so an agent can add a
box without you having to understand the surrounding extraction logic. Prefer
matching on the form's own labels (`Early withdrawal penalty`, `Box 4`) over
position, because issuers reorder boxes between years.

## Limitations

- **Not tax advice, and it does not file anything.** It produces a summary for
  you or your preparer to check.
- **Layout-dependent parsing.** Extraction is matched against the text and
  tables that specific issuers actually produce. A new brokerage, a redesigned
  statement, or a mid-year format change can produce zeros rather than an error.
  Check the parity flag and spot-check the totals against the PDF.
- **Brokerage detection covers 15 institutions and 12 clearing firms.** Anything
  else depends on the filename convention above.
- **Sales tax is New York only**, single-county, and keyword-driven. It is an
  estimate: your real liability depends on the jurisdiction at the point of sale,
  and exempt status depends on how an item was actually used. A restaurant is
  exempt for a senior citizen but taxable for everyone else, and no keyword
  matcher can tell the difference.
- **Does not reconcile against a filed return.** It has no view of what you
  already reported.
- **Wash sales are read, not recomputed** (see above).

## Privacy

Runs entirely on your machine. Documents are read from disk and never leave it.
The sample-document directories and `docs/tax/` are gitignored, and Windows
shortcut files are excluded because they embed absolute paths from the machine
that created them.

## Tests

```bash
pip install -e ".[browser-tests]"
playwright install chromium
python -m pytest tests/ -q
```

Without sample documents: **96 passed, 35 skipped, 1 xfailed**. With your own
documents supplied, the document-dependent tests run as well.
