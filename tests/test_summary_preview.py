"""Unit tests for summary preview table formatting and clipboard sanitization."""

import pytest
import pandas as pd

from tax_tools.formatter import (
    format_brokerage_display_name,
    sanitize_for_clipboard,
    render_summary_table_html,
)
import tax_tools.formatter as formatter_module
from tax_tools.models import (
    AggregationReport,
    BrokerageAccountStatement,
    Form8949Box,
    Form8949Summary,
    Form1099INT,
    Form1099DIV,
)
from app import build_1099_summary_df


# =========================================================================
# Unit Tests for format_brokerage_display_name
# =========================================================================

def test_format_brokerage_display_name_standard_masked():
    """Verify standard masked account suffix formatting."""
    assert format_brokerage_display_name("BBAE", "***-3240") == "BBAE -3240"
    assert format_brokerage_display_name("Robinhood", "12345678") == "Robinhood -5678"
    assert format_brokerage_display_name("Fidelity", "Z12345678") == "Fidelity -5678"


def test_format_brokerage_display_name_short_and_edge_cases():
    """Verify edge cases: short account, empty, None, and whitespace."""
    assert format_brokerage_display_name("Webull", "12") == "Webull -12"
    assert format_brokerage_display_name("Vanguard", "") == "Vanguard"
    assert format_brokerage_display_name("Schwab", None) == "Schwab"
    assert format_brokerage_display_name("", "***-9999") == "-9999"
    assert format_brokerage_display_name(None, "***-9999") == "-9999"
    assert format_brokerage_display_name(None, None) == ""


# =========================================================================
# Unit Tests for sanitize_for_clipboard (Ticket 08)
# =========================================================================

def test_sanitize_for_clipboard_positive_currency():
    """Verify positive currency values stripped of dollar signs and commas."""
    assert sanitize_for_clipboard("$12,345.67") == "12345.67"
    assert sanitize_for_clipboard("$1,000.00") == "1000.00"
    assert sanitize_for_clipboard("$0.00") == "0.00"
    assert sanitize_for_clipboard("$50.25") == "50.25"


def test_sanitize_for_clipboard_negative_currency():
    """Verify negative currency formats cleanly retain negative sign without dollar signs."""
    assert sanitize_for_clipboard("-$500.00") == "-500.00"
    assert sanitize_for_clipboard("- $500.00") == "-500.00"
    assert sanitize_for_clipboard("$-500.00") == "-500.00"
    assert sanitize_for_clipboard("($500.00)") == "-500.00"
    assert sanitize_for_clipboard("-$12,345.67") == "-12345.67"


def test_sanitize_for_clipboard_zero_formats():
    """Verify zero currency formats."""
    assert sanitize_for_clipboard("$0.00") == "0.00"
    assert sanitize_for_clipboard("0.00") == "0.00"
    assert sanitize_for_clipboard(0) == "0"
    assert sanitize_for_clipboard(0.0) == "0.00"


def test_sanitize_for_clipboard_numeric_types():
    """Verify raw float and int handling."""
    assert sanitize_for_clipboard(1234.56) == "1234.56"
    assert sanitize_for_clipboard(-789.1) == "-789.10"
    assert sanitize_for_clipboard(100) == "100"


def test_sanitize_for_clipboard_non_currency_strings():
    """Verify text columns (Brokerage Name, Account #) preserve raw text."""
    assert sanitize_for_clipboard("BBAE -3240") == "BBAE -3240"
    assert sanitize_for_clipboard("***-3240") == "***-3240"
    assert sanitize_for_clipboard("Robinhood") == "Robinhood"
    assert sanitize_for_clipboard("Apex Clearing Corporation") == "Apex Clearing Corporation"
    assert sanitize_for_clipboard("PASS") == "PASS"


def test_sanitize_for_clipboard_empty_and_none():
    """Verify None and empty strings return empty string."""
    assert sanitize_for_clipboard(None) == ""
    assert sanitize_for_clipboard("") == ""
    assert sanitize_for_clipboard("   ") == ""


def test_sanitize_for_clipboard_nan():
    """Verify pandas NaN yields an empty string rather than the literal text 'nan'.

    An absent dataframe cell arrives as float NaN, and f"{nan:.2f}" renders as
    'nan'. Left unchecked that string becomes copyable, so clicking a blank cell
    pastes "nan" into tax filing software.
    """
    assert sanitize_for_clipboard(float("nan")) == ""
    assert sanitize_for_clipboard(pd.NA) == ""
    assert sanitize_for_clipboard(pd.NaT) == ""
    # Infinities are legitimate floats and must not be swallowed.
    assert sanitize_for_clipboard(float("inf")) == "inf"


def test_render_summary_table_html_omits_copy_payload_for_blank_cells():
    """Blank cells render empty and carry no data-copy, so they are not clickable."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "Apex",
            "Account #": "",
            "ST Proceeds": "$0.00",
        }
    ])
    html_output = render_summary_table_html(df)

    # No literal 'nan' leaks into the rendered table.
    assert ">nan<" not in html_output
    assert "nan" not in html_output
    # Zero still carries a payload; blank does not.
    assert 'data-copy="0.00"' in html_output
    assert '<span class="cell-text"></span>' in html_output


# =========================================================================
# Tests for Target Columns and HTML Table Generation
# =========================================================================

def test_target_copy_columns_constant_removed():
    """Click-to-copy now covers every data cell, so the column allow-list is gone."""
    import tax_tools

    assert not hasattr(tax_tools, "TARGET_COPY_COLUMNS")
    assert not hasattr(formatter_module, "TARGET_COPY_COLUMNS")


def test_render_summary_table_html_contains_click_to_copy_payloads():
    """Verify rendered HTML carries sanitized copy payloads on every data cell."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "BBAE -3240",
            "Account #": "***-3240",
            "ST Proceeds": "$1,000.00",
            "ST Basis": "$800.00",
            "ST Wash Sale": "$25.00",
            "ST Net": "$225.00",
            "LT Proceeds": "$500.00",
            "LT Basis": "$400.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$100.00",
            "Total Proceeds": "$1,500.00",
            "Total Cost Basis": "$1,200.00",
            "Total Wash Sale": "$25.00",
            "Total Net Gain/(Loss)": "$325.00",
            "Ordinary Interest": "$50.00",
            "US Treasury Interest": "$120.00",
            "Clearing Firm": "Apex",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # Check for navigator.clipboard interaction
    assert "navigator.clipboard.writeText" in html_output
    # Check for sanitized copy payloads in HTML
    assert 'data-copy="BBAE -3240"' in html_output
    assert 'data-copy="***-3240"' in html_output
    # Ensure currency values are sanitized in the copy data attributes!
    assert 'data-copy="1000.00"' in html_output
    assert 'data-copy="800.00"' in html_output
    assert 'data-copy="25.00"' in html_output
    assert 'data-copy="500.00"' in html_output
    assert 'data-copy="400.00"' in html_output
    assert 'data-copy="0.00"' in html_output

    # Every column is now copyable, including ones outside the old allow-list.
    assert 'data-copy="1500.00"' in html_output
    assert 'data-copy="Apex"' in html_output
    assert 'data-copy="PASS"' in html_output

    # Dedicated copy buttons are gone.
    assert "copy-btn" not in html_output

    # Check for visual feedback styling
    assert "copied" in html_output


# =========================================================================
# Unit Tests for Section Dividers and Semantic Group Inactive Shading (Ticket 09)
# =========================================================================

def test_is_val_zero():
    """Verify is_val_zero correctly identifies zero vs non-zero values across formats."""
    from tax_tools.formatter import is_val_zero

    # Zero values
    assert is_val_zero(0) is True
    assert is_val_zero(0.0) is True
    assert is_val_zero("$0.00") is True
    assert is_val_zero("0.00") is True
    assert is_val_zero("-$0.00") is True
    assert is_val_zero("($0.00)") is True
    assert is_val_zero("-") is True
    assert is_val_zero("") is True
    assert is_val_zero(None) is True

    # Non-zero values
    assert is_val_zero(100.0) is False
    assert is_val_zero(-50.0) is False
    assert is_val_zero("$1,000.00") is False
    assert is_val_zero("-$25.50") is False
    assert is_val_zero("($500.00)") is False
    assert is_val_zero("$0.01") is False


def test_is_semantic_group_zero():
    """Verify is_semantic_group_zero accurately checks all fields in a semantic group."""
    from tax_tools.formatter import is_semantic_group_zero, SEMANTIC_GROUPS

    st_cols = SEMANTIC_GROUPS["Short-Term"]
    lt_cols = SEMANTIC_GROUPS["Long-Term"]
    int_cols = SEMANTIC_GROUPS["Interest"]

    # All-zero Short-Term row
    row_all_zero_st = pd.Series({
        "ST Proceeds": "$0.00",
        "ST Basis": "$0.00",
        "ST Wash Sale": "$0.00",
        "ST Net": "$0.00",
        "LT Proceeds": "$500.00",
        "LT Basis": "$400.00",
        "LT Wash Sale": "$0.00",
        "LT Net": "$100.00",
        "Ordinary Interest": "$0.00",
        "US Treasury Interest": "$0.00",
    })

    assert is_semantic_group_zero(row_all_zero_st, st_cols) is True
    assert is_semantic_group_zero(row_all_zero_st, lt_cols) is False
    assert is_semantic_group_zero(row_all_zero_st, int_cols) is True

    # Any non-zero in group makes group active (not zero)
    row_one_nonzero_st = pd.Series({
        "ST Proceeds": "$0.00",
        "ST Basis": "$0.00",
        "ST Wash Sale": "$15.00",  # wash sale only
        "ST Net": "$0.00",
    })
    assert is_semantic_group_zero(row_one_nonzero_st, st_cols) is False

    row_loss_nonzero_st = pd.Series({
        "ST Proceeds": "$100.00",
        "ST Basis": "$200.00",
        "ST Wash Sale": "$0.00",
        "ST Net": "-$100.00",
    })
    assert is_semantic_group_zero(row_loss_nonzero_st, st_cols) is False

    # Interest group: either non-zero makes group active
    row_interest = pd.Series({
        "Ordinary Interest": "$0.00",
        "US Treasury Interest": "$45.20",
    })
    assert is_semantic_group_zero(row_interest, int_cols) is False


def test_render_summary_table_html_section_dividers():
    """Verify that vertical dividers preceding ST Proceeds and LT Proceeds are rendered in headers and data rows."""
    from tax_tools.formatter import DIVIDER_COLUMNS

    assert "ST Proceeds" in DIVIDER_COLUMNS
    assert "LT Proceeds" in DIVIDER_COLUMNS

    df = pd.DataFrame([
        {
            "Brokerage Name": "BBAE -3240",
            "Account #": "***-3240",
            "ST Proceeds": "$1,000.00",
            "ST Basis": "$800.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$200.00",
            "LT Proceeds": "$500.00",
            "LT Basis": "$400.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$100.00",
            "Total Proceeds": "$1,500.00",
            "Total Cost Basis": "$1,200.00",
            "Total Wash Sale": "$0.00",
            "Total Net Gain/(Loss)": "$300.00",
            "Ordinary Interest": "$0.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "Apex",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # Header check: th elements for ST Proceeds and LT Proceeds have section-divider class
    assert 'class="sortable section-divider"' in html_output
    assert 'ST Proceeds' in html_output
    assert 'LT Proceeds' in html_output

    # CSS check: section-divider defines thickened border-left
    assert ".summary-table th.section-divider" in html_output
    assert ".summary-table td.section-divider" in html_output
    assert "border-left: 3px solid" in html_output


def test_render_summary_table_html_semantic_group_inactive_shading():
    """Verify inactive groups (all zeros) receive .group-inactive and #DEE2E6 styling, while active groups stay unshaded."""
    df = pd.DataFrame([
        {
            # Row 0: ST is all zero (should be inactive), LT is active, Interest is all zero (inactive)
            "Brokerage Name": "Firstrade -3792",
            "Account #": "90000104",
            "ST Proceeds": "$0.00",
            "ST Basis": "$0.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$0.00",
            "LT Proceeds": "$1,500.00",
            "LT Basis": "$1,000.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$500.00",
            "Total Proceeds": "$1,500.00",
            "Total Cost Basis": "$1,000.00",
            "Total Wash Sale": "$0.00",
            "Total Net Gain/(Loss)": "$500.00",
            "Ordinary Interest": "$0.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "Apex",
            "Parity Status": "PASS",
        },
        {
            # Row 1: ST is active, LT is all zero (should be inactive), Interest is active
            "Brokerage Name": "Robinhood -0847",
            "Account #": "90000200",
            "ST Proceeds": "$50,000.00",
            "ST Basis": "$45,000.00",
            "ST Wash Sale": "$1,200.00",
            "ST Net": "$6,200.00",
            "LT Proceeds": "$0.00",
            "LT Basis": "$0.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$0.00",
            "Total Proceeds": "$50,000.00",
            "Total Cost Basis": "$45,000.00",
            "Total Wash Sale": "$1,200.00",
            "Total Net Gain/(Loss)": "$6,200.00",
            "Ordinary Interest": "$150.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "Robinhood Securities",
            "Parity Status": "PASS",
        },
    ])
    html_output = render_summary_table_html(df)

    # CSS definition check for group-inactive and increased contrast
    assert ".summary-table td.group-inactive" in html_output
    assert "#CED4DA" in html_output
    assert "#343A40" in html_output

    # Typography and padding check
    assert "font-size: 0.75rem;" in html_output
    assert "padding: 7px 10px;" in html_output
    assert "padding: 6px 10px;" in html_output

    # Row 0: ST columns should have group-inactive
    # ST Proceeds also has section-divider, so class should contain both
    assert 'class="section-divider group-inactive"' in html_output or 'class="group-inactive section-divider"' in html_output

    # Row 1: LT columns should have group-inactive
    # LT Proceeds also has section-divider, so class should contain both
    assert 'class="section-divider group-inactive"' in html_output

    # Active wash sale retained soft-red highlight (#FFC7CE / #9C0006)
    assert "wash-sale-active" in html_output
    assert "#FFC7CE" in html_output
    assert "#9C0006" in html_output


# =========================================================================
# Unit Tests for Clipboard Fallback & Inline Copy Styling (Tickets 10 & 16)
# =========================================================================

def test_render_summary_table_html_clipboard_fallback_and_inline_styling():
    """Verify the clipboard fallback and the inline click-to-copy styling."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "Fidelity -5678",
            "Account #": "***-5678",
            "ST Proceeds": "$10,000.00",
            "ST Basis": "$8,000.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$2,000.00",
            "LT Proceeds": "$5,000.00",
            "LT Basis": "$4,000.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$1,000.00",
            "Total Proceeds": "$15,000.00",
            "Total Cost Basis": "$12,000.00",
            "Total Wash Sale": "$0.00",
            "Total Net Gain/(Loss)": "$3,000.00",
            "Ordinary Interest": "$100.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "National Financial Services",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # 1. Clipboard fallback mechanism & robust event delegation
    assert "navigator.clipboard.writeText" in html_output
    assert "document.execCommand('copy')" in html_output
    assert "fallbackCopy" in html_output
    assert "textarea" in html_output
    assert "addEventListener('click'" in html_output

    # The click trigger is delegated only. An inline onclick would fire a second
    # copyToClipboard call per click, because both would match the same event.
    assert "onclick=" not in html_output
    assert "window.copyToClipboard" not in html_output
    assert ".cell-text[data-copy]" in html_output

    # 2. Inline click-to-copy styling
    assert "text-decoration: underline;" in html_output
    assert "color: #0d6efd;" in html_output
    assert "cursor: pointer;" in html_output
    assert ".cell-text.copied" in html_output

    # The clipboard icon must be a pseudo-element so sorting, which reads
    # .cell-text textContent, is not corrupted by the icon or check glyph.
    assert ".cell-text::after" in html_output


# =========================================================================
# Unit Tests for Interactive Column Header Sorting (Ticket 12)
# =========================================================================

def test_render_summary_table_html_sortable_headers_and_indicators():
    """Verify table headers include sortable class, col type attributes, and sort icons."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "Fidelity -5678",
            "Account #": "***-5678",
            "ST Proceeds": "$10,000.00",
            "ST Basis": "$8,000.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$2,000.00",
            "LT Proceeds": "$5,000.00",
            "LT Basis": "$4,000.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$1,000.00",
            "Total Proceeds": "$15,000.00",
            "Total Cost Basis": "$12,000.00",
            "Total Wash Sale": "$0.00",
            "Total Net Gain/(Loss)": "$3,000.00",
            "Ordinary Interest": "$100.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "National Financial Services",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # 1. Verify sortable header attributes and classes
    assert 'class="sortable"' in html_output or 'class="section-divider sortable"' in html_output or 'class="sortable section-divider"' in html_output
    assert 'data-col-index=' in html_output
    assert 'data-col-type="numeric"' in html_output
    assert 'data-col-type="text"' in html_output

    # 2. Verify sort indicator icon elements
    assert '<span class="sort-icon">⇅</span>' in html_output or 'class="sort-icon"' in html_output

    # 3. Verify CSS styling for sortable headers
    assert "cursor: pointer" in html_output
    assert "user-select: none" in html_output
    assert ".summary-table th.sortable" in html_output or ".summary-table th:hover" in html_output
    assert ".sort-icon" in html_output
    assert ".sorted-asc" in html_output
    assert ".sorted-desc" in html_output

    # 4. Verify checkbox column header is present
    assert "checkbox-header" in html_output
    assert "master-checkbox" in html_output
    assert "type=\"checkbox\"" in html_output


def test_render_summary_table_html_client_side_sorting_script():
    """Verify embedded client-side script includes sort logic, currency parsing, and DOM row reordering."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "Robinhood -1234",
            "Account #": "1234",
            "ST Proceeds": "$500.00",
            "ST Basis": "$400.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$100.00",
            "LT Proceeds": "$0.00",
            "LT Basis": "$0.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$0.00",
            "Total Proceeds": "$500.00",
            "Total Cost Basis": "$400.00",
            "Total Wash Sale": "$0.00",
            "Total Net Gain/(Loss)": "$100.00",
            "Ordinary Interest": "$0.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "Robinhood Securities",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # 1. Sort handler functions exposed and implemented
    assert "sortTable" in html_output
    assert "parseCellValue" in html_output or "parseSortValue" in html_output

    # 2. Currency stripping and numeric parsing
    assert "replace(/\\$/g" in html_output or "replace('$'," in html_output or "replace(/\\$/" in html_output
    assert "parseFloat" in html_output

    # 3. Direction toggling and visual indicator updates
    assert "'asc'" in html_output
    assert "'desc'" in html_output
    assert "▲" in html_output
    assert "▼" in html_output

    # 4. DOM row reordering
    assert "tbody.appendChild" in html_output

    # 5. Robust listener attachment
    assert "__sortTableListenerAttached" in html_output or "sortTable" in html_output

    # 6. Checkbox selection script is present
    assert "__checkboxSelectionAttached" in html_output or "checkboxSelection" in html_output


def test_render_summary_table_html_checkbox_selection():
    """Verify checkbox column renders and master toggle / row selection works."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "BBAE -3240",
            "Account #": "***-3240",
            "ST Proceeds": "$1,000.00",
            "ST Basis": "$800.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$225.00",
            "LT Proceeds": "$500.00",
            "LT Basis": "$400.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$100.00",
            "Total Proceeds": "$1,500.00",
            "Total Cost Basis": "$1,200.00",
            "Total Wash Sale": "$0.00",
            "Total Net Gain/(Loss)": "$325.00",
            "Ordinary Interest": "$50.00",
            "US Treasury Interest": "$120.00",
            "Clearing Firm": "Apex",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # 1. Checkbox column header with master checkbox
    assert "checkbox-header" in html_output
    assert "master-checkbox" in html_output

    # 2. Row checkboxes present in tbody
    assert 'class="row-checkbox"' in html_output
    assert 'data-row-id="' in html_output

    # 3. Master checkbox in header
    assert 'type="checkbox"' in html_output

    # 4. Checkbox column present in table
    assert 'class="checkbox-cell"' in html_output


def test_render_summary_table_html_inline_copy_and_formatting_with_checkbox():
    """Verify that adding sortable headers and checkboxes retains inline click-to-copy, section dividers, zero group styles, and new checkbox features."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "BBAE -3240",
            "Account #": "***-3240",
            "ST Proceeds": "$0.00",
            "ST Basis": "$0.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$0.00",
            "LT Proceeds": "$1,000.00",
            "LT Basis": "$500.00",
            "LT Wash Sale": "$250.00",
            "LT Net": "$750.00",
            "Total Proceeds": "$1,000.00",
            "Total Cost Basis": "$500.00",
            "Total Wash Sale": "$250.00",
            "Total Net Gain/(Loss)": "$750.00",
            "Ordinary Interest": "$0.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "Apex",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # Verifies inline copy data attributes and formatting are preserved
    assert 'data-copy="1000.00"' in html_output

    # Preserves section dividers
    assert "section-divider" in html_output

    # Preserves wash sale styling
    assert "wash-sale-active" in html_output

    # Preserves inactive zero-group shading
    assert "group-inactive" in html_output

    # New: checkbox column present
    assert 'class="checkbox-cell"' in html_output
    assert 'class="row-checkbox"' in html_output


def test_render_summary_table_html_preserves_inline_copy_and_formatting():
    """Verify that adding sortable headers retains inline copy, dividers, and zero group styles."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "BBAE -3240",
            "Account #": "***-3240",
            "ST Proceeds": "$0.00",
            "ST Basis": "$0.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$0.00",
            "LT Proceeds": "$1,000.00",
            "LT Basis": "$500.00",
            "LT Wash Sale": "$250.00",
            "LT Net": "$750.00",
            "Total Proceeds": "$1,000.00",
            "Total Cost Basis": "$500.00",
            "Total Wash Sale": "$250.00",
            "Total Net Gain/(Loss)": "$750.00",
            "Ordinary Interest": "$0.00",
            "US Treasury Interest": "$0.00",
            "Clearing Firm": "Apex",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # Preserves click-to-copy payloads
    assert 'class="cell-text" data-copy="1000.00"' in html_output
    assert 'data-copy="1000.00"' in html_output

    # Preserves section dividers
    assert "section-divider" in html_output

    # Preserves wash sale styling
    assert "wash-sale-active" in html_output

    # Preserves inactive zero-group shading
    assert "group-inactive" in html_output


# =========================================================================
# Unit Tests for Ticket 15 Acceptance Criteria
# =========================================================================

def test_ticket_15_summary_table_preview_refinements():
    """Verify Ticket 15 typography, column names, row hover, and contrast styling."""
    df = pd.DataFrame([
        {
            "Brokerage Name": "Charles Schwab -1234",
            "Account #": "1234",
            "ST Proceeds": "$0.00",
            "ST Basis": "$0.00",
            "ST Wash Sale": "$0.00",
            "ST Net": "$0.00",
            "LT Proceeds": "$5,000.00",
            "LT Basis": "$4,000.00",
            "LT Wash Sale": "$0.00",
            "LT Net": "$1,000.00",
            "Total Proceeds": "$5,000.00",
            "Total Cost Basis": "$4,000.00",
            "Total Wash Sale": "$0.00",
            "Total Net": "$1,000.00",
            "Box 1 Interest Income": "$250.00",
            "Box 3 - Savings Bonds and Treasury Interest": "$75.00",
            "Clearing Firm": "Charles Schwab & Co.",
            "Parity Status": "PASS",
        }
    ])
    html_output = render_summary_table_html(df)

    # 1. Font size reduced by 1pt to 0.75rem
    assert "font-size: 0.75rem;" in html_output

    # 2. Total Net column header
    assert "Total Net" in html_output
    assert "Total Net Gain/(Loss)" not in html_output

    # 3. Interest column headers titled Box 1 Interest Income & Box 3 - Savings Bonds and Treasury Interest
    assert "Box 1 Interest Income" in html_output
    assert "Box 3 - Savings Bonds and Treasury Interest" in html_output

    # 4. Row hover uses subtle light blue rather than light grey
    assert "background-color: #e8f4fd;" in html_output
    assert ".summary-table tr:hover td:not(.wash-sale-active):not(.group-inactive)" in html_output

    # 5. Inactive semantic group cells have darkened grey background
    assert ".summary-table td.group-inactive" in html_output
    assert "#CED4DA" in html_output
    assert 'class="section-divider group-inactive"' in html_output or 'class="group-inactive"' in html_output



