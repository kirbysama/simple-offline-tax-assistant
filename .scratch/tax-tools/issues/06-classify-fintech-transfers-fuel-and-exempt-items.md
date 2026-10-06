# 06: Classify Fintech Transfers, Motor Fuel & Gas Stations, Municipal Parking, and SF Match

**What to build:**
Deterministic classification rules in `SalesTaxCalculator` for recurring non-spend transfers and exempt transactions to prevent them from falling back to taxable general retail. Specifically:
- P2P and brokerage transfer merchants (`Paypal`, `Robinhood`, `WU digital`, `CashApp`, `Cash App`, `fennel`) classify as non-spend transfers (`TransactionTreatment.EXCLUDED_TRANSFER`) with 0 pre-tax base and 0 sales tax.
- Fuel and gas station merchants (`Fuel 4`, `exxon`, `quick chek`, `valero`, `fuel hub`, `Delta`, and generic gas/service stations) classify as tax-exempt (`TransactionTreatment.EXEMPT`).
- Municipal parking (`PARKNYC`) classifies as exempt (`TransactionTreatment.EXEMPT`).
- Medical residency matching fees (`SF Match`) classify as exempt education (`TransactionTreatment.EXEMPT` under Education).

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Add fintech transfer keywords (`PAYPAL`, `ROBINHOOD`, `WU DIGITAL`, `CASHAPP`, `CASH APP`, `FENNEL`) to Tier 1 transfer exclusions in `SalesTaxCalculator` assigning `TransactionTreatment.EXCLUDED_TRANSFER`.
- [x] Add motor fuel merchants and gas station keywords (`FUEL 4`, `EXXON`, `QUICK CHEK`, `QUICKCHEK`, `VALERO`, `FUEL HUB`, `DELTA`, `GAS STATION`, `SERVICE STATION`) under Tier 4 tax-exempt classifications in `SalesTaxCalculator` assigning `TransactionTreatment.EXEMPT`.
- [x] Add municipal parking (`PARKNYC`) under Tier 4 commuter transit/tolls/parking tax-exempt classifications assigning `TransactionTreatment.EXEMPT`.
- [x] Add `SF MATCH` under Tier 4 utilities, rent & education tax-exempt classifications assigning `TransactionTreatment.EXEMPT` with an educational category and rationale.
- [x] Ensure pre-tax amount and sales tax are set to 0.0 for all excluded transfers and exempt categories.
- [x] Add comprehensive automated tests in `tests/test_sales_tax_calculator.py` verifying each requested merchant matches and classifies as expected.

## Answer

Implemented deterministic classification rules for fintech non-spend transfers and tax-exempt items in `SalesTaxCalculator`:

1. **Fintech / P2P / Brokerage Transfers (Tier 1 Exclusions)**:
   - Added `PAYPAL`, `ROBINHOOD`, `WU DIGITAL`, `WUVISAAFT`, `CASHAPP`, `CASH APP`, and `FENNEL` to Tier 1 `transfer_keywords`.
   - All matching transactions are assigned `TransactionTreatment.EXCLUDED_TRANSFER` with `pre_tax_amount = 0.0` and `sales_tax = 0.0`.
   - Prevents recurring banking transfers from falling through into taxable retail defaults.

2. **Motor Fuel & Gas Stations (Tier 4D Exemptions)**:
   - Added Tier 4D classification matching `cat_upper in ("GASOLINE", "GAS")` or keywords `FUEL 4`, `EXXON`, `QUICK CHEK`, `QUICKCHEK`, `VALERO`, `FUEL HUB`, `GAS STATION`, `SERVICE STATION`, and Delta service station indicators.
   - Assigned `TransactionTreatment.EXEMPT`, categorized as `"Motor Fuel & Gas Stations"`, and assigned rationale `"Exempt under NY Tax Law § 1115: motor fuel and service station purchases"`.
   - Sets `pre_tax_amount = 0.0` and `sales_tax = 0.0`.

3. **Municipal Parking (Tier 4B Exemptions)**:
   - Added `PARKNYC` and `PARK NYC` under Tier 4B commuter transit, tolls & parking.
   - Assigned `TransactionTreatment.EXEMPT`, categorized as `"Commuter Transit, Tolls & Parking"`, with `pre_tax_amount = 0.0` and `sales_tax = 0.0`.

4. **Medical Residency Matching - SF Match (Tier 4E Exemptions)**:
   - Added `SF MATCH` and `SFMATCH` under Tier 4E education.
   - Assigned `TransactionTreatment.EXEMPT`, categorized as `"Education & Residency"`, with rationale `"Exempt: medical residency matching program and educational examination fee"`, with `pre_tax_amount = 0.0` and `sales_tax = 0.0`.

5. **Automated Verification**:
   - Added unit test cases across all categories in `tests/test_sales_tax_calculator.py` (`test_fintech_and_p2p_transfers_excluded`, `test_motor_fuel_and_gas_stations_exempt`, `test_municipal_parking_parknyc_exempt`, `test_sf_match_residency_fee_exempt_education`).
   - Ran pytest test suite with all 27 sales tax tests passing.

