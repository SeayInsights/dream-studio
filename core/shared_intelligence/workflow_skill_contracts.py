"""Repo-owned workflow and skill contract definitions.

These contracts are source authority for how Dream Studio should evaluate,
route, version, harden, deprecate, and promote repeatable workflows and skills.
They intentionally do not read or write runtime SQLite. Later migrations may
persist contract instances, but this module is the additive repo-owned contract
surface for the first hardening slice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

WORKFLOW_SKILL_CONTRACT_SCHEMA = "dream_studio.workflow_skill_contracts.v1"

APPROVED_LIFECYCLE_STATES: tuple[str, ...] = (
    "proposed",
    "researched",
    "draft_generated",
    "active",
    "deprecated",
    "removal_candidate",
    "removed",
    "retained_reference_only",
)

APPROVED_LIFECYCLE_STATE_SET = frozenset(APPROVED_LIFECYCLE_STATES)

APPROVED_MUTATION_RISK_CLASSES: tuple[str, ...] = (
    "none",
    "read_only",
    "source_additive",
    "source_mutating",
    "runtime_state_mutating",
    "sqlite_mutating",
    "migration",
    "dependency_mutating",
    "artifact_lifecycle_mutating",
    "external_project_mutating",
    "commit_push_deploy",
    "security_sensitive",
)

APPROVED_MUTATION_RISK_SET = frozenset(APPROVED_MUTATION_RISK_CLASSES)

MUTATION_CAPABLE_RISKS = frozenset(
    APPROVED_MUTATION_RISK_SET - {"none", "read_only"}
)

RUNTIME_OR_DB_MUTATION_RISKS = frozenset(
    {"runtime_state_mutating", "sqlite_mutating", "migration"}
)

SECRET_OR_SENSITIVE_TERMS = (
    "secret",
    "secrets",
    "credential",
    "credentials",
    "token",
    "auth",
    "sensitive",
)

EXPLICIT_APPROVAL_TERMS = ("approval", "operator", "explicit", "manual_review")


@dataclass(frozen=True)
class ContractValidationResult:
    """Structured validation result for workflow and skill contracts."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_operator_decision: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "required_operator_decision": self.required_operator_decision,
        }


@dataclass(frozen=True)
class WorkflowContract:
    """Contract shape for repeatable workflow execution."""

    id: str
    version: str
    purpose: str
    lifecycle_state: str
    triggers: tuple[str, ...] = ()
    non_triggers: tuple[str, ...] = ()
    input_contract: tuple[str, ...] = ()
    output_contract: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    allowed_context: tuple[str, ...] = ()
    forbidden_context: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    stop_gates: tuple[str, ...] = ()
    approval_requirements: tuple[str, ...] = ()
    mutation_risk: str = "read_only"
    validation_requirements: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    evals: tuple[str, ...] = ()
    learning_emits: tuple[str, ...] = ()
    failure_classes: tuple[str, ...] = ()
    failure_gate_evolution: tuple[str, ...] = ()
    privacy_boundary: str = ""
    downstream_action_classes: tuple[str, ...] = ()
    contract_atlas_impact: str = ""
    owner: str = ""
    notes: str = ""


@dataclass(frozen=True)
class SkillContract:
    """Contract shape for reusable Dream Studio skills."""

    id: str
    version: str
    skill_family: str
    lifecycle_state: str
    owner: str
    capabilities: tuple[str, ...] = ()
    when_to_use: tuple[str, ...] = ()
    when_not_to_use: tuple[str, ...] = ()
    input_contract: tuple[str, ...] = ()
    output_contract: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    allowed_context: tuple[str, ...] = ()
    forbidden_context: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    evidence_expectations: tuple[str, ...] = ()
    validation_requirements: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    evals: tuple[str, ...] = ()
    gotcha_inputs: tuple[str, ...] = ()
    learning_inputs: tuple[str, ...] = ()
    emitted_learning_types: tuple[str, ...] = ()
    versioning_policy: str = ""
    deprecation_policy: str = ""
    removal_policy: str = ""
    rollback_or_supersession_metadata: dict[str, Any] = field(default_factory=dict)
    privacy_boundary: str = ""
    notes: str = ""


def validate_workflow_contract(contract: WorkflowContract | dict[str, Any]) -> ContractValidationResult:
    """Validate a workflow contract without touching runtime state."""

    payload = _payload(contract)
    errors: list[str] = []
    warnings: list[str] = []
    required_operator_decision = False

    _require_text(payload, "id", errors)
    _require_text(payload, "version", errors)
    _require_text(payload, "purpose", errors)
    _validate_lifecycle(payload, errors)
    _validate_mutation_risk(payload, errors)
    _require_sequence(payload, "evidence_requirements", errors)
    _require_sequence(payload, "output_contract", errors)

    mutation_risk = str(payload.get("mutation_risk") or "")
    if mutation_risk in MUTATION_CAPABLE_RISKS:
        required_operator_decision = True
        _require_sequence(payload, "stop_gates", errors)
        _require_sequence(payload, "approval_requirements", errors)

    if mutation_risk == "external_project_mutating":
        required_operator_decision = True
        if not (
            _contains_any(payload.get("approval_requirements"), ("external_project",))
            and _contains_any(payload.get("approval_requirements"), ("approval", "approved"))
        ):
            errors.append(
                "external_project_mutating workflow requires explicit external project approval"
            )

    if mutation_risk in RUNTIME_OR_DB_MUTATION_RISKS:
        required_operator_decision = True
        if not _contains_any(payload.get("stop_gates"), ("runtime", "sqlite", "migration", "db")):
            errors.append(
                "runtime/SQLite/migration workflow requires explicit runtime or DB stop gate"
            )

    if _allows_secret_or_sensitive_access(payload):
        required_operator_decision = True
        if not _contains_any(payload.get("approval_requirements"), EXPLICIT_APPROVAL_TERMS):
            errors.append(
                "contract allowing secrets/sensitive access requires explicit approval boundary"
            )

    if not payload.get("privacy_boundary"):
        warnings.append("privacy_boundary is recommended for workflow contracts")
    if not payload.get("contract_atlas_impact"):
        warnings.append("contract_atlas_impact is recommended for workflow contracts")

    return ContractValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        required_operator_decision=required_operator_decision,
    )


def validate_skill_contract(contract: SkillContract | dict[str, Any]) -> ContractValidationResult:
    """Validate a skill contract without touching runtime state."""

    payload = _payload(contract)
    errors: list[str] = []
    warnings: list[str] = []
    required_operator_decision = False

    _require_text(payload, "id", errors)
    _require_text(payload, "version", errors)
    _require_text(payload, "skill_family", errors)
    _require_text(payload, "owner", errors)
    _validate_lifecycle(payload, errors)
    _require_sequence(payload, "capabilities", errors)
    _require_sequence(payload, "output_contract", errors)
    _require_sequence(payload, "evidence_expectations", errors)

    if _skill_is_mutation_capable(payload):
        required_operator_decision = True
        _require_sequence(payload, "forbidden_actions", errors)

    lifecycle_state = str(payload.get("lifecycle_state") or "")
    if lifecycle_state in {"removal_candidate", "removed"} and not payload.get("removal_policy"):
        errors.append("skill removal_candidate or removed state requires removal_policy")

    if _allows_secret_or_sensitive_access(payload):
        required_operator_decision = True
        if not _contains_any(
            payload.get("forbidden_actions"),
            ("secret", "credential", "sensitive", "without_explicit_approval"),
        ):
            errors.append(
                "skill allowing secrets/sensitive access requires explicit forbidden action boundary"
            )
        if not _contains_any(
            (
                payload.get("privacy_boundary", ""),
                payload.get("notes", ""),
                payload.get("deprecation_policy", ""),
            ),
            EXPLICIT_APPROVAL_TERMS,
        ):
            errors.append(
                "skill allowing secrets/sensitive access requires explicit approval boundary"
            )

    if not payload.get("versioning_policy"):
        warnings.append("versioning_policy is recommended for skill contracts")
    if payload.get("lifecycle_state") == "deprecated" and not payload.get("deprecation_policy"):
        warnings.append("deprecated skill should document deprecation_policy")

    return ContractValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        required_operator_decision=required_operator_decision,
    )


def example_read_only_workflow_contract() -> WorkflowContract:
    """Return a valid read-only workflow contract fixture."""

    return WorkflowContract(
        id="analyze_repo_read_only",
        version="0.1.0",
        purpose="Inspect a repository and produce evidence-backed analysis without mutation.",
        lifecycle_state="draft_generated",
        triggers=("repo_health_audit", "architecture_audit"),
        non_triggers=("source mutation", "dependency adoption"),
        input_contract=("target repo metadata", "analysis intent", "allowed read scope"),
        output_contract=("repo summary", "evidence refs", "downstream action classification"),
        required_context=("target intake",),
        allowed_context=("repo files in approved scope",),
        forbidden_context=("secrets", "unrelated project history"),
        allowed_actions=("read_source", "summarize_evidence"),
        forbidden_actions=("write_source", "run_migrations", "inspect_secrets"),
        evidence_requirements=("file refs", "source refs"),
        stop_gates=("secret encountered", "external mutation needed"),
        approval_requirements=(),
        mutation_risk="read_only",
        validation_requirements=("contract output shape",),
        tests=("tests/unit/test_workflow_skill_contracts.py",),
        evals=("repo_analysis_fixture_eval",),
        learning_emits=("external_project_pattern", "documentation_gap"),
        failure_classes=("missing_context", "unclear_requirement"),
        failure_gate_evolution=("add operator question when intake is ambiguous",),
        privacy_boundary="Do not include secrets or private unrelated project history.",
        downstream_action_classes=("reference_only", "manual_review_required"),
        contract_atlas_impact="workflow_contracts.analyze_repo_read_only",
        owner="core:analyze",
    )


def example_mutation_capable_workflow_contract() -> WorkflowContract:
    """Return a valid source-additive workflow contract fixture."""

    return WorkflowContract(
        id="workflow_contract_source_additive",
        version="0.1.0",
        purpose="Add repo-owned contract definitions after operator approval.",
        lifecycle_state="draft_generated",
        triggers=("approved implementation work order",),
        non_triggers=("runtime DB changes", "external project mutation"),
        input_contract=("approved file scope", "validation plan", "rollback plan"),
        output_contract=("source diff", "test result", "evidence refs"),
        required_context=("approved Work Order",),
        allowed_context=("approved source files",),
        forbidden_context=("secrets", "runtime SQLite contents"),
        allowed_actions=("write_approved_source_files", "run_focused_tests"),
        forbidden_actions=("run_migrations", "mutate_runtime_state", "inspect_secrets"),
        evidence_requirements=("git diff", "focused pytest output", "diff check output"),
        stop_gates=("file outside approved scope", "runtime mutation needed", "sqlite migration needed"),
        approval_requirements=("current operator source_additive approval",),
        mutation_risk="source_additive",
        validation_requirements=("focused unit tests", "diff --check"),
        tests=("tests/unit/test_workflow_skill_contracts.py",),
        evals=("contract_validation_eval",),
        learning_emits=("workflow_gotcha", "gate_recommendation"),
        failure_classes=("approval_boundary_violation", "output_contract_miss"),
        failure_gate_evolution=("add stricter validation when contract output misses recur",),
        privacy_boundary="No runtime SQLite or private local state is read or written.",
        downstream_action_classes=("integration_work_order_ready",),
        contract_atlas_impact="workflow_contracts.source_additive",
        owner="core:shared_intelligence",
    )


def example_active_skill_contract() -> SkillContract:
    """Return a valid active skill contract fixture."""

    return SkillContract(
        id="ds_core_plan",
        version="0.1.0",
        skill_family="ds-core",
        lifecycle_state="active",
        owner="core:plan",
        capabilities=("work_order_planning", "milestone_breakdown", "approval_gate_mapping"),
        when_to_use=("approved planning", "milestone decomposition"),
        when_not_to_use=("secret inspection", "runtime DB mutation without approval"),
        input_contract=("goal", "constraints", "authority refs"),
        output_contract=("bounded Work Orders", "validation expectations"),
        required_context=("current PRD or operator goal",),
        allowed_context=("relevant project authority",),
        forbidden_context=("secrets", "unrelated project history"),
        allowed_actions=("create_plan", "classify_gates"),
        forbidden_actions=("mutate_runtime_state", "inspect_secrets"),
        evidence_expectations=("authority refs", "approval boundaries"),
        validation_requirements=("scope checks",),
        tests=("tests/unit/test_workflow_skill_contracts.py",),
        evals=("planning_contract_eval",),
        gotcha_inputs=("scope creep", "missing approval boundary"),
        learning_inputs=("operator correction", "validation failure"),
        emitted_learning_types=("operator_preference", "workflow_gotcha"),
        versioning_policy="Version when input/output contract changes.",
        deprecation_policy="Deprecate only after replacement workflow is active and references migrate.",
        privacy_boundary="Private project authority stays local unless explicitly sanitized.",
        notes="Active example only; not registered as live runtime authority.",
    )


def example_removal_candidate_skill_contract() -> SkillContract:
    """Return a valid removal-candidate skill contract fixture."""

    return SkillContract(
        id="legacy_design_reference_skill",
        version="0.1.0",
        skill_family="design",
        lifecycle_state="removal_candidate",
        owner="quality:design",
        capabilities=("design_reference_review",),
        when_to_use=("reference-only comparison during removal planning",),
        when_not_to_use=("new routing", "runtime mutation"),
        input_contract=("reference docs", "replacement owner", "migration plan"),
        output_contract=("removal readiness classification", "reference migration checklist"),
        required_context=("skill registry refs",),
        allowed_context=("repo docs", "skill metadata"),
        forbidden_context=("secrets", "private unrelated project data"),
        allowed_actions=("read_metadata", "produce_removal_plan"),
        forbidden_actions=("delete_skill", "remove_files", "inspect_secrets"),
        evidence_expectations=("references found", "replacement owner evidence"),
        validation_requirements=("no active route depends on skill",),
        tests=("tests/unit/test_workflow_skill_contracts.py",),
        evals=("skill_lifecycle_eval",),
        gotcha_inputs=("stale references",),
        learning_inputs=("operator correction",),
        emitted_learning_types=("skill_deprecation_signal",),
        versioning_policy="Record state transitions and replacement owner.",
        deprecation_policy="Deprecate before removal unless operator explicitly approves direct removal.",
        removal_policy="Removal requires explicit operator approval, backup, reference migration, and validation.",
        rollback_or_supersession_metadata={
            "replacement_owner": "quality:design",
            "rollback": "restore retained reference or backup copy",
        },
        privacy_boundary="Do not publish private skill usage evidence without sanitization.",
        notes="Removal fixture only; not a live Huashu removal instruction.",
    )


def validate_contract(contract: WorkflowContract | SkillContract | dict[str, Any]) -> ContractValidationResult:
    """Dispatch validation based on contract shape."""

    payload = _payload(contract)
    if "skill_family" in payload or "capabilities" in payload:
        return validate_skill_contract(payload)
    return validate_workflow_contract(payload)


def _payload(contract: WorkflowContract | SkillContract | dict[str, Any]) -> dict[str, Any]:
    if is_dataclass(contract):
        return asdict(contract)
    return dict(contract)


def _require_text(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    if not str(payload.get(key) or "").strip():
        errors.append(f"missing {key}")


def _require_sequence(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if isinstance(value, str):
        value = (value,) if value.strip() else ()
    if not value:
        errors.append(f"missing {key}")


def _validate_lifecycle(payload: dict[str, Any], errors: list[str]) -> None:
    lifecycle_state = str(payload.get("lifecycle_state") or "")
    if lifecycle_state not in APPROVED_LIFECYCLE_STATE_SET:
        errors.append(f"invalid lifecycle_state: {lifecycle_state}")


def _validate_mutation_risk(payload: dict[str, Any], errors: list[str]) -> None:
    mutation_risk = str(payload.get("mutation_risk") or "none")
    if mutation_risk not in APPROVED_MUTATION_RISK_SET:
        errors.append(f"invalid mutation_risk: {mutation_risk}")


def _contains_any(value: Any, terms: tuple[str, ...]) -> bool:
    values: tuple[Any, ...]
    if isinstance(value, (list, tuple, set)):
        values = tuple(value)
    else:
        values = (value,)
    haystack = " ".join(str(item).lower() for item in values)
    return any(term.lower() in haystack for term in terms)


def _allows_secret_or_sensitive_access(payload: dict[str, Any]) -> bool:
    allowed_values = (
        payload.get("allowed_actions"),
        payload.get("required_context"),
        payload.get("allowed_context"),
        payload.get("input_contract"),
    )
    return _contains_any(allowed_values, SECRET_OR_SENSITIVE_TERMS) and not _contains_any(
        payload.get("forbidden_actions"), ("inspect_secrets", "read_secrets", "secret")
    )


def _skill_is_mutation_capable(payload: dict[str, Any]) -> bool:
    mutation_terms = (
        "write",
        "mutate",
        "delete",
        "remove",
        "archive",
        "migration",
        "install",
        "commit",
        "push",
        "deploy",
        "submit",
    )
    return _contains_any(payload.get("allowed_actions"), mutation_terms)
