"""Project PRD lifecycle, change-order, milestone, and route authority.

This module keeps product authority in SQLite and treats files as optional
exports. It deliberately uses injected SQLite connections so tests and release
gates can run against rehearsal databases without touching the live install.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

PRD_AUTHORITY_SOURCE_TABLES: tuple[str, ...] = (
    "project_intake_records",
    "project_intake_questions",
    "project_assumption_records",
    "prd_version_records",
    "project_milestone_records",
    "project_work_order_authority_records",
    "project_change_order_records",
    "prd_amendment_records",
    "prd_route_reconciliation_records",
    "prd_documents",
    "business_projects",  # reg_projects deleted in migration 084
)

QUESTION_MODES = {
    "quick_start",
    "standard_discovery",
    "full_discovery",
    "import_existing_project",
}
PRD_LIFECYCLE_STATES = {
    "draft_generated",
    "in_flight_formalization",
    "user_review_required",
    "user_confirmed",
    "current",
    "needs_update",
    "superseded",
    "manual_review_required",
    "closed_reconciled",
}
FORMALIZATION_CONFIDENCE = {
    "high_confidence_current",
    "medium_confidence_needs_review",
    "draft_generated_needs_operator_review",
    "manual_review_required",
}
CHANGE_TYPES = {
    "scope_addition",
    "scope_reduction",
    "requirement_change",
    "architecture_change",
    "data_model_change",
    "security_or_privacy_change",
    "integration_change",
    "UI_or_design_change",
    "release_target_change",
    "priority_change",
    "assumption_change",
    "non_goal_change",
    "milestone_replan",
    "manual_review_required",
}

MILESTONE_TEMPLATE: tuple[tuple[str, str], ...] = (
    ("intake-formalization", "Intake / formalization"),
    ("architecture-data-model", "Architecture / data model"),
    ("core-implementation", "Core implementation"),
    ("ui-ux-design", "UI / UX / design"),
    ("security-readiness", "Security / readiness"),
    ("validation", "Validation"),
    ("release-demo-deployment", "Release / demo / deployment"),
    ("documentation-cleanup", "Documentation / cleanup"),
    ("closeout-reconciliation", "Closeout / reconciliation"),
)

QUESTION_BANK: tuple[dict[str, Any], ...] = (
    {
        "group": "product purpose",
        "question": "What problem should this project solve for its users?",
        "criticality": "critical",
        "keywords": ("problem", "purpose", "solve", "goal", "platform", "tool"),
    },
    {
        "group": "target users",
        "question": "Who are the primary target users or operators?",
        "criticality": "critical",
        "keywords": ("user", "operator", "customer", "team", "audience"),
    },
    {
        "group": "core use cases",
        "question": "What are the first workflows or use cases that must work?",
        "criticality": "important",
        "keywords": ("workflow", "use case", "feature", "flow", "task"),
    },
    {
        "group": "goals",
        "question": "Which outcomes define success for the initial version?",
        "criticality": "important",
        "keywords": ("success", "metric", "outcome", "acceptance"),
    },
    {
        "group": "non-goals",
        "question": "What should stay out of scope for this version?",
        "criticality": "important",
        "keywords": ("non-goal", "out of scope", "avoid", "exclude"),
    },
    {
        "group": "MVP scope",
        "question": "What is the smallest useful MVP scope?",
        "criticality": "critical",
        "keywords": ("mvp", "minimum", "first version", "initial"),
    },
    {
        "group": "data/storage needs",
        "question": "What data must be stored, imported, or retained?",
        "criticality": "critical",
        "keywords": ("database", "data", "sqlite", "storage", "retention", "import"),
    },
    {
        "group": "security/privacy sensitivity",
        "question": "Does the project handle private, sensitive, regulated, auth, payment, or personal data?",
        "criticality": "critical",
        "keywords": (
            "auth",
            "secret",
            "private",
            "pii",
            "payment",
            "health",
            "financial",
            "children",
            "security",
        ),
    },
    {
        "group": "integrations",
        "question": "Which external systems, APIs, files, or repos are in scope?",
        "criticality": "important",
        "keywords": ("api", "github", "integration", "webhook", "external", "mcp"),
    },
    {
        "group": "AI/tool/model needs",
        "question": "Which AI adapters, tools, or model providers are expected to participate?",
        "criticality": "important",
        "keywords": ("ai", "adapter", "claude", "codex", "model", "agent"),
    },
    {
        "group": "frontend/backend/database needs",
        "question": "What frontend, backend, API, and database surfaces are expected?",
        "criticality": "important",
        "keywords": ("frontend", "backend", "api", "dashboard", "ui", "database"),
    },
    {
        "group": "deployment/release expectations",
        "question": "Where should this run, and what release or deployment boundary applies?",
        "criticality": "critical",
        "keywords": ("deploy", "release", "publish", "install", "local", "cloud"),
    },
    {
        "group": "timeline/priority",
        "question": "What is the timeline, urgency, or priority order?",
        "criticality": "important",
        "keywords": ("timeline", "priority", "deadline", "urgent"),
    },
    {
        "group": "constraints",
        "question": "What constraints, guardrails, dependencies, or approval boundaries apply?",
        "criticality": "critical",
        "keywords": ("constraint", "guardrail", "approval", "policy", "boundary"),
    },
    {
        "group": "desired autonomy level",
        "question": "Should Dream Studio ask before each step, continue through safe milestones, or stop at every gate?",
        "criticality": "important",
        "keywords": ("continue", "autonomous", "approval", "ask", "safe"),
    },
)


def build_project_intake_plan(
    project_description: str,
    *,
    mode: str = "standard_discovery",
    project_id: str | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Create adaptive intake questions without writing state."""

    question_mode = _enum(mode, QUESTION_MODES, "standard_discovery")
    description = project_description or ""
    answered = _answered_groups(description)
    questions: list[dict[str, Any]] = []
    for spec in QUESTION_BANK:
        already_answered = spec["group"] in answered
        if _include_question(question_mode, spec["criticality"], already_answered):
            qid = _stable_id(
                "intake-question",
                project_id or project_name or "new-project",
                question_mode,
                spec["group"],
            )
            questions.append(
                {
                    "question_id": qid,
                    "group": spec["group"],
                    "question": spec["question"],
                    "criticality": spec["criticality"],
                    "already_answered": already_answered,
                    "inferred_answer": (
                        "Covered by provided project description." if already_answered else None
                    ),
                    "response_status": "assumption" if already_answered else "pending",
                }
            )

    if question_mode == "import_existing_project":
        questions.insert(
            0,
            {
                "question_id": _stable_id(
                    "intake-question", project_id or project_name or "new-project", "repo-evidence"
                ),
                "group": "existing evidence",
                "question": "Which repo/docs/evidence surfaces are approved for read-only intake?",
                "criticality": "critical",
                "already_answered": False,
                "inferred_answer": None,
                "response_status": "pending",
            },
        )

    assumptions, unknowns = _assumptions_and_unknowns(description, questions, answered)
    return {
        "model_name": "dream_studio_project_intake_plan",
        "derived_view": True,
        "primary_authority": False,
        "writes_authorized": False,
        "project_id": project_id,
        "project_name": project_name,
        "question_mode": question_mode,
        "question_count": len(questions),
        "questions": questions,
        "question_groups": sorted({question["group"] for question in questions}),
        "assumptions": assumptions,
        "known_unknowns": unknowns,
        "classification": _project_classification(description),
        "policy": {
            "do_not_jump_straight_to_code": True,
            "ask_only_critical_blockers_in_quick_start": question_mode == "quick_start",
            "mark_assumptions_explicitly": True,
            "mark_unknowns_explicitly": True,
        },
    }


def project_prd_authority_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return dashboard-ready PRD lifecycle authority."""

    missing = _missing_source_tables(conn)
    if missing:
        return _empty_summary(project_id, missing)
    where, params = _project_where(project_id)
    prds = _current_prd_rows(conn, where, params, limit=limit)
    milestones = _latest_rows(
        conn,
        "project_milestone_records",
        where,
        params,
        order_by="sequence_number ASC, created_at DESC",
        limit=limit,
    )
    work_orders = _latest_rows(
        conn,
        "project_work_order_authority_records",
        where,
        params,
        order_by="created_at DESC",
        limit=limit,
    )
    change_orders = _latest_rows(
        conn,
        "project_change_order_records",
        where,
        params,
        order_by="requested_at DESC",
        limit=limit,
    )
    reconciliations = _latest_rows(
        conn,
        "prd_route_reconciliation_records",
        where,
        params,
        order_by="created_at DESC",
        limit=limit,
    )
    assumptions = _latest_rows(
        conn,
        "project_assumption_records",
        where,
        params,
        order_by="created_at DESC",
        limit=limit,
    )
    lifecycle_counts = Counter(row["lifecycle_status"] for row in prds)
    change_counts = Counter(row["status"] for row in change_orders)
    pending_questions = _pending_questions(conn, project_id, limit=limit)
    return {
        "model_name": "dream_studio_prd_authority_lifecycle",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "project_id": project_id,
        "source_tables": list(PRD_AUTHORITY_SOURCE_TABLES),
        "source_status": {
            "status": "available" if not missing else "partial",
            "missing_tables": missing,
        },
        "current_prds": [_normalize_prd_row(row) for row in prds],
        "prd_count": len(prds),
        "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
        "current_milestones": [_normalize_milestone(row) for row in milestones],
        "active_work_orders": [_normalize_work_order(row) for row in work_orders],
        "change_order_history": [_normalize_change_order(row) for row in change_orders],
        "pending_change_orders": [
            _normalize_change_order(row)
            for row in change_orders
            if row.get("status") in {"draft", "manual_review_required"}
        ],
        "change_order_counts": dict(sorted(change_counts.items())),
        "route_reconciliations": [_normalize_reconciliation(row) for row in reconciliations],
        "route_reconciliation_status": _route_reconciliation_status(reconciliations),
        "pending_questions": pending_questions,
        "assumptions": [_normalize_assumption(row) for row in assumptions],
        "policy": {
            "sqlite_is_prd_authority": True,
            "files_are_exports": True,
            "change_orders_required_for_material_changes": True,
            "no_silent_prd_overwrite": True,
            "external_repo_prd_files_require_approval": True,
        },
        "next_safe_action": _next_safe_action(prds, change_orders, milestones),
        "empty_state": "No PRD lifecycle authority exists for this scope.",
    }


def project_details_prd_authority(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    """Return Project Details PRD authority fields."""

    summary = project_prd_authority_summary(conn, project_id=project_id, limit=25)
    current = summary["current_prds"][0] if summary["current_prds"] else None
    reconciliations = summary["route_reconciliations"]
    return {
        "summary": summary,
        "prd_version": current,
        "prd_confidence": current.get("confidence") if current else "manual_review_required",
        "in_flight_formalization_status": (
            current.get("lifecycle_status") if current else "manual_review_required"
        ),
        "pending_prd_questions": summary["pending_questions"],
        "prd_assumptions": summary["assumptions"],
        "current_milestones": summary["current_milestones"],
        "active_work_orders": summary["active_work_orders"],
        "change_order_history": summary["change_order_history"],
        "pending_change_orders": summary["pending_change_orders"],
        "route_reconciliation_status": summary["route_reconciliation_status"],
        "planned_vs_actual_route_summary": (
            reconciliations[0].get("planned_vs_actual") if reconciliations else None
        ),
        "next_safe_action": summary["next_safe_action"],
        "derived_view": True,
        "primary_authority": False,
    }


def validate_prd_authority_summary(summary: Mapping[str, Any]) -> list[str]:
    """Validate the dashboard read model for release-gate coverage."""

    errors: list[str] = []
    if summary.get("primary_authority") is not False:
        errors.append("PRD authority summary must be marked as a derived dashboard view")
    policy = summary.get("policy", {})
    if not policy.get("sqlite_is_prd_authority"):
        errors.append("PRD authority summary must identify SQLite as authority")
    if not policy.get("change_orders_required_for_material_changes"):
        errors.append("material change-order policy is missing")
    if "prd_version_records" not in summary.get("source_tables", []):
        errors.append("prd_version_records source table missing")
    return errors


def _include_question(mode: str, criticality: str, already_answered: bool) -> bool:
    if mode == "quick_start":
        return criticality == "critical" and not already_answered
    if mode == "standard_discovery":
        return criticality in {"critical", "important"} and not already_answered
    if mode == "full_discovery":
        return not already_answered
    if mode == "import_existing_project":
        return not already_answered
    return not already_answered


def _answered_groups(description: str) -> set[str]:
    text = description.lower()
    answered = set()
    for spec in QUESTION_BANK:
        if any(keyword in text for keyword in spec["keywords"]):
            answered.add(spec["group"])
    return answered


def _assumptions_and_unknowns(
    description: str,
    questions: Sequence[Mapping[str, Any]],
    answered_groups: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    assumptions: list[dict[str, str]] = []
    unknowns: list[dict[str, str]] = []
    for group in sorted(answered_groups or set()):
        assumptions.append(
            {
                "group": group,
                "text": f"{group} appears covered by the provided description.",
                "status": "assumption",
            }
        )
    for question in questions:
        if question.get("already_answered") and question.get("group") not in (
            answered_groups or set()
        ):
            assumptions.append(
                {
                    "group": str(question["group"]),
                    "text": f"{question['group']} appears covered by the provided description.",
                    "status": "assumption",
                }
            )
        else:
            unknowns.append(
                {
                    "group": str(question["group"]),
                    "text": str(question["question"]),
                    "status": "unknown",
                }
            )
    if not description.strip():
        unknowns.append(
            {
                "group": "project description",
                "text": "No project description was provided.",
                "status": "operator_confirmation_required",
            }
        )
    return assumptions, unknowns


def _project_classification(description: str) -> dict[str, str]:
    text = description.lower()
    security = "standard"
    if any(word in text for word in ("pii", "payment", "health", "financial", "children")):
        security = "sensitive_or_regulated_review_required"
    elif any(word in text for word in ("auth", "private", "secret", "security")):
        security = "security_sensitive"
    deployment = "local_first"
    if any(word in text for word in ("deploy", "cloud", "public", "publish", "release")):
        deployment = "release_or_deployment_expected"
    project_type = "application"
    if any(word in text for word in ("library", "package", "sdk")):
        project_type = "library_or_package"
    elif any(word in text for word in ("docs", "content", "seo", "marketing")):
        project_type = "content_or_public_site"
    elif any(word in text for word in ("data", "analytics", "dashboard")):
        project_type = "analytics_or_dashboard"
    autonomy = (
        "safe_autonomous_continuation" if "continue" in text or "go" in text else "operator_review"
    )
    readiness = (
        "production_readiness_required"
        if deployment == "release_or_deployment_expected" or security != "standard"
        else "lightweight_readiness"
    )
    return {
        "project_type": project_type,
        "deployment_expectation": deployment,
        "autonomy_level": autonomy,
        "security_classification": security,
        "readiness_classification": readiness,
    }


def _current_prd_rows(
    conn: sqlite3.Connection,
    where: str,
    params: Sequence[Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT * FROM prd_version_records
        {where}
        ORDER BY current_version DESC, updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_rows(
    conn: sqlite3.Connection,
    table: str,
    where: str,
    params: Sequence[Any],
    *,
    order_by: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, table):
        return []
    rows = conn.execute(
        f"SELECT * FROM {table} {where} ORDER BY {order_by} LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _pending_questions(
    conn: sqlite3.Connection, project_id: str | None, *, limit: int
) -> list[dict[str, Any]]:
    if not _table_exists(conn, "project_intake_questions"):
        return []
    if project_id:
        where = "WHERE project_id = ? AND response_status IN ('pending', 'operator_confirmation_required', 'unknown')"
        params: tuple[Any, ...] = (project_id,)
    else:
        where = "WHERE response_status IN ('pending', 'operator_confirmation_required', 'unknown')"
        params = ()
    rows = conn.execute(
        f"""
        SELECT * FROM project_intake_questions
        {where}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [
        {
            "question_id": row["question_id"],
            "group": row["question_group"],
            "question": row["question_text"],
            "criticality": row["criticality"],
            "response_status": row["response_status"],
        }
        for row in rows
    ]


def _project_where(project_id: str | None) -> tuple[str, tuple[Any, ...]]:
    if project_id:
        return "WHERE project_id = ?", (project_id,)
    return "", ()


def _normalize_prd_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "prd_version_id": row["prd_version_id"],
        "prd_id": row["prd_id"],
        "project_id": row["project_id"],
        "version_number": row["version_number"],
        "title": row["title"],
        "lifecycle_status": row["lifecycle_status"],
        "confidence": row["confidence"],
        "summary": row["summary"],
        "current_version": bool(row["current_version"]),
        "operator_review_required": bool(row["operator_review_required"]),
        "known_unknowns": _json_load(row.get("known_unknowns_json"), []),
        "source_refs": _json_load(row.get("source_refs_json"), []),
        "evidence_refs": _json_load(row.get("evidence_refs_json"), []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _normalize_milestone(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "milestone_id": row["milestone_id"],
        "project_id": row["project_id"],
        "sequence_number": row["sequence_number"],
        "milestone_name": row["milestone_name"],
        "status": row["status"],
        "stage_gate": _json_load(row.get("stage_gate_json"), {}),
        "validation_expectations": _json_load(row.get("validation_expectations_json"), []),
        "security_readiness_checks": _json_load(row.get("security_readiness_checks_json"), []),
        "evidence_requirements": _json_load(row.get("evidence_requirements_json"), []),
    }


def _normalize_work_order(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "work_order_id": row["work_order_id"],
        "project_id": row["project_id"],
        "milestone_id": row["milestone_id"],
        "purpose": row["purpose"],
        "status": row["status"],
        "approved_surfaces": _json_load(row.get("approved_surfaces_json"), []),
        "validation": _json_load(row.get("validation_json"), []),
        "stop_gates": _json_load(row.get("stop_gates_json"), []),
        "route_decision_expectations": _json_load(row.get("route_decision_expectations_json"), {}),
    }


def _normalize_change_order(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "change_order_id": row["change_order_id"],
        "project_id": row["project_id"],
        "requested_by": row["requested_by"],
        "requested_at": row["requested_at"],
        "user_request": row["user_request"],
        "change_type": row["change_type"],
        "risk_classification": row["risk_classification"],
        "approval_requirement": row["approval_requirement"],
        "status": row["status"],
        "affected_prd_sections": _json_load(row.get("affected_prd_sections_json"), []),
        "validation_impact": _json_load(row.get("validation_impact_json"), []),
    }


def _normalize_reconciliation(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reconciliation_id": row["reconciliation_id"],
        "project_id": row["project_id"],
        "reconciliation_event": row["reconciliation_event"],
        "planned_vs_actual": _json_load(row.get("planned_vs_actual_json"), {}),
        "accepted_deviations": _json_load(row.get("accepted_deviations_json"), []),
        "unresolved_deviations": _json_load(row.get("unresolved_deviations_json"), []),
        "final_project_status": row["final_project_status"],
        "current_next_action": row["current_next_action"],
    }


def _normalize_assumption(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "assumption_id": row["assumption_id"],
        "project_id": row["project_id"],
        "assumption_text": row["assumption_text"],
        "status": row["status"],
        "confirmation_required": bool(row["confirmation_required"]),
    }


def _route_reconciliation_status(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "not_started",
            "reason": "No milestone, release, or project closeout route reconciliation is recorded yet.",
        }
    latest = rows[0]
    unresolved = _json_load(latest.get("unresolved_deviations_json"), [])
    return {
        "status": "manual_review_required" if unresolved else "current",
        "latest_reconciliation_id": latest["reconciliation_id"],
        "unresolved_deviation_count": len(unresolved),
        "final_project_status": latest["final_project_status"],
    }


def _next_safe_action(
    prds: Sequence[Mapping[str, Any]],
    change_orders: Sequence[Mapping[str, Any]],
    milestones: Sequence[Mapping[str, Any]],
) -> str:
    pending = [
        row for row in change_orders if row.get("status") in {"draft", "manual_review_required"}
    ]
    if pending:
        return "Review pending Project Change Order before updating PRD or milestones."
    if not prds:
        return "Create or formalize PRD authority before implementation."
    current = prds[0]
    if current.get("operator_review_required"):
        return "Operator review is required before marking the PRD current."
    active = [row for row in milestones if row.get("status") in {"planned", "active"}]
    if active:
        return f"Prepare or execute Work Order for milestone: {active[0]['milestone_name']}."
    return "Route reconciliation or closeout review is the next safe action."


def _empty_summary(project_id: str | None, missing: Sequence[str]) -> dict[str, Any]:
    return {
        "model_name": "dream_studio_prd_authority_lifecycle",
        "derived_view": True,
        "primary_authority": False,
        "project_id": project_id,
        "source_tables": list(PRD_AUTHORITY_SOURCE_TABLES),
        "source_status": {"status": "unavailable", "missing_tables": list(missing)},
        "current_prds": [],
        "prd_count": 0,
        "lifecycle_counts": {},
        "change_order_counts": {},
        "current_milestones": [],
        "active_work_orders": [],
        "change_order_history": [],
        "pending_change_orders": [],
        "route_reconciliations": [],
        "route_reconciliation_status": {"status": "unavailable"},
        "pending_questions": [],
        "assumptions": [],
        "policy": {
            "sqlite_is_prd_authority": True,
            "files_are_exports": True,
            "change_orders_required_for_material_changes": True,
        },
        "next_safe_action": "Apply current migrations before using PRD lifecycle authority.",
        "empty_state": "PRD lifecycle authority tables are unavailable.",
    }


def _missing_source_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        table
        for table in PRD_AUTHORITY_SOURCE_TABLES
        if table != "reg_projects"
        and table != "business_projects"
        and not _table_exists(conn, table)
    ]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _json(value: Any, default: Any = None) -> str:
    if value is None:
        value = default
    return json.dumps(value, sort_keys=True)


def _json_load(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _enum(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _stable_id(prefix: str, *parts: str) -> str:
    text = "::".join(str(part or "") for part in parts)
    slug_source = "-".join(part for part in parts if part) or prefix
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug_source.lower()).strip("-")[:48]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{slug}-{digest}" if slug else f"{prefix}-{digest}"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
