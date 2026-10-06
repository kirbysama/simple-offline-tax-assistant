# 08: One-Click Numeric Copy Buttons for Target Columns

**What to build:** Add one-click copy buttons to 8 designated columns in the Interactive Summary Table Preview (`Brokerage Name`, `Account #`, `ST Proceeds`, `ST Basis`, `ST Wash Sale`, `LT Proceeds`, `LT Basis`, and `LT Wash Sale`). When copying any column that displays a dollar sign, only the pure numerical value (stripped of `$`) is copied to the clipboard, allowing instant pasting into tax filing software.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

## Acceptance Criteria

- [x] Provide clipboard data sanitization logic that strips `$` from currency amounts (e.g., `$12,345.67` -> `12345.67` or `12,345.67`, `-$500.00` -> `-500.00`, `$0.00` -> `0.00`) while preserving raw text for non-currency columns (`Brokerage Name`, `Account #`).
- [x] Integrate one-click copy buttons into the 8 target columns in the Interactive Summary Table Preview: `Brokerage Name`, `Account #`, `ST Proceeds`, `ST Basis`, `ST Wash Sale`, `LT Proceeds`, `LT Basis`, and `LT Wash Sale`.
- [x] Execute client-side clipboard copy via `navigator.clipboard.writeText(...)` without triggering Streamlit server reruns.
- [x] Provide momentary visual feedback upon copying (e.g. checkmark icon and/or "Copied!" tooltip for ~1.2s).
- [x] Include unit tests verifying numerical sanitization across positive, negative, zero, and string formats.
