"""Streamlit Web Dashboard for Tax Tools.

Unified local web application providing independent interactive interfaces for:
1. 1099 Tax Aggregator (Form 8949, 1099-INT, 1099-DIV multi-brokerage consolidation)
2. NY Sales Tax Calculator (credit card activity normalization & reverse sales tax calculation)
"""

import io
import os
import tempfile
from typing import List, Optional

import pandas as pd
import streamlit as st

from tax_tools.excel_exporter import export_1099_excel
from tax_tools.models import AggregationReport, BrokerageAccountStatement
from tax_tools.parser_1099 import parse_1099_pdf, parse_1099_pdf_batch
from tax_tools.sales_tax_calculator import SalesTaxCalculator
from tax_tools.sales_tax_exporter import SalesTaxExcelExporter
from tax_tools.sales_tax_models import DEFAULT_COUNTY, NY_COUNTY_RATES, SalesTaxReport
from tax_tools.sales_tax_pipeline import find_activity_directory
from tax_tools.scanner import find_sample_directory
from tax_tools.validator import validate_statement_parity
from tax_tools.formatter import format_brokerage_display_name, render_summary_table_html


# Configure Page
st.set_page_config(
    page_title="Tax Assistant - 1099 Aggregator & NY Sales Tax",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)


def format_currency(val: float) -> str:
    """Format float into standard currency representation."""
    if val < 0:
        return f"-${abs(val):,.2f}"
    return f"${val:,.2f}"


def process_1099_paths(file_paths: List[str]) -> tuple[AggregationReport, bytes]:
    """Parses 1099 PDF paths, validates parity, and generates Excel in-memory bytes."""
    all_statements: List[BrokerageAccountStatement] = []
    batch_results = parse_1099_pdf_batch(file_paths)
    for pdf_path, statements, error in batch_results:
        if error:
            st.error(f"Error parsing '{os.path.basename(pdf_path)}': {error}")
            continue
        for stmt in statements:
            errors = validate_statement_parity(stmt)
            if errors:
                stmt.notes.extend(errors)
            all_statements.append(stmt)

    report = AggregationReport(statements=all_statements)
    buf = io.BytesIO()
    export_1099_excel(report, buf)
    buf.seek(0)
    return report, buf.getvalue()


def process_sales_tax_paths(file_paths: List[str], county_name: str) -> tuple[SalesTaxReport, bytes]:
    """Ingests credit card activity files, calculates sales tax, and generates Excel in-memory bytes."""
    calculator = SalesTaxCalculator(county_name=county_name)
    report = calculator.process_files(file_paths)
    buf = io.BytesIO()
    exporter = SalesTaxExcelExporter()
    exporter.export(report, buf)
    buf.seek(0)
    return report, buf.getvalue()


def build_1099_summary_df(report: AggregationReport) -> pd.DataFrame:
    """Builds interactive summary DataFrame for 1099 statements preview."""
    rows = []
    for s in report.statements:
        st_box = s.form_8949.short_term_total
        lt_box = s.form_8949.long_term_total
        grand_box = s.form_8949.grand_total
        st_wash = st_box.wash_sale_disallowed
        lt_wash = lt_box.wash_sale_disallowed
        tot_wash = s.form_8949.total_wash_sale_disallowed
        ord_int = s.form_1099_int.box_1_interest
        ust_int = s.form_1099_int.box_3_us_treasury
        rows.append({
            "Brokerage Name": format_brokerage_display_name(s.brokerage_name, s.account_number),
            "Account #": s.account_number,
            "ST Proceeds": format_currency(st_box.proceeds),
            "ST Basis": format_currency(st_box.cost_basis),
            "ST Wash Sale": format_currency(st_wash),
            "ST Net": format_currency(st_box.net_gain_loss),
            "LT Proceeds": format_currency(lt_box.proceeds),
            "LT Basis": format_currency(lt_box.cost_basis),
            "LT Wash Sale": format_currency(lt_wash),
            "LT Net": format_currency(lt_box.net_gain_loss),
            "Total Proceeds": format_currency(grand_box.proceeds),
            "Total Cost Basis": format_currency(grand_box.cost_basis),
            "Total Wash Sale": format_currency(tot_wash),
            "Total Net": format_currency(grand_box.net_gain_loss),
            "Box 1 Interest Income": format_currency(ord_int),
            "Box 3 - Savings Bonds and Treasury Interest": format_currency(ust_int),
            "Clearing Firm": s.clearing_firm or "-",
            "Parity Status": "PASS" if s.parity_passed else "REVIEW",
        })
    return pd.DataFrame(rows)


def highlight_wash_sales(val):
    """Styles wash sale amount in red font and soft red background if non-zero."""
    try:
        # Check if float or string with currency
        if isinstance(val, (int, float)):
            is_positive = val > 0
        else:
            cleaned = str(val).replace("$", "").replace(",", "").replace("-", "").strip()
            is_positive = float(cleaned) > 0 if cleaned else False
        if is_positive:
            return "background-color: #FFC7CE; color: #9C0006; font-weight: bold;"
    except Exception:
        pass
    return ""


def render_1099_tab() -> None:
    """Renders Tab 1: 1099 Multi-Brokerage Tax Aggregator."""
    st.header("📑 1099 Tax Aggregator")
    st.markdown(
        "Consolidate multiple brokerage consolidated 1099 PDF statements locally and deterministically. "
        "Extracts **IRS Form 8949** summary totals (Boxes A–F), **Form 1099-INT** interest "
        "(isolating NY Form IT-201 S-102 tax-exempt U.S. Treasury interest), and **Form 1099-DIV** distributions."
    )

    st.info(
        "⚠️ **Official PDF Requirement:** Statements must be official PDF downloads obtained directly from your "
        "financial institution or brokerage. Scanned documents, photos, or mobile captures may fail or extract data "
        "incorrectly because exact digital text layers and layout structures are required."
    )

    col_up, col_actions = st.columns([3, 1])

    with col_up:
        uploader_key = f"1099_file_uploader_{st.session_state.get('1099_uploader_key', 0)}"
        uploaded_pdfs = st.file_uploader(
            "Upload 1099 forms (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            key=uploader_key,
            help="Select one or more consolidated 1099 PDFs from any covered brokerage.",
        )

    with col_actions:
        st.write("")
        st.write("")
        sample_dir_1099 = "Sample Form 1099" if os.path.isdir("Sample Form 1099") else None
        sample_dir_int = "Sample 1099-INT" if os.path.isdir("Sample 1099-INT") else None

        use_sample = st.button(
            "📂 Load Sample 1099s",
            disabled=not (sample_dir_1099 or sample_dir_int),
            help="Loads sample statements from Sample Form 1099/ and Sample 1099-INT/.",
            use_container_width=True,
        )

        clear_btn = st.button(
            "Clear",
            help="Reset uploaded 1099 PDF list and clear existing parsed state.",
            use_container_width=True,
        )

        if clear_btn:
            st.session_state.pop("1099_report", None)
            st.session_state.pop("1099_excel_bytes", None)
            st.session_state.pop("1099_summary_df", None)
            st.session_state["1099_uploader_key"] = st.session_state.get("1099_uploader_key", 0) + 1
            st.rerun()

    btn_process = st.button("🚀 Process 1099s", type="primary", use_container_width=False)

    if btn_process or use_sample:
        files_to_process: List[str] = []
        temp_dir_obj: Optional[tempfile.TemporaryDirectory] = None

        if uploaded_pdfs and not use_sample:
            temp_dir_obj = tempfile.TemporaryDirectory()
            for uf in uploaded_pdfs:
                temp_path = os.path.join(temp_dir_obj.name, uf.name)
                with open(temp_path, "wb") as f:
                    f.write(uf.getbuffer())
                files_to_process.append(temp_path)
        elif use_sample:
            sample_dirs_to_load = [d for d in [sample_dir_1099, sample_dir_int] if d and os.path.isdir(d)]
            for s_dir in sample_dirs_to_load:
                for f in sorted(os.listdir(s_dir)):
                    if f.lower().endswith(".pdf"):
                        files_to_process.append(os.path.join(s_dir, f))
        elif uploaded_pdfs:
            temp_dir_obj = tempfile.TemporaryDirectory()
            for uf in uploaded_pdfs:
                temp_path = os.path.join(temp_dir_obj.name, uf.name)
                with open(temp_path, "wb") as f:
                    f.write(uf.getbuffer())
                files_to_process.append(temp_path)
        else:
            st.warning("Please upload one or more 1099 PDF files or click 'Load Sample 1099s'.")
            return

        with st.spinner("Extracting summary tables across statements deterministically..."):
            report, excel_bytes = process_1099_paths(files_to_process)
            st.session_state["1099_report"] = report
            st.session_state["1099_excel_bytes"] = excel_bytes
            st.session_state["1099_summary_df"] = build_1099_summary_df(report)

        if temp_dir_obj:
            temp_dir_obj.cleanup()

    # Render results if available in session state
    if "1099_report" in st.session_state and st.session_state["1099_report"] is not None:
        report: AggregationReport = st.session_state["1099_report"]
        excel_bytes: bytes = st.session_state["1099_excel_bytes"]
        summary_df: pd.DataFrame = st.session_state["1099_summary_df"]

        st.divider()

        if report.rejected_statements:
            for rej in report.rejected_statements:
                src_str = f" from `{os.path.basename(rej.source_file)}`" if rej.source_file else ""
                st.warning(
                    f"⚠️ **Duplicate Statement Rejected:** {rej.brokerage_name} (Account {rej.account_number}){src_str} "
                    f"matches an already ingested statement and was excluded from aggregate totals and preview."
                )

        # Download button placed at the top of results
        st.download_button(
            label="💾 Download 1099_Tax_Summary.xlsx",
            data=excel_bytes,
            file_name="1099_Tax_Summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=False,
        )

        # KPI Metrics
        agg_8949 = report.aggregate_8949
        agg_int = report.aggregate_int
        agg_div = report.aggregate_div
        total_wash_disallowed = agg_8949.total_wash_sale_disallowed

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Statements Parsed", len(report.statements))
        m2.metric(
            "Parity Check",
            "PASSED" if report.all_parity_passed else "ATTENTION NEEDED",
            help="Confirms math consistency (Proceeds minus Cost Basis plus Adjustments equals Net Gain/Loss) across all statements.",
        )
        m3.metric("Net Capital Gain/(Loss)", format_currency(agg_8949.grand_total.net_gain_loss))
        m4.metric(
            "Wash Sales Disallowed",
            format_currency(total_wash_disallowed),
            help="IRS Form 1099-B Box 1g / Form 8949 column (g) wash sale loss disallowed amounts.",
        )
        m5.metric("Ordinary Interest (Box 1)", format_currency(agg_int.box_1_interest))
        m6.metric(
            "US Treasury Interest (Box 3)",
            format_currency(agg_int.box_3_us_treasury),
            help="Exempt from New York State tax (Form IT-201 line 28 / subtraction S-102)",
        )

        st.subheader("Interactive Summary Table Preview")
        st.caption(
            "📋 Click any table cell (except headers) to copy its value instantly. "
            "Hover over a cell to underline the text and reveal the clipboard icon. "
            "Currency figures are automatically stripped of '$' for direct entry into tax filing software."
        )
        # Render custom interactive preview table with click-to-copy cells
        st.html(render_summary_table_html(summary_df), unsafe_allow_javascript=True)

        # Also support collapsible raw dataframe view
        with st.expander("🔍 View Raw Tabular Data Grid", expanded=False):
            wash_cols = [c for c in ["ST Wash Sale", "LT Wash Sale", "Total Wash Sale"] if c in summary_df.columns]
            styled_df = summary_df.style.map(highlight_wash_sales, subset=wash_cols)
            st.dataframe(styled_df, width="stretch", hide_index=True)

        with st.expander("📊 View Consolidated Form 8949 Schedule Totals", expanded=False):
            f8949_data = [
                {"Category": "Part I: Box A (Short-Term Reported)", "Proceeds": agg_8949.box_a.proceeds, "Cost Basis": agg_8949.box_a.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.box_a.wash_sale_disallowed, "Adjustments": agg_8949.box_a.adjustments, "Net Gain/(Loss)": agg_8949.box_a.net_gain_loss, "Parity": "PASS" if agg_8949.box_a.is_parity_valid else "FAIL"},
                {"Category": "Part I: Box B (Short-Term Non-Reported)", "Proceeds": agg_8949.box_b.proceeds, "Cost Basis": agg_8949.box_b.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.box_b.wash_sale_disallowed, "Adjustments": agg_8949.box_b.adjustments, "Net Gain/(Loss)": agg_8949.box_b.net_gain_loss, "Parity": "PASS" if agg_8949.box_b.is_parity_valid else "FAIL"},
                {"Category": "Part I: Box C (Short-Term Not Received)", "Proceeds": agg_8949.box_c.proceeds, "Cost Basis": agg_8949.box_c.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.box_c.wash_sale_disallowed, "Adjustments": agg_8949.box_c.adjustments, "Net Gain/(Loss)": agg_8949.box_c.net_gain_loss, "Parity": "PASS" if agg_8949.box_c.is_parity_valid else "FAIL"},
                {"Category": "Part I Short-Term Total", "Proceeds": agg_8949.short_term_total.proceeds, "Cost Basis": agg_8949.short_term_total.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.short_term_total.wash_sale_disallowed, "Adjustments": agg_8949.short_term_total.adjustments, "Net Gain/(Loss)": agg_8949.short_term_total.net_gain_loss, "Parity": "PASS" if agg_8949.short_term_total.is_parity_valid else "FAIL"},
                {"Category": "Part II: Box D (Long-Term Reported)", "Proceeds": agg_8949.box_d.proceeds, "Cost Basis": agg_8949.box_d.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.box_d.wash_sale_disallowed, "Adjustments": agg_8949.box_d.adjustments, "Net Gain/(Loss)": agg_8949.box_d.net_gain_loss, "Parity": "PASS" if agg_8949.box_d.is_parity_valid else "FAIL"},
                {"Category": "Part II: Box E (Long-Term Non-Reported)", "Proceeds": agg_8949.box_e.proceeds, "Cost Basis": agg_8949.box_e.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.box_e.wash_sale_disallowed, "Adjustments": agg_8949.box_e.adjustments, "Net Gain/(Loss)": agg_8949.box_e.net_gain_loss, "Parity": "PASS" if agg_8949.box_e.is_parity_valid else "FAIL"},
                {"Category": "Part II: Box F (Long-Term Not Received)", "Proceeds": agg_8949.box_f.proceeds, "Cost Basis": agg_8949.box_f.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.box_f.wash_sale_disallowed, "Adjustments": agg_8949.box_f.adjustments, "Net Gain/(Loss)": agg_8949.box_f.net_gain_loss, "Parity": "PASS" if agg_8949.box_f.is_parity_valid else "FAIL"},
                {"Category": "Part II Long-Term Total", "Proceeds": agg_8949.long_term_total.proceeds, "Cost Basis": agg_8949.long_term_total.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.long_term_total.wash_sale_disallowed, "Adjustments": agg_8949.long_term_total.adjustments, "Net Gain/(Loss)": agg_8949.long_term_total.net_gain_loss, "Parity": "PASS" if agg_8949.long_term_total.is_parity_valid else "FAIL"},
                {"Category": "Grand Total (Schedule D)", "Proceeds": agg_8949.grand_total.proceeds, "Cost Basis": agg_8949.grand_total.cost_basis, "Wash Sale Disallowed (1g)": agg_8949.grand_total.wash_sale_disallowed, "Adjustments": agg_8949.grand_total.adjustments, "Net Gain/(Loss)": agg_8949.grand_total.net_gain_loss, "Parity": "PASS" if agg_8949.grand_total.is_parity_valid else "FAIL"},
            ]
            f8949_df = pd.DataFrame(f8949_data)
            styled_f8949 = f8949_df.style.map(highlight_wash_sales, subset=["Wash Sale Disallowed (1g)"])
            st.dataframe(styled_f8949, width="stretch", hide_index=True)

        with st.expander("💰 View Interest & Dividends Summary", expanded=False):
            c_int, c_div = st.columns(2)
            with c_int:
                st.write("**Form 1099-INT Summary**")
                st.write(f"- Box 1 (Total Ordinary Interest): **${agg_int.box_1_interest:,.2f}**")
                st.write(f"- Box 3 (U.S. Treasury Obligations): **${agg_int.box_3_us_treasury:,.2f}** *(NY IT-201 Line 28 Subtraction)*")
                st.write(f"- Box 8 (Tax-Exempt Interest): **${agg_int.box_8_tax_exempt:,.2f}**")
                st.write(f"- Total Interest Income: **${agg_int.total_interest:,.2f}**")
            with c_div:
                st.write("**Form 1099-DIV Summary**")
                st.write(f"- Box 1a (Total Ordinary Dividends): **${agg_div.box_1a_ordinary_dividends:,.2f}**")
                st.write(f"- Box 1b (Qualified Dividends): **${agg_div.box_1b_qualified_dividends:,.2f}**")
                st.write(f"- Box 5 (Section 199A Dividends): **${agg_div.box_5_section_199a:,.2f}**")


def render_sales_tax_tab() -> None:
    """Renders Tab 2: Credit Card Ingestion & Bank/Card Statement Reverse Sales Tax Calculator."""
    st.header("💳 Bank/Card Statement Reverse Sales Tax Calculator")
    st.markdown(
        "Ingest annual credit card activity CSV/Excel statements, auto-detect bank schemas, "
        "exclude non-spend transactions, categorize tax-exempt purchases, net returns with negative sales tax, "
        "and calculate deductible New York State and local sales tax paid across all 62 NY counties."
    )

    col_up, col_config = st.columns([3, 2])

    with col_up:
        uploaded_activity = st.file_uploader(
            "Upload Credit Card Activity Statements (CSV / Excel)",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key="sales_tax_file_uploader",
            help="Accepts Chase, Amex, Citi, Discover, Capital One, BofA, Apple Card, or generic CSV/Excel activity exports.",
        )

    county_options = list(NY_COUNTY_RATES.keys())
    default_idx = county_options.index(DEFAULT_COUNTY) if DEFAULT_COUNTY in county_options else 0

    with col_config:
        selected_county = st.selectbox(
            "Select New York County Jurisdiction",
            options=county_options,
            index=default_idx,
            key="sales_tax_county_selector",
            help="Covers all 62 New York counties with statutory combined sales tax rates.",
        )

        sample_act_dir = find_activity_directory()
        has_act_samples = sample_act_dir is not None and os.path.isdir(sample_act_dir)
        use_act_sample = st.button(
            "📂 Load Sample Statements",
            disabled=not has_act_samples,
            help="Loads 6 sample card/checking statements from Sample Activity Statements/.",
            use_container_width=True,
        )

    btn_calculate = st.button("🧮 Calculate NY Sales Tax", type="primary", use_container_width=False)

    if btn_calculate or use_act_sample:
        files_to_process: List[str] = []
        temp_dir_obj: Optional[tempfile.TemporaryDirectory] = None

        if uploaded_activity and not use_act_sample:
            temp_dir_obj = tempfile.TemporaryDirectory()
            for uf in uploaded_activity:
                temp_path = os.path.join(temp_dir_obj.name, uf.name)
                with open(temp_path, "wb") as f:
                    f.write(uf.getbuffer())
                files_to_process.append(temp_path)
        elif use_act_sample and has_act_samples:
            files_to_process = [
                os.path.join(sample_act_dir, f)
                for f in sorted(os.listdir(sample_act_dir))
                if f.lower().endswith((".csv", ".xlsx", ".xls"))
            ]
        elif uploaded_activity:
            temp_dir_obj = tempfile.TemporaryDirectory()
            for uf in uploaded_activity:
                temp_path = os.path.join(temp_dir_obj.name, uf.name)
                with open(temp_path, "wb") as f:
                    f.write(uf.getbuffer())
                files_to_process.append(temp_path)
        else:
            st.warning("Please upload one or more activity files (CSV/Excel) or click 'Load Sample Statements'.")
            return

        with st.spinner("Normalizing bank statements and computing reverse sales tax..."):
            report, excel_bytes = process_sales_tax_paths(files_to_process, selected_county)
            st.session_state["sales_tax_report"] = report
            st.session_state["sales_tax_excel_bytes"] = excel_bytes

        if temp_dir_obj:
            temp_dir_obj.cleanup()

    # Render results if available in session state
    if "sales_tax_report" in st.session_state and st.session_state["sales_tax_report"] is not None:
        report: SalesTaxReport = st.session_state["sales_tax_report"]
        excel_bytes: bytes = st.session_state["sales_tax_excel_bytes"]

        st.divider()

        # Single-click download button
        st.download_button(
            label="💾 Download NY_Sales_Tax_Report.xlsx",
            data=excel_bytes,
            file_name="NY_Sales_Tax_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=False,
        )

        # Real-time KPI Metric Cards as specified in Ticket 04:
        # (Total Spend, Excluded, Exempt, Taxable, Total NY Sales Tax Paid)
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Total Spend", format_currency(report.total_gross_spend), help="Net spending on goods & services")
        kpi2.metric("Excluded", format_currency(report.total_excluded), help="Non-spend payments, fees, transfers")
        kpi3.metric("Exempt", format_currency(report.total_exempt), help="Groceries, medicine, transit, utilities")
        kpi4.metric("Taxable", format_currency(report.total_taxable), help="Qualifying purchases subject to sales tax")
        kpi5.metric(
            "Total NY Sales Tax Paid",
            format_currency(report.total_sales_tax_paid),
            help=f"Calculated at {report.tax_rate*100:.3f}% combined rate for {report.county}",
        )

        st.subheader("Category Breakdown & Audit Trail")
        cat_summaries = report.category_summaries
        if cat_summaries:
            cat_df = pd.DataFrame([
                {
                    "Category": cs.category,
                    "Treatment": cs.treatment,
                    "Transaction Count": cs.transaction_count,
                    "Gross Spend": cs.gross_amount,
                    "Taxable Amount": cs.taxable_amount,
                    "Sales Tax Paid": cs.sales_tax_paid,
                    "% of Total Tax": cs.pct_of_total_tax / 100.0,
                }
                for cs in cat_summaries
            ])
            st.dataframe(
                cat_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Gross Spend": st.column_config.NumberColumn("Gross Spend", format="$%.2f"),
                    "Taxable Amount": st.column_config.NumberColumn("Taxable Amount", format="$%.2f"),
                    "Sales Tax Paid": st.column_config.NumberColumn("Sales Tax Paid", format="$%.2f"),
                    "% of Total Tax": st.column_config.NumberColumn("% of Total Tax", format="%.1f%%"),
                },
            )

        with st.expander("📋 Itemized Transaction Ledger Preview", expanded=False):
            search_query = st.text_input("Filter transactions by description or merchant:", "")
            filtered_txns = report.transactions
            if search_query:
                filtered_txns = [
                    t for t in filtered_txns
                    if search_query.lower() in t.description.lower()
                    or search_query.lower() in t.category.lower()
                ]

            ledger_df = pd.DataFrame([
                {
                    "Date": t.date,
                    "Description": t.description,
                    "Amount": t.amount,
                    "Category": t.category,
                    "Treatment": t.treatment.value,
                    "Pre-Tax Amount": t.pre_tax_amount if t.is_taxable else 0.0,
                    "NY Sales Tax": t.sales_tax if t.is_taxable else 0.0,
                    "Bank / Account": f"{t.source_bank} ({t.source_account})",
                    "Classification Reason": t.classification_reason,
                }
                for t in filtered_txns[:500]  # Cap preview at 500 for UI responsiveness
            ])
            st.dataframe(
                ledger_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
                    "Pre-Tax Amount": st.column_config.NumberColumn("Pre-Tax Amount", format="$%.2f"),
                    "NY Sales Tax": st.column_config.NumberColumn("NY Sales Tax", format="$%.2f"),
                },
            )


def main():
    """Main Streamlit application entrypoint."""
    st.title("💼 Deterministic Tax Assistant")
    st.caption(
        "Secure, local, zero-AI-runtime tools for bulk-extracting tax-time data from multi-brokerage 1099s & New York Sales Tax deductions. "
        "Uses pattern-matching and filter lists, so it may make mistakes with formats that it wasn't taught, and it may become outdated as formats change."
    )

    tab1099, tab_sales_tax = st.tabs(["📑 1099 Tax Aggregator", "💳 Bank/Card Statement Reverse Sales Tax Calculator"])

    with tab1099:
        render_1099_tab()

    with tab_sales_tax:
        render_sales_tax_tab()


if __name__ == "__main__":
    main()
