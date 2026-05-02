"""
HTML email template renderer with variable substitution.

Uses simple {{variable}} syntax for template variables.
No external dependencies - pure Python string replacement.
"""

import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """
    Renders HTML email templates with variable substitution.

    Uses simple {{variable}} placeholder syntax.
    Templates are loaded from analytics/core/email/templates/ directory.

    Example:
        renderer = TemplateRenderer()

        html = renderer.render("report_notification.html", {
            "report_title": "Weekly Summary",
            "date_range": "April 24-30, 2026",
            "key_metrics": {"sessions": 145, "tokens": "2.5M"}
        })
    """

    def __init__(self, template_dir: Path = None):
        """
        Initialize template renderer.

        Args:
            template_dir: Directory containing templates (defaults to ./templates)
        """
        if template_dir is None:
            # Default to templates/ subdirectory
            template_dir = Path(__file__).parent / "templates"

        self.template_dir = Path(template_dir)

        if not self.template_dir.exists():
            logger.warning(f"Template directory not found: {self.template_dir}")

    def render(self, template_name: str, data: Dict[str, Any]) -> str:
        """
        Render a template with provided data.

        Args:
            template_name: Template filename (e.g., "report_notification.html")
            data: Dictionary of template variables

        Returns:
            Rendered HTML string

        Raises:
            FileNotFoundError: If template file doesn't exist

        Example:
            html = renderer.render("alert_notification.html", {
                "alert_title": "High CPU Usage",
                "metric_value": "95%",
                "threshold": "80%"
            })
        """
        template_path = self.template_dir / template_name

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        try:
            # Load template
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()

            # Replace variables
            for key, value in data.items():
                placeholder = f"{{{{{key}}}}}"

                # Handle nested dict values (e.g., key_metrics)
                if isinstance(value, dict):
                    # Convert dict to HTML list
                    html_list = "<ul>"
                    for k, v in value.items():
                        html_list += f"<li><strong>{k}:</strong> {v}</li>"
                    html_list += "</ul>"
                    html = html.replace(placeholder, html_list)
                else:
                    # Simple value replacement
                    html = html.replace(placeholder, str(value))

            return html

        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {e}")
            raise

    def render_string(self, template_string: str, data: Dict[str, Any]) -> str:
        """
        Render a template string (not from file) with provided data.

        Args:
            template_string: HTML template string with {{variable}} placeholders
            data: Dictionary of template variables

        Returns:
            Rendered HTML string

        Example:
            html = renderer.render_string(
                "<h1>{{title}}</h1><p>{{message}}</p>",
                {"title": "Hello", "message": "World"}
            )
        """
        html = template_string

        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"

            if isinstance(value, dict):
                html_list = "<ul>"
                for k, v in value.items():
                    html_list += f"<li><strong>{k}:</strong> {v}</li>"
                html_list += "</ul>"
                html = html.replace(placeholder, html_list)
            else:
                html = html.replace(placeholder, str(value))

        return html
