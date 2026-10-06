"""Automated end-to-end tests for 1099 PDF parsing and Form 8949 parity verification."""

import os
import pytest
from tax_tools.models import Form8949Box, Form8949Summary, BrokerageAccountStatement
from tax_tools.parser_1099 import (
    clean_amount,
    detect_brokerage,
    detect_account_number,
    parse_1099_pdf,
)
from tax_tools.validator import validate_box_parity, validate_statement_parity
from tax_tools.scanner import run_1099_pipeline, find_sample_directory

SAMPLE_DIR = "Sample Form 1099"


def test_clean_amount():
    assert clean_amount("$1,234.56") == 1234.56
    assert clean_amount("($50.25)") == -50.25
    assert clean_amount("-12.00") == -12.00
    assert clean_amount("--") == 0.0
    assert clean_amount("") == 0.0
    assert clean_amount("N/A") == 0.0


def test_parity_assertion():
    # Perfect parity: Proceeds 100 - Cost 80 + Adj 5 == Net 25
    valid, disc = validate_box_parity("Box A", proceeds=100.0, cost_basis=80.0, adjustments=5.0, net_gain_loss=25.0)
    assert valid is True
    assert disc == 0.0

    # Mismatch
    valid, disc = validate_box_parity("Box A", proceeds=100.0, cost_basis=80.0, adjustments=5.0, net_gain_loss=30.0)
    assert valid is False
    assert disc == -5.0


def test_brokerage_detection_text_first():
    # When brand is in text
    brand, clearing = detect_brokerage("Welcome to Charles Schwab & Co., Inc. tax statement", "unnamed.pdf")
    assert brand == "Charles Schwab"

    # When brand is absent from text, fallback to filename
    brand, clearing = detect_brokerage("Generic IRS Recipient Instructions", "SoFi Individual Brokerage 1 2025 Form 1099.pdf")
    assert brand == "SoFi"

    # Filename fallback for BBAE
    brand, clearing = detect_brokerage("Apex Clearing Corporation Redbridge Securities LLC", "BBAE Individual Brokerage 1 2025 Form 1099.pdf")
    assert brand == "BBAE"
    assert clearing == "Apex Clearing Corporation"


def test_account_number_masking():
    # Preserves masked format and excludes phone / OMB numbers
    assert detect_account_number("<BranchAccount>9AA10001", "file.pdf") == "9AA10001"
    assert detect_account_number("Account Number: 3900-0060", "file.pdf") == "3900-0060"
    assert detect_account_number("ORIGINAL:\n700-00513", "file.pdf") == "700-00513"
    assert detect_account_number("OMB No. 1545-0110 Account No. ZA9-711863", "file.pdf") == "ZA9-711863"


def test_account_number_rejects_recipient_name_structurally():
    """
    A recipient's name appearing after an "Account No." label must never be
    mistaken for an account number. This is decided on shape (an account
    number carries a digit or a mask character), not by recognising any
    particular person's name, so it holds for documents the parser was never
    developed against.
    """
    for name in ("JANE Q PUBLIC TOD", "RODNEY DANGERFIELD", "MARIE CURIE", "李 明"):
        assert detect_account_number(f"Account No.{name}\n", "file.pdf") != name

    # Cross-reference prose is rejected for the same reason.
    for prose in ("SEE BOX 1", "NO ACCOUNT", "TYPES EXHIBIT A"):
        assert detect_account_number(f"Account No. {prose}\n", "file.pdf") != prose

    # Institution location codes match the letter-digit-hyphen-4-digits shape
    # that Pattern 4 explicitly excludes.
    assert detect_account_number("CHASE 3415 VISION DRIVE OH4-7214", "file.pdf") != "OH4-7214"

    # A real number in the same document is still found.
    assert detect_account_number(
        "Account No. JANE Q PUBLIC TOD\nAccount Number: 700-00513", "file.pdf"
    ) == "700-00513"


def test_format_brokerage_display_name():
    from tax_tools.formatter import format_brokerage_display_name

    # Standard account numbers
    assert format_brokerage_display_name("BBAE", "9AA10001") == "BBAE -0001"
    assert format_brokerage_display_name("Robinhood", "12345678") == "Robinhood -5678"

    # Masked account numbers
    assert format_brokerage_display_name("BBAE", "***-3240") == "BBAE -3240"
    assert format_brokerage_display_name("Fidelity", "XXXX-7788") == "Fidelity -7788"
    assert format_brokerage_display_name("Chase", "***4321") == "Chase -4321"

    # Trailing hyphen prevention (e.g. account numbers ending with '-3240')
    assert format_brokerage_display_name("BBAE", "ACC-3240") == "BBAE -3240"
    assert format_brokerage_display_name("Broker", "-1234") == "Broker -1234"

    # Short account numbers (< 4 characters)
    assert format_brokerage_display_name("SoFi", "123") == "SoFi -123"
    assert format_brokerage_display_name("SoFi", "9") == "SoFi -9"
    assert format_brokerage_display_name("SoFi", "-42") == "SoFi -42"

    # Empty, whitespace, None account numbers
    assert format_brokerage_display_name("Charles Schwab", None) == "Charles Schwab"
    assert format_brokerage_display_name("Charles Schwab", "") == "Charles Schwab"
    assert format_brokerage_display_name("Charles Schwab", "   ") == "Charles Schwab"
    assert format_brokerage_display_name("Charles Schwab", "----") == "Charles Schwab"

    # Edge cases: None or empty brokerage name
    assert format_brokerage_display_name(None, "12345678") == "-5678"
    assert format_brokerage_display_name("", "12345678") == "-5678"
    assert format_brokerage_display_name(None, None) == ""
    assert format_brokerage_display_name("", "") == ""


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_sample_directory_discovery():
    sample_dir = find_sample_directory()
    assert sample_dir is not None
    assert os.path.isdir(sample_dir)


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_bbae_statement():
    pdf_path = os.path.join(SAMPLE_DIR, "BBAE Individual Brokerage 1 2025 Form 1099.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "BBAE"
    assert s.clearing_firm == "Apex Clearing Corporation"
    assert s.account_number == "9AA10001"
    assert s.form_8949.box_a.proceeds == 564.24
    assert s.form_8949.box_a.cost_basis == 137.93
    assert s.form_8949.box_a.net_gain_loss == 426.31
    assert s.parity_passed is True


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_fidelity_statement():
    pdf_path = os.path.join(SAMPLE_DIR, "Fidelity 2025 Individual Consolidated Form 1099.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "Fidelity"
    assert s.account_number == "ZA9-711863"
    assert s.form_8949.box_a.proceeds == 861.32
    assert s.form_8949.box_a.cost_basis == 446.88
    assert s.form_8949.box_a.net_gain_loss == 414.44
    assert s.parity_passed is True


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_chase_statement():
    pdf_path = os.path.join(SAMPLE_DIR, "x Chase Brokerage Account 2 Form 1099 2025.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "Chase"
    assert s.account_number == "700-00513"
    assert s.form_8949.box_a.proceeds == 39.66
    assert s.form_8949.box_a.cost_basis == 37.97
    assert s.form_8949.box_a.net_gain_loss == 1.69
    assert s.form_8949.box_b.proceeds == 1.95
    assert s.form_8949.box_b.cost_basis == 1.95
    assert s.parity_passed is True


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_all_sample_files_ingestion_and_parity():
    report = run_1099_pipeline(SAMPLE_DIR, output_excel="test_1099_output.xlsx")
    assert len(report.statements) >= 14
    for stmt in report.statements:
        errors = validate_statement_parity(stmt)
        assert len(errors) == 0, f"Parity failed for {stmt.brokerage_name} ({stmt.account_number}): {errors}"
        assert stmt.parity_passed is True
    assert report.all_parity_passed is True


def test_form_1099_int_model_and_aggregation():
    from tax_tools.models import Form1099INT
    int1 = Form1099INT(box_1_interest=100.50, box_3_us_treasury=45.25, box_8_tax_exempt=15.00)
    int2 = Form1099INT(box_1_interest=50.25, box_3_us_treasury=10.00, box_8_tax_exempt=5.00)
    combined = int1 + int2
    assert combined.box_1_interest == 150.75
    assert combined.box_3_us_treasury == 55.25
    assert combined.box_8_tax_exempt == 20.00
    assert combined.total_interest == 226.00


def test_form_1099_div_model_and_aggregation():
    from tax_tools.models import Form1099DIV
    div1 = Form1099DIV(box_1a_ordinary_dividends=200.00, box_1b_qualified_dividends=150.00, box_5_section_199a=25.00)
    div2 = Form1099DIV(box_1a_ordinary_dividends=100.00, box_1b_qualified_dividends=75.00, box_5_section_199a=10.00)
    combined = div1 + div2
    assert combined.box_1a_ordinary_dividends == 300.00
    assert combined.box_1b_qualified_dividends == 225.00
    assert combined.box_5_section_199a == 35.00


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_sofi_interest_extraction():
    pdf_path = os.path.join(SAMPLE_DIR, "SoFi Individual Brokerage 1 2025 Form 1099.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "SoFi"
    assert s.form_1099_int.box_1_interest == 56.00
    assert s.form_1099_int.box_3_us_treasury == 0.00
    assert s.form_1099_int.box_8_tax_exempt == 0.00


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_wellstrade_interest_and_dividends():
    pdf_path = os.path.join(SAMPLE_DIR, "WellsTrade 2025 Individual Form 1099.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "WellsTrade"
    assert s.form_1099_int.box_1_interest == 0.07
    assert s.form_1099_int.box_3_us_treasury == 0.00
    assert s.form_1099_div.box_1a_ordinary_dividends == 0.42
    assert s.form_1099_div.box_1b_qualified_dividends == 0.00


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_fidelity_dividends_extraction():
    pdf_path = os.path.join(SAMPLE_DIR, "Fidelity 2025 Individual Consolidated Form 1099.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.form_1099_div.box_1a_ordinary_dividends == 13.24
    assert s.form_1099_div.box_1b_qualified_dividends == 2.25
    assert s.clearing_firm == "National Financial Services LLC"


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_vanguard_dividends_extraction():
    pdf_path = os.path.join(SAMPLE_DIR, "Vanguard Individual Brokerage 1 2025 Form 1099.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "Vanguard"
    assert s.form_1099_div.box_1a_ordinary_dividends == 10.68
    assert s.form_1099_div.box_1b_qualified_dividends == 0.80
    assert s.clearing_firm == "Vanguard Marketing Corporation"


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_schwab_dividends_extraction():
    pdf_path = os.path.join(SAMPLE_DIR, "Schwab Form 1099 Composite and Year-End Summary - 2025.PDF")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "Charles Schwab"
    assert s.form_1099_div.box_1a_ordinary_dividends == 3.00
    assert s.form_1099_div.box_1b_qualified_dividends == 0.08
    assert s.clearing_firm == "Charles Schwab & Co., Inc."


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_chase_dividends_extraction():
    pdf_path = os.path.join(SAMPLE_DIR, "x Chase Brokerage Account 2 Form 1099 2025.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "Chase"
    assert s.form_1099_div.box_1a_ordinary_dividends == 3.44
    assert s.form_1099_div.box_1b_qualified_dividends == 3.44
    assert s.clearing_firm == "J.P. Morgan Securities LLC"


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_robinhood_multi_account_interest_and_dividends():
    pdf_path = os.path.join(SAMPLE_DIR, "Robinhood 2025 Consolidated Form 1099 ALL ACCOUNTS.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 10
    
    # Check the specific high-activity account 90000200
    acct_master = next((s for s in stmts if s.account_number == "90000200"), None)
    assert acct_master is not None
    assert acct_master.form_1099_int.box_1_interest == 54.79
    assert acct_master.form_1099_div.box_1a_ordinary_dividends == 98.37
    assert acct_master.form_1099_div.box_1b_qualified_dividends == 12.38

    # All Robinhood accounts should have Robinhood Securities LLC clearing firm
    for s in stmts:
        assert s.clearing_firm == "Robinhood Securities LLC"


def test_synthetic_ny_treasury_subtraction_isolation():
    """Validates that Box 3 Treasury interest is distinctly isolated from Box 1 and Box 8."""
    from tax_tools.parser_1099 import parse_general_int_and_div
    text = (
        "1a- Total Ordinary Dividends 50.00\n"
        "1b- Qualified Dividends 20.00\n"
        "5- Section 199A Dividends 10.00\n"
        "1- Interest Income 1000.00\n"
        "3- Interest on US Savings Bonds & Treasury Obligations 450.00\n"
        "8- Tax-Exempt Interest 75.00\n"
    )
    form_int, form_div = parse_general_int_and_div(text, "Fennel")
    assert form_int.box_1_interest == 1000.00
    assert form_int.box_3_us_treasury == 450.00
    assert form_int.box_8_tax_exempt == 75.00
    assert form_div.box_1a_ordinary_dividends == 50.00
    assert form_div.box_1b_qualified_dividends == 20.00
    assert form_div.box_5_section_199a == 10.00
    assert form_int.total_interest == 1525.00


def test_models_wash_sale_disallowed_parity():
    """Validates that wash sale disallowances aggregate properly without disrupting mathematical parity."""
    summary = Form8949Summary(
        box_a=Form8949Box("Box A", proceeds=15630.76, cost_basis=32811.25, adjustments=7912.35, net_gain_loss=-9268.14, wash_sale_disallowed=7912.35),
        box_d=Form8949Box("Box D", proceeds=262.63, cost_basis=1248.90, adjustments=527.57, net_gain_loss=-458.70, wash_sale_disallowed=527.57),
    )
    assert summary.all_parity_passed is True
    assert summary.box_a.is_parity_valid is True
    assert summary.box_d.is_parity_valid is True
    assert summary.short_term_total.wash_sale_disallowed == 7912.35
    assert summary.long_term_total.wash_sale_disallowed == 527.57
    assert summary.grand_total.wash_sale_disallowed == 8439.92
    assert summary.total_wash_sale_disallowed == 8439.92


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_robinhood_wash_sale_extraction():
    """Tests that Robinhood statement extracts wash sale loss disallowed amounts accurately."""
    pdf_path = os.path.join(SAMPLE_DIR, "Robinhood 2025 Consolidated Form 1099 ALL ACCOUNTS.pdf")
    stmts = parse_1099_pdf(pdf_path)
    acct_master = next((s for s in stmts if s.account_number == "90000200"), None)
    assert acct_master is not None
    assert acct_master.form_8949.box_a.wash_sale_disallowed == 7912.35
    assert acct_master.form_8949.box_d.wash_sale_disallowed == 527.57
    assert acct_master.form_8949.total_wash_sale_disallowed == 8439.92
    assert acct_master.parity_passed is True


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_firstrade_and_public_wash_sale_extraction():
    """Tests that Apex statements (Firstrade and Public) extract wash sale loss disallowed amounts."""
    # Firstrade
    ft_path = os.path.join(SAMPLE_DIR, "Firstrade 2025 Individual Form 1099.pdf")
    ft_stmts = parse_1099_pdf(ft_path)
    assert len(ft_stmts) == 1
    assert ft_stmts[0].form_8949.box_a.wash_sale_disallowed == 19.58
    assert ft_stmts[0].form_8949.total_wash_sale_disallowed == 19.58
    assert ft_stmts[0].parity_passed is True

    # Public
    pub_path = os.path.join(SAMPLE_DIR, "Public 2025 Indiv 1 Form 1099.pdf")
    pub_stmts = parse_1099_pdf(pub_path)
    assert len(pub_stmts) == 1
    assert pub_stmts[0].form_8949.box_a.wash_sale_disallowed == 0.43
    assert pub_stmts[0].form_8949.total_wash_sale_disallowed == 0.43
    assert pub_stmts[0].parity_passed is True


def test_cached_pages_memoization():
    """Validates that CachedPages calls extract_text at most once per page."""
    from unittest.mock import MagicMock
    from tax_tools.parser_1099 import CachedPages

    mock_page_0 = MagicMock()
    mock_page_0.extract_text.return_value = "Page 0 content"
    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "Page 1 content"

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page_0, mock_page_1]

    cached = CachedPages(mock_reader)
    assert cached.num_pages == 2

    # Multiple accesses to page 0
    t1 = cached.get_text(0)
    t2 = cached.get_text(0)
    assert t1 == "Page 0 content"
    assert t2 == "Page 0 content"
    assert mock_page_0.extract_text.call_count == 1

    # Access page 1 via all_text
    all_t = cached.all_text()
    assert "Page 0 content" in all_t
    assert "Page 1 content" in all_t
    assert mock_page_0.extract_text.call_count == 1
    assert mock_page_1.extract_text.call_count == 1


def test_parse_1099_pdf_batch_empty_and_fallback():
    """Validates edge cases for batch processing including empty list and single file."""
    from tax_tools.parser_1099 import parse_1099_pdf_batch

    assert parse_1099_pdf_batch([]) == []

    # Non-existent file error handling
    res = parse_1099_pdf_batch(["non_existent_file.pdf"])
    assert len(res) == 1
    path, stmts, err = res[0]
    assert path == "non_existent_file.pdf"
    assert stmts == []
    assert err is not None


@pytest.mark.skipif(not os.path.isdir(SAMPLE_DIR), reason="Sample 1099 directory not present")
def test_parse_1099_pdf_batch_multi_files():
    """Validates parallel batch parsing on multiple sample files."""
    from tax_tools.parser_1099 import parse_1099_pdf_batch

    f1 = os.path.join(SAMPLE_DIR, "BBAE Individual Brokerage 1 2025 Form 1099.pdf")
    f2 = os.path.join(SAMPLE_DIR, "x Chase Brokerage Account 2 Form 1099 2025.pdf")

    batch_res = parse_1099_pdf_batch([f1, f2])
    assert len(batch_res) == 2
    assert batch_res[0][0] == f1
    assert batch_res[0][2] is None
    assert len(batch_res[0][1]) == 1
    assert batch_res[0][1][0].brokerage_name == "BBAE"

    assert batch_res[1][0] == f2
    assert batch_res[1][2] is None
    assert len(batch_res[1][1]) == 1
    assert batch_res[1][1][0].brokerage_name == "Chase"


SAMPLE_INT_DIR = "Sample 1099-INT"


@pytest.mark.skipif(not os.path.isdir(SAMPLE_INT_DIR), reason="Sample 1099-INT directory not present")
def test_bofa_1099_int_extraction():
    """Validates Bank of America Form 1099-INT parsing."""
    pdf_path = os.path.join(SAMPLE_INT_DIR, "BofA Bank of America 2025 Form 1099-INT.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "Bank of America"
    assert s.account_number == "0487 000483109943591" or s.account_number.endswith("43591")
    assert s.form_1099_int.box_1_interest == 300.00
    assert s.form_1099_int.box_3_us_treasury == 0.00
    assert s.form_1099_int.box_8_tax_exempt == 0.00


@pytest.mark.skipif(not os.path.isdir(SAMPLE_INT_DIR), reason="Sample 1099-INT directory not present")
def test_chase_mortgage_1099_int_extraction():
    """Validates Chase Mortgage Form 1099-INT parsing across two statement formats."""
    # Format 1: Chase Mortgage 2025 Form 1099-INT.pdf
    pdf_path1 = os.path.join(SAMPLE_INT_DIR, "Chase Mortgage 2025 Form 1099-INT.pdf")
    stmts1 = parse_1099_pdf(pdf_path1)
    assert len(stmts1) == 1
    s1 = stmts1[0]
    assert s1.brokerage_name == "Chase"
    assert s1.account_number == "1809900001"
    assert s1.form_1099_int.box_1_interest == 18.51

    # Format 2: Chase Mortgage Account Form 1099-INT 2025.pdf
    pdf_path2 = os.path.join(SAMPLE_INT_DIR, "Chase Mortgage Account Form 1099-INT 2025.pdf")
    stmts2 = parse_1099_pdf(pdf_path2)
    assert len(stmts2) == 1
    s2 = stmts2[0]
    assert s2.brokerage_name == "Chase"
    assert s2.account_number == "1809900001"
    assert s2.form_1099_int.box_1_interest == 18.51


@pytest.mark.skipif(not os.path.isdir(SAMPLE_INT_DIR), reason="Sample 1099-INT directory not present")
def test_sofi_checking_1099_int_extraction():
    """Validates SoFi Bank checking account Form 1099-INT parsing."""
    pdf_path = os.path.join(SAMPLE_INT_DIR, "SoFi Checking 2025 Form 1099-INT.pdf")
    stmts = parse_1099_pdf(pdf_path)
    assert len(stmts) == 1
    s = stmts[0]
    assert s.brokerage_name == "SoFi"
    assert s.account_number == "36990516"
    assert s.form_1099_int.box_1_interest == 56.00


# =========================================================================
# Unit Tests for Duplicate 1099 Statement Detection and Rejection (Ticket 12)
# =========================================================================

def test_duplicate_statement_detection_and_rejection():
    """Verify that multiple statements for the same brokerage and account are deduplicated."""
    from tax_tools.models import (
        normalize_brokerage_name,
        normalize_account_number,
        AggregationReport,
        BrokerageAccountStatement,
        Form8949Box,
        Form8949Summary,
        Form1099INT,
    )

    stmt1 = BrokerageAccountStatement(
        brokerage_name="Robinhood",
        account_number="12345678",
        source_file="Robinhood_Statement_1.pdf",
        form_8949=Form8949Summary(
            box_a=Form8949Box("Box A", proceeds=1000.0, cost_basis=800.0, net_gain_loss=200.0)
        ),
        form_1099_int=Form1099INT(box_1_interest=50.0),
    )
    stmt2 = BrokerageAccountStatement(
        brokerage_name="Robinhood",
        account_number="12345678",
        source_file="Robinhood_Statement_Copy.pdf",
        form_8949=Form8949Summary(
            box_a=Form8949Box("Box A", proceeds=1000.0, cost_basis=800.0, net_gain_loss=200.0)
        ),
        form_1099_int=Form1099INT(box_1_interest=50.0),
    )

    report = AggregationReport(statements=[stmt1, stmt2])

    # 1. Duplicate statement rejected from active statements
    assert len(report.statements) == 1
    assert report.statements[0] is stmt1
    assert len(report.rejected_statements) == 1
    assert report.rejected_statements[0] is stmt2
    assert stmt2.is_duplicate is True

    # 2. Totals are not double-counted
    assert report.aggregate_8949.grand_total.proceeds == 1000.0
    assert report.aggregate_int.box_1_interest == 50.0

    # 3. User notes surface the rejection clearly
    assert any("Duplicate statement rejected: Robinhood" in n for n in report.notes)
    assert any("Robinhood_Statement_Copy.pdf" in n for n in report.notes)


def test_duplicate_normalization_case_and_whitespace():
    """Verify normalization handles case differences, extra whitespace, and hyphens."""
    from tax_tools.models import (
        normalize_brokerage_name,
        normalize_account_number,
        AggregationReport,
        BrokerageAccountStatement,
    )

    assert normalize_brokerage_name("  Charles   Schwab  ") == "charles schwab"
    assert normalize_brokerage_name("ROBINHOOD") == "robinhood"
    assert normalize_account_number(" 9AA-10001 ") == "9aa10001"
    assert normalize_account_number("9AA 10001") == "9aa10001"

    stmt1 = BrokerageAccountStatement(
        brokerage_name="Charles Schwab",
        account_number="123-4567",
        source_file="file1.pdf",
    )
    stmt2 = BrokerageAccountStatement(
        brokerage_name="  charles   schwab  ",
        account_number=" 1234567 ",
        source_file="file2.pdf",
    )

    report = AggregationReport(statements=[stmt1, stmt2])
    assert len(report.statements) == 1
    assert len(report.rejected_statements) == 1
    assert report.rejected_statements[0] is stmt2


def test_different_accounts_or_brokerages_not_rejected():
    """Verify statements with different accounts or different brokerages process normally."""
    from tax_tools.models import AggregationReport, BrokerageAccountStatement

    # Same brokerage, different accounts
    s1 = BrokerageAccountStatement(brokerage_name="Fidelity", account_number="Z1234")
    s2 = BrokerageAccountStatement(brokerage_name="Fidelity", account_number="Z5678")

    # Different brokerages, same account
    s3 = BrokerageAccountStatement(brokerage_name="Robinhood", account_number="12345")
    s4 = BrokerageAccountStatement(brokerage_name="Webull", account_number="12345")

    report = AggregationReport(statements=[s1, s2, s3, s4])
    assert len(report.statements) == 4
    assert len(report.rejected_statements) == 0


def test_missing_account_numbers_not_rejected_as_duplicate():
    """Verify statements with missing/blank account numbers do not collide falsely as duplicates."""
    from tax_tools.models import AggregationReport, BrokerageAccountStatement

    s1 = BrokerageAccountStatement(brokerage_name="Charles Schwab", account_number="")
    s2 = BrokerageAccountStatement(brokerage_name="Charles Schwab", account_number="")

    report = AggregationReport(statements=[s1, s2])
    assert len(report.statements) == 2
    assert len(report.rejected_statements) == 0




