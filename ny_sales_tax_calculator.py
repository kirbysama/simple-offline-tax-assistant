#!/usr/bin/env python3
"""Standalone CLI Entrypoint for Credit Card Ingestion & NY Reverse Sales Tax Calculator.

Ingests annual credit card and banking activity CSV/Excel statements, normalizes
schemas, excludes non-spend items, classifies exempt vs. taxable spend, reverse-calculates
New York State and local sales tax paid across all 62 NY counties (defaulting to NYC 8.875%),
and exports an audit-ready multi-tab Excel workbook (NY_Sales_Tax_Report.xlsx).
"""

import argparse
import os
import sys
from typing import List, Optional

from tax_tools.sales_tax_calculator import SalesTaxCalculator
from tax_tools.sales_tax_exporter import SalesTaxExcelExporter
from tax_tools.sales_tax_models import DEFAULT_COUNTY, NY_COUNTY_RATES, SalesTaxReport
from tax_tools.sales_tax_pipeline import find_activity_directory


def collect_activity_files(inputs: Optional[List[str]]) -> List[str]:
    """Resolves input arguments (file paths or directories) into a list of CSV/Excel files."""
    if not inputs:
        sample_dir = find_activity_directory()
        if not sample_dir:
            raise FileNotFoundError(
                "No activity statements directory found. Please specify CSV/Excel files or an input directory, "
                "or place files in 'Sample Activity Statements/'."
            )
        inputs = [sample_dir]

    files: List[str] = []
    supported_exts = (".csv", ".xlsx", ".xls")

    for item in inputs:
        if os.path.isdir(item):
            for fname in sorted(os.listdir(item)):
                if fname.lower().endswith(supported_exts):
                    files.append(os.path.join(item, fname))
        elif os.path.isfile(item):
            if item.lower().endswith(supported_exts):
                files.append(item)
            else:
                print(f"Warning: Skipping non-activity file: {item}", file=sys.stderr)
        else:
            raise FileNotFoundError(f"Input path does not exist: {item}")

    if not files:
        raise ValueError(f"No CSV or Excel files found in specified inputs: {inputs}")

    return sorted(list(dict.fromkeys(files)))


def process_sales_tax_files(
    files: List[str],
    county_name: str = DEFAULT_COUNTY,
    output_excel: str = "NY_Sales_Tax_Report.xlsx",
    quiet: bool = False,
) -> SalesTaxReport:
    """Processes activity files and generates the Excel audit report."""
    calculator = SalesTaxCalculator(county_name=county_name)
    report = calculator.process_files(files)

    exporter = SalesTaxExcelExporter()
    exporter.export(report, output_excel)

    if not quiet:
        print_summary(report, output_excel)

    return report


def print_summary(report: SalesTaxReport, output_excel: str) -> None:
    """Prints a formatted summary table of transaction classification and sales tax."""
    print("=" * 80)
    print(" NEW YORK SALES TAX CALCULATOR - EXECUTION SUMMARY")
    print("=" * 80)
    print(f"Jurisdiction Selected:     {report.county}")
    print(f"Combined Sales Tax Rate:   {report.tax_rate * 100:.3f}%")
    print(f"Total Transactions:        {report.total_transactions:,}")
    print(f"Spend Transactions:        {len(report.spend_transactions):,}")
    print("-" * 80)
    print(f"Total Gross Spend:         ${report.total_gross_spend:,.2f}")
    print(f"Non-Spend Excluded:        ${report.total_excluded:,.2f}  (Payments, fees, transfers)")
    print(f"Tax-Exempt Spend:          ${report.total_exempt:,.2f}  (Groceries, transit, medical, utilities)")
    print(f"Out-of-State Excluded:     ${report.total_out_of_state:,.2f}  (Airfare, out-of-state lodging)")
    print(f"Net Taxable Spend:         ${report.total_taxable:,.2f}")
    print(f"Calculated Pre-Tax Base:   ${report.total_pre_tax:,.2f}")
    print(f"Deductible NY Sales Tax:   ${report.total_sales_tax_paid:,.2f}")
    print("=" * 80)

    # Top categories breakdown
    summaries = report.category_summaries
    if summaries:
        print("TOP CATEGORIES BY SALES TAX PAID:")
        print(f"{'Category':<32} {'Treatment':<12} {'Gross Spend':<14} {'Tax Paid':<12} {'% of Tax'}")
        print("-" * 80)
        for cat in summaries[:8]:
            pct_str = f"{cat.pct_of_total_tax:.1f}%" if cat.pct_of_total_tax > 0 else "-"
            print(
                f"{cat.category[:30]:<32} "
                f"{cat.treatment[:10]:<12} "
                f"${cat.gross_amount:>10,.2f}   "
                f"${cat.sales_tax_paid:>8,.2f}   "
                f"{pct_str:>6}"
            )
        print("=" * 80)

    print(f"Workbook successfully generated: {os.path.abspath(output_excel)}")
    print("=" * 80)


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="ny_sales_tax_calculator.py",
        description="Ingest credit card activity files and calculate New York reverse sales tax.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Path(s) to activity CSV/Excel files or directory (default: Sample Activity Statements/).",
    )
    parser.add_argument(
        "-i", "--input",
        dest="input_opt",
        help="Input directory or statement file path.",
    )
    parser.add_argument(
        "-c", "--county",
        default=DEFAULT_COUNTY,
        help="New York county jurisdiction (default: %(default)s).",
    )
    parser.add_argument(
        "-o", "--output",
        default="NY_Sales_Tax_Report.xlsx",
        help="Output Excel report path (default: NY_Sales_Tax_Report.xlsx).",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress verbose summary output.",
    )
    parser.add_argument(
        "--list-counties",
        action="store_true",
        help="List all 62 New York counties and their sales tax rates, then exit.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_counties:
        print("=" * 50)
        print("NEW YORK COUNTIES AND COMBINED SALES TAX RATES")
        print("=" * 50)
        for county, rate in sorted(NY_COUNTY_RATES.items()):
            print(f"{county:<40} {rate*100:6.3f}%")
        return 0

    raw_inputs = list(args.inputs)
    if args.input_opt:
        raw_inputs.append(args.input_opt)

    try:
        activity_files = collect_activity_files(raw_inputs if raw_inputs else None)
        process_sales_tax_files(
            files=activity_files,
            county_name=args.county,
            output_excel=args.output,
            quiet=args.quiet,
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
