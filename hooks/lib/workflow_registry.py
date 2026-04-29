"""Workflow registry — scan, enrich, and format workflow YAML metadata."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from lib.studio_db import last_run as _db_last_run, run_count as _db_run_count
except ImportError:
    _db_last_run = _db_run_count = None  # type: ignore[assignment]

try:
    from lib.workflow_cost import estimate_workflow_cost as _estimate_cost
except ImportError:
    _estimate_cost = None  # type: ignore[assignment]

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "workflows"


def list_workflows(workflows_dir: Path | None = None) -> list[dict]:
    """Return enriched metadata dicts for every *.yaml in workflows_dir."""
    d = workflows_dir or _DEFAULT_DIR
    result = []
    for p in sorted(d.glob("*.yaml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        name = data.get("name") or p.stem
        desc = (data.get("description") or "(no description)").strip()
        tok: int | None = None
        if _estimate_cost:
            try:
                tok = _estimate_cost(data)["total_estimated"] or None
            except Exception:
                pass
        lr = _db_last_run(name) if _db_last_run else None
        rc = _db_run_count(name) if _db_run_count else 0
        result.append({"name": name, "description": desc, "yaml_path": str(p),
                        "estimated_tokens": tok, "last_run": lr, "run_count": rc})
    return result


def format_registry_table(workflows: list[dict]) -> str:
    """Return a box-drawing table listing all workflows."""
    if not workflows:
        return "No workflows found."
    now = datetime.now(timezone.utc)
    wn = max(4, max(len(w["name"]) for w in workflows))
    wd = min(45, max(11, max(len(w["description"]) for w in workflows)))
    wt, wl, wr = 6, 8, 4
    def _row(n, d, t, l, r):
        return f"│ {n:<{wn}} │ {d:<{wd}} │ {t:>{wt}} │ {l:<{wl}} │ {r:>{wr}} │"
    bar = lambda c1, c2, c3: f"{c1}{'─'*(wn+2)}{c2}{'─'*(wd+2)}{c2}{'─'*(wt+2)}{c2}{'─'*(wl+2)}{c2}{'─'*(wr+2)}{c3}"
    lines = [
        bar("┌", "┬", "┐"),
        _row("Name", "Description", "Tokens", "Last Run", "Runs"),
        bar("├", "┼", "┤"),
    ]
    for w in workflows:
        lines.append(_row(
            w["name"], w["description"][:wd],
            _fmt_tokens(w["estimated_tokens"]),
            _fmt_last_run(w["last_run"], now),
            str(w["run_count"]),
        ))
    lines.append(bar("└", "┴", "┘"))
    return "\n".join(lines)


def _fmt_tokens(v: int | None) -> str:
    if v is None:
        return "—"
    return f"{v // 1000}k" if v >= 1000 else str(v)


def _fmt_last_run(lr: dict | None, now: datetime) -> str:
    if lr is None:
        return "never"
    ts = lr.get("finished_at") or lr.get("started_at") or ""
    try:
        s = (now - datetime.fromisoformat(ts)).total_seconds()
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{int(s / 60)}m ago"
        if s < 86400:
            return f"{int(s / 3600)}h ago"
        return f"{int(s / 86400)}d ago"
    except Exception:
        return ts[:10] if ts else "?"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    print(format_registry_table(list_workflows()))
