#!/usr/bin/env python3
"""Standalone CLI Entrypoint for 1099 Multi-Brokerage Aggregator & Tax Parser.

Extracts Form 8949 capital gains/losses, Form 1099-INT interest (isolating NY-exempt
U.S. Treasury interest), and Form 1099-DIV dividends across all brokerages into a
consolidated Excel workbook (1099_Tax_Summary.xlsx).
"""

import argparse
import os
import sys
from typing import List, Optional

from tax_tools.models import AggregationReport, BrokerageAccountStatement
from tax_tools.parser_1099 import parse_1099_pdf, parse_1099_pdf_batch
from tax_tools.validator import validate_statement_parity
from tax_tools.excel_exporter import export_1099_excel
from tax_tools.scanner import find_sample_directory
from tax_tools.formatter import format_brokerage_display_name


def collect_pdf_files(inputs: Optional[List[str]]) -> List[str]:
    """Resolves input arguments (file paths or directories) into a sorted list of PDF files."""
    if not inputs:
        sample_dir = find_sample_directory()
        if not sample_dir:
            raise FileNotFoundError(
                "No 1099 input directory found. Please specify PDF files or an input directory, "
                "or place files in 'Sample Form 1099/'."
            )
        inputs = [sample_dir]

    pdf_files: List[str] = []
    for item in inputs:
        if os.path.isdir(item):
            for fname in sorted(os.listdir(item)):
                if fname.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(item, fname))
        elif os.path.isfile(item):
            if item.lower().endswith(".pdf"):
                pdf_files.append(item)
            else:
                print(f"Warning: Skipping non-PDF file: {item}", file=sys.stderr)
        else:
            raise FileNotFoundError(f"Input path does not exist: {item}")

    if not pdf_files:
        raise ValueError(f"No PDF files located in specified inputs: {inputs}")

    return sorted(list(dict.fromkeys(pdf_files)))


def process_1099_files(
    pdf_files: List[str],
    output_excel: str = "1099_Tax_Summary.xlsx",
    quiet: bool = False,
) -> AggregationReport:
    """Parses, validates, aggregates, and exports 1099 PDF files to Excel."""
    all_statements: List[BrokerageAccountStatement] = []
    batch_results = parse_1099_pdf_batch(pdf_files)
    for pdf_path, statements, error in batch_results:
        if error:
            print(f"Error parsing '{pdf_path}': {error}", file=sys.stderr)
            continue
        for stmt in statements:
            errors = validate_statement_parity(stmt)
            if errors:
                stmt.notes.extend(errors)
            all_statements.append(stmt)

    report = AggregationReport(statements=all_statements)
    if report.rejected_statements and not quiet:
        for rej in report.rejected_statements:
            src = f" from '{rej.source_file}'" if rej.source_file else ""
            print(f"Warning: Rejected duplicate statement: {rej.brokerage_name} (Account {rej.account_number}){src}", file=sys.stderr)

    # Export to Excel
    export_1099_excel(report, output_excel)

    if not quiet:
        print_summary(report, output_excel)

    return report


def print_summary(report: AggregationReport, output_excel: str) -> None:
    """Prints a formatted summary table of parsed accounts and aggregate totals."""
    print("=" * 132)
    print(" 1099 CONSOLIDATED TAX AGGREGATOR - EXECUTION SUMMARY")
    print("=" * 132)
    print(f"{'Brokerage Name':<18} {'Account #':<12} {'ST Net':<12} {'LT Net':<12} {'Total Net':<13} {'ST Wash':<11} {'LT Wash':<11} {'Tot Wash':<11} {'Ord Int':<10} {'US Treas':<10} {'Parity'}")
    print("-" * 132)

    for stmt in report.statements:
        st_gl = stmt.form_8949.short_term_total.net_gain_loss
        lt_gl = stmt.form_8949.long_term_total.net_gain_loss
        tot_gl = stmt.form_8949.grand_total.net_gain_loss
        st_wash = stmt.form_8949.short_term_total.wash_sale_disallowed
        lt_wash = stmt.form_8949.long_term_total.wash_sale_disallowed
        tot_wash = stmt.form_8949.total_wash_sale_disallowed
        ord_int = stmt.form_1099_int.box_1_interest
        ust_int = stmt.form_1099_int.box_3_us_treasury
        parity_str = "PASS" if stmt.parity_passed else "CHECK"
        st_str = f"${st_gl:,.2f}" if st_gl >= 0 else f"-${abs(st_gl):,.2f}"
        lt_str = f"${lt_gl:,.2f}" if lt_gl >= 0 else f"-${abs(lt_gl):,.2f}"
        tot_str = f"${tot_gl:,.2f}" if tot_gl >= 0 else f"-${abs(tot_gl):,.2f}"
        st_wash_str = f"${st_wash:,.2f}" if st_wash > 0 else "$0.00"
        lt_wash_str = f"${lt_wash:,.2f}" if lt_wash > 0 else "$0.00"
        tot_wash_str = f"${tot_wash:,.2f}" if tot_wash > 0 else "$0.00"
        print(
            f"{stmt.brokerage_name[:17]:<18} "
            f"{stmt.account_number[:11]:<12} "
            f"{st_str:<12} "
            f"{lt_str:<12} "
            f"{tot_str:<13} "
            f"{st_wash_str:<11} "
            f"{lt_wash_str:<11} "
            f"{tot_wash_str:<11} "
            f"${ord_int:,.2f} "
            f"${ust_int:,.2f} "
            f"{parity_str}"
        )

    print("=" * 132)
    agg_8949 = report.aggregate_8949
    st_gl = agg_8949.short_term_total.net_gain_loss
    lt_gl = agg_8949.long_term_total.net_gain_loss
    grand_gl = agg_8949.grand_total.net_gain_loss
    st_wash_total = agg_8949.short_term_total.wash_sale_disallowed
    lt_wash_total = agg_8949.long_term_total.wash_sale_disallowed
    total_wash = agg_8949.total_wash_sale_disallowed
    agg_int = report.aggregate_int
    agg_div = report.aggregate_div

    print(f"Total Brokerage Statements Parsed: {len(report.statements)}")
    print(f"All Mathematical Parity Passed:   {report.all_parity_passed}")
    print("-" * 132)
    print(f"Form 8949 Part I Short-Term Net:    ${st_gl:,.2f}" if st_gl >= 0 else f"Form 8949 Part I Short-Term Net:   -${abs(st_gl):,.2f}")
    print(f"Form 8949 Part II Long-Term Net:   ${lt_gl:,.2f}" if lt_gl >= 0 else f"Form 8949 Part II Long-Term Net:  -${abs(lt_gl):,.2f}")
    print(f"Form 8949 Combined Net Gain/(Loss): ${grand_gl:,.2f}" if grand_gl >= 0 else f"Form 8949 Combined Net Gain/(Loss):-${abs(grand_gl):,.2f}")
    print(f"Short-Term Wash Sales Disallowed:   ${st_wash_total:,.2f}")
    print(f"Long-Term Wash Sales Disallowed:    ${lt_wash_total:,.2f}")
    print(f"Total Form 1099-B Wash Disallowed:  ${total_wash:,.2f}")
    print(f"Form 1099-INT Ordinary Interest:    ${agg_int.box_1_interest:,.2f}")
    print(f"Form 1099-INT US Treasury (NY S-102):${agg_int.box_3_us_treasury:,.2f}  [Exempt from NY State Tax]")
    print(f"Form 1099-DIV Ordinary Dividends:   ${agg_div.box_1a_ordinary_dividends:,.2f}")
    print(f"Form 1099-DIV Qualified Dividends:  ${agg_div.box_1b_qualified_dividends:,.2f}")

    if report.rejected_statements:
        print("-" * 132)
        print(f" REJECTED DUPLICATE STATEMENTS: {len(report.rejected_statements)} (EXCLUDED FROM TOTALS & EXPORT)")
        for rej in report.rejected_statements:
            src = f" [Source: {rej.source_file}]" if rej.source_file else ""
            print(f"  • {rej.brokerage_name} (Account: {rej.account_number}){src}")

    print("=" * 102)
    print(f"Workbook successfully generated: {os.path.abspath(output_excel)}")
    print("=" * 102)


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="tax_1099_parser.py",
        description="Extract Form 8949, 1099-INT, and 1099-DIV data from multi-brokerage PDFs into Excel.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Path(s) to 1099 PDF files or directory containing PDF files (default: Sample Form 1099/).",
    )
    parser.add_argument(
        "-i", "--input",
        dest="input_opt",
        help="Input directory or PDF file path.",
    )
    parser.add_argument(
        "-o", "--output",
        default="1099_Tax_Summary.xlsx",
        help="Output Excel workbook file path (default: 1099_Tax_Summary.xlsx).",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress verbose summary output.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    raw_inputs = list(args.inputs)
    if args.input_opt:
        raw_inputs.append(args.input_opt)

    try:
        pdf_files = collect_pdf_files(raw_inputs if raw_inputs else None)
        process_1099_files(
            pdf_files=pdf_files,
            output_excel=args.output,
            quiet=args.quiet,
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
