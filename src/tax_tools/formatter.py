"""Preview and table formatting utilities for tax data.

Includes account number suffix formatting, clipboard data sanitization,
and semantic styling helpers for the interactive preview tables.
"""

from typing import Any, Optional
import math
import re


def _is_missing(val: Any) -> bool:
    """Report whether a table cell holds no value.

    Covers None, the float NaN that pandas produces for an absent cell, and the
    pandas/numpy missing singletons (pd.NA, NaT). Their str() forms are literal
    text such as 'nan' or '<NA>', which must never reach the screen or clipboard.
    Checked by class name so this module does not need to import pandas.
    """
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    return type(val).__name__ in ("NAType", "NaTType")


def format_brokerage_display_name(brokerage_name: Optional[str], account_number: Optional[str]) -> str:
    """Format brokerage display name with trailing account number suffix.

    Appends the last 4 characters of the statement account number (e.g. 'BBAE -0001').
    Safely handles masked accounts ('***-3240'), short account strings, empty/None values.
    """
    base_name = str(brokerage_name).strip() if brokerage_name is not None else ""
    if not account_number:
        return base_name

    acct_str = str(account_number).strip()
    if not acct_str:
        return base_name

    last_4 = acct_str[-4:] if len(acct_str) >= 4 else acct_str
    # If last_4 starts with a hyphen or dash (e.g. from '***-3240' -> '-3240'), strip leading hyphens to avoid double hyphens
    last_4 = last_4.lstrip("-")
    if not last_4:
        return base_name

    if not base_name:
        return f"-{last_4}"

    return f"{base_name} -{last_4}"


def sanitize_for_clipboard(val: Any) -> str:
    """Sanitize tabular value for tax software clipboard copying.

    For currency values (or strings containing '$'), strips the '$' sign and commas
    while preserving negative signs, decimal precision, and standard numerical representation
    (e.g., '$12,345.67' -> '12345.67', '-$500.00' -> '-500.00', '($500.00)' -> '-500.00',
    '$0.00' -> '0.00').
    Raw text is preserved as a clean string for non-currency values (e.g., 'Brokerage Name', 'Account #').
    Missing values (None, and the float NaN that pandas produces for empty cells) yield an
    empty string, so a blank cell is never copyable rather than copying the literal text 'nan'.
    """
    if _is_missing(val):
        return ""

    if isinstance(val, (int, float)):
        # Pure numeric float or int
        if isinstance(val, float):
            return f"{val:.2f}"
        return str(val)

    s = str(val).strip()
    if not s:
        return ""

    # Check if string represents a currency amount (contains '$' or is formatted as currency/accounting)
    if "$" in s:
        cleaned = s.replace("$", "").replace(",", "").strip()
        # Handle accounting parenthesis negative format: '(500.00)' -> '-500.00'
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = f"-{cleaned[1:-1].strip()}"
        # Handle '- 500.00' or '-$500.00' where minus was separated or preserved
        cleaned = re.sub(r"-\s+", "-", cleaned)
        return cleaned

    # Non-currency string or raw text (e.g. Brokerage Name, Account #)
    return s


SEMANTIC_GROUPS = {
    "Short-Term": [
        "ST Proceeds",
        "ST Basis",
        "ST Wash Sale",
        "ST Net",
    ],
    "Long-Term": [
        "LT Proceeds",
        "LT Basis",
        "LT Wash Sale",
        "LT Net",
    ],
    "Interest": [
        "Box 1 Interest Income",
        "Box 3 - Savings Bonds and Treasury Interest",
        "Ordinary Interest",
        "US Treasury Interest",
    ],
}

# Column names preceded by a prominent, thickened vertical divider
DIVIDER_COLUMNS = ["ST Proceeds", "LT Proceeds"]

NUMERIC_COLUMNS = {
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
    "Total Net Gain/(Loss)",
    "Box 1 Interest Income",
    "Box 3 - Savings Bonds and Treasury Interest",
    "Ordinary Interest",
    "US Treasury Interest",
}


def is_val_zero(val: Any) -> bool:
    """Check if a numeric or currency-formatted value represents zero."""
    if val is None:
        return True
    if isinstance(val, (int, float)):
        return abs(val) < 1e-9
    s = str(val).replace("$", "").replace(",", "").strip()
    if not s or s == "-":
        return True
    if s.startswith("(") and s.endswith(")"):
        s = f"-{s[1:-1].strip()}"
    try:
        return abs(float(s)) < 1e-9
    except ValueError:
        return False


def is_semantic_group_zero(row: Any, group_cols: list[str]) -> bool:
    """Check if all values for the specified column group in a row evaluate to zero."""
    # row can be a pandas Series or dict-like
    present_cols = [c for c in group_cols if (c in row if hasattr(row, "__contains__") else False)]
    if not present_cols:
        return False
    return all(is_val_zero(row[c]) for c in present_cols)


def render_summary_table_html(df) -> str:
    """Render interactive HTML table with one-click copy buttons, thickened section dividers, semantic shading, and per-row selection checkboxes.

    Features:
    - Thickened visual dividers before Short-Term ('ST Proceeds') and Long-Term ('LT Proceeds') sections.
    - Semantic group zero evaluation: groups (Short-Term, Long-Term, Interest) are shaded muted grey (#DEE2E6)
      when all values in that group are zero for a given statement row.
    - Inline click-to-copy on every data cell: hovering underlines the text, turns it blue, and reveals a
      clipboard icon; clicking the cell text copies the value. Blank cells are not clickable.
    - Clipboard sanitization: Currency values are copied as pure numerical numbers (stripped of '$').
    - Client-side copy via navigator.clipboard.writeText(...) without Streamlit server reruns.
    - The copy is triggered by a single delegated document listener. An inline onclick handler is
      deliberately not used, because it would fire a second copy per click.
    - Momentary visual feedback: the cell turns green with a checkmark icon for ~1.2s.
    - Highlight positive wash sales with soft-red background (#FFC7CE) and red text (#9C0006).
    - Per-row selection checkboxes: each row has a leftmost checkbox with data-row-id derived from the masked account number.
      A master "select all" / "select none" toggle appears in the column header with indeterminate state support.
    """
    import html

    # Build HTML table
    headers = list(df.columns)
    rows_html = []

    for _, row in df.iterrows():
        # Evaluate zero status for each semantic group in this row
        group_is_zero = {}
        for g_name, g_cols in SEMANTIC_GROUPS.items():
            group_is_zero[g_name] = is_semantic_group_zero(row, g_cols)

        cells_html = []

        # Add checkbox cell as the first column
        account_number = row.get("Account #", "")
        cells_html.append(f'<td class="checkbox-cell"><input type="checkbox" class="row-checkbox" data-row-id="{html.escape(str(account_number))}" /></td>')

        for col in headers:
            raw_val = row[col]
            # An absent cell arrives as float NaN (or pd.NA), whose str() is literal
            # text like "nan". Show nothing rather than that.
            display_str = "" if _is_missing(raw_val) else str(raw_val)
            clipboard_val = sanitize_for_clipboard(raw_val)

            # Determine css classes and inline styles
            classes = []
            styles = []

            # Section divider check: thickened border before Short-Term and Long-Term sections
            if col in DIVIDER_COLUMNS:
                classes.append("section-divider")

            # Check if this column belongs to an inactive (all-zero) semantic group
            in_zero_group = False
            for g_name, g_cols in SEMANTIC_GROUPS.items():
                if col in g_cols and group_is_zero.get(g_name, False):
                    in_zero_group = True
                    break

            if in_zero_group:
                classes.append("group-inactive")

            # Wash sale highlighting: positive wash sale (> $0.00) takes precedence
            if col in ("ST Wash Sale", "LT Wash Sale", "Total Wash Sale"):
                cleaned = str(raw_val).replace("$", "").replace(",", "").replace("-", "").strip()
                try:
                    if float(cleaned) > 0:
                        classes.append("wash-sale-active")
                except (ValueError, TypeError):
                    pass

            class_attr = f' class="{" ".join(classes)}"' if classes else ""

            # Every data cell is click-to-copy. The clipboard payload rides on the
            # text span itself so that clicking the text is the trigger, and so that
            # copyToClipboard() keeps its existing element contract unchanged.
            # Blank values get no data-copy, which leaves them inert rather than
            # clickable-but-silent.
            escaped_disp = html.escape(display_str)
            if clipboard_val:
                escaped_clip = html.escape(clipboard_val, quote=True)
                cell_content = (
                    f'<span class="cell-text" data-copy="{escaped_clip}" '
                    f'title="Click to copy">{escaped_disp}</span>'
                )
            else:
                cell_content = f'<span class="cell-text">{escaped_disp}</span>'

            cells_html.append(f"<td{class_attr}>{cell_content}</td>")
        rows_html.append(f"<tr>{''.join(cells_html)}</tr>")

    # Build thead with sortable and divider classes where appropriate
    # Add checkbox column header as the first column
    thead_cells = []
    thead_cells.append(
        f'<th class="sortable checkbox-header" data-col-type="checkbox" style="width: 40px; text-align: center;">'
        f'<span class="th-content">'
        f'<input type="checkbox" class="master-checkbox" />'
        f'<span class="th-label">Select</span>'
        f'</span>'
        f'</th>'
    )
    for idx, c in enumerate(headers):
        classes = ["sortable"]
        if c in DIVIDER_COLUMNS:
            classes.append("section-divider")
        th_class = f' class="{" ".join(classes)}"'
        col_type = "numeric" if c in NUMERIC_COLUMNS else "text"
        thead_cells.append(
            f'<th{th_class} data-col-index="{idx}" data-col-type="{col_type}">'
            f'<span class="th-content">'
            f'<span class="th-label">{html.escape(c)}</span>'
            f'<span class="sort-icon">⇅</span>'
            f'</span>'
            f'</th>'
        )
    thead_th = "".join(thead_cells)
    tbody_tr = "\n".join(rows_html)

    return f"""
<div class="summary-table-container">
  <style>
    .summary-table-container {{
      width: 100%;
      overflow-x: auto;
      margin: 1rem 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 0.75rem;
      border: 1px solid #e0e0e0;
      border-radius: 6px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .summary-table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      white-space: nowrap;
    }}
    .summary-table th {{
      background-color: #f8f9fa;
      color: #212529;
      font-weight: 600;
      padding: 7px 10px;
      border-bottom: 2px solid #dee2e6;
      border-right: 1px solid #e9ecef;
      position: sticky;
      top: 0;
      z-index: 10;
      cursor: pointer;
      user-select: none;
      transition: background-color 0.15s ease-in-out;
    }}
    .summary-table th.sortable:hover {{
      background-color: #e9ecef;
    }}
    .th-content {{
      display: inline-flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      width: 100%;
    }}
    .sort-icon {{
      font-size: 0.75rem;
      opacity: 0.45;
      margin-left: 4px;
      transition: opacity 0.15s ease-in-out, color 0.15s ease-in-out;
    }}
    .summary-table th.sorted-asc .sort-icon,
    .summary-table th.sorted-desc .sort-icon {{
      opacity: 1;
      color: #0d6efd;
      font-weight: bold;
    }}
    .summary-table td {{
      padding: 6px 10px;
      border-bottom: 1px solid #e9ecef;
      border-right: 1px solid #e9ecef;
      color: #212529;
      background-color: #ffffff;
    }}
    .summary-table th.section-divider,
    .summary-table td.section-divider {{
      border-left: 3px solid #6c757d !important;
    }}
    .summary-table td.group-inactive {{
      background-color: #CED4DA !important;
      color: #343A40;
    }}
    .summary-table td.wash-sale-active {{
      background-color: #FFC7CE !important;
      color: #9C0006 !important;
      font-weight: bold;
    }}
    .summary-table tr:hover td:not(.wash-sale-active):not(.group-inactive) {{
      background-color: #e8f4fd;
    }}
    .summary-table td .cell-text {{
      cursor: pointer;
      transition: color 0.15s ease-in-out;
    }}
    .summary-table td .cell-text:hover {{
      text-decoration: underline;
      color: #0d6efd;
    }}
    /* The clipboard icon must be a pseudo-element, never a real child node.
       sortTable() reads .cell-text textContent to sort by, so a real icon span
       would make the column sort as "1000.00(clipboard)" and then as
       "1000.00(check)" straight after a copy. */
    .summary-table td .cell-text::after {{
      content: '📋';
      margin-left: 3px;
      font-size: 0.65rem;
      vertical-align: middle;
      opacity: 0;
      transition: opacity 0.15s ease-in-out;
    }}
    .summary-table td .cell-text:hover::after {{
      opacity: 1;
    }}
    /* Copy confirmation. copyToClipboard() toggles the 'copied' class and looks for
       a .copy-icon child; finding none is already handled, so the visible feedback
       is driven from here instead. */
    .summary-table td .cell-text.copied {{
      color: #0f5132;
      text-decoration: none;
    }}
    .summary-table td .cell-text.copied::after {{
      content: '✓';
      opacity: 1;
      animation: fadeInOut 1.2s ease-in-out forwards;
    }}
    @keyframes fadeInOut {{
      0% {{ opacity: 0; }}
      15% {{ opacity: 1; }}
      85% {{ opacity: 1; }}
      100% {{ opacity: 0; }}
    }}
    /* Checkbox column: narrow, centered, compact */
    .summary-table th.checkbox-header,
    .summary-table td.checkbox-cell {{
      width: 40px;
      min-width: 40px;
      max-width: 40px;
      padding: 6px 4px;
      text-align: center;
      text-align: center;
      border-right: 2px solid #dee2e6;
    }}
    .summary-table td.checkbox-cell {{
      background-color: #ffffff;
    }}
    .summary-table tr:hover td.checkbox-cell {{
      background-color: #ffffff;
    }}
    /* Master checkbox styling */
    .master-checkbox {{
      width: 16px;
      height: 16px;
      cursor: pointer;
      accent-color: #0d6efd;
    }}
    .row-checkbox {{
      width: 15px;
      height: 15px;
      cursor: pointer;
      accent-color: #0d6efd;
    }}
    /* Sortable header cursor (checkbox header uses pointer via master-checkbox) */
    .summary-table th.sortable:hover {{
      background-color: #e9ecef;
    }}
    /* Indeterminate state styling hint */
    .summary-table th.checkbox-header .master-checkbox:indeterminate {{
      opacity: 0.7;
    }}
  </style>

  <table class="summary-table">
    <thead>
      <tr>{thead_th}</tr>
    </thead>
    <tbody>
      {tbody_tr}
    </tbody>
  </table>

  <script>
    (function() {{
      function copyToClipboard(button) {{
        if (!button) return;
        const textToCopy = button.getAttribute('data-copy');
        if (!textToCopy && textToCopy !== '0' && textToCopy !== '0.00') return;

        function showFeedback() {{
          button.classList.add('copied');
          const iconSpan = button.querySelector('.copy-icon');
          if (iconSpan) iconSpan.textContent = '✓';

          setTimeout(() => {{
            button.classList.remove('copied');
            if (iconSpan) iconSpan.textContent = '📋';
          }}, 1200);
        }}

        function fallbackCopy() {{
          try {{
            const textArea = document.createElement('textarea');
            textArea.value = textToCopy;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            textArea.setAttribute('readonly', '');
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);
            if (successful) {{
              showFeedback();
            }} else {{
              console.error('Fallback execCommand copy was unsuccessful');
            }}
          }} catch (err) {{
            console.error('Fallback execCommand failed: ', err);
          }}
        }}

        if (navigator.clipboard && navigator.clipboard.writeText) {{
          navigator.clipboard.writeText(textToCopy).then(() => {{
            showFeedback();
          }}).catch(err => {{
            console.warn('navigator.clipboard.writeText failed, trying fallback: ', err);
            fallbackCopy();
          }});
        }} else {{
          fallbackCopy();
        }}
      }}

      // Single trigger: delegated from the document so that a Streamlit re-render
      // (which drops inline onclick handlers via DOMPurify) still works. Adding an
      // inline onclick as well would fire copyToClipboard twice per click.
      if (!window.__copyTableListenerAttached) {{
        window.__copyTableListenerAttached = true;
        document.addEventListener('click', function(e) {{
          const cellText = e.target.closest('.cell-text[data-copy]');
          if (cellText) {{
            e.preventDefault();
            copyToClipboard(cellText);
          }}
        }}, true);
      }}

      function parseCellValue(text, type) {{
        if (!text) return type === 'numeric' ? 0 : '';
        if (type === 'numeric') {{
          let s = text.replace(/\\$/g, '').replace(/,/g, '').trim();
          if (!s || s === '-') return 0;
          if (s.startsWith('(') && s.endsWith(')')) {{
            s = '-' + s.slice(1, -1).trim();
          }}
          s = s.replace(/^-\\s+/, '-');
          const val = parseFloat(s);
          return isNaN(val) ? 0 : val;
        }}
        return text.trim();
      }}

      function sortTable(th) {{
        if (!th) return;

        const table = th.closest('table');
        if (!table) return;
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        const colIndex = parseInt(th.getAttribute('data-col-index'), 10);
        const colType = th.getAttribute('data-col-type') || 'text';

        const currentDirection = th.getAttribute('data-sort-direction');
        const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';

        // Reset all other headers in this table
        const allThs = table.querySelectorAll('th');
        allThs.forEach(header => {{
          if (header !== th) {{
            header.removeAttribute('data-sort-direction');
            header.classList.remove('sorted-asc', 'sorted-desc');
            const icon = header.querySelector('.sort-icon');
            if (icon) icon.textContent = '⇅';
          }}
        }});

        // Set active header state
        th.setAttribute('data-sort-direction', newDirection);
        th.classList.remove('sorted-asc', 'sorted-desc');
        th.classList.add(newDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');
        const activeIcon = th.querySelector('.sort-icon');
        if (activeIcon) {{
          activeIcon.textContent = newDirection === 'asc' ? '▲' : '▼';
        }}

        const getCellText = cell => {{
          if (!cell) return '';
          const textSpan = cell.querySelector('.cell-text');
          return textSpan ? textSpan.textContent : cell.textContent;
        }};

        // Collect rows and sort
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((rowA, rowB) => {{
          const cellA = rowA.children[colIndex];
          const cellB = rowB.children[colIndex];

          const textA = getCellText(cellA);
          const textB = getCellText(cellB);

          const valA = parseCellValue(textA, colType);
          const valB = parseCellValue(textB, colType);

          if (colType === 'numeric') {{
            return newDirection === 'asc' ? valA - valB : valB - valA;
          }} else {{
            const cmp = valA.localeCompare(valB, undefined, {{ numeric: true, sensitivity: 'base' }});
            return newDirection === 'asc' ? cmp : -cmp;
          }}
        }});

        // Re-append sorted rows to tbody
        rows.forEach(row => tbody.appendChild(row));
      }}

      if (!window.__sortTableListenerAttached) {{
        window.__sortTableListenerAttached = true;
        document.addEventListener('click', function(e) {{
          const th = e.target.closest('.summary-table th.sortable');
          if (th) {{
            sortTable(th);
          }}
        }}, true);
      }}

      // Checkbox selection functionality
      if (!window.__checkboxSelectionAttached) {{
        window.__checkboxSelectionAttached = true;

        // Master checkbox: select/deselect all rows
        const masterCheckbox = document.querySelector('.summary-table thead .master-checkbox');
        if (masterCheckbox) {{
          masterCheckbox.addEventListener('change', function(e) {{
            const isChecked = e.target.checked;
            const allRowCheckboxes = document.querySelectorAll('.summary-table tbody .row-checkbox');
            allRowCheckboxes.forEach(cb => {{
              cb.checked = isChecked;
              cb.indeterminate = false;
            }});
          }});
        }}

        // Row checkboxes update master state
        const allRowCheckboxes = document.querySelectorAll('.summary-table tbody .row-checkbox');
        if (allRowCheckboxes.length > 0) {{
          const masterInThead = document.querySelector('.summary-table thead .master-checkbox');
          if (masterInThead) {{
            const updateMasterState = () => {{
              const allChecked = Array.from(allRowCheckboxes).every(cb => cb.checked);
              const anyChecked = Array.from(allRowCheckboxes).some(cb => cb.checked);
              masterInThead.checked = allChecked;
              masterInThead.indeterminate = anyChecked && !allChecked;
            }};
            allRowCheckboxes.forEach(cb => cb.addEventListener('change', updateMasterState));
            // Initial state
            updateMasterState();
          }}
        }}
      }}
    }})();
  </script>
</div>

"""
