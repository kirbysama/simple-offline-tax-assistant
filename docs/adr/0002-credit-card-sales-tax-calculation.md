# ADR 0002: Deterministic Credit Card Ingestion and NY Reverse Sales Tax Calculator

## Status
Accepted

## Context
IRS Schedule A allows itemizing taxpayers to deduct actual state and local general sales taxes paid instead of state income taxes. Credit card activity exports record only settled gross transaction amounts without sales tax line items. Taxpayers require a deterministic, local mechanism to:
1. Normalize activity exports across disparate banking formats (Chase, Amex, Citi, Discover, Capital One, BofA, Apple Card, Generic).
2. Exclude non-spend transactions (payments, transfers, interest, annual fees, adjustments).
3. Classify transactions into exempt categories (unprepared food/groceries, healthcare/prescriptions, commuter transit/tolls, utilities/rent) vs taxable goods and dining.
4. Default ambiguous retail merchants to taxable spend.
5. Offset deductions accurately with merchant refunds and negative sales tax.
6. Reverse-calculate exact sales tax paid across all 62 New York counties, defaulting to New York City (8.875%).
7. Generate an audit-ready multi-tab Excel workbook (`NY_Sales_Tax_Report.xlsx`).

## Decision
1. **Multi-Dialect Bank Schema Detection**: Implement pattern matching on header column names and row characteristics to detect bank dialects (Chase Credit, Chase Checking, Amex, Citi, Discover, Capital One, Bank of America, Apple Card, Generic).
2. **Sign Normalization**: Standardize all spend amounts so that gross purchases are positive values and returns/refunds are negative values, accounting for inverted bank conventions (e.g. Chase recording sales as negative amounts).
3. **Deterministic Multi-Tier Classification**:
   - Tier 1: Exclusion rule matching non-spend descriptions (`Payment Thank You`, `AUTOPAY`, `DIRECTPAY`, annual fees, interest, transfers).
   - Tier 2: Geographic exclusion rule matching airfare, out-of-state lodging, and foreign transactions.
   - Tier 3: Exemption rule matching keywords and bank category tags for unprepared food/groceries, healthcare, transit, and utilities.
   - Tier 4: Taxable rule matching restaurants, delivery, entertainment, electronics.
   - Tier 5: Ambiguous default rule mapping remaining retail purchases to taxable.
4. **Exact Cent Parity Reverse Tax Calculation**:
   $$\text{Pre-Tax} = \text{round}\left(\frac{\text{Amount}}{1 + r}, 2\right), \quad \text{Sales Tax} = \text{round}(\text{Amount} - \text{Pre-Tax}, 2)$$
   Ensuring $\text{Pre-Tax} + \text{Sales Tax} = \text{Amount}$ parity for both positive charges and negative refunds.
5. **OpenPyXL Multi-Tab Export**: Generate `NY_Sales_Tax_Report.xlsx` with:
   - Tab 1: Executive KPI Deduction Summary
   - Tab 2: Itemized Transaction Ledger with classification rationale
   - Tab 3: Category Breakdown & Card Summary Audit Trail

## Consequences
- 100% deterministic, offline execution with zero API fees and privacy preservation.
- Full parity and audit readiness for Schedule A and New York tax reporting.
