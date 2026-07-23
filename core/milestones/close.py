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
from datetime import datetime, UTC
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

    from core.milestones.artifacts import read_milestone_artifact

    failures: list[str] = []

    # CHECK 1 — design audit
    content = read_milestone_artifact(ms_dir, "design-audit.md")
    if content is None:
        failures.append(
            "Design audit required. Invoke website:critique across all UI surfaces and"
            f" write results to the docstore as milestones/{ms_dir.name}/design-audit.md"
        )
    else:
        for m in re.finditer(r"Score:\s*(\d+)/(\d+)", content):
            if int(m.group(1)) < 3:
                failures.append(f"Design audit: score {m.group(1)}/{m.group(2)} is below minimum 3")
                break

    # CHECK 2 — security audit
    content = read_milestone_artifact(ms_dir, "security-audit.md")
    if content is None:
        failures.append("Security audit required.")
    else:
        if "BLOCKED" in content.upper():
            failures.append("Security audit: security-audit.md contains BLOCKED")

    # CHECK 3 — hardening
    content = read_milestone_artifact(ms_dir, "harden-results.md")
    if content is None:
        failures.append("Hardening check required. Invoke quality:harden and write results.")
    else:
        if "PASSED" not in content.upper():
            failures.append("Hardening check: harden-results.md does not contain PASSED")

    # CHECK 4 — Core Web Vitals (UI milestones only)
    if has_ui:
        content = read_milestone_artifact(ms_dir, "cwv-results.md")
        if content is None:
            failures.append("Core Web Vitals check required.")
        else:
            if "PASSED" not in content.upper():
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
            "SELECT milestone_id, project_id, title, status FROM business_milestones"
            " WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if ms_row is None:
            return {"ok": False, "error": f"Milestone not found: {milestone_id}"}

        ms_id, project_id, ms_title, _ms_status = ms_row

        wo_rows = conn.execute(
            "SELECT work_order_id, title, status, work_order_type"
            " FROM business_work_orders WHERE milestone_id = ? ORDER BY created_at ASC",
            (milestone_id,),
        ).fetchall()

        # A milestone can close once no work order is still OPEN. Both "closed" and
        # "cancelled" are TERMINAL — a cancelled WO is intentionally-dropped work, not
        # outstanding work, so it must not block the milestone (previously only "closed"
        # counted as terminal, which stranded milestones whose only non-closed WOs were
        # cancelled, even under force=True since this is a hard precondition).
        _TERMINAL_WO_STATUSES = {"closed", "cancelled"}
        open_wos = [(r[0], r[1], r[2]) for r in wo_rows if r[2] not in _TERMINAL_WO_STATUSES]
        if open_wos:
            # Canonical-events fallback: work_order.closed is terminal — any
            # matching event means the WO is closed regardless of projection lag.
            open_wo_ids = [r[0] for r in open_wos]
            placeholders = ",".join("?" * len(open_wo_ids))
            closed_in_canonical = {
                row[0]
                for row in conn.execute(
                    f"SELECT work_order_id FROM business_canonical_events"
                    f" WHERE event_type = 'work_order.closed'"
                    f" AND work_order_id IN ({placeholders})",
                    open_wo_ids,
                ).fetchall()
            }
            open_wos = [r for r in open_wos if r[0] not in closed_in_canonical]
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

        now = datetime.now(UTC).isoformat()

        if force and failures:
            for reason in failures:
                try:
                    import spool.writer as _spool_writer

                    from canonical.events.envelope import CanonicalEventEnvelope

                    envelope = CanonicalEventEnvelope(
                        event_type="gate.bypassed",
                        session_id=None,
                        payload={
                            "milestone_id": milestone_id,
                            "reason": reason,
                        },
                        timestamp=now,
                        severity="warning",
                        trace={
                            "milestone_id": milestone_id,
                            "project_id": project_id,
                        },
                    )
                    _spool_writer.write_event(envelope.to_dict())
                except Exception:
                    pass

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        envelope = CanonicalEventEnvelope(
            event_type="milestone.completed",
            session_id=None,
            payload={
                "milestone_id": milestone_id,
                "title": ms_title,
                "forced": force,
            },
            timestamp=now,
            severity="info",
            trace={"milestone_id": milestone_id, "project_id": project_id},
        )
        _spool_writer.write_event(envelope.to_dict())
    except Exception:
        pass

    # Flush the milestone.completed spool event through the projection pipeline so
    # callers see status='complete' in the read model without a manual sync_tick.
    # Best-effort — a transient projection failure degrades to the daemon's next cycle.
    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
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
