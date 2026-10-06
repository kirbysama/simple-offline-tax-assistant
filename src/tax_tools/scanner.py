"""Ingestion pipeline for 1099 tax sample forms."""

import os
import sys
from typing import List, Optional
from tax_tools.models import AggregationReport, BrokerageAccountStatement
from tax_tools.parser_1099 import parse_1099_pdf, parse_1099_pdf_batch
from tax_tools.validator import validate_statement_parity
from tax_tools.excel_exporter import export_1099_excel


DEFAULT_SAMPLE_DIRS = [
    "Sample Form 1099",
    "Sample 1099-INT",
    "samples/1099",
    "samples",
    "data/1099",
]


def find_sample_directory(explicit_dir: Optional[str] = None) -> Optional[str]:
    """
    Finds or prompts for a directory containing 1099 PDF files.
    """
    if explicit_dir and os.path.isdir(explicit_dir):
        return explicit_dir

    for candidate in DEFAULT_SAMPLE_DIRS:
        if os.path.isdir(candidate):
            pdfs = [f for f in os.listdir(candidate) if f.lower().endswith(".pdf")]
            if pdfs:
                return candidate

    return None


def run_1099_pipeline(
    input_dir: Optional[str] = None,
    output_excel: str = "1099_Tax_Summary.xlsx",
) -> AggregationReport:
    """
    Executes the end-to-end 1099 ingestion, parity validation, and Excel export pipeline.
    """
    sample_dir = find_sample_directory(input_dir)
    if not sample_dir:
        raise FileNotFoundError(
            "No sample 1099 directory found. Please supply sample 1099 PDFs in a designated "
            "directory (e.g. 'Sample Form 1099' or 'samples/1099/') to calibrate layout patterns."
        )

    pdf_files = [
        os.path.join(sample_dir, f)
        for f in sorted(os.listdir(sample_dir))
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        raise ValueError(f"No PDF files found in directory: {sample_dir}")

    all_statements: List[BrokerageAccountStatement] = []
    batch_results = parse_1099_pdf_batch(pdf_files)
    for pdf_path, statements, error in batch_results:
        if error:
            print(f"Warning: Failed to parse {pdf_path}: {error}", file=sys.stderr)
            continue
        for stmt in statements:
            # Run parity check
            errors = validate_statement_parity(stmt)
            if errors:
                stmt.notes.extend(errors)
            all_statements.append(stmt)

    report = AggregationReport(statements=all_statements)
    if report.rejected_statements:
        for rej in report.rejected_statements:
            src = f" from '{rej.source_file}'" if rej.source_file else ""
            print(f"Warning: Rejected duplicate statement: {rej.brokerage_name} (Account {rej.account_number}){src}", file=sys.stderr)

    # Export to Excel
    export_1099_excel(report, output_excel)

    return report


if __name__ == "__main__":
    report = run_1099_pipeline()
    print(f"Processed {len(report.statements)} account statements.")
    print(f"All parity passed: {report.all_parity_passed}")
    print("Exported: 1099_Tax_Summary.xlsx")
