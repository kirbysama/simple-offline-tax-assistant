# 09: Section Dividers and Semantic Group Inactive Shading

**What to build:** In the Interactive Summary Table Preview, thicken the visual dividers before the Short-Term (ST) and Long-Term (LT) sections to make section boundaries obvious, and shade entire semantic column groups (Short-Term, Long-Term, Interest) with a light grey background whenever all values in that group are zero for a given row.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance Criteria

- [x] Add prominent, thickened vertical dividers preceding the Short-Term section (`ST Proceeds`) and Long-Term section (`LT Proceeds`) across both table header and data rows.
- [x] Implement semantic group zero evaluation per row for:
  - **Short-Term Group**: `ST Proceeds`, `ST Basis`, `ST Wash Sale`, `ST Net Gain/(Loss)`.
  - **Long-Term Group**: `LT Proceeds`, `LT Basis`, `LT Wash Sale`, `LT Net Gain/(Loss)`.
  - **Interest Group**: `Ordinary Interest`, `US Treasury Interest`.
- [x] If all numerical values in a semantic group are zero for a statement row, style the entire group of cells with a muted light grey background (e.g. `#F1F3F5`).
- [x] If any value in a group is non-zero, leave the entire group unshaded (active).
- [x] Ensure active wash sales (> $0.00) retain their soft-red highlight (`#FFC7CE` background / `#9C0006` text).
- [x] Add unit tests verifying group zero-detection logic and styling rules across diverse statement fixtures.

