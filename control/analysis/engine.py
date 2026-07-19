"""
Project Intelligence Engine - Orchestrates full 5-phase analysis pipeline.

Phases:
1. Discovery - File inventory, LOC, git metadata, entry points
2. Research - Stack compatibility and best practices
3. Audit - Architecture violations and health scoring
4. Bug Analysis - Pattern-based bug detection with risk scoring
5. Synthesis - PRD generation from all analysis data
"""

from pathlib import Path
from typing import Any
from datetime import datetime, UTC
import uuid
import time

from control.analysis.discovery import discover_project
from control.analysis.research import research_stack
from control.analysis.audit import audit_architecture
from control.analysis.bugs import analyze_bugs
from control.analysis.synthesis import generate_prd
from control.analysis.stacks import (
    AdapterRegistry,
    NextJSAdapter,
    AstroAdapter,
    PythonGenericAdapter,
)
from control.analysis.stacks.detector import detect_stack
from core.config.database import transaction

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as CanonicalEventType
from canonical.events.redactor import redact_file_path
from emitters.shared.spool_writer import write_envelopes

from core.config.paths import project_planning_dir, project_sessions_dir

# Import EventNormalizer for legacy activity-log enrichment (PHASE 1 Step 2)
try:
    from core.adapters.normalizers import EventNormalizer

    _event_normalizer = EventNormalizer()
    _NORMALIZER_AVAILABLE = True
except ImportError:
    _NORMALIZER_AVAILABLE = False


def analyze_project(path: Path, run_type: str = "full") -> dict[str, Any]:
    """
    Run full 5-phase project analysis.

    Args:
        path: Project root directory
        run_type: Analysis type ('full', 'incremental', 'targeted')

    Returns:
        {
            "run_id": str,
            "project_id": str,
            "project_name": str,
            "project_data": Dict,
            "stack": Dict,
            "research": Dict,
            "audit": Dict,
            "bugs": Dict,
            "prd_path": Path,
            "duration_seconds": float,
            "status": str,
            "error": Optional[str]
        }
    """
    path = Path(path).resolve()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(UTC).isoformat()
    start_time = time.time()

    # Initialize adapter registry
    registry = AdapterRegistry()
    registry.register(NextJSAdapter())
    registry.register(AstroAdapter())
    registry.register(PythonGenericAdapter())

    # reg_projects deleted in migration 084. Look up project in business_projects by path.
    # The broken project_source INSERT path is removed here; business_projects is now the
    # canonical project registry.
    with transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            # WO-PROJECT-REG-HARDENING: deterministic lookup when duplicate rows
            # share a project_path — prefer active, then paused, exclude deleted,
            # most-recent first — instead of an arbitrary LIMIT 1.
            "SELECT project_id FROM business_projects"
            " WHERE project_path = ? AND status != 'deleted'"
            " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,"
            " updated_at DESC LIMIT 1",
            (str(path),),
        )
        existing_project = cursor.fetchone()

    if existing_project:
        project_id = existing_project[0]
    else:
        # Register new project in business_projects with a UUID.
        project_id = str(uuid.uuid4())
        project_name = path.name

        planning_path = str(project_planning_dir(project_name))
        sessions_path = str(project_sessions_dir(project_name))

        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.PROJECT_REGISTERED.value,
                    session_id=None,
                    payload={
                        "project_id": project_id,
                        "project_path": redact_file_path(str(path)),
                        "project_name": project_name,
                        "project_source": "analysis_engine",
                        "planning_path": redact_file_path(planning_path),
                        "sessions_path": redact_file_path(sessions_path),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        with transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO business_projects"
                " (project_id, name, description, status, project_path, created_at, updated_at)"
                " VALUES (?, ?, '', 'active', ?, ?, ?)",
                (project_id, project_name, str(path), started_at, started_at),
            )

    result = {
        "run_id": run_id,
        "project_id": project_id,
        "status": "running",
        "error": None,
        "duration_seconds": 0.0,
    }

    try:
        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_STARTED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "run_type": run_type,
                        "project_path": redact_file_path(str(path)),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        # Phase 1: Discovery
        print(f"[{run_id}] Phase 1/5: Discovery...")
        project_data = discover_project(path)
        result["project_name"] = project_data.get("project_name", "unknown")
        result["project_data"] = project_data

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_DISCOVERY_COMPLETED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "files_discovered": len(project_data.get("file_inventory", {})),
                        "lines_of_code": project_data.get("lines_of_code", {}).get("total", 0),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        # Detect stack
        detected = detect_stack(path)
        adapter = registry.get_adapter(detected.adapter) if detected.adapter else None
        stack = adapter.analyze_stack(path) if adapter else {"framework": "unknown"}
        result["stack"] = stack

        # Phase 2: Research
        print(f"[{run_id}] Phase 2/5: Research...")
        research = research_stack(stack, project_data)
        result["research"] = research

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_RESEARCH_COMPLETED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "stack_framework": stack.get("framework", "unknown"),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        # Phase 3: Architecture Audit
        print(f"[{run_id}] Phase 3/5: Architecture Audit...")
        audit = audit_architecture(path, project_data, stack)
        result["audit"] = audit

        violations_count = len(audit.get("violations", []))

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_AUDIT_COMPLETED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "violations_count": violations_count,
                        "health_score": audit.get("health_score", 0),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        # Phase 4: Bug Analysis
        print(f"[{run_id}] Phase 4/5: Bug Analysis...")
        bugs = analyze_bugs(path, project_data, stack)
        result["bugs"] = bugs

        bugs_count = len(bugs.get("bugs", []))

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_BUG_ANALYSIS_COMPLETED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "bugs_count": bugs_count,
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        # Phase 5: Synthesis (PRD Generation)
        print(f"[{run_id}] Phase 5/5: PRD Generation...")
        prd_path = generate_prd(
            project_id=project_id,
            project_data=project_data,
            stack=stack,
            research=research,
            audit=audit,
            bugs=bugs,
        )
        result["prd_path"] = prd_path

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_SYNTHESIS_COMPLETED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "prd_path": redact_file_path(str(prd_path)),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        # Update project metadata in business_projects (reg_projects deleted in migration 084)
        _update_project_metadata(project_id, path, project_data, stack, audit)

        # Mark analysis as completed
        duration = time.time() - start_time
        result["duration_seconds"] = duration
        result["status"] = "completed"

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_COMPLETED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "duration_seconds": duration,
                        "violations_count": violations_count,
                        "bugs_count": bugs_count,
                        "health_score": audit.get("health_score", 0),
                        "prd_path": redact_file_path(str(prd_path)),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        print(f"[{run_id}] Analysis complete!")
        print(f"  - Violations: {violations_count}")
        print(f"  - Bugs: {bugs_count}")
        print(f"  - Health Score: {audit.get('health_score', 0):.1f}/10")
        print(f"  - PRD: {prd_path}")
        print(f"  - Duration: {duration:.1f}s")

    except Exception as e:
        # Mark as failed
        result["status"] = "failed"
        result["error"] = str(e)

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.ANALYSIS_FAILED.value,
                    session_id=None,
                    payload={
                        "run_id": run_id,
                        "project_id": project_id,
                        "error_message": str(e),
                    },
                    severity="error",
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        print(f"[{run_id}] Analysis failed: {e}")
        raise

    return result


def _update_project_metadata(
    project_id: str,
    path: Path,
    project_data: dict[str, Any],
    stack: dict[str, Any],
    audit: dict[str, Any],
) -> None:
    """Update project metadata in business_projects.

    reg_projects deleted in migration 084. Analysis columns (stack_detected, health_score,
    total_files, lines_of_code) are not stored in business_projects in this release —
    they need a dedicated project_analysis_metadata table when the analysis engine is
    rebuilt against business_projects. For now, emit the event for traceability only.
    """
    now = datetime.now(UTC).isoformat()
    # Check if project exists in business_projects
    with transaction() as conn:
        cursor = conn.execute(
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        )
        exists = cursor.fetchone()

    if exists:
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.PROJECT_UPDATED.value,
                    session_id=None,
                    payload={
                        "project_id": project_id,
                        "stack_detected": stack.get("framework", "unknown"),
                        "health_score": min(1.0, audit.get("health_score", 0.0) / 10.0),
                        "total_files": len(project_data.get("file_inventory", {})),
                        "lines_of_code": project_data.get("lines_of_code", {}).get("total", 0),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )
        # Update path and timestamps in business_projects (analysis metrics deferred)
        with transaction() as conn:
            conn.execute(
                "UPDATE business_projects SET project_path = ?, updated_at = ? WHERE project_id = ?",
                (str(path), now, project_id),
            )
    else:
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.PROJECT_REGISTERED.value,
                    session_id=None,
                    payload={
                        "project_id": project_id,
                        "project_name": project_data.get("project_name", path.name),
                        "stack_detected": stack.get("framework", "unknown"),
                        "health_score": min(1.0, audit.get("health_score", 0.0) / 10.0),
                        "total_files": len(project_data.get("file_inventory", {})),
                        "lines_of_code": project_data.get("lines_of_code", {}).get("total", 0),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )
        with transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO business_projects"
                " (project_id, name, description, status, project_path, created_at, updated_at)"
                " VALUES (?, ?, '', 'active', ?, ?, ?)",
                (project_id, project_data.get("project_name", path.name), str(path), now, now),
            )
