"""Deterministic 1099 PDF Parser targeting Form 8949 Summaries."""

import os
import re
from typing import List, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor
import pypdf
import pdfplumber

from tax_tools.models import (
    Form8949Box,
    Form8949Summary,
    Form1099INT,
    Form1099DIV,
    BrokerageAccountStatement,
)


KNOWN_BROKERAGES = [
    # (Regex pattern in document text, Canonical Brand Name)
    (r"\bpublic\.com\b|\bpublic\s+investing\b", "Public"),
    (r"\brobinhood\b", "Robinhood"),
    (r"\bcharles\s+schwab\b|\bschwab\b", "Charles Schwab"),
    (r"\bvanguard\b", "Vanguard"),
    (r"\bfidelity\b", "Fidelity"),
    (r"\bfirstrade\b", "Firstrade"),
    (r"\btradier\b", "Tradier"),
    (r"\bwebull\b", "Webull"),
    (r"\bwellstrade\b|\bwells\s+fargo\b", "WellsTrade"),
    (r"\bj\.?p\.?\s*morgan\b|\bchase\b", "Chase"),
    (r"\bbank\s+of\s+america\b|\bbofa\b", "Bank of America"),
    (r"\bfennel\b", "Fennel"),
    (r"\bsofi\b", "SoFi"),
    (r"\bbbae\b", "BBAE"),
    (r"\bdspac\b", "DSpac"),
]

KNOWN_CLEARING_FIRMS = [
    (r"\bapex\s+clearing\b", "Apex Clearing Corporation"),
    (r"\bdrivewealth\b", "DriveWealth LLC"),
    (r"\bnational\s+financial\s+services\b|\bnfs\b", "National Financial Services LLC"),
    (r"\brobinhood\s+securities\b", "Robinhood Securities LLC"),
    (r"\bj\.?p\.?\s*morgan\s+securities\b", "J.P. Morgan Securities LLC"),
    (r"\bcharles\s+schwab\s+&\s+co\b", "Charles Schwab & Co., Inc."),
    (r"\bvanguard\s+marketing\b", "Vanguard Marketing Corporation"),
    (r"\bredbridge\s+securities\b", "Redbridge Securities LLC"),
    (r"\bwells\s+fargo\s+clearing\s+services\b", "Wells Fargo Clearing Services, LLC"),
    (r"\bwebull\s+financial\b", "Webull Financial LLC"),
    (r"\bsofi\s+bank\b", "SoFi Bank, N.A."),
    (r"\bbank\s+of\s+america\b", "Bank of America, N.A."),
]

FILENAME_BRAND_PATTERNS = [
    (r"^BBAE\b", "BBAE"),
    (r"^BofA\b|^Bank\s+of\s+America\b", "Bank of America"),
    (r"^DSpac\b", "DSpac"),
    (r"^Fennel\b", "Fennel"),
    (r"^Fidelity\b", "Fidelity"),
    (r"^Firstrade\b", "Firstrade"),
    (r"^Public\b", "Public"),
    (r"^Robinhood\b", "Robinhood"),
    (r"^Schwab\b", "Charles Schwab"),
    (r"^SoFi\b", "SoFi"),
    (r"^Tradier\b", "Tradier"),
    (r"^Vanguard\b", "Vanguard"),
    (r"^WeBull\b", "Webull"),
    (r"^WellsTrade\b", "WellsTrade"),
    (r"^x\s*Chase\b|^Chase\b", "Chase"),
]


def clean_amount(val_str: str) -> float:
    """Parses numeric amount from string, handling currency symbols and negatives."""
    if not val_str:
        return 0.0
    val_str = val_str.replace("$", "").replace(",", "").replace(" ", "").strip()
    if not val_str or val_str in ("--", "-", "N/A", "none", "NONE"):
        return 0.0
    if val_str.startswith("(") and val_str.endswith(")"):
        val_str = "-" + val_str[1:-1]
    try:
        return round(float(val_str), 2)
    except ValueError:
        return 0.0


def detect_brokerage(doc_text: str, filename: str) -> Tuple[str, Optional[str]]:
    """
    Detects brokerage brand and clearing firm.
    Uses document text/headers first. If unrecognized, falls back to the filename.
    """
    brand = None
    clearing = None

    # Check clearing firms in document text
    for pattern, name in KNOWN_CLEARING_FIRMS:
        if re.search(pattern, doc_text, re.IGNORECASE):
            clearing = name
            break

    # Check brand in document text
    for pattern, name in KNOWN_BROKERAGES:
        if re.search(pattern, doc_text, re.IGNORECASE):
            brand = name
            break

    # Fallback to filename if brand not identified in document text
    if not brand:
        base_name = os.path.basename(filename)
        for pattern, name in FILENAME_BRAND_PATTERNS:
            if re.search(pattern, base_name, re.IGNORECASE):
                brand = name
                break
        if not brand:
            first_word = base_name.split()[0].replace("_", "").replace("-", "")
            brand = first_word if first_word else "Unknown Brokerage"

    return brand, clearing


def detect_account_number(doc_text: str, filename: str) -> str:
    """
    Extracts account number from document text/header preserving original masking.
    Falls back to filename if not found in text.
    """
    # Pattern 1: <BranchAccount>XXXX (Used by Apex Clearing statements)
    m = re.search(r"<BranchAccount>\s*([A-Za-z0-9\-]+)", doc_text)
    if m:
        return m.group(1).strip()

    # Pattern 2: 8-10 digit account numbers (e.g. "Account 12345678")
    m = re.search(r"\bAccount\s+([0-9]{8,10})\b", doc_text)
    if m:
        return m.group(1).strip()

    # Pattern 3: Alphanumeric brokerage masks (e.g. AA1-234567, 1234-5678)
    # Exclude OMB numbers like 1545-XXXX and 7-digit phone numbers like 662-2739, 456-7634
    matches = re.findall(r"\b([A-Z0-9]{3,4}-[0-9]{4,7})\b", doc_text)
    for cand in matches:
        if not cand.startswith("1545-") and not re.match(r"^\d{3}-\d{4}$", cand) and not re.match(r"^[A-Z]{2}\d-\d{4}$", cand):
            return cand.strip()

    # Pattern 4b: Table layout for 1099-INT (e.g. Chase Mortgage "1809900001 $18.51")
    m = re.search(r"\n\s*([0-9]{8,14})\s+\$[0-9,]+\.[0-9]{2}", doc_text)
    if m:
        return m.group(1).strip()

    # Pattern 4c: Standard IRS Form 1099-INT lower block (e.g. SoFi "Account number (see instructions)" followed by digits)
    m = re.search(r"Account number \(see instructions\)[^\n]*\n(?:[^\n]*\n){1,15}?\s*([0-9]{7,12})\b", doc_text)
    if m:
        return m.group(1).strip()

    # Pattern 4: Account Number: / Account No: XXXX (or on the next line)
    m = re.search(r"(?:Account\s*(?:Number|No\.?|#)?[:\s]+)([A-Za-z0-9\*\-]+(?:\s+[A-Za-z0-9\*\-]+)?)", doc_text, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        # An account number must carry a digit or an explicit mask character.
        # That single rule rejects the three things this pattern otherwise
        # mis-captures: the recipient's name ("Account No. JANE Q PUBLIC TOD"),
        # cross-reference prose ("Account No. SEE BOX 1"), and institution
        # location codes ("CHASE O3415 VISION DRIVE OH4-7214"). Keying on shape
        # rather than on any particular taxpayer's name keeps the parser
        # working for documents that are not the ones it was developed against.
        looks_like_account = any(ch.isdigit() for ch in cand) or "*" in cand
        if (
            cand
            and looks_like_account
            and not cand.startswith("1545-")
            and not re.match(r"^\d{3}-\d{4}$", cand)
            and not re.match(r"^[A-Z]{2}\d-\d{4}$", cand)
        ):
            return cand

    # Pattern 5: Fallback to filename
    base_name = os.path.basename(filename)
    m = re.search(r"\b([0-9]{3,4}-[0-9]{4,6})\b", base_name)
    if m:
        return m.group(1)
    m = re.search(r"\b([0-9A-Z]{8})\b", base_name)
    if m:
        return m.group(1)
    m = re.search(r"\b([0-9]{7,10})\b", base_name)
    if m:
        return m.group(1)

    return "UNKNOWN-ACCT"


class CachedPages:
    """Memoizes extracted page text for a pypdf reader to prevent redundant extraction passes."""

    def __init__(self, reader: pypdf.PdfReader) -> None:
        self.reader = reader
        self._cache: List[Optional[str]] = [None] * len(reader.pages)
        self.num_pages: int = len(reader.pages)

    def get_text(self, idx: int) -> str:
        if 0 <= idx < self.num_pages:
            if self._cache[idx] is None:
                self._cache[idx] = self.reader.pages[idx].extract_text() or ""
            return self._cache[idx]
        return ""

    def all_text(self) -> str:
        return "\n".join(self.get_text(i) for i in range(self.num_pages))


def parse_apex_summary(pdf_path: str, target_page_idx: Optional[int] = None) -> Form8949Summary:
    """
    Parses Apex Clearing summary layout using word coordinates with pdfplumber.
    Used by: BBAE, DSpac, Fennel, Firstrade, Public, Tradier, WeBull.
    If target_page_idx is provided, directly targets that page to bypass redundant page scanning.
    """
    summary = Form8949Summary()
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_check = (
                [pdf.pages[target_page_idx]]
                if target_page_idx is not None and 0 <= target_page_idx < len(pdf.pages)
                else pdf.pages[:10]
            )
            for page in pages_to_check:
                text = page.extract_text() or ""
                if target_page_idx is not None or "Summary Of Sale Proceeds" in text or "Summary of Sale Proceeds" in text:
                    words = page.extract_words()
                    lines = {}
                    for w in words:
                        bucket = round(w["top"] / 3) * 3
                        lines.setdefault(bucket, []).append(w)

                    for bucket in sorted(lines.keys()):
                        row = sorted(lines[bucket], key=lambda x: x["x0"])
                        row_text = " ".join(w["text"] for w in row)
                        amounts = [w["text"] for w in row if re.match(r"^-?\$?[0-9,]+\.[0-9]{2}$", w["text"])]

                        if "Short-term" in row_text and "covered" in row_text and "noncovered" not in row_text:
                            if len(amounts) >= 5:
                                summary.box_a.proceeds = clean_amount(amounts[0])
                                summary.box_a.cost_basis = clean_amount(amounts[1])
                                summary.box_a.adjustments = round(clean_amount(amounts[2]) + clean_amount(amounts[3]), 2)
                                summary.box_a.wash_sale_disallowed = clean_amount(amounts[3])
                                summary.box_a.net_gain_loss = clean_amount(amounts[4])

                        elif "Short-term" in row_text and "noncovered" in row_text:
                            if len(amounts) >= 5:
                                summary.box_b.proceeds = clean_amount(amounts[0])
                                summary.box_b.cost_basis = clean_amount(amounts[1])
                                summary.box_b.adjustments = round(clean_amount(amounts[2]) + clean_amount(amounts[3]), 2)
                                summary.box_b.wash_sale_disallowed = clean_amount(amounts[3])
                                summary.box_b.net_gain_loss = clean_amount(amounts[4])

                        elif "Long-term" in row_text and "covered" in row_text and "noncovered" not in row_text:
                            if len(amounts) >= 5:
                                summary.box_d.proceeds = clean_amount(amounts[0])
                                summary.box_d.cost_basis = clean_amount(amounts[1])
                                summary.box_d.adjustments = round(clean_amount(amounts[2]) + clean_amount(amounts[3]), 2)
                                summary.box_d.wash_sale_disallowed = clean_amount(amounts[3])
                                summary.box_d.net_gain_loss = clean_amount(amounts[4])

                        elif "Long-term" in row_text and "noncovered" in row_text:
                            if len(amounts) >= 5:
                                summary.box_e.proceeds = clean_amount(amounts[0])
                                summary.box_e.cost_basis = clean_amount(amounts[1])
                                summary.box_e.adjustments = round(clean_amount(amounts[2]) + clean_amount(amounts[3]), 2)
                                summary.box_e.wash_sale_disallowed = clean_amount(amounts[3])
                                summary.box_e.net_gain_loss = clean_amount(amounts[4])
                    break
    except Exception:
        pass
    return summary


def parse_vanguard_robinhood_text(text: str) -> Form8949Summary:
    """
    Parses Vanguard / Robinhood standard summary table layout.
    """
    summary = Form8949Summary()
    patterns = [
        ("box_a", r"Short\s*A\s*\(basis reported to the IRS\)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)"),
        ("box_b", r"Short\s*B\s*\(basis not reported to the IRS\)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)"),
        ("box_c", r"Short\s*C\s*\(Form 1099-B not received\)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)"),
        ("box_d", r"Long\s*D\s*\(basis reported to the IRS\)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)"),
        ("box_e", r"Long\s*E\s*\(basis not reported to the IRS\)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)"),
        ("box_f", r"Long\s*F\s*\(Form 1099-B not received\)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)\s+([-\d\.,]+)"),
    ]

    for box_attr, pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            box: Form8949Box = getattr(summary, box_attr)
            box.proceeds = clean_amount(m.group(1))
            box.cost_basis = clean_amount(m.group(2))
            box.adjustments = round(clean_amount(m.group(3)) + clean_amount(m.group(4)), 2)
            box.wash_sale_disallowed = clean_amount(m.group(4))
            box.net_gain_loss = clean_amount(m.group(5))

    return summary


def parse_five_number_row(nums: List[str]) -> Tuple[float, float, float, float, float]:
    """
    Given a list of numeric strings from a summary row, extracts
    (proceeds, cost_basis, adjustments, net_gain_loss, wash_sale_disallowed) using mathematical parity.
    Handles column order differences (WellsTrade vs Chase).
    """
    if len(nums) < 4:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    p = clean_amount(nums[0])
    if len(nums) >= 5:
        cand_b1 = clean_amount(nums[1])
        cand_b2 = clean_amount(nums[2])
        adj1 = clean_amount(nums[3])
        net = clean_amount(nums[4])
        
        # Test 1: cand_b1 is Basis, cand_b2 is Market Discount (WellsTrade order)
        # Net == p - cand_b1 + (cand_b2 + adj1)
        if abs(round(p - cand_b1 + (cand_b2 + adj1) - net, 2)) <= 0.02:
            return p, cand_b1, round(cand_b2 + adj1, 2), net, adj1
            
        # Test 2: cand_b2 is Basis, cand_b1 is Market Discount (Chase order)
        # Net == p - cand_b2 + (cand_b1 + adj1)
        if abs(round(p - cand_b2 + (cand_b1 + adj1) - net, 2)) <= 0.02:
            return p, cand_b2, round(cand_b1 + adj1, 2), net, adj1

        # Fallback to standard WellsTrade order
        return p, cand_b1, round(cand_b2 + adj1, 2), net, adj1
    else:
        # 4 numbers: proceeds, basis, adj, net
        basis = clean_amount(nums[1])
        adj = clean_amount(nums[2])
        net = clean_amount(nums[3])
        return p, basis, adj, net, adj


def parse_wellstrade_chase_text(text: str) -> Form8949Summary:
    """
    Parses WellsTrade and Chase Form 8949 summary tables.
    """
    summary = Form8949Summary()
    for line in text.splitlines():
        line_clean = line.strip()
        if re.search(r"^Box\s*A\b", line_clean, re.IGNORECASE) and "ordinary" not in line_clean.lower() and "subtotal" not in line_clean.lower():
            nums = re.findall(r"[-+]?\$?[0-9,]+\.[0-9]{2}", line_clean)
            p, b, adj, net, wash = parse_five_number_row(nums)
            summary.box_a.proceeds, summary.box_a.cost_basis, summary.box_a.adjustments, summary.box_a.net_gain_loss, summary.box_a.wash_sale_disallowed = p, b, adj, net, wash

        elif re.search(r"^Box\s*B\b", line_clean, re.IGNORECASE) and "ordinary" not in line_clean.lower() and "subtotal" not in line_clean.lower() and "or box e" not in line_clean.lower():
            nums = re.findall(r"[-+]?\$?[0-9,]+\.[0-9]{2}", line_clean)
            p, b, adj, net, wash = parse_five_number_row(nums)
            summary.box_b.proceeds, summary.box_b.cost_basis, summary.box_b.adjustments, summary.box_b.net_gain_loss, summary.box_b.wash_sale_disallowed = p, b, adj, net, wash

        elif re.search(r"^Box\s*D\b", line_clean, re.IGNORECASE) and "ordinary" not in line_clean.lower() and "subtotal" not in line_clean.lower():
            nums = re.findall(r"[-+]?\$?[0-9,]+\.[0-9]{2}", line_clean)
            p, b, adj, net, wash = parse_five_number_row(nums)
            summary.box_d.proceeds, summary.box_d.cost_basis, summary.box_d.adjustments, summary.box_d.net_gain_loss, summary.box_d.wash_sale_disallowed = p, b, adj, net, wash

        elif re.search(r"^Box\s*E\b", line_clean, re.IGNORECASE) and "ordinary" not in line_clean.lower() and "subtotal" not in line_clean.lower():
            nums = re.findall(r"[-+]?\$?[0-9,]+\.[0-9]{2}", line_clean)
            p, b, adj, net, wash = parse_five_number_row(nums)
            summary.box_e.proceeds, summary.box_e.cost_basis, summary.box_e.adjustments, summary.box_e.net_gain_loss, summary.box_e.wash_sale_disallowed = p, b, adj, net, wash

    return summary


def parse_schwab_text(text: str) -> Form8949Summary:
    """
    Parses Charles Schwab Form 1099 Composite summary lines.
    """
    summary = Form8949Summary()
    for line in text.splitlines():
        if "Total Short-Term" in line and "Cost basis is reported to the IRS" in line:
            nums = re.findall(r"[-+]?\$?[0-9,]+\.[0-9]{2}", line)
            if len(nums) >= 3:
                summary.box_a.proceeds = clean_amount(nums[0])
                summary.box_a.cost_basis = clean_amount(nums[1])
                summary.box_a.adjustments = 0.0
                summary.box_a.net_gain_loss = clean_amount(nums[2])
        elif "Total Long-Term" in line and "Cost basis is reported to the IRS" in line:
            nums = re.findall(r"[-+]?\$?[0-9,]+\.[0-9]{2}", line)
            if len(nums) >= 3:
                summary.box_d.proceeds = clean_amount(nums[0])
                summary.box_d.cost_basis = clean_amount(nums[1])
                summary.box_d.adjustments = 0.0
                summary.box_d.net_gain_loss = clean_amount(nums[2])
    return summary


def parse_fidelity_text(text: str) -> Form8949Summary:
    """
    Parses Fidelity 1099-B summary lines.
    """
    summary = Form8949Summary()
    m_totals = re.search(r"TOTALS\s+([-\d\.,]+)\s+([-\d\.,]+)", text)
    if m_totals:
        summary.box_a.proceeds = clean_amount(m_totals.group(1))
        summary.box_a.cost_basis = clean_amount(m_totals.group(2))

    m_gain = re.search(r"Box\s*A\s*Short-Term Realized Gain\s+([-\d\.,]+)", text)
    m_loss = re.search(r"Box\s*A\s*Short-Term Realized Loss\s+([-\d\.,]+)", text)
    if m_gain or m_loss:
        gain = clean_amount(m_gain.group(1)) if m_gain else 0.0
        loss = clean_amount(m_loss.group(1)) if m_loss else 0.0
        summary.box_a.net_gain_loss = round(gain + loss, 2)

    m_gain_b = re.search(r"Box\s*B\s*Short-Term Realized Gain\s+([-\d\.,]+)", text)
    m_loss_b = re.search(r"Box\s*B\s*Short-Term Realized Loss\s+([-\d\.,]+)", text)
    if m_gain_b or m_loss_b:
        gain = clean_amount(m_gain_b.group(1)) if m_gain_b else 0.0
        loss = clean_amount(m_loss_b.group(1)) if m_loss_b else 0.0
        summary.box_b.net_gain_loss = round(gain + loss, 2)
        summary.box_b.proceeds = round(gain + loss, 2)

    return summary


def parse_robinhood_int_and_div(div_txt: str, int_txt: str) -> Tuple[Form1099INT, Form1099DIV]:
    """Parses Form 1099-INT and Form 1099-DIV from Robinhood statement pages."""
    form_div = Form1099DIV()
    form_int = Form1099INT()

    for line in div_txt.splitlines():
        l = line.strip()
        m = re.search(r"1a-\s*Total\s+ordinary\s+dividends[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_div.box_1a_ordinary_dividends = clean_amount(m.group(1))
        m = re.search(r"1b-\s*Qualified\s+dividends\s+([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_div.box_1b_qualified_dividends = clean_amount(m.group(1))
        m = re.search(r"5-\s*Section\s+199A\s+dividends\s+([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_div.box_5_section_199a = clean_amount(m.group(1))

    for line in int_txt.splitlines():
        l = line.strip()
        m = re.search(r"1-\s*Interest\s+income[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_int.box_1_interest = clean_amount(m.group(1))
        m = re.search(r"3-\s*Interest\s+on\s+US\s+Savings[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_int.box_3_us_treasury = clean_amount(m.group(1))
        m = re.search(r"8-\s*Tax-exempt\s+interest[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_int.box_8_tax_exempt = clean_amount(m.group(1))

    return form_int, form_div


def parse_general_int_and_div(all_text: str, brand: str) -> Tuple[Form1099INT, Form1099DIV]:
    """
    Parses Form 1099-INT and Form 1099-DIV across all supported brokerage statement layouts.
    """
    form_int = Form1099INT()
    form_div = Form1099DIV()
    lines = [l.strip() for l in all_text.splitlines() if l.strip()]

    # 1. Apex Clearing Layout (BBAE, DSpac, Fennel, Firstrade, Public, Tradier, WeBull)
    for l in lines:
        m = re.search(r"^([-\d\.,]+)\s*1a-\s*Total\s+Ordinary\s+Dividends", l, re.IGNORECASE)
        if not m:
            m = re.search(r"1a-?\s*Total\s+Ordinary\s+Dividends[^\n\d]*?([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_div.box_1a_ordinary_dividends = clean_amount(m.group(1))

        m = re.search(r"^([-\d\.,]+)\s*1b-\s*Qualified\s+Dividends", l, re.IGNORECASE)
        if not m:
            m = re.search(r"1b-?\s*Qualified\s+Dividends[^\n\d]*?([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_div.box_1b_qualified_dividends = clean_amount(m.group(1))

        m = re.search(r"^([-\d\.,]+)\s*5-\s*Section\s+199A\s+Dividends", l, re.IGNORECASE)
        if not m:
            m = re.search(r"5-?\s*Section\s+199A\s+Dividends[^\n\d]*?([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_div.box_5_section_199a = clean_amount(m.group(1))

        m = re.search(r"^([-\d\.,]+)\s*1-\s*Interest\s+Income", l, re.IGNORECASE)
        if not m:
            m = re.search(r"1-?\s*Interest\s+Income[^\n\d]*?([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_int.box_1_interest = clean_amount(m.group(1))

        m = re.search(r"^([-\d\.,]+)\s*3-\s*Interest\s+on\s+US\s+Savings\s+Bonds", l, re.IGNORECASE)
        if not m:
            m = re.search(r"3-?\s*Interest\s+on\s+US\s+Savings[^\n\d]*?([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_int.box_3_us_treasury = clean_amount(m.group(1))

        m = re.search(r"^([-\d\.,]+)\s*8-\s*Tax-Exempt\s+Interest", l, re.IGNORECASE)
        if not m:
            m = re.search(r"8-?\s*Tax-Exempt\s+Interest[^\n\d]*?([-\d\.,]+)$", l, re.IGNORECASE)
        if m:
            form_int.box_8_tax_exempt = clean_amount(m.group(1))

    # 2. Vanguard Layout
    if brand == "Vanguard":
        for l in lines:
            m = re.search(r"1a-\s*Total\s+ordinary\s+dividends[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
            if m:
                form_div.box_1a_ordinary_dividends = clean_amount(m.group(1))
            m = re.search(r"1b-\s*Qualified\s+dividends\s+([-\d\.,]+)$", l, re.IGNORECASE)
            if m:
                form_div.box_1b_qualified_dividends = clean_amount(m.group(1))
            m = re.search(r"5-\s*Section\s+199A\s+dividends\s+([-\d\.,]+)$", l, re.IGNORECASE)
            if m:
                form_div.box_5_section_199a = clean_amount(m.group(1))
            m = re.search(r"1-\s*Interest\s+income[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
            if m:
                form_int.box_1_interest = clean_amount(m.group(1))
            m = re.search(r"3-\s*Interest\s+on\s+US\s+Savings[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
            if m:
                form_int.box_3_us_treasury = clean_amount(m.group(1))
            m = re.search(r"8-\s*Tax-exempt\s+interest[^\n]*?\s+([-\d\.,]+)$", l, re.IGNORECASE)
            if m:
                form_int.box_8_tax_exempt = clean_amount(m.group(1))

    # 3. WellsTrade Layout
    elif brand == "WellsTrade":
        for l in lines:
            m = re.search(r"1a\.\s*Total\s+Ordinary\s+Dividends\s+\$?([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_1a_ordinary_dividends = clean_amount(m.group(1))
            m = re.search(r"1b\.\s*Qualified\s+Dividends\s+\$?([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_1b_qualified_dividends = clean_amount(m.group(1))
            m = re.search(r"5\.\s*Section\s+199A\s+Dividends\s+\$?([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_5_section_199a = clean_amount(m.group(1))
            m = re.search(r"1\.\s*Interest\s+Income\s+\$?([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_1_interest = clean_amount(m.group(1))
            m = re.search(r"3\.\s*Interest\s+on\s+U\.S\.\s*Savings\s+Bonds[^\$]*?\$([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_3_us_treasury = clean_amount(m.group(1))
            m = re.search(r"8\.\s*Tax-Exempt\s*Interest\s+\$?([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_8_tax_exempt = clean_amount(m.group(1))

    # 4. Fidelity Layout
    elif brand == "Fidelity":
        for l in lines:
            m = re.search(r"1a\s+Total\s+Ordinary\s+Dividends\s*\.{3,}\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_1a_ordinary_dividends = clean_amount(m.group(1))
            m = re.search(r"1b\s+Qualified\s+Dividends\s*\.{3,}\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_1b_qualified_dividends = clean_amount(m.group(1))
            m = re.search(r"5\s+Section\s+199A\s+Dividends\s*\.{3,}\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_5_section_199a = clean_amount(m.group(1))
            m = re.search(r"\b1\s+Interest\s+Income\s*\.{3,}\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_1_interest = clean_amount(m.group(1))
            m = re.search(r"\b3\s+Interest\s+on\s+U\.S\.\s*Savings\s+Bonds[^\n\.]*\.{3,}\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_3_us_treasury = clean_amount(m.group(1))
            m = re.search(r"\b8\s+Tax-Exempt\s+Interest\s*\.{3,}\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_8_tax_exempt = clean_amount(m.group(1))

    # 5. Charles Schwab Layout
    elif brand == "Charles Schwab":
        for idx, l in enumerate(lines):
            if "1a Total Ordinary Dividends" in l:
                for offset in [1, 2, 3]:
                    if idx + offset < len(lines):
                        nxt = lines[idx + offset]
                        m = re.match(r"^\$\s*([-\d\.,]+)$", nxt.strip())
                        if m:
                            form_div.box_1a_ordinary_dividends = clean_amount(m.group(1))
                            break
            m = re.search(r"1b\s+Qualified\s+Dividends\s+\$\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_1b_qualified_dividends = clean_amount(m.group(1))
            m = re.search(r"5\s+Section\s+199A\s+Dividends\s+\$\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_5_section_199a = clean_amount(m.group(1))
            m = re.search(r"\b1\s+Interest\s+Income\s+\$\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_1_interest = clean_amount(m.group(1))
            m = re.search(r"\b3\s+Interest\s+on\s+U\.S\.\s+Savings[^\$]*\$\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_3_us_treasury = clean_amount(m.group(1))
            m = re.search(r"\b8\s+Tax-Exempt\s+Interest\s+\$\s*([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_8_tax_exempt = clean_amount(m.group(1))

    # 6. Chase Layout
    elif brand == "Chase":
        for l in lines:
            m = re.search(r"\$([-\d\.,]+)\s*Total\s*Ordinary\s*Dividends", l, re.IGNORECASE)
            if m:
                form_div.box_1a_ordinary_dividends = clean_amount(m.group(1))
            m = re.search(r"\$([-\d\.,]+)\s*Total\s*Qualified\s*Dividends", l, re.IGNORECASE)
            if m:
                form_div.box_1b_qualified_dividends = clean_amount(m.group(1))
            m = re.search(r"5\.\s*Section\s*199A\s*dividends[^\$]*\$([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_div.box_5_section_199a = clean_amount(m.group(1))
            m = re.search(r"1\.\s*Interest\s*income[^\$]*\$([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_1_interest = clean_amount(m.group(1))
            m = re.search(r"3\.\s*Interest\s*on\s*U\.S\.\s*Savings[^\$]*\$([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_3_us_treasury = clean_amount(m.group(1))
            m = re.search(r"8\.\s*Tax-exempt\s*interest[^\$]*\$([-\d\.,]+)", l, re.IGNORECASE)
            if m:
                form_int.box_8_tax_exempt = clean_amount(m.group(1))
            # Chase 1099-INT details table row: e.g. "1809900001 $18.51 $0.00 $0.00 ..."
            m = re.search(r"^[0-9]{8,14}\s+\$?([-\d\.,]+)\s+\$?([-\d\.,]+)\s+\$?([-\d\.,]+)", l)
            if m:
                if form_int.box_1_interest == 0.0:
                    form_int.box_1_interest = clean_amount(m.group(1))
                if form_int.box_3_us_treasury == 0.0:
                    form_int.box_3_us_treasury = clean_amount(m.group(3))

    # 7. SoFi Layout
    elif brand == "SoFi":
        for idx, l in enumerate(lines):
            if "FAQ PAGE: SOFI.COM" in l:
                for offset in [1, 2]:
                    if idx + offset < len(lines):
                        nxt = lines[idx + offset]
                        if re.match(r"^[0-9,]+\.[0-9]{2}$", nxt):
                            form_int.box_1_interest = clean_amount(nxt)
                            break
            m = re.search(r"Interest\s+income[^\$0-9]*\$?\s*([0-9,]+\.[0-9]{2})", l, re.IGNORECASE)
            if m and form_int.box_1_interest == 0.0:
                form_int.box_1_interest = clean_amount(m.group(1))

    # 8. Bank of America Layout
    elif brand == "Bank of America":
        for l in lines:
            m = re.search(r"(?:INTEREST\s+INCOME|TOTAL\s+INTEREST)\s+\$?([0-9,]+\.[0-9]{2})", l, re.IGNORECASE)
            if m:
                form_int.box_1_interest = clean_amount(m.group(1))
                break

    return form_int, form_div


def parse_1099_pdf(pdf_path: str) -> List[BrokerageAccountStatement]:
    """
    Parses a single 1099 PDF statement and returns one or more BrokerageAccountStatement objects.
    (Files with multiple consolidated sub-accounts like Robinhood return a statement per account).
    """
    filename = os.path.basename(pdf_path)
    reader = pypdf.PdfReader(pdf_path)
    cached = CachedPages(reader)
    num_pages = cached.num_pages

    # Extract text from first 5 pages for header detection
    header_text = "\n".join(cached.get_text(i) for i in range(min(5, num_pages))) + "\n"

    brand, clearing = detect_brokerage(header_text, filename)

    # Special handling for Robinhood multi-account PDF
    if brand == "Robinhood":
        statements = []
        for i in range(num_pages):
            txt = cached.get_text(i)
            if "SUMMARY OF PROCEEDS, GAINS & LOSSES" in txt:
                m_acc = re.search(r"Account\s+([A-Za-z0-9\-]+)", txt)
                acc_num = m_acc.group(1) if m_acc else detect_account_number(txt, filename)
                summary = parse_vanguard_robinhood_text(txt)

                int_txt = cached.get_text(i + 1) if i + 1 < num_pages else ""
                form_int, form_div = parse_robinhood_int_and_div(txt, int_txt)

                stmt = BrokerageAccountStatement(
                    brokerage_name=brand,
                    account_number=acc_num,
                    clearing_firm=clearing or "Robinhood Securities LLC",
                    source_file=filename,
                    form_8949=summary,
                    form_1099_int=form_int,
                    form_1099_div=form_div,
                    notes=[f"Robinhood sub-account statement from page {i+1}"],
                )
                statements.append(stmt)
        if statements:
            return statements

    # Standard single-account statement
    account_number = detect_account_number(header_text, filename)
    summary = Form8949Summary()

    # Determine layout type
    if clearing == "Apex Clearing Corporation" or any(brand == b for b in ["BBAE", "DSpac", "Fennel", "Firstrade", "Public", "Tradier", "Webull"]):
        target_idx = None
        for i in range(min(10, num_pages)):
            txt = cached.get_text(i)
            if "Summary Of Sale Proceeds" in txt or "Summary of Sale Proceeds" in txt:
                target_idx = i
                break
        summary = parse_apex_summary(pdf_path, target_page_idx=target_idx)
    elif brand == "Vanguard":
        for i in range(min(5, num_pages)):
            txt = cached.get_text(i)
            if "SUMMARY OF PROCEEDS, GAINS & LOSSES" in txt:
                summary = parse_vanguard_robinhood_text(txt)
                break
    elif brand in ("WellsTrade", "Chase"):
        for i in range(num_pages):
            txt = cached.get_text(i)
            if "SHORT-TERM GAINS" in txt or "SHORT TERM GAINS" in txt:
                summary = parse_wellstrade_chase_text(txt)
                if summary.box_a.proceeds > 0 or summary.box_b.proceeds > 0:
                    break
    elif brand == "Charles Schwab":
        for i in range(num_pages):
            txt = cached.get_text(i)
            if "Total Short-Term" in txt and "Cost basis is reported to the IRS" in txt:
                summary = parse_schwab_text(txt)
                if summary.box_a.proceeds > 0 or summary.box_a.net_gain_loss != 0:
                    break
    elif brand == "Fidelity":
        all_text = cached.all_text()
        summary = parse_fidelity_text(all_text)

    # Extract 1099-INT and 1099-DIV across all pages for this account
    all_doc_text = cached.all_text()
    form_int, form_div = parse_general_int_and_div(all_doc_text, brand)

    statement = BrokerageAccountStatement(
        brokerage_name=brand,
        account_number=account_number,
        clearing_firm=clearing,
        source_file=filename,
        form_8949=summary,
        form_1099_int=form_int,
        form_1099_div=form_div,
    )
    return [statement]


def _parse_pdf_worker(pdf_path: str) -> Tuple[str, List[BrokerageAccountStatement], Optional[str]]:
    """Worker function for parallel processing."""
    try:
        stmts = parse_1099_pdf(pdf_path)
        return (pdf_path, stmts, None)
    except Exception as e:
        return (pdf_path, [], str(e))


def parse_1099_pdf_batch(
    pdf_paths: List[str],
    max_workers: Optional[int] = None,
) -> List[Tuple[str, List[BrokerageAccountStatement], Optional[str]]]:
    """
    Parses multiple 1099 PDF files concurrently across CPU cores.
    Falls back gracefully to sequential execution for single files or in restricted environments.
    Returns list of (pdf_path, statements, error_message) preserving input order.
    """
    if not pdf_paths:
        return []

    # Sequential optimization for single files (avoids process spawn overhead)
    if len(pdf_paths) == 1:
        return [_parse_pdf_worker(pdf_paths[0])]

    try:
        cpu_cnt = os.cpu_count() or 4
        workers = min(len(pdf_paths), cpu_cnt if max_workers is None else max_workers)
        with ProcessPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(_parse_pdf_worker, pdf_paths))
    except Exception:
        # Graceful fallback to sequential processing
        return [_parse_pdf_worker(p) for p in pdf_paths]
