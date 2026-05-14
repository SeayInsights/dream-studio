#!/usr/bin/env python3
"""Create GitHub issues for event-driven-refactor tasks"""

import subprocess
import sys
from pathlib import Path

# Track A Tasks
TRACK_A_TASKS = [
    (
        "TA-001",
        "Create backup of all databases",
        "TR-A05",
        "none",
        "All 3 DB files copied to backups/ with timestamps, SHA256 checksums recorded",
    ),
    (
        "TA-002",
        "Audit database schemas and connection strings",
        "TR-A01, TR-A05",
        "none",
        "Document created with table inventory, connection string list, schema conflicts identified",
    ),
    (
        "TA-003",
        "Create migration 021 (merge schemas)",
        "TR-A01",
        "TA-002",
        "Migration file created with CREATE TABLE IF NOT EXISTS for all analytics.db tables",
    ),
    (
        "TA-004",
        "Write database merge script",
        "TR-A01, TR-A05",
        "TA-003",
        "Script with dry-run mode, row count validation, rollback function, progress logging",
    ),
    (
        "TA-005",
        "Run database merge (dry-run)",
        "TR-A05",
        "TA-004",
        "Dry-run completes successfully, report shows 0 data loss, 0 FK violations",
    ),
    (
        "TA-006",
        "Run database merge (production)",
        "TR-A01, TR-A05",
        "TA-005",
        "Merge completes, validation script passes, all row counts match backup",
    ),
    (
        "TA-007",
        "Update connection strings in FastAPI",
        "TR-A01",
        "TA-006",
        "All routes query studio.db, API health check passes, no import errors",
    ),
    (
        "TA-008",
        "Update connection strings in hooks",
        "TR-A01",
        "TA-006",
        "All hooks use studio.db path, grep returns 0 matches for old DB names",
    ),
    (
        "TA-009",
        "Delete old databases",
        "TR-A01",
        "TA-007, TA-008",
        "Old DB files moved to backups/archived/, only studio.db remains, all tests pass",
    ),
    (
        "TA-010",
        "Audit hooks for decision logic",
        "TR-A02",
        "TA-009",
        "Document created with hook list, logic types, extraction targets identified",
    ),
    (
        "TA-011",
        "Simplify meta hooks",
        "TR-A02",
        "TA-010",
        "All meta hooks <50 lines, no decision logic, old versions saved as *_legacy.py",
    ),
    (
        "TA-012",
        "Simplify quality hooks",
        "TR-A02",
        "TA-010",
        "All quality hooks <50 lines, pattern detection extracted, old versions saved",
    ),
    (
        "TA-013",
        "Simplify core hooks",
        "TR-A02",
        "TA-010",
        "All core hooks <50 lines, workflow logic remains, old versions saved",
    ),
    (
        "TA-014",
        "Create guardrail data models",
        "TR-A03",
        "none",
        "Pydantic models defined: GuardrailRule, TriggerCondition, GuardrailDecision",
    ),
    (
        "TA-015",
        "Create migration 022 (guardrail metadata)",
        "TR-A03",
        "TA-014",
        "Migration creates guardrail_decisions and guardrail_rules_audit tables",
    ),
    (
        "TA-016",
        "Implement rule loader (YAML → models)",
        "TR-A03",
        "TA-014",
        "Function load_rules(path) returns list of GuardrailRule objects, validates schema",
    ),
    (
        "TA-017",
        "Implement rule evaluator",
        "TR-A03, TR-A04",
        "TA-015, TA-016",
        "Function evaluate(event_id) returns allow|block|require_approval, logs to DB",
    ),
    (
        "TA-018",
        "Create security guardrail rules",
        "TR-A03, TR-A04",
        "TA-017",
        "Rules defined: GR-001 (block secrets), GR-002 (require approval for critical vulns)",
    ),
    (
        "TA-019",
        "Create quality guardrail rules",
        "TR-A03",
        "TA-017",
        "Rules defined: GR-010 (warn on large commits), GR-011 (warn on missing tests)",
    ),
    (
        "TA-020",
        "Integrate guardrails with hooks",
        "TR-A04",
        "TA-018, TA-019",
        "Pre-commit hook calls evaluator, advisory messages print, exit code tested",
    ),
    (
        "TA-021",
        "Run full test suite",
        "TR-A06",
        "TA-011, TA-012, TA-013, TA-020",
        "pytest passes, check_hook_size.py confirms all hooks <50 lines",
    ),
    (
        "TA-022",
        "Performance benchmark",
        "TR-A07",
        "TA-021",
        "benchmark_queries.py shows no queries >20% slower, report saved",
    ),
]

# Track B Tasks
TRACK_B_TASKS = [
    (
        "TB-001",
        "Create analytics pyproject.toml",
        "TR-B01, TR-B06",
        "Track A TA-006",
        "Package definition with minimal dependencies, pip install succeeds",
    ),
    (
        "TB-002",
        "Extract event schema models",
        "TR-B01",
        "TB-001",
        "Pydantic models for CanonicalEvent, ActivityLog, HookExecution, SecurityFinding",
    ),
    (
        "TB-003",
        "Update analytics __init__.py imports",
        "TR-B01",
        "TB-002",
        "All imports relative to analytics package, import succeeds in clean venv",
    ),
    (
        "TB-004",
        "Create migration 023 (analytics views)",
        "TR-B02",
        "TB-003",
        "Migration creates 5 views: vw_security_summary, vw_activity_timeline, vw_risk_hotspots, vw_hook_performance, vw_guardrail_decisions",
    ),
    (
        "TB-005",
        "Implement vw_security_summary",
        "TR-B02",
        "TB-004",
        "View unifies sec_sarif_findings, sec_cve_matches, sec_manual_reviews, sec_hook_checks",
    ),
    (
        "TB-006",
        "Implement vw_activity_timeline",
        "TR-B02",
        "TB-004",
        "View queries activity_log, sorts by timestamp DESC, extracts JSON summary",
    ),
    (
        "TB-007",
        "Implement vw_risk_hotspots",
        "TR-B02",
        "TB-004",
        "View aggregates findings by file_path, filters open status, counts >=3",
    ),
    (
        "TB-008",
        "Implement vw_hook_performance + vw_guardrail_decisions",
        "TR-B02",
        "TB-004",
        "Both views query respective tables, aggregate correctly",
    ),
    (
        "TB-009",
        "Refactor security routes to view-driven",
        "TR-B02, TR-B04",
        "TB-005",
        "/security/findings queries vw_security_summary ONLY, response JSON unchanged",
    ),
    (
        "TB-010",
        "Refactor analytics routes to view-driven",
        "TR-B02, TR-B04",
        "TB-006",
        "All routes query vw_activity_timeline, no Python aggregations",
    ),
    (
        "TB-011",
        "Refactor hooks routes to view-driven",
        "TR-B02, TR-B04",
        "TB-008",
        "/hooks/performance queries vw_hook_performance, response unchanged",
    ),
    (
        "TB-012",
        "Add caching headers to all routes",
        "TR-B03",
        "TB-009, TB-010, TB-011",
        "All routes return Cache-Control: max-age=300, conditional requests supported",
    ),
    (
        "TB-013",
        "Implement risk scoring engine",
        "TR-B05",
        "TB-003",
        "Engine class with fetch_unscored_events(), compute_risk_score(), emit_enriched_event()",
    ),
    (
        "TB-014",
        "Add CLI for risk engine",
        "TR-B05",
        "TB-013",
        "CLI runs standalone for 5 min without errors, emits events to activity_log",
    ),
    (
        "TB-015",
        "Run full integration test",
        "TR-B03, TR-B04, TR-B06",
        "TB-012, TB-014",
        "All SC-B1..SC-B5 verified, benchmark shows >20% improvement",
    ),
]

# Track C Tasks
TRACK_C_TASKS = [
    (
        "TC-001",
        "Create adapters package structure",
        "TR-C01",
        "none",
        "Package structure with BaseAdapter, CanonicalEvent, TraceContext, imports succeed",
    ),
    (
        "TC-002",
        "Implement EventNormalizer",
        "TR-C01",
        "TC-001",
        "EventNormalizer class with normalize(), adapter registry, register_adapter()",
    ),
    (
        "TC-003",
        "Implement ClaudeAdapter",
        "TR-C02",
        "TC-001",
        "ClaudeAdapter with normalize(), preserves all Claude fields, backward compatible",
    ),
    (
        "TC-004",
        "Implement GPTAdapter + DefaultAdapter",
        "TR-C03, TR-C04",
        "TC-001",
        "GPTAdapter mock + DefaultAdapter pass-through with warning log",
    ),
    (
        "TC-005",
        "Create migration 024 (adapter metadata)",
        "TR-C01",
        "TC-002",
        "Migration creates adapter_executions table, no FK violations",
    ),
    (
        "TC-006",
        "Identify all activity_log.insert() callsites",
        "TR-C06",
        "none",
        "Document with grep results, list of files to modify, integration strategy",
    ),
    (
        "TC-007",
        "Integrate normalizer with skill invocation",
        "TR-C06",
        "TC-002, TC-003, TC-006",
        "Skill invocation calls event_normalizer.normalize(), one skill tested end-to-end",
    ),
    (
        "TC-008",
        "Update all activity_log callsites",
        "TR-C06",
        "TC-007",
        "All callsites use normalizer, no direct inserts without normalization",
    ),
    (
        "TC-009",
        "Run full verification",
        "TR-C02, TR-C03, TR-C04, TR-C05, TR-C06",
        "TC-008",
        "All SC-C1..SC-C5 verified, <10ms overhead, all skills pass",
    ),
]


def create_issue(task_id, title, implements, depends_on, acceptance, track):
    """Create a single GitHub issue"""
    body = f"""**Task ID:** {task_id}
**Track:** {track}
**Implements:** {implements}
**Depends on:** {depends_on}

**Acceptance Criteria:**
{acceptance}

**Spec:** .planning/specs/event-driven-refactor/

**Branch:** refactor/track-{track.lower()}-{task_id.lower()}
"""

    labels = f"track-{track.lower()},refactor,event-driven-architecture"

    cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        f"[{task_id}] {title}",
        "--body",
        body,
        "--label",
        labels,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issue_url = result.stdout.strip()
        print(f"✅ {task_id}: {issue_url}")
        return issue_url
    except subprocess.CalledProcessError as e:
        print(f"❌ {task_id}: Failed - {e.stderr}", file=sys.stderr)
        return None


def main():
    print("Creating GitHub issues for event-driven-refactor...\n")

    print("=== Track A: Data Plane (22 tasks) ===")
    for task_id, title, implements, depends_on, acceptance in TRACK_A_TASKS:
        create_issue(task_id, title, implements, depends_on, acceptance, "A")

    print("\n=== Track B: Analytics Plane (15 tasks) ===")
    for task_id, title, implements, depends_on, acceptance in TRACK_B_TASKS:
        create_issue(task_id, title, implements, depends_on, acceptance, "B")

    print("\n=== Track C: Control Plane (9 tasks) ===")
    for task_id, title, implements, depends_on, acceptance in TRACK_C_TASKS:
        create_issue(task_id, title, implements, depends_on, acceptance, "C")

    print("\n✅ All 46 issues created!")


if __name__ == "__main__":
    main()
