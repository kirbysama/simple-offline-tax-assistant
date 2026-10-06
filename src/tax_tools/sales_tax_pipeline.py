"""Pipeline and CLI runner for Credit Card Ingestion and NY Sales Tax Calculator."""

import os
import sys
from pathlib import Path
from typing import List, Optional

from tax_tools.sales_tax_calculator import SalesTaxCalculator
from tax_tools.sales_tax_exporter import SalesTaxExcelExporter
from tax_tools.sales_tax_models import DEFAULT_COUNTY, SalesTaxReport


DEFAULT_ACTIVITY_DIRS = [
    "Sample Activity Statements",
    "samples/activity",
    "activity",
    "data/activity",
]


def find_activity_directory(explicit_dir: Optional[str] = None) -> Optional[str]:
    """Find a directory containing credit card activity CSV/Excel statements."""
    if explicit_dir and os.path.isdir(explicit_dir):
        return explicit_dir

    for candidate in DEFAULT_ACTIVITY_DIRS:
        if os.path.isdir(candidate):
            files = [
                f for f in os.listdir(candidate)
                if f.lower().endswith((".csv", ".xlsx", ".xls"))
            ]
            if files:
                return candidate

    return None


def run_sales_tax_pipeline(
    input_dir: Optional[str] = None,
    county_name: str = DEFAULT_COUNTY,
    output_excel: str = "NY_Sales_Tax_Report.xlsx",
) -> SalesTaxReport:
    """Executes the end-to-end credit card ingestion, classification, reverse tax calculation, and Excel export."""
    activity_dir = find_activity_directory(input_dir)
    if not activity_dir:
        raise FileNotFoundError(
            "No credit card activity directory found. Please supply CSV or Excel activity statements in "
            "a designated directory (e.g. 'Sample Activity Statements/')."
        )

    files = [
        os.path.join(activity_dir, f)
        for f in sorted(os.listdir(activity_dir))
        if f.lower().endswith((".csv", ".xlsx", ".xls"))
    ]

    if not files:
        raise ValueError(f"No activity files found in directory: {activity_dir}")

    calculator = SalesTaxCalculator(county_name=county_name)
    report = calculator.process_files(files)

    exporter = SalesTaxExcelExporter()
    exporter.export(report, output_excel)

    return report


if __name__ == "__main__":
    county = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COUNTY
    report = run_sales_tax_pipeline(county_name=county)
    print("=" * 60)
    print("NEW YORK SALES TAX CALCULATOR - EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Jurisdiction:             {report.county}")
    print(f"Combined Tax Rate:        {report.tax_rate*100:.3f}%")
    print(f"Total Transactions:       {report.total_transactions}")
    print(f"Total Gross Spend:        ${report.total_gross_spend:,.2f}")
    print(f"Non-Spend Excluded:       ${report.total_excluded:,.2f}")
    print(f"Tax-Exempt Spend:         ${report.total_exempt:,.2f}")
    print(f"Out-of-State Excluded:    ${report.total_out_of_state:,.2f}")
    print(f"Net Taxable Spend:        ${report.total_taxable:,.2f}")
    print(f"Pre-Tax Base:             ${report.total_pre_tax:,.2f}")
    print(f"Deductible NY Sales Tax:  ${report.total_sales_tax_paid:,.2f}")
    print("=" * 60)
    print("Workbook generated: NY_Sales_Tax_Report.xlsx")
