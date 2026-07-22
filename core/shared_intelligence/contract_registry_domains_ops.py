"""Contract registry domains — ops half (last 10 of 19 domains) + CONTRACT_DOMAINS.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_registry.py. Assembles the
combined `CONTRACT_DOMAINS` tuple from `_CONTRACT_DOMAINS_CORE` (see
contract_registry_domains_core.py) and this module's `_CONTRACT_DOMAINS_OPS`.

Gate-infra companion edit (WO-GF-SHARED-INTEL-SPLIT, non-verbatim, required):
domain `expert_workflow_system` source_patterns widened with the
`expert_workflows_*.py` glob so the docs-drift gate continues to match the new
sibling files (precedent: `shared_intelligence_adapters` already uses
`adapter_*.py`).
"""

from __future__ import annotations

from typing import Any

from .contract_registry_constants import PRD_DOC
from .contract_registry_domains_core import _CONTRACT_DOMAINS_CORE

_CONTRACT_DOMAINS_OPS: tuple[dict[str, Any], ...] = (
    {
        "domain_id": "workflow_and_hooks",
        "domain_name": "Workflow And Hook Runtime",
        "source_patterns": [
            "hooks/**",
            "runtime/hooks/**",
            "canonical/workflows/**",
            "control/execution/workflow/**",
        ],
        "contract_refs": [
            "docs/HOOK_RUNTIME.md",
            "docs/WORKFLOW_RUNTIME.md",
            "docs/WORKFLOWS.md",
            "docs/contracts/hook-contract.md",
            "docs/contracts/workflow-contract.md",
        ],
        "docs_refs": [
            "docs/operator-guide.md",
        ],
        "required_doc_refs": [
            "docs/HOOK_RUNTIME.md",
            "docs/WORKFLOW_RUNTIME.md",
        ],
        "release_blocking": True,
        "freshness_policy": "hook_or_workflow_changes_require_runtime_docs_refresh",
        "public_export_boundary": "runtime_hooks_public_secrets_private",
    },
    {
        "domain_id": "expert_workflow_system",
        "domain_name": "Expert Skills And Workflow System",
        "source_patterns": [
            "core/shared_intelligence/expert_workflows.py",
            "core/shared_intelligence/expert_workflows_*.py",
            # skills/career/** removed (Wave 2): the career skill pack was deleted along with
            # the career_ops telemetry layer. canonical/skills/** (DS packs) is a different
            # path and is NOT matched here.
            # workflows/**: removed (O1). This pattern was BROKEN — workflow YAMLs live at
            # canonical/workflows/ but "workflows/**" does NOT match "canonical/workflows/**"
            # (fnmatch prefix mismatch). The pattern matched zero files. Also: the 24 canonical
            # workflow templates are general dev tools, not expert-workflow-system components
            # (grep confirmed zero coupling to expert_workflows.py). The 7 relevant workflow
            # files (idea-to-pr, fix-issue, etc.) are a separate O2 coverage gap to add
            # deliberately with correct canonical/ prefixes in a follow-on WO.
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/expert-workflow-systems.md",
            "docs/architecture/contract-atlas.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "required_doc_refs": [
            "docs/operations/expert-workflow-systems.md",
            # docs/architecture/contract-atlas.md removed (Wave 7): friction-prune fan-out — kept
            # gated only in its home contract_atlas domain. Stays in contract_refs.
            # docs/README.md removed (Wave 7): O1 README precedent. Stays in docs_refs.
        ],
        "release_blocking": True,
        "freshness_policy": "expert_skill_or_workflow_changes_require_overlap_matrix_and_docs_refresh",
        "public_export_boundary": (
            "career_data_private_by_default_public_outputs_sanitized_and_operator_approved"
        ),
    },
    {
        "domain_id": "release_publication_gate",
        "domain_name": "Release Gate And Publication Boundary",
        "source_patterns": [
            ".github/workflows/**",
            "core/release/github_pr_cicd_gate.py",
            "interfaces/cli/ci_gate.py",
            "interfaces/cli/repo_publication_readiness.py",
            "interfaces/cli/lint_baseline.py",
            "interfaces/cli/contract_docs_drift_gate.py",
            "interfaces/cli/contract_atlas_lifecycle_gate.py",
            "core/release/repo_publication_readiness.py",
            "core/projects/external_validation.py",
            "core/projects/dashboard_views.py",
            "core/telemetry/docker_profiles.py",
            "runtime/config/release-gates/**",
        ],
        "contract_refs": [
            "docs/operations/lint-format-baseline-policy.md",
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/repo-publication-privacy.md",
            "docs/operations/external-project-validation-pipeline.md",
            "docs/operations/docker-module-profiles.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/operator-guide.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            "docs/operations/lint-format-baseline-policy.md",
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/repo-publication-privacy.md",
            "docs/operations/external-project-validation-pipeline.md",
            "docs/operations/docker-module-profiles.md",
            # README.md removed (O1): release-gate / lint-baseline changes don't affect README
            # content. Phase 18.4 stamps confirmed "No README content change required." README
            # accuracy is a release-boundary judgment (reviewed by a human at release/publication
            # time), not a per-PR mechanical coupling. See PUBLICATION_BOUNDARY.md for the
            # release-boundary checklist where README currency is now recorded.
        ],
        "release_blocking": True,
        "freshness_policy": "release_gate_changes_require_release_docs_refresh",
        "public_export_boundary": "release_evidence_private_release_policy_public",
    },
    {
        "domain_id": "career_capability_agent_github_intake",
        "domain_name": "Capability Center, Scoped Agents, And GitHub Repo Intake",
        "source_patterns": [
            "core/shared_intelligence/capability_center.py",
            "core/shared_intelligence/scoped_agents.py",
            "core/shared_intelligence/github_repo_intake.py",
            "core/event_store/migrations/044_career_capability_agent_github_authority.sql",
            "core/module_contracts.py",
            "core/module_profiles.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/github-repo-intake-evaluation.md",
            "docs/architecture/contract-atlas.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/PUBLICATION_BOUNDARY.md",
        ],
        "required_doc_refs": [
            "docs/operations/github-repo-intake-evaluation.md",
            # docs/architecture/contract-atlas.md removed (Wave 7): friction-prune fan-out.
            # docs/README.md removed (Wave 7): O1 README precedent.
            # docs/PUBLICATION_BOUNDARY.md removed (Wave 7): kept gated in release_publication_gate
            # where it belongs. Stays in docs_refs.
        ],
        "release_blocking": True,
        "freshness_policy": (
            "private_career_capability_agent_or_github_intake_changes_require_docs_and_public_boundary_refresh"
        ),
        "public_export_boundary": (
            "career_data_private_by_default_github_evaluation_evidence_sanitized_before_public_export"
        ),
    },
    {
        "domain_id": "platform_hardening_sequence",
        "domain_name": "Platform Hardening Sequence",
        "source_patterns": [
            "core/shared_intelligence/platform_hardening.py",
            "core/event_store/migrations/046_platform_hardening_authority.sql",
            # interfaces/cli/ds.py removed (O1): same catch-all issue as installed_adapter_runtime.
            # Platform hardening behavior is defined in platform_hardening.py + the specific
            # migration above. KNOWN LIMITATION: a ds.py-only handler change that alters
            # platform-hardening behavior without touching those files would not fire this domain.
            # Accepted — the whole-file coupling produced only content-free stamps.
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            # docs/operations/platform-hardening-sequence.md removed from required (Wave 7): List A
            # ungating. Doc stays in docs/ (NOT moved): code-coupled as evidence in
            # maturity_ledger.py (platform_hardening_sequence area). Remains a non-blocking ref.
            "docs/operations/platform-hardening-sequence.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/installed-platform-productization.md",
            # docs/operations/task-attribution-and-outcomes.md removed (Wave 7): doc moved to
            # internal planning docs (.planning/docs/) — a deleted file must not be referenced.
        ],
        "required_doc_refs": [
            # docs/operations/platform-hardening-sequence.md removed from required (Wave 7): List A
            # ungating — domain keeps DATABASE + MIGRATION_AUTHORITY. Doc stays (code-coupled).
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            # docs/PUBLICATION_BOUNDARY.md removed (Wave 7): kept gated in release_publication_gate.
            # docs/architecture/contract-atlas.md removed (Wave 7): friction-prune fan-out.
            # docs/architecture/dream-studio-dashboard-projection-mapping.md removed (Wave 7):
            # friction-prune fan-out. Doc stays in docs/ (code-coupled); non-blocking ref.
        ],
        "release_blocking": True,
        "freshness_policy": "platform_hardening_authority_or_surface_changes_require_policy_privacy_installer_demo_docs_refresh",
        "public_export_boundary": "private_evidence_stays_private_sanitized_rollups_and_demo_packets_only",
    },
    {
        # O2: schema coherence audit detector — narrow domain, intentionally separate from
        # sqlite_schema_authority. The detector's relevant doc is aspirational-schema-debt.md
        # (what it finds, the severity logic, the blind spots), NOT DATABASE.md/MIGRATION_AUTHORITY.md
        # which document the schema itself. Coupling the detector to schema-structure docs would
        # create a stamp-trap: detector changes (finding types, severity, swallow inventory) have
        # no bearing on the schema definition docs. Phase 18.4 evidence: every schema_coherence.py
        # change was accompanied by a substantive aspirational-schema-debt.md update (PRs #103,
        # #105, #106, #110). Zero cases where debt-doc review would have been content-free.
        "domain_id": "schema_coherence_audit",
        "domain_name": "Schema Coherence Audit",
        "source_patterns": [
            "core/config/schema_coherence.py",
        ],
        "contract_refs": [
            "docs/architecture/aspirational-schema-debt.md",
        ],
        "docs_refs": [],
        "required_doc_refs": [
            "docs/architecture/aspirational-schema-debt.md",
        ],
        "release_blocking": True,
        "freshness_policy": "schema_coherence_audit_changes_require_debt_doc_refresh",
        "public_export_boundary": "schema_coherence_findings_are_operational_evidence_not_public_claims",
    },
    {
        # Work-order engine → ds-workorder skill surface coupling.
        # core/work_orders/*.py are the authoritative functions wrapped by ds-workorder
        # skill modes (start, execute, close, block, status). When the engine API changes
        # (return shapes, gate names, field names), the corresponding SKILL.md surface
        # contract must be reviewed and updated in the same changeset so operators do not
        # get instructions that mismatch what the functions return.
        # Phase 18 evidence: WO-GATE-PARITY (PR #269), WO-GRADER-LOOKUP (PRs #267–268),
        # and WO-TASK-UX (PR #266) all changed engine + SKILL.md in the same PR — the
        # coupling was implicit; this domain makes it explicit and enforced.
        "domain_id": "work_orders_engine_skill_surface",
        "domain_name": "Work Orders Engine → DS-Workorder Skill Surface",
        "source_patterns": [
            "core/work_orders/**",
        ],
        "contract_refs": [
            "canonical/skills/ds-workorder/SKILL.md",
            "canonical/skills/ds-workorder/modes/start/SKILL.md",
            "canonical/skills/ds-workorder/modes/execute/SKILL.md",
            "canonical/skills/ds-workorder/modes/close/SKILL.md",
            "canonical/skills/ds-workorder/modes/block/SKILL.md",
            "canonical/skills/ds-workorder/modes/status/SKILL.md",
        ],
        "docs_refs": [],
        "required_doc_refs": [
            "canonical/skills/ds-workorder/SKILL.md",
        ],
        "release_blocking": True,
        "freshness_policy": "work_orders_engine_changes_require_ds_workorder_skill_surface_review",
        "public_export_boundary": "skill_surface_docs_are_agent_contracts_not_public_api",
    },
    {
        # Projects engine → ds-project skill surface coupling.
        # Same pattern as work_orders_engine_skill_surface.
        "domain_id": "projects_engine_skill_surface",
        "domain_name": "Projects Engine → DS-Project Skill Surface",
        "source_patterns": [
            "core/projects/**",
        ],
        "contract_refs": [
            "canonical/skills/ds-project/SKILL.md",
        ],
        "docs_refs": [],
        "required_doc_refs": [
            "canonical/skills/ds-project/SKILL.md",
        ],
        "release_blocking": True,
        "freshness_policy": "projects_engine_changes_require_ds_project_skill_surface_review",
        "public_export_boundary": "skill_surface_docs_are_agent_contracts_not_public_api",
    },
    {
        # Milestones engine → ds-milestone skill surface coupling.
        # Same pattern as work_orders_engine_skill_surface.
        "domain_id": "milestones_engine_skill_surface",
        "domain_name": "Milestones Engine → DS-Milestone Skill Surface",
        "source_patterns": [
            "core/milestones/**",
        ],
        "contract_refs": [
            "canonical/skills/ds-milestone/SKILL.md",
        ],
        "docs_refs": [],
        "required_doc_refs": [
            "canonical/skills/ds-milestone/SKILL.md",
        ],
        "release_blocking": True,
        "freshness_policy": "milestones_engine_changes_require_ds_milestone_skill_surface_review",
        "public_export_boundary": "skill_surface_docs_are_agent_contracts_not_public_api",
    },
    {
        # STRUCTURE.md has a hand-written directory tree that drifts as packs evolve.
        # Adding packs.yaml as a source here means any pack/mode change requires STRUCTURE.md
        # to be updated in the same changeset — enforcing the AUTO-DIRECTORY-TREE contract.
        "domain_id": "repo_structure_navigation",
        "domain_name": "Repository Structure And Navigation",
        "source_patterns": [
            "packs.yaml",
            "packs/**",
        ],
        "contract_refs": [
            "STRUCTURE.md",
            "docs/reference/layer-map.md",
            "docs/reference/skills-index.md",
        ],
        "docs_refs": [],
        "required_doc_refs": [
            "STRUCTURE.md",
        ],
        "release_blocking": True,
        "freshness_policy": "pack_definition_changes_require_structure_doc_refresh",
        "public_export_boundary": "structure_docs_public_runtime_state_private",
    },
)

CONTRACT_DOMAINS: tuple[dict[str, Any], ...] = _CONTRACT_DOMAINS_CORE + _CONTRACT_DOMAINS_OPS
