"""
PDF Report Renderer: Stub for PDF generation.

This module is a STUB that will be implemented when PDF generation
is required. It follows the same interface as html_report.

WHY THIS IS A STUB:
- PDF generation requires additional system dependencies (wkhtmltopdf or WeasyPrint)
- Docker image would need to include these dependencies
- HTML output is sufficient for MVP

HOW TO IMPLEMENT:
1. Install wkhtmltopdf: apt-get install wkhtmltopdf
2. Use pdfkit library: pip install pdfkit
3. Or use WeasyPrint: pip install weasyprint

Example implementation with pdfkit:
```python
import pdfkit
from renderer.html_report import render_html_report

def render_pdf_report(report_json, narrative=None):
    html = render_html_report(report_json, narrative)
    return pdfkit.from_string(html, False)
```
"""

from pathlib import Path
from typing import Any

from domain.report_schema import ReportJSON


class PDFNotImplementedError(NotImplementedError):
    """Raised when PDF generation is attempted but not available."""
    pass


def render_pdf_report(
    report_json: ReportJSON,
    narrative: str | None = None
) -> bytes:
    """
    Render ReportJSON to PDF.
    
    NOT IMPLEMENTED - This is a stub.
    
    Args:
        report_json: The structured report data
        narrative: Optional narrative text
        
    Raises:
        PDFNotImplementedError: Always, until implemented
    """
    raise PDFNotImplementedError(
        "PDF generation requires wkhtmltopdf or WeasyPrint. "
        "Install dependencies and implement this function. "
        "For now, use render_html_report() and convert manually."
    )


def save_pdf_report(
    report_json: ReportJSON,
    output_path: str | Path,
    narrative: str | None = None
) -> Path:
    """
    Render and save PDF report to file.
    
    NOT IMPLEMENTED - This is a stub.
    
    Args:
        report_json: The structured report data
        output_path: Path to save the PDF file
        narrative: Optional narrative text
        
    Raises:
        PDFNotImplementedError: Always, until implemented
    """
    raise PDFNotImplementedError(
        "PDF generation not implemented. Use save_html_report() instead."
    )


class PDFReportGenerator:
    """
    Generator class for PDF CMA reports.
    
    STUB - Not implemented.
    
    When implemented, this will:
    1. Render HTML using html_report module
    2. Convert to PDF using wkhtmltopdf or WeasyPrint
    3. Apply page breaks and print styling
    """
    
    def __init__(self, **kwargs: Any):
        """
        Initialize PDF generator.
        
        Raises:
            PDFNotImplementedError: Always
        """
        raise PDFNotImplementedError(
            "PDFReportGenerator requires additional dependencies. "
            "See module docstring for implementation instructions."
        )
    
    def render(self, report_json: ReportJSON, narrative: str | None = None) -> bytes:
        """Render to PDF bytes."""
        raise PDFNotImplementedError("Not implemented")
    
    def save(self, report_json: ReportJSON, output_path: str | Path, narrative: str | None = None) -> Path:
        """Save to PDF file."""
        raise PDFNotImplementedError("Not implemented")
