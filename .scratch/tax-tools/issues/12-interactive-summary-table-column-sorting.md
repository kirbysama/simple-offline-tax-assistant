# 12: Interactive Summary Table Column Header Sorting

**What to build:**
Restore column header click-to-sort functionality in the 1099 Aggregator Interactive Summary Table Preview. Implement client-side JavaScript sorting triggered by clicking on any column header (`<th>`), toggling between ascending and descending order. Support smart type detection (parsing currency amounts, negatives, and commas for numerical comparisons, and case-insensitive string comparisons for text columns). Provide visual sort direction indicators (neutral `⇅`, ascending `▲`, descending `▼`), preserve all cell formatting (one-click copy buttons, section dividers, wash-sale highlights, and inactive zero-group shading), and execute completely client-side without triggering Streamlit server reruns.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

## Acceptance Criteria

- [x] In `src/tax_tools/formatter.py` (`render_summary_table_html`), add interactive sort capability to all table headers (`<th>`), including `cursor: pointer`, user-select prevention, and visual sort indicators (`⇅` by default).
- [x] Implement client-side sorting in the embedded `<script>`:
  - On header click, toggle sort order (ascending on first click, descending on next click).
  - Reset sort indicators on all other columns to neutral (`⇅`) and set the active column indicator to `▲` (ascending) or `▼` (descending).
  - Deterministically identify numeric/currency columns (`ST Proceeds`, `ST Basis`, `ST Wash Sale`, `ST Net`, `LT Proceeds`, `LT Basis`, `LT Wash Sale`, `LT Net`, `Total Proceeds`, `Total Cost Basis`, `Total Wash Sale`, `Total Net Gain/(Loss)`, `Ordinary Interest`, `US Treasury Interest`) versus text columns (`Brokerage Name`, `Account #`, `Clearing Firm`, `Parity Status`).
  - Correctly clean and parse currency strings (removing `$`, `,`, whitespace, handling negative signs and accounting parentheses `(100.00)` -> `-100.00`, treating `-` as zero) to perform numerical comparison rather than lexical string comparison.
  - Reorder `<tr>` DOM elements in `<tbody>` without recreating them, ensuring all inline copy buttons, `data-copy` attributes, section dividers, wash-sale highlights, and group-inactive backgrounds remain intact and fully functional.
  - Execute completely client-side within the browser without triggering Streamlit server refreshes or reruns.
- [x] Add unit tests in `tests/test_summary_preview.py` asserting:
  - Header cells (`<th>`) render with sort attributes/classes and visual sort indicators.
  - CSS contains sortable header styling (`cursor: pointer`, hover states, indicator styling).
  - Embedded script includes sort handler, column type detection, currency parsing, and DOM row reordering logic.
  - Existing one-click copy buttons, section dividers, and semantic zero shading remain intact and functional.
- [x] Verify that all unit and integration tests pass cleanly (`pytest`).
