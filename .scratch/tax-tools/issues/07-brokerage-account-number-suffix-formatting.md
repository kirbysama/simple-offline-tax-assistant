# 07: Brokerage Account Number Suffix Formatting

**What to build:** In the Interactive Summary Table Preview, append the last 4 characters of the statement account number to the Brokerage Name column (e.g., `BBAE -3240`), making it immediately obvious which account is being viewed across multiple accounts held at the same financial institution.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

## Acceptance Criteria

- [x] Provide a helper function to format the brokerage display name given a brokerage name and account number string (e.g. `format_brokerage_display_name(brokerage_name, account_number)`).
- [x] For standard and masked account numbers (e.g. `***-3240`, `12345678`), cleanly extract the trailing 4 characters and format as `f"{brokerage_name} -{last_4}"` (e.g. `BBAE -3240`).
- [x] Safely handle edge cases: if account number has fewer than 4 characters, is blank, or is None, gracefully fall back without raising IndexError or formatting anomalies.
- [x] Update `build_1099_summary_df` to populate the `Brokerage Name` column with this formatted display name.
- [x] Add unit tests covering standard, masked, short, and empty account numbers, asserting expected display name output across all test fixtures.
