# 11: Summary Table Density, Header Shortening, Contrast & Column Reordering

**What to build:** 
Shorten the Short-Term and Long-Term Net Gain/(Loss) column headers to `ST Net` and `LT Net`, reduce the preview table font size by 1 pt for increased data density, move the `Clearing Firm` column to the far right of the table so that primary financial numbers take precedence, and increase the visual contrast between shaded (inactive all-zero) and unshaded (active) cells.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

## Acceptance Criteria

- [x] In `app.py` (`build_1099_summary_df`), shorten column names from `"ST Net Gain/(Loss)"` to `"ST Net"` and `"LT Net Gain/(Loss)"` to `"LT Net"`.
- [x] In `src/tax_tools/formatter.py` (`SEMANTIC_GROUPS`), update the Short-Term and Long-Term semantic group mappings to reference `"ST Net"` and `"LT Net"`, ensuring zero-detection and inactive shading continue to work seamlessly.
- [x] In `app.py` (`build_1099_summary_df`), reorder columns so that `"Clearing Firm"` is moved from column 3 to the far right of the table (e.g. after `"US Treasury Interest"` or right beside `"Parity Status"`), ensuring high-priority figures (`Brokerage Name`, `Account #`, ST/LT figures, and Interest) appear first.
- [x] In `src/tax_tools/formatter.py` (CSS in `render_summary_table_html`), reduce the table font size by 1 pt (from `0.875rem` / ~14px down to `0.8125rem` / ~13px or `10pt`), adjusting header and cell padding accordingly to achieve a compact, high-density financial table layout.
- [x] Increase visual contrast between shaded (inactive) and unshaded (active) cells in `render_summary_table_html`: deepen the inactive cell shading (e.g., from subtle `#F1F3F5` to a more distinct darker muted tone like `#E2E6EA` / `#DEE2E6` with `#6c757d` text, while maintaining active cells as clean crisp white `#ffffff` or transparent), making inactive sections immediately distinguishable from active sections at a glance.
- [x] Update unit tests across `tests/test_cli_and_app.py` and `tests/test_summary_preview.py` to assert the new column names (`ST Net`, `LT Net`), the right-most placement of `Clearing Firm`, updated contrast styles, and updated typography.
- [x] Verify that the complete test suite passes (`.\.venv\Scripts\python.exe -m pytest`).
