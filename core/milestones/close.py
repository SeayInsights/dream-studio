"""Milestone close: verify gate artifacts, mutate to complete, emit events.

This module replaces the monolithic `_milestone_close` handler in
`interfaces/cli/ds.py`. The handler previously mixed plain-text success
output with JSON error output, which made it awkward for skills and
workflows to consume programmatically. The pure ``close_milestone``
function returns a single canonical result dict across every path —
missing milestone, open work orders, gate failures, forced bypass,
and success — and the CLI wrapper is the only place that formats the
legacy operator-facing output.

Gate verification:
- All work orders under the milestone must be ``status='complete'``.
- ``<planning_root>/milestones/<id>/design-audit.md`` must exist and
  every ``Score: N/M`` line must have ``N >= 3``.
- ``security-audit.md`` must exist and must not contain ``BLOCKED``.
- ``harden-results.md`` must exist and contain ``PASSED``.
- For milestones that include any UI work order
  (``ui_component`` / ``ui_page``), ``cwv-results.md`` must exist and
  contain ``PASSED``.

The ``force=True`` path bypasses gate failures, emits ``gate.bypassed``
spool events (one per failure), and still completes the milestone.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

_UI_WO_TYPES: frozenset[str] = frozenset({"ui_component", "ui_page"})


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    return paths.sqlite_path


def _evaluate_milestone_artifacts(ms_dir: Path, *, has_ui: bool) -> list[str]:
    """Run all artifact checks under ``ms_dir``. Returns list of failure reasons."""

    failures: list[str] = []

    # CHECK 1 — design audit
    audit_path = ms_dir / "design-audit.md"
    if not audit_path.is_file():
        failures.append(
            "Design audit required. Invoke website:critique across all UI surfaces and"
            f" write results to .planning/milestones/{ms_dir.name}/design-audit.md"
        )
    else:
        content = audit_path.read_text(encoding="utf-8")
        for m in re.finditer(r"Score:\s*(\d+)/(\d+)", content):
            if int(m.group(1)) < 3:
                failures.append(f"Design audit: score {m.group(1)}/{m.group(2)} is below minimum 3")
                break

    # CHECK 2 — security audit
    sec_path = ms_dir / "security-audit.md"
    if not sec_path.is_file():
        failures.append("Security audit required.")
    else:
        if "BLOCKED" in sec_path.read_text(encoding="utf-8").upper():
            failures.append("Security audit: security-audit.md contains BLOCKED")

    # CHECK 3 — hardening
    harden_path = ms_dir / "harden-results.md"
    if not harden_path.is_file():
        failures.append("Hardening check required. Invoke quality:harden and write results.")
    else:
        if "PASSED" not in harden_path.read_text(encoding="utf-8").upper():
            failures.append("Hardening check: harden-results.md does not contain PASSED")

    # CHECK 4 — Core Web Vitals (UI milestones only)
    if has_ui:
        cwv_path = ms_dir / "cwv-results.md"
        if not cwv_path.is_file():
            failures.append("Core Web Vitals check required.")
        else:
            if "PASSED" not in cwv_path.read_text(encoding="utf-8").upper():
                failures.append("Core Web Vitals: cwv-results.md does not contain PASSED")

    return failures


def close_milestone(
    *,
    milestone_id: str,
    force: bool = False,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Close a milestone after verifying gate artifacts.

    Returns a result dict whose shape is consistent across all paths.

    Missing milestone::

        {"ok": False, "error": "Milestone not found: <id>"}

    Open work orders remain::

        {"ok": False, "error": "Cannot close milestone: open work orders remain",
         "open_work_orders": [{"work_order_id", "title", "status"}, ...]}

    Gate failures (without ``force=True``)::

        {"ok": False, "error": "Milestone verification failed",
         "failures": [str, ...]}

    Success (gate-pass or forced)::

        {"ok": True, "milestone_id": str, "title": str, "project_id": str,
         "status": "complete", "completed_at": str, "forced": bool,
         "bypassed_gates": list[str]}
    """

    p_root = planning_root or Path.cwd() / ".planning"
    ms_dir = p_root / "milestones" / milestone_id

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        ms_row = conn.execute(
            "SELECT milestone_id, project_id, title, status FROM ds_milestones"
            " WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if ms_row is None:
            return {"ok": False, "error": f"Milestone not found: {milestone_id}"}

        ms_id, project_id, ms_title, _ms_status = ms_row

        wo_rows = conn.execute(
            "SELECT work_order_id, title, status, work_order_type"
            " FROM ds_work_orders WHERE milestone_id = ? ORDER BY created_at ASC",
            (milestone_id,),
        ).fetchall()

        open_wos = [(r[0], r[1], r[2]) for r in wo_rows if r[2] != "complete"]
        if open_wos:
            return {
                "ok": False,
                "error": "Cannot close milestone: open work orders remain",
                "open_work_orders": [
                    {"work_order_id": r[0], "title": r[1], "status": r[2]} for r in open_wos
                ],
            }

        has_ui = any(r[3] in _UI_WO_TYPES for r in wo_rows)
        failures = _evaluate_milestone_artifacts(ms_dir, has_ui=has_ui)

        if failures and not force:
            return {
                "ok": False,
                "error": "Milestone verification failed",
                "failures": failures,
            }

        now = datetime.now(timezone.utc).isoformat()

        if force and failures:
            for reason in failures:
                try:
                    import spool.writer as _spool_writer

                    _spool_writer.write_event(
                        {
                            "event_id": str(uuid.uuid4()),
                            "event_type": "gate.bypassed",
                            "timestamp": now,
                            "trace": {
                                "milestone_id": milestone_id,
                                "project_id": project_id,
                            },
                            "severity": "warning",
                            "payload": {
                                "milestone_id": milestone_id,
                                "reason": reason,
                            },
                            "source_type": "confirmed",
                        }
                    )
                except Exception:
                    pass

        conn.execute(
            "UPDATE ds_milestones SET status = 'complete', updated_at = ? WHERE milestone_id = ?",
            (now, milestone_id),
        )
        conn.commit()

    try:
        import spool.writer as _spool_writer

        _spool_writer.write_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "milestone.completed",
                "timestamp": now,
                "trace": {"milestone_id": milestone_id, "project_id": project_id},
                "severity": "info",
                "payload": {
                    "milestone_id": milestone_id,
                    "title": ms_title,
                    "forced": force,
                },
                "source_type": "confirmed",
            }
        )
    except Exception:
        pass

    return {
        "ok": True,
        "milestone_id": milestone_id,
        "title": ms_title,
        "project_id": project_id,
        "status": "complete",
        "completed_at": now,
        "forced": force,
        "bypassed_gates": failures if force else [],
    }
