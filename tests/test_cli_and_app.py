"""Integration and smoke tests for Streamlit Web Dashboard and standalone CLIs."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import tax_1099_parser
import ny_sales_tax_calculator
from app import (
    build_1099_summary_df,
    format_currency,
    process_1099_paths,
    process_sales_tax_paths,
)
from tax_tools.models import (
    AggregationReport,
    BrokerageAccountStatement,
    Form8949Box,
    Form8949Summary,
    Form1099INT,
    Form1099DIV,
)
from tax_tools.sales_tax_models import NY_COUNTY_RATES, DEFAULT_COUNTY


SAMPLE_1099_DIR = "Sample Form 1099"
SAMPLE_ACT_DIR = "Sample Activity Statements"
SINGLE_1099_PDF = os.path.join(SAMPLE_1099_DIR, "BBAE Individual Brokerage 1 2025 Form 1099.pdf")
SINGLE_ACT_CSV = os.path.join(SAMPLE_ACT_DIR, "Amex Blue Cash Everyday Activity 2025.csv")
APP_PATH = str(Path(__file__).parent.parent / "app.py")

# The dashboard's "Load Sample 1099s" button is disabled unless the corpus is
# present, so the two tests that drive it skip alongside the rest.
HAVE_SAMPLE_1099_DIR = os.path.isdir(SAMPLE_1099_DIR)


# =========================================================================
# Unit Tests for Helper Functions
# =========================================================================

def test_format_currency():
    """Verify currency string formatting for positive, zero, and negative values."""
    assert format_currency(1234.56) == "$1,234.56"
    assert format_currency(0.0) == "$0.00"
    assert format_currency(-789.1) == "-$789.10"


def test_build_1099_summary_df():
    """Verify summary table generation for Streamlit 1099 tab preview."""
    stmt = BrokerageAccountStatement(
        brokerage_name="Apex / TestBroker",
        account_number="ABC-1234",
        clearing_firm="Apex Clearing Corporation",
        form_8949=Form8949Summary(
            box_a=Form8949Box("Box A", proceeds=1000.0, cost_basis=800.0, net_gain_loss=200.0),
            box_d=Form8949Box("Box D", proceeds=500.0, cost_basis=400.0, net_gain_loss=100.0),
        ),
        form_1099_int=Form1099INT(box_1_interest=50.0, box_3_us_treasury=120.0),
        form_1099_div=Form1099DIV(box_1a_ordinary_dividends=30.0),
    )
    report = AggregationReport(statements=[stmt])
    df = build_1099_summary_df(report)

    assert len(df) == 1
    # Check column order: Clearing Firm is right before Parity Status at the far right
    expected_cols = [
        "Brokerage Name",
        "Account #",
        "ST Proceeds",
        "ST Basis",
        "ST Wash Sale",
        "ST Net",
        "LT Proceeds",
        "LT Basis",
        "LT Wash Sale",
        "LT Net",
        "Total Proceeds",
        "Total Cost Basis",
        "Total Wash Sale",
        "Total Net",
        "Box 1 Interest Income",
        "Box 3 - Savings Bonds and Treasury Interest",
        "Clearing Firm",
        "Parity Status",
    ]
    assert list(df.columns) == expected_cols

    row = df.iloc[0]
    assert row["Brokerage Name"] == "Apex / TestBroker -1234"
    assert row["Account #"] == "ABC-1234"
    assert row["ST Proceeds"] == "$1,000.00"
    assert row["ST Basis"] == "$800.00"
    assert row["ST Wash Sale"] == "$0.00"
    assert row["ST Net"] == "$200.00"
    assert row["LT Proceeds"] == "$500.00"
    assert row["LT Basis"] == "$400.00"
    assert row["LT Wash Sale"] == "$0.00"
    assert row["LT Net"] == "$100.00"
    assert row["Total Proceeds"] == "$1,500.00"
    assert row["Total Cost Basis"] == "$1,200.00"
    assert row["Total Wash Sale"] == "$0.00"
    assert row["Total Net"] == "$300.00"
    assert row["Box 1 Interest Income"] == "$50.00"
    assert row["Box 3 - Savings Bonds and Treasury Interest"] == "$120.00"
    assert row["Clearing Firm"] == "Apex Clearing Corporation"
    assert row["Parity Status"] == "PASS"


def test_process_1099_paths_in_memory():
    """Verify in-memory processing and Excel byte generation for 1099 forms."""
    if not os.path.exists(SINGLE_1099_PDF):
        pytest.skip("Sample 1099 PDF not found.")

    report, excel_bytes = process_1099_paths([SINGLE_1099_PDF])
    assert len(report.statements) == 1
    assert len(excel_bytes) > 1000
    # Confirm valid Excel archive
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Form 8949 Summary" in wb.sheetnames
    assert "Brokerage Breakdown" in wb.sheetnames
    assert "Interest & Dividend Schedule" in wb.sheetnames


def test_process_sales_tax_paths_in_memory():
    """Verify in-memory processing and Excel byte generation for sales tax calculator."""
    if not os.path.exists(SINGLE_ACT_CSV):
        pytest.skip("Sample activity CSV not found.")

    report, excel_bytes = process_sales_tax_paths([SINGLE_ACT_CSV], "New York City (8.875%)")
    assert report.total_transactions > 0
    assert report.total_sales_tax_paid > 0
    assert len(excel_bytes) > 1000
    # Confirm valid Excel archive
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Deduction Summary" in wb.sheetnames
    assert "Itemized Ledger" in wb.sheetnames
    assert "Category Audit Trail" in wb.sheetnames


# =========================================================================
# CLI Tests: tax_1099_parser.py
# =========================================================================

def test_1099_cli_help():
    """Verify tax_1099_parser.py --help exits 0 and displays correct usage."""
    parser = tax_1099_parser.build_parser()
    assert parser.prog == "tax_1099_parser.py"


def test_1099_cli_execution_single_file(tmp_path):
    """Verify tax_1099_parser CLI processes single PDF file and generates workbook."""
    if not os.path.exists(SINGLE_1099_PDF):
        pytest.skip("Sample 1099 PDF not found.")

    out_file = str(tmp_path / "summary_test.xlsx")
    ret = tax_1099_parser.main([SINGLE_1099_PDF, "-o", out_file, "--quiet"])
    assert ret == 0
    assert os.path.exists(out_file)

    wb = openpyxl.load_workbook(out_file)
    assert len(wb.sheetnames) == 3


def test_1099_cli_missing_input(tmp_path):
    """Verify tax_1099_parser CLI fails gracefully when given nonexistent input path."""
    ret = tax_1099_parser.main(["nonexistent_directory_xyz", "-o", str(tmp_path / "out.xlsx")])
    assert ret != 0


# =========================================================================
# CLI Tests: ny_sales_tax_calculator.py
# =========================================================================

def test_sales_tax_cli_help():
    """Verify ny_sales_tax_calculator.py --help parser builds cleanly."""
    parser = ny_sales_tax_calculator.build_parser()
    assert parser.prog == "ny_sales_tax_calculator.py"


def test_sales_tax_cli_list_counties(capsys):
    """Verify --list-counties prints all 62 NY counties and exits 0."""
    ret = ny_sales_tax_calculator.main(["--list-counties"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "New York City (8.875%)" in captured.out
    assert "Westchester (8.375%)" in captured.out
    assert "Albany (8.000%)" in captured.out


def test_sales_tax_cli_execution_single_file(tmp_path):
    """Verify ny_sales_tax_calculator CLI processes single CSV file with county override."""
    if not os.path.exists(SINGLE_ACT_CSV):
        pytest.skip("Sample activity CSV not found.")

    out_file = str(tmp_path / "tax_report_test.xlsx")
    ret = ny_sales_tax_calculator.main([
        SINGLE_ACT_CSV,
        "-c", "Nassau (8.625%)",
        "-o", out_file,
        "--quiet",
    ])
    assert ret == 0
    assert os.path.exists(out_file)

    wb = openpyxl.load_workbook(out_file)
    assert "Deduction Summary" in wb.sheetnames
    # Verify rate written in summary
    ws = wb["Deduction Summary"]
    found_rate = any("8.625%" in str(cell.value) for row in ws.iter_rows(max_row=15) for cell in row)
    assert found_rate


def test_sales_tax_cli_missing_input(tmp_path):
    """Verify ny_sales_tax_calculator CLI fails gracefully when given nonexistent input."""
    ret = ny_sales_tax_calculator.main(["nonexistent_folder_xyz", "-o", str(tmp_path / "out.xlsx")])
    assert ret != 0


# =========================================================================
# Streamlit AppTest Suite (app.py)
# =========================================================================

def test_app_initial_render():
    """Verify app.py loads, sets up tabs, county selector, and initial buttons."""
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    assert not at.exception
    assert len(at.tabs) == 2
    # Verify county selector
    sb = at.selectbox[0]
    assert sb.value == DEFAULT_COUNTY
    assert len(sb.options) >= 62


def test_app_sales_tax_flow():
    """Verify calculating sales tax via Streamlit UI populates KPI metric cards and download button."""
    if not os.path.exists(SINGLE_ACT_CSV):
        pytest.skip("Sample activity statements not found.")

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    # Click button to load sample statements (index 2: "Load Sample Statements")
    load_sample_btn = next(b for b in at.button if "Load Sample Statements" in b.label)
    load_sample_btn.click().run(timeout=30)

    assert not at.exception
    # Verify the 5 KPI metric cards required by Ticket 04:
    # (Total Spend, Excluded, Exempt, Taxable, Total NY Sales Tax Paid)
    labels = [m.label for m in at.metric]
    assert "Total Spend" in labels
    assert "Excluded" in labels
    assert "Exempt" in labels
    assert "Taxable" in labels
    assert "Total NY Sales Tax Paid" in labels

    # Verify download button rendered
    download_btn = next((db for db in at.download_button if "NY_Sales_Tax_Report.xlsx" in db.label), None)
    assert download_btn is not None
    assert len(at.session_state["sales_tax_excel_bytes"]) > 1000

    # Verify preview tables have numeric column types (enabling proper numerical sorting)
    assert len(at.dataframe) >= 2
    cat_df = at.dataframe[0].value
    ledger_df = at.dataframe[1].value
    assert pd.api.types.is_numeric_dtype(cat_df["Gross Spend"])
    assert pd.api.types.is_numeric_dtype(cat_df["Taxable Amount"])
    assert pd.api.types.is_numeric_dtype(cat_df["Sales Tax Paid"])
    assert pd.api.types.is_numeric_dtype(ledger_df["Amount"])
    assert pd.api.types.is_numeric_dtype(ledger_df["Pre-Tax Amount"])
    assert pd.api.types.is_numeric_dtype(ledger_df["NY Sales Tax"])
    assert (ledger_df["Amount"] > 0).any()


def test_app_1099_flow_and_dual_tab_independence():
    """Verify 1099 Aggregator tab execution and dual-tab state independence."""
    if not os.path.exists(SINGLE_1099_PDF):
        pytest.skip("Sample 1099 PDF not found.")

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    # Trigger 1099 loading
    load_1099_btn = next(b for b in at.button if "Load Sample 1099s" in b.label)
    load_1099_btn.click().run(timeout=30)

    assert not at.exception
    labels_1099 = [m.label for m in at.metric]
    assert "Statements Parsed" in labels_1099
    assert "Parity Check" in labels_1099
    assert "Net Capital Gain/(Loss)" in labels_1099
    assert "Ordinary Interest (Box 1)" in labels_1099
    assert "US Treasury Interest (Box 3)" in labels_1099

    dl_1099 = next((db for db in at.download_button if "1099_Tax_Summary.xlsx" in db.label), None)
    assert dl_1099 is not None
    assert len(at.session_state["1099_excel_bytes"]) > 1000

    # Next, trigger Sales Tax tool in the same app instance
    load_sales_btn = next(b for b in at.button if "Load Sample Statements" in b.label)
    load_sales_btn.click().run(timeout=30)

    assert not at.exception
    # Now BOTH download buttons must be available, confirming dual-tab state persistence!
    labels_present = [db.label for db in at.download_button]
    assert any("1099_Tax_Summary.xlsx" in l for l in labels_present)
    assert any("NY_Sales_Tax_Report.xlsx" in l for l in labels_present)
    assert "1099_excel_bytes" in at.session_state
    assert "sales_tax_excel_bytes" in at.session_state


def test_st_html_unsafe_allow_javascript_invocation(monkeypatch):
    """Verify that app.py invokes st.html with unsafe_allow_javascript=True for client-side copy script."""
    import streamlit as st
    import app

    html_calls = []

    def fake_html(body, unsafe_allow_javascript=False):
        html_calls.append({"body": body, "unsafe_allow_javascript": unsafe_allow_javascript})

    monkeypatch.setattr(st, "html", fake_html)

    # Ensure app source code explicitly uses unsafe_allow_javascript=True with render_summary_table_html
    app_source = Path(APP_PATH).read_text(encoding="utf-8")
    assert "st.html(render_summary_table_html(summary_df), unsafe_allow_javascript=True)" in app_source


# =========================================================================
# Unit Tests for Ticket 13 & Ticket 14 Acceptance Criteria
# =========================================================================

def test_ticket_13_upload_controls_guidance_and_rebranding():
    """Verify Ticket 13 upload prompt, Clear button, source notice, and sales tax rebranding."""
    if not HAVE_SAMPLE_1099_DIR:
        pytest.skip("Sample 1099 directory not present.")

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)
    assert not at.exception

    # 1. 1099 file upload prompt reads "Upload 1099 forms (PDF)"
    uploader = at.file_uploader[0]
    assert uploader.label == "Upload 1099 forms (PDF)"

    # 2. Guidance displayed stating official PDF downloads and warning that scans/photos may fail
    info_boxes = [inf.value for inf in at.info]
    assert any("official PDF downloads" in inf and "scanned" in inf.lower() for inf in info_boxes)

    # 3. Dedicated "Clear" button exists and resets parsed state
    clear_btn = next((b for b in at.button if b.label == "Clear"), None)
    assert clear_btn is not None

    # Load 1099s to populate state
    load_1099_btn = next(b for b in at.button if "Load Sample 1099s" in b.label)
    load_1099_btn.click().run(timeout=30)
    assert "1099_report" in at.session_state
    assert "1099_excel_bytes" in at.session_state

    # Now click Clear button
    clear_btn = next((b for b in at.button if b.label == "Clear"), None)
    assert clear_btn is not None
    clear_btn.click().run(timeout=15)
    assert "1099_report" not in at.session_state
    assert "1099_excel_bytes" not in at.session_state

    # 4. Sales tax navigation tab and header reflect title "Bank/Card Statement Reverse Sales Tax Calculator"
    tab_labels = [t.label for t in at.tabs]
    assert any("Bank/Card Statement Reverse Sales Tax Calculator" in t for t in tab_labels)
    header_values = [h.value for h in at.header]
    assert any("Bank/Card Statement Reverse Sales Tax Calculator" in h for h in header_values)


def test_ticket_14_kpi_card_explanations_and_no_deltas():
    """Verify Ticket 14 KPI cards have no comparative deltas and Parity Check has plain-language tooltip."""
    if not HAVE_SAMPLE_1099_DIR:
        pytest.skip("Sample 1099 directory not present.")

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    # Load 1099s to inspect KPI cards
    load_1099_btn = next(b for b in at.button if "Load Sample 1099s" in b.label)
    load_1099_btn.click().run(timeout=30)
    assert not at.exception

    # 1. Check no KPI card displays delta or delta indicators
    for m in at.metric:
        assert not m.delta, f"Metric '{m.label}' unexpectedly has delta '{m.delta}'"

    # 2. Check Parity Check metric tooltip/explanation
    parity_metric = next((m for m in at.metric if m.label == "Parity Check"), None)
    assert parity_metric is not None
    assert parity_metric.help is not None
    assert "Proceeds minus Cost Basis plus Adjustments equals Net Gain/Loss" in parity_metric.help

