# Domain Glossary: Tax Assistant

This glossary defines standard terminology used across the codebase and issue tracker.

### Consolidated Form 1099
An annual tax statement combining reporting for 1099-B (broker transactions), 1099-DIV (dividends), 1099-INT (interest), and 1099-MISC/OID from an investment institution.

### Form 8949 Summary Reporting
Summary reporting method on IRS Form 8949 / Schedule D where aggregate totals are reported rather than trade-by-trade entries, broken down by category:
- **Part I: Short-Term Capital Gains and Losses**
  - **Box A**: Transactions reported on Form(s) 1099-B showing basis was reported to the IRS.
  - **Box B**: Transactions reported on Form(s) 1099-B showing basis was NOT reported to the IRS.
  - **Box C**: Transactions not reported on Form(s) 1099-B.
- **Part II: Long-Term Capital Gains and Losses**
  - **Box D**: Transactions reported on Form(s) 1099-B showing basis was reported to the IRS.
  - **Box E**: Transactions reported on Form(s) 1099-B showing basis was NOT reported to the IRS.
  - **Box F**: Transactions not reported on Form(s) 1099-B.

### Form 8949 Category Totals
For each Box (A through F):
- **Proceeds**: Total gross sales proceeds (Box 1d).
- **Cost Basis**: Total allowable cost or other basis (Box 1e).
- **Adjustments**: Net adjustments including Wash Sale Disallowance (Box 1g / code W) and accrued market discount (Box 1f).
- **Net Gain/Loss**: Total net realized gain or loss for the category.

### Mathematical Parity
The core accounting assertion that:
$$\text{Proceeds} - \text{Cost Basis} + \text{Adjustments} = \text{Net Gain/Loss}$$
Must hold across every reported box and total within a $\pm \$0.01$ rounding tolerance.

### Brokerage Brand
The taxpayer's facing brokerage or fintech application (e.g., BBAE, DSpac, Fennel, Fidelity, Firstrade, Public, Robinhood, Schwab, SoFi, Tradier, Vanguard, WeBull, Wells Fargo/WellsTrade, Chase).

### Clearing House / Carrying Firm
The underlying entity executing, clearing, and settling trades and issuing the 1099 document (e.g., Apex Clearing Corporation, DriveWealth LLC, National Financial Services LLC, J.P. Morgan Securities LLC, Charles Schwab & Co., Inc.).

### Masked Account Number
The brokerage account identifier preserving original masking formatting (e.g., `***-1234` or `700-00513`).

---

## Credit Card & NY Sales Tax Domain

### Bank Schema Dialect
The tabular export layout format provided by a specific credit card or banking institution (Chase, American Express, Citi, Discover, Capital One, Bank of America, Apple Card, or Generic). Includes differences in column names (`Transaction Date` vs `Date` vs `Trans. Date`), sign conventions (positive vs negative debits), and separate vs consolidated debit/credit columns.

### Non-Spend Exclusion
Transactions that represent financial adjustments rather than purchases of goods or services, including card bill payments (`Payment Thank You`, `AUTOPAY`), balance transfers, interest and finance charges, annual card membership fees, and late fees. These are completely excluded from gross spend.

### Geographic Exclusion
Purchases occurring outside New York jurisdiction, such as out-of-state hotel lodging, airfare, and foreign currency / international transactions, which are not subject to New York State or local sales tax.

### Tax-Exempt Spending
Purchases of goods or services legally exempt from New York State and local sales tax:
- **Unprepared Food & Groceries**: Food for home consumption purchased at supermarkets, grocery stores, bakeries, and farmers markets (NY Tax Law § 1115(a)(1)).
- **Prescription & Medical**: Prescription drugs, medical devices, dental services, doctor visits, and healthcare (NY Tax Law § 1115(a)(3)).
- **Commuter Transit & Tolls**: Public transit (MTA subway, bus, Long Island Rail Road, Metro-North), PATH, and bridge/tunnel tolls (E-ZPass).
- **Utilities & Rent & Education**: Residential utilities (electric, natural gas), water, mobile phone service, tuition, and residential rent.

### Taxable Spending
Purchases of tangible personal property and taxable services:
- Restaurants, cafes, bars, and prepared food delivery (NY Tax Law § 1105(d)).
- Electronics, hardware, home furnishings, apparel, and entertainment.
- General retail merchandise.
- **Ambiguous Merchant Default**: Any non-exempt, non-excluded retail transaction whose exact tax status cannot be unambiguously proven defaults to taxable per IRS Schedule A / NY State audit convention.

### Negative Sales Tax Offset
A merchant refund or return represented as a negative transaction amount. It reverse-calculates negative sales tax paid, ensuring net sales tax deductions accurately reconcile against net expenditures.

### Reverse Sales Tax Calculation
Given a gross settled purchase amount $A$ inclusive of sales tax and a local statutory tax rate $r$:
$$\text{Pre-Tax Base} = \frac{A}{1 + r}, \quad \text{Sales Tax} = A \times \frac{r}{1 + r}$$
With exact cent parity enforced: $\text{Pre-Tax Base} + \text{Sales Tax} = A$.

### Combined New York Sales Tax Rate
The aggregate statutory sales tax rate composed of New York State tax (4.0%), local city/county tax, and the Metropolitan Commuter Transportation District (MCTD) surcharge (0.375% in the 12-county commuter district). Defaults to New York City (8.875%).

