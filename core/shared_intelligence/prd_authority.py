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
from pathlib import Path
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


def record_project_intake(
    conn: sqlite3.Connection,
    *,
    intake_id: str,
    project_description: str,
    mode: str = "standard_discovery",
    project_id: str | None = None,
    project_name: str | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Persist intake and adaptive questions into SQLite authority."""

    validate_prd_authority_schema(conn)
    plan = build_project_intake_plan(
        project_description,
        mode=mode,
        project_id=project_id,
        project_name=project_name,
    )
    classification = plan["classification"]
    conn.execute(
        """
        INSERT OR REPLACE INTO project_intake_records (
            intake_id, project_id, project_name, project_description,
            question_mode, project_type, deployment_expectation, autonomy_level,
            security_classification, readiness_classification, critical_blockers_json,
            assumptions_json, known_unknowns_json, source_refs_json,
            evidence_refs_json, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            intake_id,
            project_id,
            project_name,
            project_description,
            plan["question_mode"],
            classification["project_type"],
            classification["deployment_expectation"],
            classification["autonomy_level"],
            classification["security_classification"],
            classification["readiness_classification"],
            _json([q for q in plan["questions"] if q["criticality"] == "critical"]),
            _json(plan["assumptions"]),
            _json(plan["known_unknowns"]),
            _json(source_refs, []),
            _json(evidence_refs, []),
            "draft_generated",
        ),
    )
    for question in plan["questions"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO project_intake_questions (
                question_id, intake_id, project_id, question_mode, question_group,
                question_text, criticality, already_answered, inferred_answer,
                response_status, source_refs_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                question["question_id"],
                intake_id,
                project_id,
                plan["question_mode"],
                question["group"],
                question["question"],
                question["criticality"],
                1 if question["already_answered"] else 0,
                question.get("inferred_answer"),
                question["response_status"],
                _json(source_refs, []),
            ),
        )
    return {**plan, "intake_id": intake_id, "persisted": True}


def generate_prd_draft(
    *,
    project_id: str,
    project_name: str,
    project_description: str,
    intake_plan: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
    lifecycle_status: str = "draft_generated",
) -> dict[str, Any]:
    """Generate an evidence-marked PRD draft payload."""

    plan = dict(
        intake_plan or build_project_intake_plan(project_description, project_id=project_id)
    )
    classification = plan.get("classification") or _project_classification(project_description)
    unknowns = list(plan.get("known_unknowns") or [])
    assumptions = list(plan.get("assumptions") or [])
    prd_id = _stable_id("prd", project_id)
    title = f"{project_name} PRD"
    payload = {
        "schema": "dream_studio.prd_authority.v1",
        "prd_id": prd_id,
        "project_id": project_id,
        "project_identity": {
            "name": project_name,
            "status": "new_or_formalizing",
        },
        "problem_statement": _extract_sentence(project_description)
        or "Unknown; operator confirmation required.",
        "target_users": _section_value(project_description, "target users", unknowns),
        "goals": _section_value(project_description, "goals", unknowns),
        "non_goals": _section_value(project_description, "non-goals", unknowns),
        "mvp_scope": _section_value(project_description, "MVP scope", unknowns),
        "core_workflows": _section_value(project_description, "core use cases", unknowns),
        "success_criteria": _section_value(project_description, "success criteria", unknowns),
        "current_status": lifecycle_status,
        "architecture_summary": _evidence_value(evidence, "architecture_summary"),
        "stack_dependency_summary": _evidence_value(evidence, "stack_dependency_summary"),
        "data_storage_model": _section_value(project_description, "data/storage needs", unknowns),
        "security_privacy_classification": classification["security_classification"],
        "production_readiness_considerations": _readiness_plan(classification),
        "accessibility_seo_design_needs": _frontend_design_need(project_description),
        "release_deployment_expectations": classification["deployment_expectation"],
        "risks": _risks_from_classification(classification),
        "known_unknowns": unknowns,
        "assumptions": assumptions,
        "milestone_map": [name for _, name in MILESTONE_TEMPLATE],
        "work_order_strategy": "Generate scoped Work Orders from milestone authority before mutation.",
        "validation_expectations": _validation_expectations(classification),
        "readiness_security_plan": _readiness_plan(classification),
        "current_next_action": "Review and confirm PRD authority before risky implementation.",
        "source_refs": list((evidence or {}).get("source_refs") or []),
        "evidence_refs": list((evidence or {}).get("evidence_refs") or []),
    }
    return {
        "prd_id": prd_id,
        "title": title,
        "lifecycle_status": _enum(lifecycle_status, PRD_LIFECYCLE_STATES, "draft_generated"),
        "confidence": "draft_generated_needs_operator_review",
        "operator_review_required": True,
        "summary": _prd_summary(payload),
        "prd": payload,
        "assumptions": assumptions,
        "known_unknowns": unknowns,
    }


def record_prd_version(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    prd_payload: Mapping[str, Any],
    lifecycle_status: str | None = None,
    confidence: str | None = None,
    current_version: bool = True,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    supersedes_version_id: str | None = None,
) -> dict[str, Any]:
    """Persist a PRD version and keep legacy PRD list compatibility."""

    validate_prd_authority_schema(conn)
    prd_id = str(prd_payload.get("prd_id") or _stable_id("prd", project_id))
    version_number = _next_version_number(conn, project_id, prd_id)
    version_id = f"{prd_id}-v{version_number}"
    status = _enum(
        lifecycle_status or str(prd_payload.get("lifecycle_status") or "draft_generated"),
        PRD_LIFECYCLE_STATES,
        "draft_generated",
    )
    confidence_value = _enum(
        confidence or str(prd_payload.get("confidence") or "draft_generated_needs_operator_review"),
        FORMALIZATION_CONFIDENCE,
        "draft_generated_needs_operator_review",
    )
    full_prd = (
        prd_payload.get("prd") if isinstance(prd_payload.get("prd"), Mapping) else prd_payload
    )
    if current_version:
        conn.execute(
            """
            UPDATE prd_version_records
            SET current_version = 0, superseded_by_version_id = COALESCE(?, superseded_by_version_id),
                updated_at = datetime('now')
            WHERE project_id = ? AND current_version = 1
            """,
            (version_id if supersedes_version_id else None, project_id),
        )
    conn.execute(
        """
        INSERT OR REPLACE INTO prd_version_records (
            prd_version_id, prd_id, project_id, version_number, title,
            lifecycle_status, confidence, prd_json, summary, source_refs_json,
            evidence_refs_json, assumption_refs_json, known_unknowns_json,
            change_order_refs_json, supersedes_version_id, current_version,
            operator_review_required, last_reviewed_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            version_id,
            prd_id,
            project_id,
            version_number,
            str(
                prd_payload.get("title")
                or full_prd.get("project_identity", {}).get("name")
                or "Project PRD"
            ),
            status,
            confidence_value,
            _json(full_prd, {}),
            str(prd_payload.get("summary") or _prd_summary(full_prd)),
            _json(source_refs if source_refs is not None else full_prd.get("source_refs"), []),
            _json(
                evidence_refs if evidence_refs is not None else full_prd.get("evidence_refs"), []
            ),
            _json(
                [
                    item.get("assumption_id")
                    for item in prd_payload.get("assumptions", [])
                    if isinstance(item, Mapping)
                ],
                [],
            ),
            _json(prd_payload.get("known_unknowns") or full_prd.get("known_unknowns"), []),
            _json(prd_payload.get("change_order_refs"), []),
            supersedes_version_id,
            1 if current_version else 0,
            0 if status in {"current", "user_confirmed"} else 1,
            _now() if status in {"current", "user_confirmed"} else None,
        ),
    )
    _record_legacy_prd_document(conn, project_id, prd_id, prd_payload, status)
    for idx, assumption in enumerate(full_prd.get("assumptions") or []):
        text = str(assumption.get("text") if isinstance(assumption, Mapping) else assumption)
        if text:
            record_project_assumption(
                conn,
                project_id=project_id,
                assumption_text=text,
                prd_id=prd_id,
                prd_version_id=version_id,
                source_refs=source_refs,
                evidence_refs=evidence_refs,
                assumption_id=_stable_id("assumption", project_id, version_id, str(idx), text),
            )
    return {
        "prd_id": prd_id,
        "prd_version_id": version_id,
        "version_number": version_number,
        "lifecycle_status": status,
        "confidence": confidence_value,
        "current_version": current_version,
        "source_refs": list(source_refs or full_prd.get("source_refs") or []),
        "evidence_refs": list(evidence_refs or full_prd.get("evidence_refs") or []),
    }


def formalize_in_flight_project(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    repo_root: Path | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    """Formalize in-flight PRD authority from current SQLite/repo evidence."""

    validate_prd_authority_schema(conn)
    project = _project_row(conn, project_id) or {
        "project_id": project_id,
        "project_name": project_id,
    }
    existing = _legacy_prd_rows(conn, project_id)
    evidence = _project_evidence(conn, project, repo_root=repo_root)
    project_name = str(project.get("project_name") or project_id)
    description = evidence["description"] or f"In-flight project {project_name}."

    if existing and _legacy_prd_is_current(existing[0]):
        lifecycle = "current"
        confidence = (
            "high_confidence_current"
            if evidence["evidence_count"]
            else "medium_confidence_needs_review"
        )
        review_required = confidence != "high_confidence_current"
    elif existing:
        lifecycle = "needs_update"
        confidence = "medium_confidence_needs_review"
        review_required = True
    else:
        lifecycle = "in_flight_formalization"
        confidence = (
            "medium_confidence_needs_review"
            if evidence["evidence_count"] >= 2
            else "draft_generated_needs_operator_review"
        )
        review_required = True

    intake = build_project_intake_plan(
        description,
        mode="import_existing_project",
        project_id=project_id,
        project_name=project_name,
    )
    draft = generate_prd_draft(
        project_id=project_id,
        project_name=project_name,
        project_description=description,
        intake_plan=intake,
        evidence=evidence,
        lifecycle_status=lifecycle,
    )
    draft["confidence"] = confidence
    draft["operator_review_required"] = review_required
    if persist:
        version = record_prd_version(
            conn,
            project_id=project_id,
            prd_payload=draft,
            lifecycle_status=lifecycle,
            confidence=confidence,
            current_version=True,
            source_refs=evidence["source_refs"],
            evidence_refs=evidence["evidence_refs"],
        )
        milestones = generate_milestones_from_prd(draft)
        record_milestone_sequence(
            conn,
            project_id=project_id,
            prd_id=version["prd_id"],
            prd_version_id=version["prd_version_id"],
            milestones=milestones,
        )
        work_orders = generate_work_orders_from_milestones(
            project_id=project_id, milestones=milestones
        )
        record_work_order_sequence(
            conn,
            project_id=project_id,
            prd_id=version["prd_id"],
            prd_version_id=version["prd_version_id"],
            work_orders=work_orders,
        )
    else:
        version = None
        milestones = generate_milestones_from_prd(draft)
        work_orders = generate_work_orders_from_milestones(
            project_id=project_id, milestones=milestones
        )

    return {
        "model_name": "dream_studio_in_flight_prd_formalization",
        "project_id": project_id,
        "formalization_status": lifecycle,
        "confidence": confidence,
        "operator_review_required": review_required,
        "existing_prd_count": len(existing),
        "evidence": evidence,
        "prd": draft,
        "milestones": milestones,
        "work_orders": work_orders,
        "persisted_version": version,
        "repo_mutation_authorized": False,
        "files_written": [],
    }


def generate_milestones_from_prd(prd_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Generate ordered milestone authority from PRD authority."""

    prd_id = str(prd_payload.get("prd_id") or prd_payload.get("prd", {}).get("prd_id") or "prd")
    project_id = str(
        prd_payload.get("project_id") or prd_payload.get("prd", {}).get("project_id") or "project"
    )
    milestones = []
    for index, (slug, name) in enumerate(MILESTONE_TEMPLATE, start=1):
        milestone_id = _stable_id("milestone", project_id, prd_id, slug)
        milestones.append(
            {
                "milestone_id": milestone_id,
                "sequence_number": index,
                "milestone_name": name,
                "status": "planned",
                "scope": {
                    "stage": slug,
                    "smallest_safe_slice": True,
                    "external_project_mutation_requires_approval": True,
                },
                "stage_gate": {
                    "requires_prd_authority": True,
                    "requires_work_order_before_mutation": True,
                    "stop_for_policy_boundaries": True,
                },
                "validation_expectations": _milestone_validation(slug),
                "security_readiness_checks": _milestone_security_readiness(slug),
                "rollback_strategy": "Revert only the milestone slice and preserve prior authority lineage.",
                "evidence_requirements": [
                    "source_refs",
                    "validation_results",
                    "route_decision_records",
                ],
                "adapter_context_requirements": [
                    "current_prd_version",
                    "current_milestone",
                    "active_work_order",
                    "assumptions",
                    "known_unknowns",
                    "stop_gates",
                ],
            }
        )
    return milestones


def record_milestone_sequence(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    prd_id: str,
    prd_version_id: str,
    milestones: Sequence[Mapping[str, Any]],
) -> None:
    validate_prd_authority_schema(conn)
    for milestone in milestones:
        conn.execute(
            """
            INSERT OR REPLACE INTO project_milestone_records (
                milestone_id, project_id, prd_id, prd_version_id,
                sequence_number, milestone_name, status, scope_json,
                stage_gate_json, validation_expectations_json,
                security_readiness_checks_json, rollback_strategy,
                evidence_requirements_json, adapter_context_requirements_json,
                source_refs_json, evidence_refs_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                milestone["milestone_id"],
                project_id,
                prd_id,
                prd_version_id,
                int(milestone["sequence_number"]),
                milestone["milestone_name"],
                milestone.get("status", "planned"),
                _json(milestone.get("scope"), {}),
                _json(milestone.get("stage_gate"), {}),
                _json(milestone.get("validation_expectations"), []),
                _json(milestone.get("security_readiness_checks"), []),
                milestone.get("rollback_strategy"),
                _json(milestone.get("evidence_requirements"), []),
                _json(milestone.get("adapter_context_requirements"), []),
                _json(milestone.get("source_refs"), []),
                _json(milestone.get("evidence_refs"), []),
            ),
        )


def generate_work_orders_from_milestones(
    *,
    project_id: str,
    milestones: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Generate Work Order authority drafts from milestones."""

    work_orders = []
    for milestone in milestones:
        work_order_id = _stable_id("wo", project_id, str(milestone["milestone_id"]))
        work_orders.append(
            {
                "work_order_id": work_order_id,
                "milestone_id": milestone["milestone_id"],
                "purpose": f"Execute {milestone['milestone_name']} for {project_id}.",
                "status": "draft",
                "scope": milestone.get("scope", {}),
                "approved_surfaces": [],
                "dependencies": [],
                "validation": milestone.get("validation_expectations", []),
                "evidence_requirements": milestone.get("evidence_requirements", []),
                "stop_gates": [
                    "destructive_data_change",
                    "external_project_mutation",
                    "push_tag_merge_deploy",
                    "secret_sensitive_access",
                    "unclear_critical_product_direction",
                    "major_architecture_change",
                ],
                "final_verdict_taxonomy": [
                    "complete",
                    "partial",
                    "blocked",
                    "manual_review_required",
                ],
                "route_decision_expectations": {
                    "continue_safe_milestones_when_policy_allows": True,
                    "operator_approval_required_for_material_risk": True,
                },
                "rollback_strategy": milestone.get("rollback_strategy"),
            }
        )
    return work_orders


def record_work_order_sequence(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    prd_id: str,
    prd_version_id: str,
    work_orders: Sequence[Mapping[str, Any]],
) -> None:
    validate_prd_authority_schema(conn)
    for work_order in work_orders:
        conn.execute(
            """
            INSERT OR REPLACE INTO project_work_order_authority_records (
                work_order_id, project_id, milestone_id, prd_id, prd_version_id,
                purpose, status, scope_json, approved_surfaces_json,
                dependencies_json, validation_json, evidence_requirements_json,
                stop_gates_json, final_verdict_taxonomy_json,
                route_decision_expectations_json, rollback_strategy,
                source_refs_json, evidence_refs_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                work_order["work_order_id"],
                project_id,
                work_order.get("milestone_id"),
                prd_id,
                prd_version_id,
                work_order["purpose"],
                work_order.get("status", "draft"),
                _json(work_order.get("scope"), {}),
                _json(work_order.get("approved_surfaces"), []),
                _json(work_order.get("dependencies"), []),
                _json(work_order.get("validation"), []),
                _json(work_order.get("evidence_requirements"), []),
                _json(work_order.get("stop_gates"), []),
                _json(work_order.get("final_verdict_taxonomy"), []),
                _json(work_order.get("route_decision_expectations"), {}),
                work_order.get("rollback_strategy"),
                _json(work_order.get("source_refs"), []),
                _json(work_order.get("evidence_refs"), []),
            ),
        )


def create_project_change_order(
    conn: sqlite3.Connection,
    *,
    change_order_id: str,
    project_id: str,
    user_request: str,
    requested_by: str = "operator",
    reason_for_change: str | None = None,
    status: str = "draft",
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Create a draft change-order record without silently overwriting PRD authority."""

    validate_prd_authority_schema(conn)
    impact = classify_change_request(user_request)
    current_prd = _current_prd(conn, project_id)
    active_milestones = _milestone_rows(conn, project_id, statuses=("planned", "active", "blocked"))
    active_work_orders = _work_order_rows(
        conn, project_id, statuses=("draft", "ready", "active", "blocked")
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO project_change_order_records (
            change_order_id, project_id, requested_by, user_request, change_type,
            reason_for_change, affected_prd_sections_json,
            affected_milestones_json, affected_work_orders_json,
            affected_security_readiness_controls_json,
            affected_architecture_contracts_json, affected_timeline_scope_json,
            affected_release_criteria_json, risk_classification,
            validation_impact_json, approval_requirement, status,
            original_prd_refs_json, original_milestone_refs_json,
            source_refs_json, evidence_refs_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            change_order_id,
            project_id,
            requested_by,
            user_request,
            impact["change_type"],
            reason_for_change or impact["reason"],
            _json(impact["affected_prd_sections"], []),
            _json([row["milestone_id"] for row in active_milestones], []),
            _json([row["work_order_id"] for row in active_work_orders], []),
            _json(impact["affected_security_readiness_controls"], []),
            _json(impact["affected_architecture_contracts"], []),
            _json(impact["affected_timeline_scope"], {}),
            _json(impact["affected_release_criteria"], []),
            impact["risk_classification"],
            _json(impact["validation_impact"], []),
            impact["approval_requirement"],
            _enum(
                status,
                {"draft", "accepted", "rejected", "deferred", "manual_review_required"},
                "draft",
            ),
            _json([current_prd["prd_version_id"]] if current_prd else [], []),
            _json([row["milestone_id"] for row in active_milestones], []),
            _json(source_refs, []),
            _json(evidence_refs, []),
        ),
    )
    return {
        "change_order_id": change_order_id,
        "project_id": project_id,
        **impact,
        "status": status,
        "original_prd_refs": [current_prd["prd_version_id"]] if current_prd else [],
        "affected_milestones": [row["milestone_id"] for row in active_milestones],
        "affected_work_orders": [row["work_order_id"] for row in active_work_orders],
        "persisted": True,
    }


def classify_change_request(user_request: str) -> dict[str, Any]:
    """Classify material PRD impact for a user-requested change."""

    text = user_request.lower()
    rules = (
        ("security_or_privacy_change", ("security", "privacy", "pii", "auth", "secret")),
        ("data_model_change", ("database", "schema", "migration", "sqlite", "table")),
        ("architecture_change", ("architecture", "module", "runtime", "service")),
        ("integration_change", ("integration", "api", "github", "mcp", "webhook")),
        ("UI_or_design_change", ("ui", "design", "dashboard", "frontend", "screen")),
        ("release_target_change", ("release", "deploy", "publish", "demo", "launch")),
        ("priority_change", ("priority", "timeline", "deadline", "sequence")),
        ("scope_reduction", ("remove", "drop", "de-scope", "reduce")),
        ("scope_addition", ("add", "expand", "include", "support")),
        ("non_goal_change", ("non-goal", "non goal", "out of scope")),
        ("assumption_change", ("assumption", "assume")),
        ("milestone_replan", ("milestone", "replan", "work order")),
    )
    change_type = "requirement_change"
    for candidate, keywords in rules:
        if any(keyword in text for keyword in keywords):
            change_type = candidate
            break
    material = change_type in {
        "security_or_privacy_change",
        "data_model_change",
        "architecture_change",
        "integration_change",
        "release_target_change",
        "scope_addition",
        "scope_reduction",
        "milestone_replan",
    }
    return {
        "change_type": change_type if change_type in CHANGE_TYPES else "manual_review_required",
        "reason": (
            "Request materially changes existing project authority."
            if material
            else "Request can be treated as a lightweight PRD amendment if policy allows."
        ),
        "affected_prd_sections": _affected_sections_for_change(change_type),
        "affected_security_readiness_controls": _affected_controls_for_change(change_type),
        "affected_architecture_contracts": (
            ["module_contracts", "Contract Atlas"]
            if change_type in {"architecture_change", "integration_change", "data_model_change"}
            else []
        ),
        "affected_timeline_scope": {
            "scope_changed": change_type
            in {"scope_addition", "scope_reduction", "milestone_replan"},
            "timeline_changed": change_type
            in {"priority_change", "release_target_change", "milestone_replan"},
        },
        "affected_release_criteria": (
            ["release_readiness", "validation_gate"]
            if change_type
            in {"release_target_change", "security_or_privacy_change", "data_model_change"}
            else []
        ),
        "validation_impact": _validation_impact_for_change(change_type),
        "risk_classification": "high" if material else "low",
        "approval_requirement": (
            "operator_approval_required" if material else "policy_may_auto_approve"
        ),
    }


def record_prd_route_reconciliation(
    conn: sqlite3.Connection,
    *,
    reconciliation_id: str,
    project_id: str,
    prd_id: str | None = None,
    prd_version_id: str | None = None,
    reconciliation_event: str = "milestone_closeout",
    planned_route: Mapping[str, Any] | None = None,
    actual_route: Mapping[str, Any] | None = None,
    completed_milestones: Sequence[str] | None = None,
    completed_work_orders: Sequence[str] | None = None,
    approved_change_orders: Sequence[str] | None = None,
    accepted_deviations: Sequence[Mapping[str, Any]] | None = None,
    unresolved_deviations: Sequence[Mapping[str, Any]] | None = None,
    validation_results: Sequence[Mapping[str, Any]] | None = None,
    security_readiness_outcomes: Mapping[str, Any] | None = None,
    final_project_status: str = "in_progress",
    current_next_action: str | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Record planned-vs-actual PRD route reconciliation."""

    validate_prd_authority_schema(conn)
    planned = dict(planned_route or {})
    actual = dict(actual_route or {})
    comparison = {
        "planned_milestones": planned.get("milestones", []),
        "actual_milestones": actual.get("milestones", []),
        "accepted_deviation_count": len(accepted_deviations or []),
        "unresolved_deviation_count": len(unresolved_deviations or []),
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO prd_route_reconciliation_records (
            reconciliation_id, project_id, prd_id, prd_version_id,
            reconciliation_event, planned_route_json, actual_route_json,
            planned_vs_actual_json, completed_milestones_json,
            completed_work_orders_json, approved_change_orders_json,
            accepted_deviations_json, unresolved_deviations_json,
            validation_results_json, security_readiness_outcomes_json,
            final_project_status, current_next_action, source_refs_json,
            evidence_refs_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            reconciliation_id,
            project_id,
            prd_id,
            prd_version_id,
            reconciliation_event,
            _json(planned, {}),
            _json(actual, {}),
            _json(comparison, {}),
            _json(completed_milestones, []),
            _json(completed_work_orders, []),
            _json(approved_change_orders, []),
            _json(accepted_deviations, []),
            _json(unresolved_deviations, []),
            _json(validation_results, []),
            _json(security_readiness_outcomes, {}),
            final_project_status,
            current_next_action,
            _json(source_refs, []),
            _json(evidence_refs, []),
        ),
    )
    return {
        "reconciliation_id": reconciliation_id,
        "project_id": project_id,
        "planned_vs_actual": comparison,
        "final_project_status": final_project_status,
        "current_next_action": current_next_action,
        "persisted": True,
    }


def project_prd_authority_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return dashboard-ready PRD lifecycle authority."""

    missing = _missing_source_tables(conn)
    if "prd_version_records" in missing:
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


def context_packet_prd_authority(
    conn: sqlite3.Connection,
    *,
    project_id: str | None,
    milestone_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build the PRD authority subset for adapter context packets."""

    if not project_id:
        return {
            "status": "unscoped",
            "reason": "No project_id was supplied; PRD authority is intentionally omitted.",
            "forbidden_context": ["unrelated_project_history", "career_private_data", "secrets"],
        }
    summary = project_details_prd_authority(conn, project_id)
    active_milestones = summary["current_milestones"]
    if milestone_id:
        active_milestones = [
            milestone
            for milestone in active_milestones
            if milestone["milestone_id"] == milestone_id
        ] or active_milestones[:1]
    return {
        "status": "available" if summary["prd_version"] else "manual_review_required",
        "current_prd_version": summary["prd_version"],
        "current_milestone": active_milestones[0] if active_milestones else None,
        "active_work_order": _active_work_order_for_packet(
            summary["active_work_orders"], milestone_id=milestone_id, task_id=task_id
        ),
        "assumptions": summary["prd_assumptions"],
        "known_unknowns": (
            summary["prd_version"].get("known_unknowns") if summary["prd_version"] else []
        ),
        "relevant_change_orders": summary["pending_change_orders"]
        or summary["change_order_history"][:5],
        "security_readiness_constraints": _packet_security_readiness_constraints(summary),
        "evidence_refs": _packet_evidence_refs(summary),
        "allowed_scope": {
            "project_id": project_id,
            "milestone_id": milestone_id,
            "task_id": task_id,
            "external_project_mutation_authorized": False,
            "secret_access_authorized": False,
            "push_deploy_authorized": False,
        },
        "validation_expectations": _packet_validation_expectations(active_milestones),
        "stop_gates": [
            "destructive data changes",
            "external project mutation",
            "push/tag/merge/deploy",
            "secret or sensitive access",
            "unclear critical product direction",
            "high-risk security/compliance uncertainty",
            "major architecture change",
            "public/private boundary change",
        ],
        "forbidden_context": [
            "unrelated project history",
            "full private operational history",
            "career data",
            "secrets",
            "raw local evidence outside scope",
        ],
    }


def validate_prd_authority_schema(conn: sqlite3.Connection) -> list[str]:
    """Return missing PRD authority tables."""

    missing = [
        table
        for table in PRD_AUTHORITY_SOURCE_TABLES
        if table != "reg_projects"
        and table != "business_projects"
        and not _table_exists(conn, table)
    ]
    if missing:
        raise RuntimeError(f"missing PRD authority tables: {', '.join(missing)}")
    return []


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


def record_project_assumption(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    assumption_text: str,
    assumption_id: str | None = None,
    intake_id: str | None = None,
    prd_id: str | None = None,
    prd_version_id: str | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
) -> None:
    validate_prd_authority_schema(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO project_assumption_records (
            assumption_id, project_id, intake_id, prd_id, prd_version_id,
            assumption_text, status, confirmation_required, source_refs_json,
            evidence_refs_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            assumption_id or _stable_id("assumption", project_id, assumption_text),
            project_id,
            intake_id,
            prd_id,
            prd_version_id,
            assumption_text,
            "operator_confirmation_required",
            1,
            _json(source_refs, []),
            _json(evidence_refs, []),
        ),
    )


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


def _section_value(
    description: str, section: str, unknowns: list[dict[str, str]]
) -> dict[str, Any]:
    if any(item.get("group") == section for item in unknowns):
        return {
            "status": "unknown",
            "value": None,
            "reason": f"{section} was not supported by provided evidence.",
        }
    return {
        "status": "assumption",
        "value": "Inferred from provided project description.",
        "operator_confirmation_required": True,
    }


def _evidence_value(evidence: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    if evidence and evidence.get(key):
        return {"status": "evidence_backed", "value": evidence[key]}
    return {"status": "unknown", "value": None, "reason": "Evidence not yet recorded."}


def _readiness_plan(classification: Mapping[str, str]) -> dict[str, Any]:
    return {
        "security": classification["security_classification"],
        "readiness": classification["readiness_classification"],
        "targeted_checks": [
            "security impact classification",
            "production readiness applicability",
            "validation evidence",
        ],
        "full_review_triggers": [
            "release/merge",
            "deployment/live cutover",
            "dependency/runtime/database/security changes",
            "major architecture changes",
        ],
    }


def _frontend_design_need(description: str) -> dict[str, Any]:
    text = description.lower()
    applicable = any(word in text for word in ("ui", "frontend", "dashboard", "web", "page"))
    return {
        "applicable": applicable,
        "needs": (
            [
                "accessibility",
                "responsive layout",
                "design system fit",
            ]
            if applicable
            else []
        ),
    }


def _risks_from_classification(classification: Mapping[str, str]) -> list[dict[str, str]]:
    risks = []
    if classification["security_classification"] != "standard":
        risks.append(
            {
                "risk": "security/privacy posture requires review",
                "status": "manual_review_required",
            }
        )
    if classification["deployment_expectation"] == "release_or_deployment_expected":
        risks.append({"risk": "release readiness must be evidence-backed", "status": "open"})
    return risks


def _validation_expectations(classification: Mapping[str, str]) -> list[str]:
    checks = ["focused tests", "dashboard/API smoke where applicable", "docs/Contract Atlas drift"]
    if classification["readiness_classification"] == "production_readiness_required":
        checks.append("targeted production readiness gate")
    return checks


def _extract_sentence(description: str) -> str | None:
    stripped = " ".join(description.split())
    if not stripped:
        return None
    return stripped.split(".")[0][:240]


def _prd_summary(prd: Mapping[str, Any]) -> str:
    identity = prd.get("project_identity") or {}
    name = identity.get("name") or prd.get("project_id") or "Project"
    problem = prd.get("problem_statement") or "PRD authority is pending review."
    return f"{name}: {problem}"


def _next_version_number(conn: sqlite3.Connection, project_id: str, prd_id: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(version_number), 0) AS max_version
        FROM prd_version_records
        WHERE project_id = ? AND prd_id = ?
        """,
        (project_id, prd_id),
    ).fetchone()
    return int(row["max_version"] or 0) + 1


def _record_legacy_prd_document(
    conn: sqlite3.Connection,
    project_id: str,
    prd_id: str,
    prd_payload: Mapping[str, Any],
    status: str,
) -> None:
    if not _table_exists(conn, "prd_documents"):
        return
    columns = _table_columns(conn, "prd_documents")
    values = {
        "prd_id": prd_id,
        "project_id": project_id,
        "title": prd_payload.get("title") or "Project PRD",
        "file_path": f"sqlite://prd_version_records/{prd_id}",
        "status": status,
        "created_at": _now(),
    }
    insert_columns = [column for column in values if column in columns]
    if not insert_columns:
        return
    placeholders = ", ".join("?" for _ in insert_columns)
    conn.execute(
        f"""
        INSERT OR REPLACE INTO prd_documents ({', '.join(insert_columns)})
        VALUES ({placeholders})
        """,
        tuple(values[column] for column in insert_columns),
    )


def _project_evidence(
    conn: sqlite3.Connection,
    project: Mapping[str, Any],
    *,
    repo_root: Path | None,
) -> dict[str, Any]:
    refs: list[str] = []
    evidence_refs: list[str] = []
    descriptions: list[str] = []
    if project.get("project_name"):
        descriptions.append(str(project["project_name"]))
    # stack_detected and stack_json were in reg_projects (deleted migration 084).
    # These columns will return None until the analysis engine is rebuilt against business_projects.
    if project.get("stack_detected"):
        refs.append("sqlite:business_projects.stack_detected")
        evidence_refs.append("sqlite:business_projects")
    if project.get("stack_json"):
        refs.append("sqlite:business_projects.stack_json")
        evidence_refs.append("sqlite:business_projects")
    if repo_root:
        root = Path(repo_root)
        for name in (
            "README.md",
            "docs/product/dream-studio-prd.md",
            "package.json",
            "pyproject.toml",
        ):
            path = root / name
            if path.exists() and path.is_file():
                refs.append(str(path))
                evidence_refs.append(str(path))
    return {
        "description": ". ".join(descriptions),
        "architecture_summary": (
            "Evidence exists in project registry and approved repo metadata." if refs else None
        ),
        "stack_dependency_summary": str(project.get("stack_detected") or "unknown"),
        "source_refs": refs,
        "evidence_refs": evidence_refs,
        "evidence_count": len(set(refs)),
    }


def _project_row(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    # reg_projects deleted in migration 084; use business_projects.
    if not _table_exists(conn, "business_projects"):
        return None
    row = conn.execute(
        "SELECT project_id, name AS project_name, description, status,"
        " project_path, created_at, updated_at"
        " FROM business_projects WHERE project_id = ? LIMIT 1",
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def _legacy_prd_rows(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    if not _table_exists(conn, "prd_documents"):
        return []
    rows = conn.execute(
        """
        SELECT * FROM prd_documents
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _legacy_prd_is_current(row: Mapping[str, Any]) -> bool:
    return str(row.get("status") or "").lower() in {"current", "user_confirmed", "approved"}


def _current_prd(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "prd_version_records"):
        return None
    row = conn.execute(
        """
        SELECT * FROM prd_version_records
        WHERE project_id = ? AND current_version = 1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def _milestone_rows(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    statuses: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    return _status_rows(conn, "project_milestone_records", project_id, "milestone_id", statuses)


def _work_order_rows(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    statuses: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    return _status_rows(
        conn,
        "project_work_order_authority_records",
        project_id,
        "work_order_id",
        statuses,
    )


def _status_rows(
    conn: sqlite3.Connection,
    table: str,
    project_id: str,
    id_column: str,
    statuses: Sequence[str] | None,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, table):
        return []
    if statuses:
        placeholders = ", ".join("?" for _ in statuses)
        rows = conn.execute(
            f"""
            SELECT * FROM {table}
            WHERE project_id = ? AND status IN ({placeholders})
            ORDER BY created_at DESC
            """,
            (project_id, *statuses),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE project_id = ? ORDER BY {id_column}",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


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


def _active_work_order_for_packet(
    work_orders: Sequence[Mapping[str, Any]],
    *,
    milestone_id: str | None,
    task_id: str | None,
) -> dict[str, Any] | None:
    if milestone_id:
        for item in work_orders:
            if item.get("milestone_id") == milestone_id:
                return dict(item)
    return dict(work_orders[0]) if work_orders else None


def _packet_security_readiness_constraints(summary: Mapping[str, Any]) -> list[str]:
    constraints = ["Run targeted readiness/security checks according to lifecycle policy."]
    if summary.get("pending_change_orders"):
        constraints.append("Pending change orders may alter readiness/security scope.")
    return constraints


def _packet_evidence_refs(summary: Mapping[str, Any]) -> list[str]:
    refs: set[str] = set()
    prd = summary.get("prd_version")
    if isinstance(prd, Mapping):
        refs.update(str(item) for item in prd.get("evidence_refs", []) if item)
    return sorted(refs)


def _packet_validation_expectations(milestones: Sequence[Mapping[str, Any]]) -> list[Any]:
    if milestones:
        return list(milestones[0].get("validation_expectations") or [])
    return ["Create PRD/milestone authority before mutation validation."]


def _milestone_validation(slug: str) -> list[str]:
    common = ["record evidence refs", "update route decision"]
    by_slug = {
        "intake-formalization": ["validate PRD authority", "operator review when required"],
        "architecture-data-model": ["data model review", "Contract Atlas impact check"],
        "core-implementation": ["focused tests", "code quality workflow"],
        "ui-ux-design": ["dashboard/API smoke", "accessibility review where applicable"],
        "security-readiness": ["security lifecycle classification", "production readiness gate"],
        "validation": ["release gate", "docs drift gate"],
        "release-demo-deployment": ["release readiness", "privacy/publication boundary"],
        "documentation-cleanup": ["docs drift", "Contract Atlas freshness"],
        "closeout-reconciliation": ["planned vs actual route reconciliation"],
    }
    return [*common, *by_slug.get(slug, [])]


def _milestone_security_readiness(slug: str) -> list[str]:
    if slug in {"security-readiness", "release-demo-deployment"}:
        return ["full applicable review when policy requires", "not_applicable reasons required"]
    if slug in {"architecture-data-model", "core-implementation"}:
        return ["targeted applicable controls", "manual_review for unknown controls"]
    return ["lightweight security/readiness impact classification"]


def _affected_sections_for_change(change_type: str) -> list[str]:
    mapping = {
        "security_or_privacy_change": [
            "security_privacy_classification",
            "readiness_security_plan",
        ],
        "data_model_change": ["data_storage_model", "architecture_summary"],
        "architecture_change": ["architecture_summary", "milestone_map"],
        "integration_change": ["integrations", "architecture_summary"],
        "UI_or_design_change": ["accessibility_seo_design_needs", "core_workflows"],
        "release_target_change": ["release_deployment_expectations", "validation_expectations"],
        "priority_change": ["milestone_map", "current_next_action"],
        "scope_addition": ["mvp_scope", "goals", "milestone_map"],
        "scope_reduction": ["mvp_scope", "non_goals", "milestone_map"],
        "non_goal_change": ["non_goals"],
        "assumption_change": ["assumptions", "known_unknowns"],
        "milestone_replan": ["milestone_map", "work_order_strategy"],
    }
    return mapping.get(change_type, ["requirements"])


def _affected_controls_for_change(change_type: str) -> list[str]:
    if change_type == "security_or_privacy_change":
        return ["47_enterprise_security_controls", "privacy_compliance_applicability"]
    if change_type == "data_model_change":
        return ["database_readiness", "migration_rollback"]
    if change_type == "integration_change":
        return ["api_resilience", "dependency_supply_chain"]
    if change_type == "release_target_change":
        return ["release_readiness", "publication_privacy"]
    return ["targeted_applicability_classification"]


def _validation_impact_for_change(change_type: str) -> list[str]:
    base = ["update PRD lineage", "recalculate affected milestones and Work Orders"]
    if change_type in {"security_or_privacy_change", "data_model_change", "release_target_change"}:
        base.append("run targeted or full readiness gate according to policy")
    return base


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
