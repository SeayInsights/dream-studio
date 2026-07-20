"""Public acquisition surface — importable facade for the full project onboarding pipeline.

Exposes the canonical four-step chain as a single entry point:

  1. intake-lite  — register_project_for_intake() → business_projects row + optional marker
  2. stack-detect — detect_and_persist_stack() → detected_stack + signals
  3. scan         — create_skill_scan_run() → scan_id (optional, only when run_scan=True)
  4. delta        — compute_scan_delta() + persist_scan_delta() → delta_id

All project registration routes through mutations.register_project (the unified write path).
No dual-write: callers must not also invoke register_project directly in the same pipeline.

Catalog entry (WO-P):
  facade:    core.projects.acquisition.acquire_project
  inputs:    target_path, project_name, run_scan, source_root, dream_studio_home
  outputs:   project_id, detected_stack, stack_confidence, [scan_id, delta_id, delta]
  used by:   onboarding flows, intake CLI, first-run wizard (WO-V)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.projects.intake import (
    detect_and_persist_stack,
    register_project_for_intake,
)


def acquire_project(
    target_path: str | Path,
    *,
    project_name: str | None = None,
    write_marker: bool = False,
    run_scan: bool = False,
    skill_id: str = "security",
    execution_ctx: dict[str, Any] | None = None,
    source_root: str | Path,
    dream_studio_home: str | Path | None = None,
) -> dict[str, Any]:
    """Run the full acquisition pipeline for a project directory.

    Steps executed:
      intake-lite  → register project in business_projects via mutations.register_project
      stack-detect → detect stack signals, persist detected_stack to business_projects
      scan         → (if run_scan=True) mint a scan_id for the named skill
      delta        → (if run_scan=True) compute + persist scan delta

    Args:
        target_path:      Directory to acquire (resolved to absolute path).
        project_name:     Override project name; defaults to directory basename.
        write_marker:     Write .dream-studio-project marker file to target_path.
        run_scan:         Also run steps 3+4 (scan creation + delta). False by default
                          because scan execution requires an approved execution_ctx.
        skill_id:         Which skill scan to create (default "security").
        execution_ctx:    Required when run_scan=True. Caller-supplied context dict
                          passed to create_skill_scan_run.
        source_root:      Dream Studio repo root.
        dream_studio_home: Override Dream Studio home directory.

    Returns a dict:
        ok           → True on success
        project_id   → UUID of the registered project
        project_name → Name stored in business_projects
        detected_stack  → Stack adapter string (e.g. "python", "node")
        stack_confidence → Detection confidence 0–1
        scan_id      → (only when run_scan=True) UUID of the created scan run
        delta_id     → (only when run_scan=True) UUID of the persisted delta
        delta        → (only when run_scan=True) {new: int, fixed: int}
        error        → error message if ok is False
    """
    target = Path(target_path).resolve()
    source = Path(source_root)

    intake_result = register_project_for_intake(
        target,
        project_name=project_name,
        write_marker=write_marker,
        source_root=source,
        dream_studio_home=dream_studio_home,
    )
    if not intake_result.get("ok"):
        return {
            "ok": False,
            "error": intake_result.get("error", "intake registration failed"),
        }

    project_id: str = intake_result["project_id"]
    stack_result = detect_and_persist_stack(project_id, target)

    # WO-BROWNFIELD-ADAPTIVE: recommend the ds-quality modes that fit the detected
    # stack (backend-api / frontend-ux / database / ops / ... ) so the brownfield
    # pipeline routes to relevant audits instead of a generic prompt.
    from core.projects.adaptive_routing import recommend_dispatches

    result: dict[str, Any] = {
        "ok": True,
        "project_id": project_id,
        "project_name": intake_result.get("name", target.name),
        "detected_stack": stack_result.get("detected_stack"),
        "stack_confidence": stack_result.get("confidence"),
        "recommended_dispatches": recommend_dispatches(stack_result),
    }

    if not run_scan:
        return result

    from core.projects.delta import compute_scan_delta, persist_scan_delta
    from core.projects.intake import create_skill_scan_run

    ctx = execution_ctx or {"source": "acquisition_facade", "approved": True}
    scan_id = create_skill_scan_run(
        project_id,
        target,
        skill_id=skill_id,
        execution_ctx=ctx,
        scope="full_repo",
    )
    delta = compute_scan_delta(scan_id, None, project_id)
    delta_id = persist_scan_delta(delta)

    result["scan_id"] = scan_id
    result["delta_id"] = delta_id
    result["delta"] = {"new": delta.new_count, "fixed": delta.fixed_count}
    return result


def get_readiness(
    project_id: str,
    target_path: str | Path,
    *,
    skill_id: str = "security",
    execution_ctx: dict[str, Any] | None = None,
    previous_scan_id: str | None = None,
) -> dict[str, Any]:
    """Create a scan run + compute delta for an already-registered project.

    Use this when the project already exists in business_projects and you only
    want to refresh the scan (e.g., incremental readiness check after code changes).

    Returns:
        ok         → True
        scan_id    → UUID of the new scan run
        delta_id   → UUID of the persisted delta
        delta      → {new: int, fixed: int, persisting: int}
    """
    from core.projects.delta import compute_scan_delta, persist_scan_delta
    from core.projects.intake import create_skill_scan_run

    target = Path(target_path).resolve()
    ctx = execution_ctx or {"source": "readiness_check", "approved": True}

    scan_id = create_skill_scan_run(
        project_id,
        target,
        skill_id=skill_id,
        execution_ctx=ctx,
        scope="full_repo",
        previous_scan_id=previous_scan_id,
    )
    delta = compute_scan_delta(scan_id, previous_scan_id, project_id)
    delta_id = persist_scan_delta(delta)

    return {
        "ok": True,
        "scan_id": scan_id,
        "delta_id": delta_id,
        "delta": {
            "new": delta.new_count,
            "fixed": delta.fixed_count,
            "persisting": delta.persisting_count,
        },
    }
