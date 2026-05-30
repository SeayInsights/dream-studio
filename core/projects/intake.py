"""Brownfield project intake pipeline.

Implements the four steps that precede security scanning:
  1. register_project_for_intake() — register + marker + UUID
  2. detect_and_persist_stack()    — run stack detector, write to business_projects
  3. create_security_scan_run()    — mint scan_id, determine if baseline
  4. persist_security_findings()   — write findings to security_findings

And the execution dispatch:
  5. run_read_only_security_scan() — invoke ds-quality:security audit safely

All execution functions require an approved execution context from
external_validation.approve_read_only_execution() — no execution without
prior safety re-assertion.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.projects.external_validation import (
    PRIVATE_TARGET_ARTIFACT_PATTERNS,
    assert_step_is_permitted,
    validate_approved_read_only_execution,
)
from core.projects.mutations import register_project


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_db() -> Path:
    from core.config.database import _default_db_path

    return _default_db_path()


# ── Phase 2: Register-first ───────────────────────────────────────────────────


def register_project_for_intake(
    target_path: Path,
    *,
    project_name: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Register a brownfield project in business_projects and write its marker.

    Returns the register_project() result dict with project_id UUID.
    After this call, resolve_project_from_cwd() on target_path returns the UUID
    (session hooks attribute correctly, not to None).

    This is a WRITE to Dream Studio's own SQLite — it does not touch the target repo.
    The .dream-studio-project marker IS written to target_path (that's the intent —
    register the repo so findings attribute correctly).
    """
    resolved = Path(target_path).resolve()
    name = project_name or resolved.name

    result = register_project(
        name=name,
        description=f"Brownfield intake: {resolved}",
        project_path=resolved,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    return result


# ── Phase 3: Stack detection ──────────────────────────────────────────────────


def detect_and_persist_stack(
    project_id: str,
    target_path: Path,
) -> dict[str, Any]:
    """Run stack detector against target_path and persist result to business_projects.

    Returns {"detected_stack": str, "confidence": float, "signals": [...]}

    Reads the target repo's manifest files (package.json, pyproject.toml, go.mod,
    Cargo.toml, etc.) — this is read-only and does not modify the target.
    """
    from control.analysis.stacks.detector import detect_stack

    result = detect_stack(Path(target_path).resolve())
    stack_id = result.adapter or "unknown"
    stack_data = {
        "adapter": result.adapter,
        "framework": result.framework,
        "version": result.version,
        "confidence": result.confidence,
        "signals": [
            {"name": s.name, "confidence": s.confidence, "source": s.source} for s in result.signals
        ],
    }

    db_path = _require_db()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE business_projects"
            " SET detected_stack = ?, stack_json = ?, updated_at = ?"
            " WHERE project_id = ?",
            (stack_id, json.dumps(stack_data), _now(), project_id),
        )
        conn.commit()

    return {"detected_stack": stack_id, **stack_data}


# ── Phase 5: Security scan run creation + findings persistence ────────────────


def create_security_scan_run(
    project_id: str,
    target_path: Path,
    *,
    execution_ctx: dict[str, Any],
    scope: str = "full_repo",
) -> str:
    """Create a security_scan_runs row and return the scan_id.

    Determines if this is the baseline scan (first scan for this project).
    Requires a valid approved execution context — safety is re-asserted here.
    """
    # Re-assert execution safety before touching the scan record
    assert_step_is_permitted("run_read_only_validation", execution_ctx)
    ctx_issues = validate_approved_read_only_execution(execution_ctx)
    if ctx_issues:
        raise ValueError(f"Safety violations in execution context: {ctx_issues}")

    scan_id = str(uuid.uuid4())
    now = _now()
    db_path = _require_db()

    with _connect(db_path) as conn:
        # Determine if this is the baseline (first scan for this project)
        existing = conn.execute(
            "SELECT COUNT(*) FROM security_scan_runs WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        is_baseline = 1 if existing == 0 else 0

        # Collect tool versions
        tool_versions = _collect_tool_versions()

        conn.execute(
            """INSERT INTO security_scan_runs
               (scan_id, project_id, is_baseline, scope, target_path,
                tool_versions_json, status, started_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)""",
            (
                scan_id,
                project_id,
                is_baseline,
                scope,
                str(Path(target_path).resolve()),
                json.dumps(tool_versions),
                now,
                now,
            ),
        )
        conn.commit()

    return scan_id


def _collect_tool_versions() -> dict[str, str]:
    """Collect installed security tool versions for audit trail."""
    versions: dict[str, str] = {}
    tools = {
        "gitleaks": ["gitleaks", "version"],
        "bandit": ["python", "-m", "bandit", "--version"],
        "semgrep": ["semgrep", "--version"],
        "pip_audit": ["python", "-m", "pip_audit", "--version"],
    }
    for tool_name, cmd in tools.items():
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (result.stdout + result.stderr).strip()
            first_line = output.splitlines()[0] if output else "unknown"
            versions[tool_name] = first_line
        except Exception:
            versions[tool_name] = "not_available"
    return versions


def persist_security_findings(
    scan_id: str,
    project_id: str,
    findings: list[dict[str, Any]],
) -> int:
    """Write security findings to security_findings table, keyed to project UUID.

    Each finding dict must have at minimum:
      rule_id, severity, description
    Optional: file_path, start_line, end_line, category, recommendation

    Returns count of findings written.
    """
    if not findings:
        _complete_scan_run(scan_id, findings_count=0)
        return 0

    db_path = _require_db()
    now = _now()
    written = 0
    severity_counts: dict[str, int] = {}

    with _connect(db_path) as conn:
        for f in findings:
            severity = str(f.get("severity", "medium")).lower()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

            conn.execute(
                """INSERT OR IGNORE INTO security_findings
                   (finding_id, project_id, scan_id, severity, category,
                    rule_id, file_path, start_line, end_line, description,
                    recommendation, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                (
                    str(uuid.uuid4()),
                    project_id,
                    scan_id,
                    severity,
                    f.get("category"),
                    f.get("rule_id"),
                    f.get("file_path"),
                    f.get("start_line"),
                    f.get("end_line"),
                    str(f.get("description", "")),
                    f.get("recommendation"),
                    now,
                    now,
                ),
            )
            written += conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()

    _complete_scan_run(scan_id, findings_count=written, severity_counts=severity_counts)
    return written


def _complete_scan_run(
    scan_id: str,
    findings_count: int = 0,
    severity_counts: dict[str, int] | None = None,
) -> None:
    sc = severity_counts or {}
    db_path = _require_db()
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE security_scan_runs
               SET status = 'completed',
                   findings_count = ?,
                   critical_count = ?,
                   high_count = ?,
                   medium_count = ?,
                   low_count = ?,
                   completed_at = ?
               WHERE scan_id = ?""",
            (
                findings_count,
                sc.get("critical", 0),
                sc.get("high", 0),
                sc.get("medium", 0),
                sc.get("low", 0),
                _now(),
                scan_id,
            ),
        )
        conn.commit()


# ── Scan scope: exclude private artifacts ─────────────────────────────────────


def build_scan_scope(
    target_path: Path,
    execution_ctx: dict[str, Any],
) -> list[Path]:
    """Return the list of files in scope for a read-only security scan.

    Enforces TWO exclusion layers:
    1. Private artifact exclusions (safety requirement, from execution context)
    2. Generated/vendored dirs (performance, correctness — not source code)

    This is the enforcement point for private artifact exclusion at execution time.
    """
    import fnmatch

    # Re-assert: private artifact exclusions must be present in execution context
    safety = execution_ctx.get("safety_assertions", {})
    exclusion_patterns = safety.get("private_artifact_exclusions")
    if not exclusion_patterns:
        raise ValueError(
            "private_artifact_exclusions not present in execution context safety_assertions. "
            "Cannot build scan scope without the exclusion list — this is a safety requirement."
        )

    # Generated/vendored dirs — not source code, excluded for performance + accuracy
    _SKIP_DIRS: frozenset[str] = frozenset(
        {
            "node_modules",
            ".next",
            ".nuxt",
            ".svelte-kit",
            "dist",
            "build",
            "out",
            ".git",
            "__pycache__",
            ".pytest_cache",
            ".tox",
            "venv",
            ".venv",
            "vendor",
            ".wrangler",
            ".react-router",
            "playwright-report",
            "test-results",
            "coverage",
            ".cache",
        }
    )

    root = Path(target_path).resolve()
    in_scope: list[Path] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # Skip generated/vendored dirs
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        # Apply private artifact exclusions using pathlib.match() which handles ** correctly,
        # plus fnmatch for non-** patterns. Pathlib match() anchors from the right so
        # "**/.env.*" matches both root-level .env.local and nested .env.local.
        excluded = False
        for pattern in exclusion_patterns:
            pat = pattern.lstrip("/")
            # pathlib.Path.match() handles ** patterns correctly
            if p.match(pat):
                excluded = True
                break
            # fallback: fnmatch for simple patterns (no **)
            if "**" not in pat and fnmatch.fnmatch(rel, pat):
                excluded = True
                break
        if not excluded:
            in_scope.append(p)

    return in_scope


def get_scan_summary(project_id: str) -> dict[str, Any]:
    """Return scan history summary for a project (queryable per project_id)."""
    db_path = _require_db()
    try:
        with _connect(db_path) as conn:
            runs = conn.execute(
                """SELECT scan_id, is_baseline, scope, findings_count,
                          critical_count, high_count, medium_count, low_count,
                          status, started_at, completed_at
                   FROM security_scan_runs
                   WHERE project_id = ?
                   ORDER BY started_at DESC""",
                (project_id,),
            ).fetchall()
            findings = conn.execute(
                """SELECT rule_id, severity, file_path, start_line, description, status
                   FROM security_findings
                   WHERE project_id = ?
                   ORDER BY severity DESC, created_at DESC""",
                (project_id,),
            ).fetchall()
        return {
            "project_id": project_id,
            "scan_runs": [dict(r) for r in runs],
            "findings": [dict(f) for f in findings],
            "finding_count": len(findings),
        }
    except Exception as exc:
        return {"project_id": project_id, "error": str(exc)}
