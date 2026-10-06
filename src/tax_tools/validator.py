"""Validation and parity integrity checking for Form 8949 data."""

from typing import List, Tuple
from tax_tools.models import Form8949Summary, BrokerageAccountStatement


class ParityValidationError(Exception):
    """Raised when mathematical parity fails beyond allowed tolerance."""
    pass


def validate_box_parity(box_name: str, proceeds: float, cost_basis: float, adjustments: float, net_gain_loss: float, tolerance: float = 0.02) -> Tuple[bool, float]:
    """
    Asserts mathematical parity:
        Proceeds - Cost Basis + Adjustments == Net Gain/Loss
    Returns (is_valid, discrepancy).
    """
    calculated_net = proceeds - cost_basis + adjustments
    discrepancy = round(calculated_net - net_gain_loss, 2)
    is_valid = abs(discrepancy) <= tolerance
    return is_valid, discrepancy


def validate_statement_parity(statement: BrokerageAccountStatement, tolerance: float = 0.02) -> List[str]:
    """
    Validates parity for all boxes in a statement.
    Returns a list of error messages (empty if all pass).
    """
    errors = []
    summary = statement.form_8949
    boxes = [
        ("Box A", summary.box_a),
        ("Box B", summary.box_b),
        ("Box C", summary.box_c),
        ("Box D", summary.box_d),
        ("Box E", summary.box_e),
        ("Box F", summary.box_f),
        ("Short-Term Total", summary.short_term_total),
        ("Long-Term Total", summary.long_term_total),
    ]

    for name, box in boxes:
        # Only validate if there is non-zero data
        if box.proceeds == 0.0 and box.cost_basis == 0.0 and box.adjustments == 0.0 and box.net_gain_loss == 0.0:
            continue
        valid, disc = validate_box_parity(name, box.proceeds, box.cost_basis, box.adjustments, box.net_gain_loss, tolerance)
        if not valid:
            errors.append(
                f"Parity mismatch in {statement.brokerage_name} ({statement.account_number}) {name}: "
                f"Proceeds ${box.proceeds:,.2f} - Basis ${box.cost_basis:,.2f} + Adj ${box.adjustments:,.2f} = "
                f"${box.proceeds - box.cost_basis + box.adjustments:,.2f}, but reported Net was ${box.net_gain_loss:,.2f} "
                f"(discrepancy ${disc:,.2f})"
            )
    return errors
