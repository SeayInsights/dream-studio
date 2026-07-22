"""Workflow completion telemetry — canonical event emission, execution_events
dual-write, and repo-context snapshotting.

WO-GF-CONTROL-INSTALL-split: see state.py facade docstring.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from core.config import paths

from .state_io import _write_state


def _try_archive_and_prune(data: dict, key: str, wf: dict) -> None:
    """Emit workflow completion telemetry, then prune from JSON. Skips silently
    on any error.

    WO 9f47a1a0: replaces the legacy archive_workflow() DB write, which
    targeted the write-orphaned raw_workflow_runs/raw_workflow_nodes tables
    (silently failing since ~2026-05-18; dropped by migration 141 — see
    core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql).
    Completion is now recorded as workflow.completed / workflow.node.completed
    canonical events written directly to the spool (the durability boundary —
    see emitters/shared/spool_writer.py), decoupled from any SQLite write.
    """
    if _emit_workflow_completion(key, wf):
        data.get("active_workflows", {}).pop(key, None)
        _write_state(data)


def _emit_workflow_completion(run_key: str, wf: dict) -> bool:
    """Best-effort: emit canonical workflow completion events to the spool,
    and dual-write execution_events telemetry.

    Returns True only if the canonical spool write succeeded — the new
    durability signal that gates JSON pruning, mirroring the old
    archive_workflow() contract where pruning only happened after a durable
    write succeeded. The execution_events dual-write is additional telemetry
    and never gates pruning, matching its pre-existing best-effort contract
    (the old _emit_workflow_telemetry() helper always swallowed its own
    failures too). Never raises — a telemetry failure must never break a
    workflow run.
    """
    try:
        _emit_canonical_workflow_events(run_key, wf)
        emitted = True
    except Exception:
        emitted = False
    _emit_execution_events_telemetry(run_key, wf)
    return emitted


def _emit_canonical_workflow_events(run_key: str, wf: dict) -> None:
    """Write workflow.completed (+ one workflow.node.completed per node)
    canonical event envelopes to the spool.

    Raises on genuine spool write failure (missing canonical/spool modules,
    disk errors) — the caller decides whether that is fatal to the pruning
    decision.
    """
    from canonical.events.envelope import CanonicalEventEnvelope
    from emitters.shared.spool_writer import write_envelopes

    nodes = wf.get("nodes", {}) or {}
    workflow_name = wf.get("workflow", "unknown")
    started_at = wf.get("started")
    finished_at = wf.get("finished")
    status = wf.get("status", "unknown")
    nodes_done = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
    trace = {"domain": "telemetry", "workflow_id": workflow_name}

    envelopes = [
        CanonicalEventEnvelope(
            event_type="workflow.completed",
            session_id=None,
            payload={
                "run_key": run_key,
                "workflow": workflow_name,
                "yaml_path": wf.get("yaml_path", ""),
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": _duration_ms(started_at, finished_at),
                "node_count": len(nodes),
                "nodes_done": nodes_done,
            },
            trace=trace,
        )
    ]
    for node_id, node in nodes.items():
        envelopes.append(
            CanonicalEventEnvelope(
                event_type="workflow.node.completed",
                session_id=None,
                payload={
                    "run_key": run_key,
                    "node_id": node_id,
                    "workflow": workflow_name,
                    "status": node.get("status", ""),
                    "output": node.get("output", ""),
                    "duration_ms": _duration_ms(node.get("started"), node.get("finished")),
                },
                trace=trace,
            )
        )
    write_envelopes(envelopes)


def _emit_execution_events_telemetry(run_key: str, wf: dict) -> None:
    """Best-effort dual-write to the execution_events telemetry spine
    (core/telemetry/emitters.py::emit_workflow_invocation).

    Unchanged consumer contract for core/telemetry/read_models.py's
    workflow_execution_graph and the workflow COMPONENT_TABLES entry.
    Previously called from within archive_workflow() (studio_db.py); moved
    here so it no longer depends on the raw_workflow_runs write succeeding.
    """
    try:
        from core.telemetry.emitters import TelemetryContext, emit_workflow_invocation
    except ImportError:
        return
    try:
        emit_workflow_invocation(
            workflow_id=str(wf.get("workflow") or "unknown"),
            status=wf.get("status", "unknown"),
            run_key=run_key,
            yaml_path=str(wf.get("yaml_path") or ""),
            started_at=wf.get("started"),
            ended_at=wf.get("finished"),
            duration_ms=_duration_ms(wf.get("started"), wf.get("finished")),
            nodes=wf.get("nodes", {}),
            context=TelemetryContext(
                project_id="dream-studio",
                process_run_id=run_key,
                source_refs=("control/execution/workflow/state.py",),
                evidence_refs=(f"spool:workflow.completed:{run_key}",),
            ),
            db_path=paths.state_dir() / "studio.db",
        )
    except Exception:
        pass


def _duration_ms(started: str | None, finished: str | None) -> int | None:
    if not started or not finished:
        return None
    try:
        start = datetime.fromisoformat(started)
        end = datetime.fromisoformat(finished)
        return int((end - start).total_seconds() * 1000)
    except (ValueError, TypeError):
        return None


# ── Repo context helper ──────────────────────────────────────────


def _generate_repo_context(data: dict, key: str) -> None:
    """Call repo_context.py to snapshot the project, store path in workflow state."""
    try:
        from control.context.repo import generate_snapshot
    except ImportError:
        return

    session_dir = paths.state_dir() / "workflow-sessions" / key
    session_dir.mkdir(parents=True, exist_ok=True)
    output_path = session_dir / "repo-context.json"

    try:
        snapshot = generate_snapshot(Path.cwd())
        output_path.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        wf = data.get("active_workflows", {}).get(key, {})
        wf["repo_context_path"] = str(output_path)
        wf["session_dir"] = str(session_dir)
        _write_state(data)
    except Exception:
        pass
