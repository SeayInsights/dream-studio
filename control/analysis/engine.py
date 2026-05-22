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
from typing import Dict, Any
from datetime import datetime, timezone
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
    from core.events.trace import TraceContext
    from core.adapters.normalizers import EventNormalizer

    _event_normalizer = EventNormalizer()
    _NORMALIZER_AVAILABLE = True
except ImportError:
    _NORMALIZER_AVAILABLE = False


def analyze_project(path: Path, run_type: str = "full") -> Dict[str, Any]:
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
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.time()

    # Initialize adapter registry
    registry = AdapterRegistry()
    registry.register(NextJSAdapter())
    registry.register(AstroAdapter())
    registry.register(PythonGenericAdapter())

    # Check if project already exists by path
    with transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT project_id FROM reg_projects WHERE project_path = ?
        """,
            (str(path),),
        )
        existing_project = cursor.fetchone()

    if existing_project:
        project_id = existing_project[0]
    else:
        project_id = f"proj_{path.name}_{uuid.uuid4().hex[:8]}"
        project_name = path.name

        planning_path = str(project_planning_dir(project_name))
        sessions_path = str(project_sessions_dir(project_name))

        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.PROJECT_REGISTERED.value,
                    session_id=None,
                    payload={
                        "project_id": project_id,
                        "project_path": redact_file_path(str(path)),
                        "project_name": project_name,
                        "project_source": "local",
                        "planning_path": redact_file_path(planning_path),
                        "sessions_path": redact_file_path(sessions_path),
                    },
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

        # Keep existing DB write (dual-write)
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO reg_projects (
                    project_id, project_path, project_name, created_at,
                    project_source, planning_path, sessions_path
                ) VALUES (?, ?, ?, ?, 'local', ?, ?)
            """,
                (project_id, str(path), project_name, started_at, planning_path, sessions_path),
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

        # Create analysis run record
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO pi_analysis_runs (
                    run_id, project_id, run_type, started_at, status
                ) VALUES (?, ?, ?, ?, 'running')
            """,
                (run_id, project_id, run_type, started_at),
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

        with transaction() as conn:
            conn.execute(
                """
                UPDATE pi_analysis_runs
                SET discovery_completed = 1
                WHERE run_id = ?
            """,
                (run_id,),
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

        with transaction() as conn:
            conn.execute(
                """
                UPDATE pi_analysis_runs
                SET research_completed = 1
                WHERE run_id = ?
            """,
                (run_id,),
            )

        # Phase 3: Architecture Audit
        print(f"[{run_id}] Phase 3/5: Architecture Audit...")
        audit = audit_architecture(path, project_data, stack)
        result["audit"] = audit

        violations_count = len(audit.get("violations", []))

        # Store violations and improvements in database (atomic)
        with transaction() as conn:
            # Store violations in database
            for violation in audit.get("violations", []):
                _store_violation(conn, project_id, violation)

            # Store improvements in database
            for improvement in audit.get("improvements", []):
                _store_improvement(conn, project_id, improvement)

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

        with transaction() as conn:
            conn.execute(
                """
                UPDATE pi_analysis_runs
                SET audit_completed = 1, violations_found = ?
                WHERE run_id = ?
            """,
                (violations_count, run_id),
            )

        # Phase 4: Bug Analysis
        print(f"[{run_id}] Phase 4/5: Bug Analysis...")
        bugs = analyze_bugs(path, project_data, stack)
        result["bugs"] = bugs

        bugs_count = len(bugs.get("bugs", []))

        # Store bugs in database
        with transaction() as conn:
            for bug in bugs.get("bugs", []):
                _store_bug(conn, project_id, bug)

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

        with transaction() as conn:
            conn.execute(
                """
                UPDATE pi_analysis_runs
                SET bug_analysis_completed = 1, bugs_found = ?
                WHERE run_id = ?
            """,
                (bugs_count, run_id),
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

        with transaction() as conn:
            conn.execute(
                """
                UPDATE pi_analysis_runs
                SET synthesis_completed = 1
                WHERE run_id = ?
            """,
                (run_id,),
            )

        # Update project metadata in reg_projects
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

        with transaction() as conn:
            conn.execute(
                """
                UPDATE pi_analysis_runs
                SET status = 'completed',
                    completed_at = ?,
                    duration_seconds = ?
                WHERE run_id = ?
            """,
                (datetime.now(timezone.utc).isoformat(), duration, run_id),
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

        with transaction() as conn:
            conn.execute(
                """
                UPDATE pi_analysis_runs
                SET status = 'failed', error_message = ?
                WHERE run_id = ?
            """,
                (str(e), run_id),
            )

        print(f"[{run_id}] Analysis failed: {e}")
        raise

    return result


def _store_violation(conn, project_id: str, violation: Dict[str, Any]) -> None:
    """Store a violation in pi_violations table."""
    violation_id = f"viol_{uuid.uuid4().hex[:12]}"

    # Map violation type to schema constraint
    vtype = violation.get("type", "architecture")
    if vtype not in ("architecture", "style", "security", "performance"):
        vtype = "architecture"

    files = str(violation.get("files", []))
    lines = str(violation.get("lines", []))

    conn.execute(
        """
        INSERT INTO pi_violations (
            violation_id, project_id, violation_type, severity,
            files, lines, description, impact, fix_recommendation, effort_estimate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            violation_id,
            project_id,
            vtype,
            violation.get("severity", "low"),
            files,
            lines,
            violation.get("description", ""),
            violation.get("impact", ""),
            violation.get("fix_recommendation", ""),
            violation.get("effort_estimate", "medium"),
        ),
    )


def _store_improvement(conn, project_id: str, improvement: Dict[str, Any]) -> None:
    """Store an improvement in pi_improvements table."""
    improvement_id = f"impr_{uuid.uuid4().hex[:12]}"

    # Map improvement type to schema constraint
    itype = improvement.get("type", "refactor")
    if itype not in ("refactor", "optimize", "modernize", "test_coverage", "documentation"):
        itype = "refactor"

    target_files = str(improvement.get("target_files", []))

    conn.execute(
        """
        INSERT INTO pi_improvements (
            improvement_id, project_id, improvement_type, priority_score,
            target_files, current_state, recommendation, benefit, effort_estimate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            improvement_id,
            project_id,
            itype,
            improvement.get("priority_score", 0.5),
            target_files,
            improvement.get("current_state", ""),
            improvement.get("recommendation", ""),
            improvement.get("benefit", ""),
            improvement.get("effort_estimate", "medium"),
        ),
    )


def _store_bug(conn, project_id: str, bug: Dict[str, Any]) -> None:
    """Store a bug in pi_bugs table."""
    bug_id = f"bug_{uuid.uuid4().hex[:12]}"

    # Map bug type to schema constraint
    btype = bug.get("type", "logic_error")
    if btype not in (
        "null_pointer",
        "race_condition",
        "resource_leak",
        "logic_error",
        "security_flaw",
    ):
        btype = "logic_error"

    conn.execute(
        """
        INSERT INTO pi_bugs (
            bug_id, project_id, bug_type, category, severity,
            file, line, issue, description, proof, impact,
            fix_recommendation, effort_estimate, likelihood, risk_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            bug_id,
            project_id,
            btype,
            bug.get("category", "correctness"),
            bug.get("severity", "low"),
            bug.get("file", ""),
            bug.get("line", 0),
            bug.get("issue", ""),
            bug.get("description", ""),
            bug.get("proof", ""),
            bug.get("impact", ""),
            bug.get("fix_recommendation", ""),
            bug.get("effort_estimate", "medium"),
            bug.get("likelihood", 0.5),
            bug.get("risk_score", 0.5),
        ),
    )


def _update_project_metadata(
    project_id: str,
    path: Path,
    project_data: Dict[str, Any],
    stack: Dict[str, Any],
    audit: Dict[str, Any],
) -> None:
    """Update or insert project metadata in reg_projects."""
    # Check if project exists
    with transaction() as conn:
        cursor = conn.execute(
            """
            SELECT project_id FROM reg_projects WHERE project_id = ?
        """,
            (project_id,),
        )
        exists = cursor.fetchone()

    if exists:
        # Slice 3: Emit event via spool pipeline
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

        # Update existing
        with transaction() as conn:
            conn.execute(
                """
                UPDATE reg_projects
                SET stack_detected = ?,
                    stack_json = ?,
                    health_score = ?,
                    total_files = ?,
                    lines_of_code = ?,
                    last_analyzed = ?
                WHERE project_id = ?
            """,
                (
                    stack.get("framework", "unknown"),
                    str(stack),
                    min(1.0, audit.get("health_score", 0.0) / 10.0),  # Normalize to 0-1
                    len(project_data.get("file_inventory", {})),
                    project_data.get("lines_of_code", {}).get("total", 0),
                    datetime.now(timezone.utc).isoformat(),
                    project_id,
                ),
            )
    else:
        # Slice 3: Emit event via spool pipeline
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

        # Insert new
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO reg_projects (
                    project_id, project_name, stack_detected, stack_json,
                    health_score, total_files, lines_of_code, first_analyzed, last_analyzed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    project_id,
                    project_data.get("project_name", path.name),
                    stack.get("framework", "unknown"),
                    str(stack),
                    min(1.0, audit.get("health_score", 0.0) / 10.0),
                    len(project_data.get("file_inventory", {})),
                    project_data.get("lines_of_code", {}).get("total", 0),
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
