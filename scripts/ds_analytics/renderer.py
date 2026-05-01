"""Render analytics dashboard to standalone HTML using Jinja2."""
from __future__ import annotations
from pathlib import Path
import sys

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lib import paths

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def render_dashboard(data: dict, output_path: Path | None = None) -> Path:
    """Render the analytics dashboard HTML.

    Args:
        data: merged analysis dict with keys: pulse_trend, skill_velocity,
              conversion_rate, and optionally git_metrics, project_name
        output_path: where to write the HTML (default: ~/.dream-studio/analytics/dashboard.html)

    Returns:
        Path to the rendered HTML file.
    """
    if output_path is None:
        output_path = paths.user_data_dir() / "analytics" / "dashboard.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("dashboard.html.j2")

    sv = data.get("skill_velocity")
    if sv is not None and hasattr(sv, "to_dict"):
        data = {**data, "skill_velocity": sv.to_dict("records")}

    data.setdefault("git_metrics", None)
    data.setdefault("all_git_metrics", None)
    data.setdefault("project_name", None)
    data.setdefault("efficiency", None)

    html = template.render(**data)
    output_path.write_text(html, encoding="utf-8")
    return output_path
