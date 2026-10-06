"""Browser tests for click-to-copy on the summary preview table (Ticket 16).

These tests drive a real browser and assert on real clipboard contents. String
assertions against the rendered HTML cannot distinguish a working copy path from a
broken one: the previous implementation shipped twice with passing tests while the
clipboard write never reached the system clipboard.

Requires a browser::

    pip install -e ".[browser-tests]"
    playwright install chromium
"""

import pandas as pd
import pytest

from tax_tools.formatter import render_summary_table_html

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is not installed; install the 'browser-tests' extra",
)
# The fixtures below rely on pytest-playwright providing the page/context fixtures.
pytest.importorskip(
    "pytest_playwright",
    reason="pytest-playwright is not installed; install the 'browser-tests' extra",
)

pytestmark = pytest.mark.browser


@pytest.fixture
def df():
    return pd.DataFrame(
        [
            {
                "Brokerage Name": "BBAE -3240",
                "Account #": "***-3240",
                "ST Proceeds": "$1,000.00",
                "ST Basis": "$800.00",
                "ST Wash Sale": "$25.00",
                "ST Net": "$175.00",
                "LT Proceeds": "$0.00",
                "LT Basis": "$0.00",
                "LT Wash Sale": "$0.00",
                "LT Net": "$0.00",
            },
            {
                "Brokerage Name": "Robinhood -5678",
                "Account #": "5678",
                "ST Proceeds": "$0.00",
                "ST Basis": "$0.00",
                "ST Wash Sale": "$0.00",
                "ST Net": "$0.00",
                "LT Proceeds": "$2,500.00",
                "LT Basis": "$1,900.00",
                "LT Wash Sale": "$0.00",
                "LT Net": "$600.00",
            },
        ]
    )


@pytest.fixture
def table(clipboard, df):
    """Load the rendered table and return the clipboard harness."""
    clipboard.load(render_summary_table_html(df))
    return clipboard


def cell(page, row, column):
    """Return the cell-text span at a given body-row / header-name position."""
    header_index = page.evaluate(
        "(name) => Array.from(document.querySelectorAll('.summary-table thead th'))"
        ".findIndex(th => th.textContent.includes(name))",
        column,
    )
    assert header_index >= 0, f"column {column!r} not found in header"
    return page.locator(
        f".summary-table tbody tr:nth-child({row}) td:nth-child({header_index + 1}) "
        ".cell-text"
    )


# =========================================================================
# Step 0 - harness sanity
#
# The harness must be able to observe a write, count writes, and see the
# sentinel. If any of these fail, a later red result means nothing.
# =========================================================================

def test_harness_reads_and_writes_the_real_clipboard(clipboard):
    clipboard.load("<p>no table here</p>")
    assert clipboard.read() == "CLIPBOARD_UNTOUCHED"
    clipboard.page.evaluate("() => navigator.clipboard.writeText('probe')")
    assert clipboard.read() == "probe"


def test_harness_counts_clipboard_writes(clipboard, df):
    clipboard.load(render_summary_table_html(df))
    clipboard.watch_writes()
    clipboard.page.evaluate("() => navigator.clipboard.writeText('first')")
    clipboard.page.evaluate("() => navigator.clipboard.writeText('second')")
    assert clipboard.writes() == ["first", "second"]


# =========================================================================
# Step 1 - clicking the cell text copies the sanitized value
# =========================================================================

def test_clicking_numeric_cell_text_copies_sanitized_value(table):
    """A currency cell copies with '$' and commas stripped.

    Displayed as "$1,000.00" but must reach the clipboard as "1000.00" so it can be
    pasted straight into tax filing software.
    """
    cell(table.page, 1, "ST Proceeds").click()
    assert table.expect_written("1000.00") == "1000.00"


def test_clicking_identifier_cell_text_copies_raw_text(table):
    """A text column copies as-is, with no numeric sanitization applied."""
    cell(table.page, 1, "Brokerage Name").click()
    assert table.expect_written("BBAE -3240") == "BBAE -3240"


def test_clicking_second_row_copies_that_rows_value(table):
    """The copied value belongs to the clicked row, not the first one."""
    cell(table.page, 2, "LT Proceeds").click()
    assert table.expect_written("2500.00") == "2500.00"


def test_no_dedicated_copy_buttons_remain(table):
    """Dedicated copy button elements are gone from the data cells."""
    assert table.page.locator(".summary-table tbody button.copy-btn").count() == 0


# =========================================================================
# Step 3 - one click, one clipboard write
# =========================================================================

def test_one_click_writes_the_clipboard_exactly_once(table):
    """A single click must produce exactly one clipboard write.

    Two triggers are wired up: an inline onclick handler and a capture-phase
    document listener. Both match the same click, so both call copyToClipboard.
    The resulting value is correct either way, which is why this only shows up if
    the writes are counted.
    """
    table.watch_writes()
    cell(table.page, 1, "ST Proceeds").click()
    table.expect_written("1000.00")
    assert table.writes() == ["1000.00"]


# =========================================================================
# Step 5 - hover affordance and copy confirmation
# =========================================================================

def icon_opacity(locator):
    """Computed opacity of the ::after clipboard icon."""
    return locator.evaluate("el => getComputedStyle(el, '::after').opacity")


def icon_content(locator):
    return locator.evaluate("el => getComputedStyle(el, '::after').content")


def test_hover_underlines_and_blues_the_cell_text(table):
    """Hovering a data cell underlines the text and turns it blue.

    Asserted through expect() because the colour transitions over 150ms, so the
    computed value is mid-animation on the first read after hover().
    """
    locator = cell(table.page, 1, "ST Proceeds")
    idle_color = locator.evaluate("el => getComputedStyle(el).color")

    locator.hover()
    table.expect(locator).to_have_css("text-decoration-line", "underline")
    table.expect(locator).to_have_css("color", "rgb(13, 110, 253)")  # #0d6efd
    assert idle_color != "rgb(13, 110, 253)"


def test_hover_reveals_an_inline_clipboard_icon(table):
    """The clipboard icon is hidden until hover, then revealed."""
    locator = cell(table.page, 1, "ST Proceeds")
    assert icon_opacity(locator) == "0"

    locator.hover()
    table.page.wait_for_function(
        "el => getComputedStyle(el, '::after').opacity === '1'", arg=locator.element_handle()
    )


def test_cell_text_shows_a_pointer_cursor(table):
    """Clickable cells advertise themselves with a pointer cursor."""
    table.expect(cell(table.page, 1, "ST Proceeds")).to_have_css("cursor", "pointer")


def test_copying_shows_confirmation_then_clears_it(table):
    """Clicking briefly applies a confirmation state that then reverts."""
    locator = cell(table.page, 1, "ST Proceeds")
    locator.click()
    table.expect_written("1000.00")

    # copyToClipboard adds 'copied' and removes it after ~1.2s.
    table.page.wait_for_selector(".summary-table .cell-text.copied", timeout=2000)
    assert icon_content(locator) not in ("none", "normal", '""')

    table.page.wait_for_selector(
        ".summary-table .cell-text.copied", state="detached", timeout=4000
    )


def test_copying_does_not_reload_the_page(table):
    """Copying must not navigate or reload (Ticket 16 acceptance criterion)."""
    table.page.evaluate("() => { window.__stillHere = true; }")
    cell(table.page, 1, "ST Proceeds").click()
    table.expect_written("1000.00")
    assert table.page.evaluate("() => window.__stillHere") is True


# =========================================================================
# Step 6 - sorting must be unaffected
#
# sortTable() reads .cell-text textContent to sort by. If the clipboard icon were
# a real child element rather than a ::after pseudo-element, this column would
# sort as "1000.00(clipboard)" and then "1000.00(check)" right after a copy.
# =========================================================================

def row_order(page, column):
    """Brokerage names in their current tbody order."""
    index = page.evaluate(
        "(name) => Array.from(document.querySelectorAll('.summary-table thead th'))"
        ".findIndex(th => th.textContent.includes(name))",
        column,
    )
    return page.evaluate(
        "(i) => Array.from(document.querySelectorAll('.summary-table tbody tr'))"
        ".map(tr => tr.children[i].querySelector('.cell-text').textContent)",
        index,
    )


def test_cell_text_content_contains_no_icon_glyph(table):
    """The icon must be a pseudo-element, invisible to textContent."""
    text = cell(table.page, 1, "ST Proceeds").text_content()
    assert text == "$1,000.00"
    for glyph in ("\U0001F4CB", "✓"):
        assert glyph not in text


def test_sorting_ignores_the_copy_state(table):
    """Clicking a cell must not corrupt the value that sorting reads."""
    locator = cell(table.page, 1, "ST Proceeds")
    locator.click()
    table.expect_written("1000.00")
    table.page.wait_for_selector(".summary-table .cell-text.copied", timeout=2000)

    # Still the plain displayed value, with no confirmation glyph mixed in.
    assert locator.text_content() == "$1,000.00"


def test_numeric_column_sorts_by_the_clicked_column(table):
    """Known pre-existing defect, not caused by Ticket 16.

    Ticket 17 prepends a checkbox cell to every row but leaves data-col-index
    0-based over the dataframe columns, so sortTable() reads
    row.children[colIndex] one cell to the left: sorting "ST Proceeds" actually
    sorts "Account #". Verified identical on main before this change.

    Kept as strict xfail so it asserts the correct behaviour, documents the
    defect, and fails loudly once someone fixes the index (strict xfail turns an
    unexpected pass into a failure, prompting removal of the marker).
    """
    page = table.page
    page.locator(".summary-table thead th", has_text="ST Proceeds").first.click()
    # Row 1 is 1000.00 and row 2 is 0.00, so ascending puts Robinhood first.
    assert row_order(page, "Brokerage Name") == ["Robinhood -5678", "BBAE -3240"]


test_numeric_column_sorts_by_the_clicked_column = pytest.mark.xfail(
    strict=True, reason="sortTable column index is off by one since Ticket 17"
)(test_numeric_column_sorts_by_the_clicked_column)


def test_copying_still_works_after_a_sort(table):
    """Reordering rows must not detach the copy payload from a cell.

    Deliberately does not assert a particular sort order: which column sorts which
    is covered by the xfail above, and encoding the buggy mapping here would make
    this test break for the wrong reason when that is fixed.
    """
    page = table.page
    header = page.locator(".summary-table thead th", has_text="LT Proceeds").first
    header.click()
    header.click()  # exercise both directions

    expected_by_brokerage = {"BBAE -3240": "0.00", "Robinhood -5678": "2500.00"}
    for row in (1, 2):
        brokerage = row_order(page, "Brokerage Name")[row - 1]
        cell(page, row, "LT Proceeds").click()
        expected = expected_by_brokerage[brokerage]
        assert table.expect_written(expected) == expected


# =========================================================================
# Step 7 - edge cases
# =========================================================================

@pytest.fixture
def edge_df():
    """Rows covering zero values, blanks, negative/accounting formats, and HTML metacharacters."""
    return pd.DataFrame(
        [
            {
                "Brokerage Name": "Zero & <Co>",
                "Account #": 'quo"te',
                "ST Proceeds": "$0.00",
                "ST Basis": "$0",
                "ST Wash Sale": "($500.00)",
                "ST Net": "-$1,234.56",
                "LT Proceeds": "",
                "LT Basis": "   ",
                "LT Wash Sale": None,
                "LT Net": "$0.00",
            }
        ]
    )


@pytest.fixture
def edge_table(clipboard, edge_df):
    clipboard.load(render_summary_table_html(edge_df))
    return clipboard


def test_zero_values_are_copyable(edge_table):
    """Zero is the most common value in this table and must still copy.

    copyToClipboard() guards with `!textToCopy && textToCopy !== '0' &&
    textToCopy !== '0.00'`, so zero is explicitly special-cased. Tidy that guard
    into a plain falsy check and every $0.00 cell silently stops copying.
    """
    cell(edge_table.page, 1, "ST Proceeds").click()
    assert edge_table.expect_written("0.00") == "0.00"

    cell(edge_table.page, 1, "ST Basis").click()
    assert edge_table.expect_written("0") == "0"


def test_negative_and_accounting_values_are_copyable(edge_table):
    """Accounting parentheses and minus signs survive sanitization."""
    cell(edge_table.page, 1, "ST Wash Sale").click()
    assert edge_table.expect_written("-500.00") == "-500.00"

    cell(edge_table.page, 1, "ST Net").click()
    assert edge_table.expect_written("-1234.56") == "-1234.56"


@pytest.mark.parametrize("column", ["LT Proceeds", "LT Basis", "LT Wash Sale"])
def test_blank_cells_do_not_copy(edge_table, column):
    """Empty, whitespace-only and None cells leave the clipboard untouched."""
    locator = cell(edge_table.page, 1, column)

    # Not clickable at all: no payload, so no misleading hover affordance.
    assert locator.get_attribute("data-copy") is None

    locator.click(force=True)
    assert edge_table.read() == "CLIPBOARD_UNTOUCHED"


def test_header_cells_do_not_copy(table):
    """Column headers are outside the click-to-copy surface."""
    table.page.locator(".summary-table thead th", has_text="Brokerage Name").click()
    table.page.wait_for_timeout(200)
    assert table.read() == "CLIPBOARD_UNTOUCHED"


def test_checkbox_column_does_not_copy(table):
    """The Ticket 17 selection checkbox must not trigger a copy."""
    table.page.locator(".summary-table tbody .row-checkbox").first.click()
    table.page.wait_for_timeout(200)
    assert table.read() == "CLIPBOARD_UNTOUCHED"


def test_checkbox_click_still_toggles_selection(table):
    """Adding click-to-copy must not swallow checkbox behaviour."""
    checkbox = table.page.locator(".summary-table tbody .row-checkbox").first
    checkbox.click()
    assert checkbox.is_checked()


def test_html_metacharacters_are_escaped(edge_table):
    """Values containing &, < and " round-trip through the attribute intact."""
    cell(edge_table.page, 1, "Brokerage Name").click()
    assert edge_table.expect_written("Zero & <Co>") == "Zero & <Co>"

    cell(edge_table.page, 1, "Account #").click()
    assert edge_table.expect_written('quo"te') == 'quo"te'


def test_click_survives_a_second_render(clipboard, df):
    """Streamlit re-renders the fragment; the newest cells must still copy.

    The document listener is attached behind a window-level guard, so after a
    re-render the click is handled by a closure captured from an earlier render.
    That only works because copyToClipboard() reads its payload off whatever
    element it is handed rather than closing over anything render-specific.
    """
    clipboard.load(render_summary_table_html(df))
    clipboard.load(render_summary_table_html(df))  # second "rerun"

    cell(clipboard.page, 1, "ST Proceeds").click()
    assert clipboard.expect_written("1000.00") == "1000.00"


def test_click_survives_inline_handlers_being_stripped(clipboard, df):
    """Streamlit's sanitiser may drop inline handlers; copying must still work.

    Guards against anyone reintroducing an inline onclick as the trigger.
    """
    clipboard.load(render_summary_table_html(df))
    clipboard.page.evaluate(
        "() => document.querySelectorAll('[onclick]')"
        ".forEach(el => el.removeAttribute('onclick'))"
    )
    cell(clipboard.page, 1, "ST Proceeds").click()
    assert clipboard.expect_written("1000.00") == "1000.00"
