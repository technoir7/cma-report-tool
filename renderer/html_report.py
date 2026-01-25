"""
HTML Report Renderer: Generates HTML from ReportJSON.

This module uses Jinja2 to render a complete HTML CMA report
from the structured ReportJSON data and optional narrative.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from domain.report_schema import ReportJSON


# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"


def get_template_env() -> Environment:
    """Create and configure Jinja2 environment."""
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True
    )


def render_html_report(
    report_json: ReportJSON,
    narrative: str | None = None,
    template_name: str = "report.html"
) -> str:
    """
    Render ReportJSON to HTML.
    
    Args:
        report_json: The structured report data
        narrative: Optional LLM-generated narrative
        template_name: Template file to use
        
    Returns:
        Rendered HTML string
    """
    env = get_template_env()
    template = env.get_template(template_name)
    
    # Prepare context
    context = {
        "report_id": str(report_json.report_id),
        "generated_at": report_json.generated_at,
        "report_version": report_json.report_version,
        "subject": report_json.subject,
        "selected_comps": report_json.selected_comps,
        "analytics": report_json.analytics,
        "limitations": report_json.limitations,
        "narrative": narrative,
        "data_source": report_json.data_source,
        "query_hash": report_json.query_hash,
    }
    
    return template.render(**context)


def save_html_report(
    report_json: ReportJSON,
    output_path: str | Path,
    narrative: str | None = None
) -> Path:
    """
    Render and save HTML report to file.
    
    Args:
        report_json: The structured report data
        output_path: Path to save the HTML file
        narrative: Optional narrative text
        
    Returns:
        Path to the saved file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    html = render_html_report(report_json, narrative)
    output_path.write_text(html, encoding="utf-8")
    
    return output_path


class HTMLReportGenerator:
    """
    Generator class for HTML CMA reports.
    
    Provides more control over template customization and output.
    """
    
    def __init__(self, template_dir: str | Path | None = None):
        """
        Initialize generator.
        
        Args:
            template_dir: Custom template directory (optional)
        """
        self.template_dir = Path(template_dir) if template_dir else TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True
        )
    
    def render(
        self,
        report_json: ReportJSON,
        narrative: str | None = None,
        extra_context: dict | None = None
    ) -> str:
        """
        Render report to HTML.
        
        Args:
            report_json: Report data
            narrative: Optional narrative
            extra_context: Additional template context
            
        Returns:
            Rendered HTML
        """
        template = self._env.get_template("report.html")
        
        context = {
            "report_id": str(report_json.report_id),
            "generated_at": report_json.generated_at,
            "report_version": report_json.report_version,
            "subject": report_json.subject,
            "selected_comps": report_json.selected_comps,
            "analytics": report_json.analytics,
            "limitations": report_json.limitations,
            "narrative": narrative,
            "data_source": report_json.data_source,
            "query_hash": report_json.query_hash,
        }
        
        if extra_context:
            context.update(extra_context)
        
        return template.render(**context)
    
    def save(
        self,
        report_json: ReportJSON,
        output_path: str | Path,
        narrative: str | None = None
    ) -> Path:
        """
        Render and save to file.
        
        Args:
            report_json: Report data
            output_path: Output file path
            narrative: Optional narrative
            
        Returns:
            Path to saved file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        html = self.render(report_json, narrative)
        output_path.write_text(html, encoding="utf-8")
        
        return output_path
