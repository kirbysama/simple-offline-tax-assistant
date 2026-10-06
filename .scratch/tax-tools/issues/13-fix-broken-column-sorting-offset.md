# 13: Fix Broken Column Header Sorting in 1099 Summary Table Preview

**What to build:**
Repair the column header click-to-sort feature in the 1099 Aggregator Interactive Summary Table Preview so that clicking a header sorts rows by the correct column. The root cause is an index offset: the table renders a leftmost per-row selection **checkbox** column before every data column, but the `data-col-index` attribute on each `<th>` starts at `0` for the first *data* column (`Brokerage Name`) without accounting for the checkbox column. As a result, the client-side `sortTable()` reads `row.children[colIndex]`, which resolves to the checkbox `<td>` instead of the intended column cell — sorting any column returns incorrect or empty results. The fix must realign the header index with the actual DOM column index (add 1 to account for the checkbox column) and verify every column sorts correctly.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## Acceptance Criteria

- [ ] In `src/tax_tools/formatter.py` (`render_summary_table_html`), ensure the `data-col-index` assigned to each data-column header accounts for the leading checkbox column (the header for `Brokerage Name` must resolve to `row.children[1]`, not `row.children[0]`).
- [ ] Verify sorting by each numeric column (`ST Proceeds`, `ST Basis`, `ST Net`, `LT Proceeds`, `LT Basis`, `LT Net`, `Total Proceeds`, `Total Cost Basis`, `Total Net`, `Total Net Gain/(Loss)`, `Box 1 Interest Income`, `Box 3 - Savings Bonds and Treasury Interest`, `Ordinary Interest`, `US Treasury Interest`) produces mathematically correct ascending/descending order.
- [ ] Verify sorting by each text column (`Brokerage Name`, `Account #`, `Clearing Firm`, `Parity Status`) produces correct alphabetical order.
- [ ] After sorting, verify all cell click-to-copy behavior remains functional (single delegated click handler, green checkmark feedback).
- [ ] After sorting, verify the per-row selection checkboxes and the master toggle/indeterminate state remain fully functional.
- [ ] After sorting, verify section dividers, wash-sale highlights, and zero-group shading remain intact.
- [ ] Update existing unit tests in `tests/test_summary_preview.py` (and any copy-specific tests) to assert sorting operates on the correct column cells, and add a regression test exercising a full ascending/descending toggle on a numeric column and a text column.
- [ ] Verify all unit and integration tests pass cleanly (`pytest`).
