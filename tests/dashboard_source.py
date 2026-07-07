"""WO-SPLIT-DASHBOARD: shared accessor for the dashboard's full source.

The inline <style>/<script> were extracted to frontend/static/{dashboard.css,
dashboard.js}. Tests that assert on dashboard markup + CSS + JS should read the
combined source through this helper rather than dashboard.html alone, so they keep
finding content regardless of which file it now lives in.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[1] / "projections" / "frontend"


def dashboard_source() -> str:
    html = (_FRONTEND / "dashboard.html").read_text(encoding="utf-8")
    css = (_FRONTEND / "static" / "dashboard.css").read_text(encoding="utf-8")
    js = (_FRONTEND / "static" / "dashboard.js").read_text(encoding="utf-8")
    return f"{html}\n{css}\n{js}"
