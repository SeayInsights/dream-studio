#!/usr/bin/env python3
"""Repository content guard hook — scans repo files before skill LLM dispatch.

Fires when a skill is about to read repository files. Applies guard rules to
detect prompt injection attempts in source code. Advisory mode: logs findings,
never blocks skill execution.

Input (stdin JSON):
  {
    "skill_id": str,           # e.g. "ds-quality"
    "mode": str,               # e.g. "security:audit"
    "target_path": str,        # repo root being scanned
    "project_id": str | None,  # business_projects UUID
    "repo_files": list[str],   # files the skill will read
    "execution_context": dict  # from external_validation
  }

Output: none (advisory — writes findings to stdout and findings table)
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure stdout handles Unicode on all platforms (Windows cp1252 doesn't support all chars)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass  # Python < 3.7 or non-reconfigurable stdout

try:
    from guardrails.scanner_utils import (
        apply_llm_candidate_patterns,
        apply_static_patterns,
        is_suppressed,
        load_guard_rules,
    )

    _GUARD_AVAILABLE = True
except ImportError:
    _GUARD_AVAILABLE = False


# File types that get scanned
INCLUDED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".env",
    ".go",
    ".rs",
    ".sh",
    ".bash",
}

# Markdown only gets LLM-confirm (never static-fire)
MD_EXTENSIONS = {".md", ".markdown", ".mdx"}

# Hard-coded vendored path exclusions (supplement yaml-level suppressions)
VENDORED_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "vendor",
    "__pycache__",
    ".git",
    "dist",
    "build",
    ".next",
}


def _should_scan(file_path: str, suppressed_globs: list[str]) -> bool:
    """Return True if this file should be scanned."""
    p = Path(file_path)
    # Check extension
    if p.suffix.lower() not in (INCLUDED_EXTENSIONS | MD_EXTENSIONS):
        return False
    # Check vendored dirs in path components
    parts = set(p.parts)
    if parts & VENDORED_DIRS:
        return False
    # Check YAML-level suppression globs
    if is_suppressed(file_path, suppressed_globs):
        return False
    return True


def _scan_file(
    file_path: str,
    rules: list[dict],
    suppressed_globs: list[str],
    size_threshold_kb: int,
    md_llm_confirm_only: bool,
) -> tuple[list[dict], list[dict]]:
    """Scan one file. Returns (static_findings, llm_candidates)."""
    try:
        path = Path(file_path)
        if not path.exists():
            return [], []

        size_kb = path.stat().st_size / 1024
        content = path.read_text(encoding="utf-8", errors="replace")

        is_md = path.suffix.lower() in MD_EXTENSIONS
        over_size_limit = size_kb > size_threshold_kb

        static_findings = []
        if not is_md:  # Markdown never gets static-fire
            static_findings = apply_static_patterns(content, rules)

        llm_candidates = []
        if not over_size_limit:  # Skip LLM-confirm on large files
            llm_candidates = apply_llm_candidate_patterns(content, rules)

        return static_findings, llm_candidates
    except Exception:
        return [], []


def _write_findings_log(findings: list[dict], target_path: str, project_id: str | None) -> None:
    """Write guard findings to diagnostics log (advisory mode)."""
    try:
        diag_dir = Path(
            os.environ.get(
                "DS_DIAGNOSTICS_DIR",
                str(Path.home() / ".dream-studio" / "diagnostics"),
            )
        )
        diag_dir.mkdir(parents=True, exist_ok=True)
        log_file = diag_dir / "guard-findings.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            for finding in findings:
                entry = {
                    "source": "on-skill-input",
                    "project_id": project_id,
                    "target_path": target_path,
                    **finding,
                }
                f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _emit_guard_events(
    findings: list[dict],
    project_id: str | None,
    scan_id: str | None,
    skill_id: str,
    mode: str,
) -> None:
    """Emit guard_events rows to studio.db for each guard action.

    Phase 2: operational telemetry distinct from the scan-time findings table.
    Findings go to findings (scan-observations); guard_events go here (runtime decisions).
    """
    import uuid
    import datetime

    try:
        # Resolve studio.db path
        db_path = Path.home() / ".dream-studio" / "state" / "studio.db"
        env_path = os.environ.get("DREAM_STUDIO_DB_PATH")
        if env_path:
            db_path = Path(env_path)
        if not db_path.exists():
            return

        import sqlite3

        conn = sqlite3.connect(str(db_path))
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for finding in findings:
                event_id = str(uuid.uuid4())
                event_type = "guard_finding_logged"
                status = finding.get("status", "")
                if "candidate" in status:
                    event_type = "guard_candidate_logged"
                details = json.dumps(
                    {
                        "matched_text": finding.get("matched_text", "")[:200],
                        "description": finding.get("description", ""),
                        "skill_id": skill_id,
                        "mode": mode,
                    }
                )
                conn.execute(
                    """INSERT OR IGNORE INTO guard_events
                       (event_id, event_type, rule_id, severity, source_type, source_id,
                        project_id, scan_id, action, confidence, details, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        event_type,
                        finding.get("rule_id"),
                        finding.get("severity"),
                        "repo_file",
                        finding.get("file_path"),
                        project_id,
                        scan_id,
                        "logged",
                        finding.get("risk_weight", finding.get("confidence")),
                        details,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # Never crash the hook chain


try:
    from guardrails.memory_taint import taint_project_memory as _taint_project_memory

    _TAINT_AVAILABLE = True
except ImportError:
    _TAINT_AVAILABLE = False


def _taint_memory_entries(project_id: str, taint_reason: str) -> None:
    """Mark memory_entries sourced from project_id as tainted (delegates to memory_taint)."""
    if _TAINT_AVAILABLE:
        _taint_project_memory(project_id, taint_reason)


def main() -> None:
    """Scan repo files for prompt injection patterns before skill execution."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return  # Never crash the hook chain

    if not _GUARD_AVAILABLE:
        return

    target_path = payload.get("target_path", "")
    project_id = payload.get("project_id")
    repo_files = payload.get("repo_files", [])
    skill_id = payload.get("skill_id", "unknown")
    mode = payload.get("mode", "unknown")

    if not repo_files or not target_path:
        return

    try:
        guard_config = load_guard_rules()
        rules = guard_config.get("rules", [])
        suppressed_globs = guard_config.get("suppressed_paths", [])
        size_threshold_kb = guard_config.get("file_size_llm_threshold_kb", 500)
        md_llm_only = guard_config.get("md_files_llm_confirm_only", True)
    except Exception:
        return

    all_static_findings: list[dict] = []
    all_llm_candidates: list[dict] = []

    for rel_path in repo_files:
        full_path = (
            str(Path(target_path) / rel_path) if not Path(rel_path).is_absolute() else rel_path
        )

        if not _should_scan(rel_path, suppressed_globs):
            continue

        static_findings, llm_candidates = _scan_file(
            full_path, rules, suppressed_globs, size_threshold_kb, md_llm_only
        )

        for f in static_findings:
            f["file_path"] = rel_path
            f["skill_id"] = skill_id
            f["mode"] = mode
        for c in llm_candidates:
            c["file_path"] = rel_path
            c["skill_id"] = skill_id
            c["mode"] = mode

        all_static_findings.extend(static_findings)
        all_llm_candidates.extend(llm_candidates)

    # Log static findings immediately
    total_findings = len(all_static_findings)
    critical_count = sum(1 for f in all_static_findings if f.get("severity") == "critical")
    high_count = sum(1 for f in all_static_findings if f.get("severity") == "high")

    if all_static_findings:
        print(
            f"[GUARD] {skill_id}:{mode} — {total_findings} finding(s)"
            f" | {critical_count} CRITICAL, {high_count} HIGH",
            flush=True,
        )
        for finding in all_static_findings[:5]:  # Show first 5
            sev = finding["severity"].upper()
            tag = "[CRITICAL]" if sev == "CRITICAL" else "[HIGH]"
            print(
                f"   {tag} {finding['description']}"
                f" in {finding['file_path']}:{finding['line_number']}",
                flush=True,
            )
        if len(all_static_findings) > 5:
            print(
                f"   ... and {len(all_static_findings) - 5} more. See diagnostics log.",
                flush=True,
            )
    elif all_llm_candidates:
        print(
            f"[GUARD] {skill_id}:{mode} — {len(all_llm_candidates)}"
            f" candidate(s) pending LLM confirmation (advisory)",
            flush=True,
        )
    # If no findings: silent (don't pollute clean runs with "no issues found" noise)

    # Write to diagnostics log + emit guard_events (Phase 2)
    if all_static_findings or all_llm_candidates:
        all_to_log = all_static_findings + [
            {**c, "status": "candidate_pending_llm_confirm"} for c in all_llm_candidates
        ]
        _write_findings_log(all_to_log, target_path, project_id)

        # Phase 2: emit guard_events to studio.db (operational telemetry)
        scan_id = payload.get("scan_id")
        _emit_guard_events(all_to_log, project_id, scan_id, skill_id, mode)

        # Phase 2: taint memory entries sourced from this repo if CRITICAL findings found
        if project_id and critical_count > 0:
            taint_reason = (
                f"CRITICAL guard finding(s) detected during {skill_id}:{mode} scan: "
                f"{critical_count} critical, {high_count} high severity patterns found"
            )
            _taint_memory_entries(project_id, taint_reason)

    # Always continue (advisory mode — never exit non-zero)


if __name__ == "__main__":
    main()
