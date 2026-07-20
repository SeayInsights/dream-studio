"""Brownfield project intake pipeline.

Implements the four steps that precede security scanning:
  1. register_project_for_intake() — register + marker + UUID
  2. detect_and_persist_stack()    — run stack detector, write to business_projects
  3. create_security_scan_run()    — mint scan_id, determine if baseline
  4. persist_security_findings()   — write findings to findings

And the execution dispatch:
  5. run_read_only_security_scan() — invoke ds-quality:security audit safely

All execution functions require an approved execution context from
external_validation.approve_read_only_execution() — no execution without
prior safety re-assertion.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.projects.external_validation import (
    assert_step_is_permitted,
    validate_approved_read_only_execution,
)
from core.projects.mutations import register_project


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── Finding hash computation ──────────────────────────────────────────────────


def compute_finding_hash(
    rule_id: str,
    file_path: str,
    code_excerpt: str | None,
) -> str:
    """Structural identity hash for a finding.

    Hash = SHA-256(rule_id + "|" + normalized_file_path + "|" + normalized_snippet).
    Stable across: line-number shifts, whitespace changes, comment edits.
    Sensitive to: the code excerpt itself changing (intentional — case 4 edge case).
    """
    norm_file = file_path.replace("\\", "/").strip()
    norm_snippet = _normalize_snippet(code_excerpt or "")
    h = hashlib.sha256()
    h.update(f"{rule_id}|{norm_file}|{norm_snippet}".encode())
    return h.hexdigest()


def _normalize_snippet(s: str) -> str:
    """Aggressively normalize a code snippet for structural comparison.

    Strips leading/trailing whitespace, collapses internal whitespace,
    and removes trailing comment content so reformatting doesn't churn.
    """
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)  # collapse any whitespace run to single space
    # Remove trailing JS/TS line comment (// ...) to absorb comment reformats
    s = re.sub(r"\s*//.*$", "", s, flags=re.MULTILINE)
    return s.strip()


def _require_db() -> Path:
    from core.config.database import _default_db_path

    return _default_db_path()


# ── Phase 2: Register-first ───────────────────────────────────────────────────


def register_project_for_intake(
    target_path: Path,
    *,
    project_name: str | None = None,
    write_marker: bool = False,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Register a brownfield project in business_projects.

    No-marker default (write_marker=False): project_path stored in business_projects;
    no .dream-studio-project file written to the target repo. The SQLite path-fallback
    resolver handles session attribution for developers who work in this repo later.

    write_marker=True for persistent projects where marker-based resolution is preferred
    (e.g., active ongoing development, not one-time brownfield scans).

    Returns the register_project() result dict with project_id UUID.
    """
    resolved = Path(target_path).resolve()
    name = project_name or resolved.name

    # WO-PROJECT-REG-HARDENING: idempotency — reuse an existing non-deleted
    # registration for this path instead of minting a duplicate project (prefer
    # active over paused, most-recent first). Re-running intake on an already
    # registered/marked repo must not create a new business_projects row.
    from core.projects.mutations import _write_project_marker
    from core.projects.queries import _require_db

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT project_id, name, status, created_at FROM business_projects"
            " WHERE project_path = ? AND status != 'deleted'"
            " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,"
            " updated_at DESC LIMIT 1",
            (str(resolved),),
        ).fetchone()
    if existing is not None:
        if write_marker:
            _write_project_marker(
                resolved,
                existing["project_id"],
                existing["name"],
                existing["created_at"],
                db_path=db_path,
            )
        return {
            "ok": True,
            "project_id": existing["project_id"],
            "name": existing["name"],
            "status": existing["status"],
            "project_path": str(resolved),
            "reused": True,
            "message": f"Reused existing registration for {resolved}",
        }

    return register_project(
        name=name,
        description=f"Brownfield intake: {resolved}",
        project_path=resolved,
        write_marker=write_marker,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )


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
        # WO-BROWNFIELD-ADAPTIVE: persist the detector's skill-dispatch signals so
        # adaptive routing (core.projects.adaptive_routing) can recommend relevant
        # ds-quality modes per repo.
        "web_framework": result.web_framework,
        "frontend_framework": result.frontend_framework,
        "database_type": result.database_type,
        "test_framework": result.test_framework,
        "architecture_framework": result.architecture_framework,
        "monorepo_type": result.monorepo_type,
        "has_dockerfile": result.has_dockerfile,
        "has_docker_compose": result.has_docker_compose,
        "has_k8s_manifest": result.has_k8s_manifest,
        "deployment_type": result.deployment_type,
        "has_pii_schema": result.has_pii_schema,
        "compliance_hints": result.compliance_hints,
        "service_type": result.service_type,
        "release_tooling": result.release_tooling,
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
    previous_scan_id: str | None = None,
) -> str:
    """Create a security scan run. Delegates to create_skill_scan_run(skill_id='security')."""
    return create_skill_scan_run(
        project_id,
        target_path,
        skill_id="security",
        execution_ctx=execution_ctx,
        scope=scope,
        previous_scan_id=previous_scan_id,
    )


def create_skill_scan_run(
    project_id: str,
    target_path: Path,
    *,
    skill_id: str,
    execution_ctx: dict[str, Any],
    scope: str = "full_repo",
    previous_scan_id: str | None = None,
) -> str:
    """Create a skill scan run row and return the scan_id.

    Generic version of create_security_scan_run() that works for any quality skill
    (security, code-quality, types-deps, etc.). All skills share the same
    scan_runs table (differentiated by skill_id) and findings
    table (differentiated by rule_id prefix: sec-*, cq-*, typ-*, dep-*, etc.).

    Determines if this is the baseline scan (first completed scan for this project
    AND this skill_id). When previous_scan_id is provided, links this scan to its
    predecessor for delta computation.

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
        # Baseline = first completed scan for this (project, skill) pair
        existing_completed = conn.execute(
            "SELECT scan_id FROM scan_runs"
            " WHERE project_id = ? AND skill_id = ? AND status = 'completed'"
            " ORDER BY completed_at DESC LIMIT 1",
            (project_id, skill_id),
        ).fetchone()
        is_baseline = 1 if existing_completed is None else 0
        prev_id = previous_scan_id or (existing_completed[0] if existing_completed else None)

        tool_versions = _collect_tool_versions()

        conn.execute(
            """INSERT INTO scan_runs
               (scan_id, project_id, skill_id, is_baseline, scope, target_path,
                tool_versions_json, previous_scan_id, status, started_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)""",
            (
                scan_id,
                project_id,
                skill_id,
                is_baseline,
                scope,
                str(Path(target_path).resolve()),
                json.dumps(tool_versions),
                prev_id,
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
    """Write security findings to findings table, keyed to project UUID.

    Each finding dict must have at minimum:
      rule_id, severity, description
    Optional: file_path, start_line, end_line, category, recommendation,
              code_excerpt (used for finding_hash), enclosing_symbol

    Computes finding_hash = structural identity hash for each finding.
    The hash enables exact-match delta computation across scans without LLM.

    Returns count of findings written.
    """
    if not findings:
        _complete_scan_run(scan_id, findings_count=0)
        return 0

    db_path = _require_db()
    written = 0
    severity_counts: dict[str, int] = {}

    # findings table retired in migration 112 (WO-Y). Write to security_events spine.
    from core.findings.mutations import record_finding as _record_finding

    for f in findings:
        severity = str(f.get("severity", "medium")).lower()
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

        rule_id = f.get("rule_id") or ""
        file_path = f.get("file_path") or ""

        try:
            _record_finding(
                project_id=project_id,
                work_order_id=None,
                severity=severity,
                title=str(f.get("description", "")),
                body=f.get("recommendation"),
                file_path=file_path or None,
                line_number=f.get("start_line"),
                scanner_type=None,
                cwe_id=None,
                owasp_category=None,
                cve_id=None,
                vuln_class=rule_id or f.get("category") or None,
                exploitability=None,
                correlation_id=scan_id,
                db_path=db_path,
            )
            written += 1
        except Exception:
            pass

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
            """UPDATE scan_runs
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
    from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL

    db_path = _require_db()
    try:
        with _connect(db_path) as conn:
            runs = conn.execute(
                """SELECT scan_id, is_baseline, scope, findings_count,
                          critical_count, high_count, medium_count, low_count,
                          status, started_at, completed_at
                   FROM scan_runs
                   WHERE project_id = ?
                   ORDER BY started_at DESC""",
                (project_id,),
            ).fetchall()
            finding_rows = conn.execute(
                # findings retired migration 112 (WO-Y); findings_current_status
                # dropped migration 140 (WO dff23cb0) — derive from security_events
                # (see core/findings/current_status.py).
                f"""SELECT COALESCE(se.vuln_class,'') AS rule_id, fcs.severity,
                          fcs.file_path, fcs.line_number AS start_line,
                          COALESCE(fcs.title,'') AS description, fcs.current_status AS status
                   FROM ({FINDINGS_CURRENT_STATUS_SQL}) fcs
                   LEFT JOIN security_events se ON se.event_id = fcs.finding_id
                   WHERE fcs.project_id = ?
                   ORDER BY fcs.severity DESC, fcs.created_at DESC""",
                (project_id,),
            ).fetchall()
        return {
            "project_id": project_id,
            "scan_runs": [dict(r) for r in runs],
            "findings": [dict(f) for f in finding_rows],
            "finding_count": len(finding_rows),
        }
    except Exception as exc:
        return {"project_id": project_id, "error": str(exc)}
