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

from analyze.discovery import discover_project
from analyze.research import research_stack
from analyze.audit import audit_architecture
from analyze.bugs import analyze_bugs
from analyze.synthesis import generate_prd
from analyze.stacks import AdapterRegistry, NextJSAdapter, AstroAdapter, PythonGenericAdapter
from analyze.stacks.detector import detect_stack
from hooks.lib.studio_db import _connect


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
    project_id = f"proj_{path.name}_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.time()

    # Initialize adapter registry
    registry = AdapterRegistry()
    registry.register(NextJSAdapter())
    registry.register(AstroAdapter())
    registry.register(PythonGenericAdapter())

    result = {
        "run_id": run_id,
        "project_id": project_id,
        "status": "running",
        "error": None,
        "duration_seconds": 0.0,
    }

    conn = _connect()
    cursor = conn.cursor()

    try:
        # Create project record first (required for foreign key constraint)
        project_name = path.name
        cursor.execute("""
            INSERT OR IGNORE INTO reg_projects (
                project_id, project_path, project_name, created_at
            ) VALUES (?, ?, ?, ?)
        """, (project_id, str(path), project_name, started_at))
        conn.commit()

        # Create analysis run record
        cursor.execute("""
            INSERT INTO pi_analysis_runs (
                run_id, project_id, run_type, started_at, status
            ) VALUES (?, ?, ?, ?, 'running')
        """, (run_id, project_id, run_type, started_at))
        conn.commit()

        # Phase 1: Discovery
        print(f"[{run_id}] Phase 1/5: Discovery...")
        project_data = discover_project(path)
        result["project_name"] = project_data.get("project_name", "unknown")
        result["project_data"] = project_data

        cursor.execute("""
            UPDATE pi_analysis_runs
            SET discovery_completed = 1
            WHERE run_id = ?
        """, (run_id,))
        conn.commit()

        # Detect stack
        detected = detect_stack(path)
        adapter = registry.get_adapter(detected.adapter) if detected.adapter else None
        stack = adapter.analyze_stack(path) if adapter else {"framework": "unknown"}
        result["stack"] = stack

        # Phase 2: Research
        print(f"[{run_id}] Phase 2/5: Research...")
        research = research_stack(stack, project_data)
        result["research"] = research

        cursor.execute("""
            UPDATE pi_analysis_runs
            SET research_completed = 1
            WHERE run_id = ?
        """, (run_id,))
        conn.commit()

        # Phase 3: Architecture Audit
        print(f"[{run_id}] Phase 3/5: Architecture Audit...")
        audit = audit_architecture(path, project_data, stack)
        result["audit"] = audit

        # Store violations in database
        for violation in audit.get("violations", []):
            _store_violation(conn, project_id, violation)

        # Store improvements in database
        for improvement in audit.get("improvements", []):
            _store_improvement(conn, project_id, improvement)

        violations_count = len(audit.get("violations", []))

        cursor.execute("""
            UPDATE pi_analysis_runs
            SET audit_completed = 1, violations_found = ?
            WHERE run_id = ?
        """, (violations_count, run_id))
        conn.commit()

        # Phase 4: Bug Analysis
        print(f"[{run_id}] Phase 4/5: Bug Analysis...")
        bugs = analyze_bugs(path, project_data, stack)
        result["bugs"] = bugs

        # Store bugs in database
        for bug in bugs.get("bugs", []):
            _store_bug(conn, project_id, bug)

        bugs_count = len(bugs.get("bugs", []))

        cursor.execute("""
            UPDATE pi_analysis_runs
            SET bug_analysis_completed = 1, bugs_found = ?
            WHERE run_id = ?
        """, (bugs_count, run_id))
        conn.commit()

        # Phase 5: Synthesis (PRD Generation)
        print(f"[{run_id}] Phase 5/5: PRD Generation...")
        prd_path = generate_prd(
            project_id=project_id,
            project_data=project_data,
            stack=stack,
            research=research,
            audit=audit,
            bugs=bugs
        )
        result["prd_path"] = prd_path

        cursor.execute("""
            UPDATE pi_analysis_runs
            SET synthesis_completed = 1
            WHERE run_id = ?
        """, (run_id,))
        conn.commit()

        # Update project metadata in reg_projects
        _update_project_metadata(conn, project_id, path, project_data, stack, audit)

        # Mark analysis as completed
        duration = time.time() - start_time
        result["duration_seconds"] = duration
        result["status"] = "completed"

        cursor.execute("""
            UPDATE pi_analysis_runs
            SET status = 'completed',
                completed_at = ?,
                duration_seconds = ?
            WHERE run_id = ?
        """, (datetime.now(timezone.utc).isoformat(), duration, run_id))
        conn.commit()

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

        cursor.execute("""
            UPDATE pi_analysis_runs
            SET status = 'failed', error_message = ?
            WHERE run_id = ?
        """, (str(e), run_id))
        conn.commit()

        print(f"[{run_id}] Analysis failed: {e}")
        raise

    finally:
        conn.close()

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

    conn.execute("""
        INSERT INTO pi_violations (
            violation_id, project_id, violation_type, severity,
            files, lines, description, impact, fix_recommendation, effort_estimate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        violation_id, project_id, vtype, violation.get("severity", "low"),
        files, lines, violation.get("description", ""),
        violation.get("impact", ""), violation.get("fix_recommendation", ""),
        violation.get("effort_estimate", "medium")
    ))


def _store_improvement(conn, project_id: str, improvement: Dict[str, Any]) -> None:
    """Store an improvement in pi_improvements table."""
    improvement_id = f"impr_{uuid.uuid4().hex[:12]}"

    # Map improvement type to schema constraint
    itype = improvement.get("type", "refactor")
    if itype not in ("refactor", "optimize", "modernize", "test_coverage", "documentation"):
        itype = "refactor"

    target_files = str(improvement.get("target_files", []))

    conn.execute("""
        INSERT INTO pi_improvements (
            improvement_id, project_id, improvement_type, priority_score,
            target_files, current_state, recommendation, benefit, effort_estimate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        improvement_id, project_id, itype, improvement.get("priority_score", 0.5),
        target_files, improvement.get("current_state", ""),
        improvement.get("recommendation", ""), improvement.get("benefit", ""),
        improvement.get("effort_estimate", "medium")
    ))


def _store_bug(conn, project_id: str, bug: Dict[str, Any]) -> None:
    """Store a bug in pi_bugs table."""
    bug_id = f"bug_{uuid.uuid4().hex[:12]}"

    # Map bug type to schema constraint
    btype = bug.get("type", "logic_error")
    if btype not in ("null_pointer", "race_condition", "resource_leak", "logic_error", "security_flaw"):
        btype = "logic_error"

    conn.execute("""
        INSERT INTO pi_bugs (
            bug_id, project_id, bug_type, category, severity,
            file, line, issue, description, proof, impact,
            fix_recommendation, effort_estimate, likelihood, risk_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        bug_id, project_id, btype, bug.get("category", "correctness"),
        bug.get("severity", "low"), bug.get("file", ""),
        bug.get("line", 0), bug.get("issue", ""),
        bug.get("description", ""), bug.get("proof", ""),
        bug.get("impact", ""), bug.get("fix_recommendation", ""),
        bug.get("effort_estimate", "medium"),
        bug.get("likelihood", 0.5), bug.get("risk_score", 0.5)
    ))


def _update_project_metadata(
    conn,
    project_id: str,
    path: Path,
    project_data: Dict[str, Any],
    stack: Dict[str, Any],
    audit: Dict[str, Any]
) -> None:
    """Update or insert project metadata in reg_projects."""
    # Check if project exists
    cursor = conn.execute("""
        SELECT project_id FROM reg_projects WHERE project_id = ?
    """, (project_id,))

    if cursor.fetchone():
        # Update existing
        conn.execute("""
            UPDATE reg_projects
            SET stack_detected = ?,
                stack_json = ?,
                health_score = ?,
                total_files = ?,
                lines_of_code = ?,
                last_analyzed = ?
            WHERE project_id = ?
        """, (
            stack.get("framework", "unknown"),
            str(stack),
            min(1.0, audit.get("health_score", 0.0) / 10.0),  # Normalize to 0-1
            len(project_data.get("file_inventory", {})),
            project_data.get("lines_of_code", {}).get("total", 0),
            datetime.now(timezone.utc).isoformat(),
            project_id
        ))
    else:
        # Insert new
        conn.execute("""
            INSERT INTO reg_projects (
                project_id, project_name, stack_detected, stack_json,
                health_score, total_files, lines_of_code, first_analyzed, last_analyzed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            project_data.get("project_name", path.name),
            stack.get("framework", "unknown"),
            str(stack),
            min(1.0, audit.get("health_score", 0.0) / 10.0),
            len(project_data.get("file_inventory", {})),
            project_data.get("lines_of_code", {}).get("total", 0),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

    conn.commit()
