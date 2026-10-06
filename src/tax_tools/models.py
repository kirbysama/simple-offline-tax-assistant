"""Data models for Form 8949 and 1099 consolidated tax reporting."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Form8949Box:
    """Represents a single Form 8949 category (Box A, B, C, D, E, F)."""
    box_name: str
    description: str = ""
    proceeds: float = 0.0
    cost_basis: float = 0.0
    adjustments: float = 0.0
    net_gain_loss: float = 0.0
    wash_sale_disallowed: float = 0.0

    @property
    def parity_difference(self) -> float:
        """Returns proceeds - cost_basis + adjustments - net_gain_loss."""
        return round(self.proceeds - self.cost_basis + self.adjustments - self.net_gain_loss, 2)

    @property
    def is_parity_valid(self) -> bool:
        """True if mathematical parity holds within $0.02 tolerance."""
        # Only check parity if there is transaction activity
        if self.proceeds == 0.0 and self.cost_basis == 0.0 and self.adjustments == 0.0 and self.net_gain_loss == 0.0:
            return True
        return abs(self.parity_difference) <= 0.02

    def __add__(self, other: "Form8949Box") -> "Form8949Box":
        return Form8949Box(
            box_name=self.box_name,
            description=self.description,
            proceeds=round(self.proceeds + other.proceeds, 2),
            cost_basis=round(self.cost_basis + other.cost_basis, 2),
            adjustments=round(self.adjustments + other.adjustments, 2),
            net_gain_loss=round(self.net_gain_loss + other.net_gain_loss, 2),
            wash_sale_disallowed=round(self.wash_sale_disallowed + other.wash_sale_disallowed, 2),
        )


@dataclass
class Form8949Summary:
    """Consolidated Form 8949 summary covering Parts I & II (Boxes A through F)."""
    box_a: Form8949Box = field(default_factory=lambda: Form8949Box("Box A", "Short-term basis reported to IRS"))
    box_b: Form8949Box = field(default_factory=lambda: Form8949Box("Box B", "Short-term basis NOT reported to IRS"))
    box_c: Form8949Box = field(default_factory=lambda: Form8949Box("Box C", "Short-term 1099-B not received"))
    box_d: Form8949Box = field(default_factory=lambda: Form8949Box("Box D", "Long-term basis reported to IRS"))
    box_e: Form8949Box = field(default_factory=lambda: Form8949Box("Box E", "Long-term basis NOT reported to IRS"))
    box_f: Form8949Box = field(default_factory=lambda: Form8949Box("Box F", "Long-term 1099-B not received"))

    @property
    def total_wash_sale_disallowed(self) -> float:
        """Total Form 1099-B Box 1g Wash Sale Disallowance across all boxes A-F."""
        return round(
            self.box_a.wash_sale_disallowed
            + self.box_b.wash_sale_disallowed
            + self.box_c.wash_sale_disallowed
            + self.box_d.wash_sale_disallowed
            + self.box_e.wash_sale_disallowed
            + self.box_f.wash_sale_disallowed,
            2,
        )

    @property
    def short_term_total(self) -> Form8949Box:
        """Sum of Part I: Box A + Box B + Box C."""
        return Form8949Box(
            box_name="Part I Total",
            description="Total Short-Term",
            proceeds=round(self.box_a.proceeds + self.box_b.proceeds + self.box_c.proceeds, 2),
            cost_basis=round(self.box_a.cost_basis + self.box_b.cost_basis + self.box_c.cost_basis, 2),
            adjustments=round(self.box_a.adjustments + self.box_b.adjustments + self.box_c.adjustments, 2),
            net_gain_loss=round(self.box_a.net_gain_loss + self.box_b.net_gain_loss + self.box_c.net_gain_loss, 2),
            wash_sale_disallowed=round(
                self.box_a.wash_sale_disallowed + self.box_b.wash_sale_disallowed + self.box_c.wash_sale_disallowed, 2
            ),
        )

    @property
    def long_term_total(self) -> Form8949Box:
        """Sum of Part II: Box D + Box E + Box F."""
        return Form8949Box(
            box_name="Part II Total",
            description="Total Long-Term",
            proceeds=round(self.box_d.proceeds + self.box_e.proceeds + self.box_f.proceeds, 2),
            cost_basis=round(self.box_d.cost_basis + self.box_e.cost_basis + self.box_f.cost_basis, 2),
            adjustments=round(self.box_d.adjustments + self.box_e.adjustments + self.box_f.adjustments, 2),
            net_gain_loss=round(self.box_d.net_gain_loss + self.box_e.net_gain_loss + self.box_f.net_gain_loss, 2),
            wash_sale_disallowed=round(
                self.box_d.wash_sale_disallowed + self.box_e.wash_sale_disallowed + self.box_f.wash_sale_disallowed, 2
            ),
        )

    @property
    def grand_total(self) -> Form8949Box:
        """Sum of all boxes (Short-Term + Long-Term)."""
        st = self.short_term_total
        lt = self.long_term_total
        return Form8949Box(
            box_name="Grand Total",
            description="Total Short-Term + Long-Term",
            proceeds=round(st.proceeds + lt.proceeds, 2),
            cost_basis=round(st.cost_basis + lt.cost_basis, 2),
            adjustments=round(st.adjustments + lt.adjustments, 2),
            net_gain_loss=round(st.net_gain_loss + lt.net_gain_loss, 2),
            wash_sale_disallowed=round(st.wash_sale_disallowed + lt.wash_sale_disallowed, 2),
        )

    @property
    def all_parity_passed(self) -> bool:
        """True if parity holds for all individual boxes and summary totals."""
        boxes = [self.box_a, self.box_b, self.box_c, self.box_d, self.box_e, self.box_f, self.short_term_total, self.long_term_total]
        return all(b.is_parity_valid for b in boxes)

    def __add__(self, other: "Form8949Summary") -> "Form8949Summary":
        return Form8949Summary(
            box_a=self.box_a + other.box_a,
            box_b=self.box_b + other.box_b,
            box_c=self.box_c + other.box_c,
            box_d=self.box_d + other.box_d,
            box_e=self.box_e + other.box_e,
            box_f=self.box_f + other.box_f,
        )


@dataclass
class Form1099INT:
    """Represents Form 1099-INT interest income report."""
    box_1_interest: float = 0.0          # Ordinary / Taxable Interest
    box_3_us_treasury: float = 0.0       # U.S. Savings Bonds & Treasury Obligations (NY IT-201 S-102 subtraction)
    box_8_tax_exempt: float = 0.0        # Tax-Exempt Interest

    @property
    def total_interest(self) -> float:
        """Total interest income (Box 1 + Box 3 + Box 8)."""
        return round(self.box_1_interest + self.box_3_us_treasury + self.box_8_tax_exempt, 2)

    def __add__(self, other: "Form1099INT") -> "Form1099INT":
        return Form1099INT(
            box_1_interest=round(self.box_1_interest + other.box_1_interest, 2),
            box_3_us_treasury=round(self.box_3_us_treasury + other.box_3_us_treasury, 2),
            box_8_tax_exempt=round(self.box_8_tax_exempt + other.box_8_tax_exempt, 2),
        )


@dataclass
class Form1099DIV:
    """Represents Form 1099-DIV dividends and distributions report."""
    box_1a_ordinary_dividends: float = 0.0  # Total Ordinary Dividends
    box_1b_qualified_dividends: float = 0.0 # Qualified Dividends
    box_5_section_199a: float = 0.0         # Section 199A Dividends

    def __add__(self, other: "Form1099DIV") -> "Form1099DIV":
        return Form1099DIV(
            box_1a_ordinary_dividends=round(self.box_1a_ordinary_dividends + other.box_1a_ordinary_dividends, 2),
            box_1b_qualified_dividends=round(self.box_1b_qualified_dividends + other.box_1b_qualified_dividends, 2),
            box_5_section_199a=round(self.box_5_section_199a + other.box_5_section_199a, 2),
        )


import os


def normalize_brokerage_name(name: Optional[str]) -> str:
    """Normalize brokerage name for comparison (strip whitespace, collapse multiple spaces, lowercase)."""
    if not name:
        return ""
    return " ".join(str(name).strip().lower().split())


def normalize_account_number(account: Optional[str]) -> str:
    """Normalize account number for comparison (strip whitespace, lowercase, remove dashes/spaces)."""
    if not account:
        return ""
    return str(account).strip().lower().replace("-", "").replace(" ", "")


@dataclass
class BrokerageAccountStatement:
    """Represents a single account parsed from a 1099 consolidated document."""
    brokerage_name: str
    account_number: str
    tax_year: int = 2025
    clearing_firm: Optional[str] = None
    source_file: str = ""
    form_8949: Form8949Summary = field(default_factory=Form8949Summary)
    form_1099_int: Form1099INT = field(default_factory=Form1099INT)
    form_1099_div: Form1099DIV = field(default_factory=Form1099DIV)
    notes: List[str] = field(default_factory=list)
    is_duplicate: bool = False

    @property
    def identity_key(self) -> Optional[tuple[str, str]]:
        """Normalized (brokerage_name, account_number) key for duplicate detection.

        Returns None if account_number or brokerage_name is blank, preventing
        erroneous duplicate collisions when account identifiers are missing.
        """
        norm_brokerage = normalize_brokerage_name(self.brokerage_name)
        norm_account = normalize_account_number(self.account_number)
        if not norm_brokerage or not norm_account:
            return None
        return (norm_brokerage, norm_account)

    def mark_as_duplicate(self) -> str:
        """Marks this statement as a duplicate and attaches a standardized rejection note."""
        self.is_duplicate = True
        source_info = f" from file '{os.path.basename(self.source_file)}'" if self.source_file else ""
        note = (
            f"Duplicate statement rejected: {self.brokerage_name} "
            f"(Account: {self.account_number}){source_info} - "
            f"matches already ingested statement."
        )
        if note not in self.notes:
            self.notes.append(note)
        return note

    @property
    def parity_passed(self) -> bool:
        return self.form_8949.all_parity_passed


@dataclass
class AggregationReport:
    """Aggregate result from processing a collection of 1099 PDF statements."""
    statements: List[BrokerageAccountStatement] = field(default_factory=list)
    rejected_statements: List[BrokerageAccountStatement] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.deduplicate()

    def _reject_duplicate(self, statement: BrokerageAccountStatement) -> None:
        """Records statement rejection and aggregates the descriptive note."""
        note = statement.mark_as_duplicate()
        self.rejected_statements.append(statement)
        if note not in self.notes:
            self.notes.append(note)

    def deduplicate(self) -> None:
        """Identifies and rejects duplicate statements based on normalized brokerage and account number."""
        if not self.statements:
            return

        seen_keys: set[tuple[str, str]] = set()
        accepted: List[BrokerageAccountStatement] = []

        for statement in self.statements:
            key = statement.identity_key
            if key is not None and key in seen_keys:
                self._reject_duplicate(statement)
            else:
                if key is not None:
                    seen_keys.add(key)
                accepted.append(statement)

        self.statements = accepted

    def add_statement(self, statement: BrokerageAccountStatement) -> bool:
        """Add a statement, rejecting it if duplicate of already ingested statement."""
        key = statement.identity_key
        existing_keys = {s.identity_key for s in self.statements if s.identity_key is not None}
        if key is not None and key in existing_keys:
            self._reject_duplicate(statement)
            return False
        self.statements.append(statement)
        return True

    @property
    def duplicates(self) -> List[BrokerageAccountStatement]:
        return self.rejected_statements

    @property
    def rejected_duplicates(self) -> List[BrokerageAccountStatement]:
        return self.rejected_statements

    @property
    def aggregate_8949(self) -> Form8949Summary:
        total = Form8949Summary()
        for stmt in self.statements:
            total = total + stmt.form_8949
        return total

    @property
    def aggregate_int(self) -> Form1099INT:
        total = Form1099INT()
        for stmt in self.statements:
            total = total + stmt.form_1099_int
        return total

    @property
    def aggregate_div(self) -> Form1099DIV:
        total = Form1099DIV()
        for stmt in self.statements:
            total = total + stmt.form_1099_div
        return total

    @property
    def all_parity_passed(self) -> bool:
        return all(s.parity_passed for s in self.statements) and self.aggregate_8949.all_parity_passed

