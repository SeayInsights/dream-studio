"""Contract registry domains — core half (first 9 of 19 domains).

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_registry.py. CONTRACT_DOMAINS
was a single 639-line literal, over the 600-line sibling cap on its own, so it
is split across this module (`_CONTRACT_DOMAINS_CORE`) and
contract_registry_domains_ops.py (`_CONTRACT_DOMAINS_OPS`), which assembles
the combined `CONTRACT_DOMAINS` tuple.

Gate-infra companion edit (WO-GF-SHARED-INTEL-SPLIT, non-verbatim, required):
domain `contract_atlas` source_patterns widened with
`contract_atlas_*.py`/`contract_registry_*.py` globs so the docs-drift gate,
change_impact_report (blast_radius), and contract_atlas_lifecycle continue to
match the new sibling files (the existing exact-filename entries are kept —
see the shared_intelligence_adapters domain's `adapter_*.py` precedent).
"""

from __future__ import annotations

from typing import Any

from .contract_registry_constants import PRD_DOC

_CONTRACT_DOMAINS_CORE: tuple[dict[str, Any], ...] = (
    {
        "domain_id": "contract_atlas",
        "domain_name": "Contract Atlas",
        "source_patterns": [
            "core/shared_intelligence/contract_atlas.py",
            "core/shared_intelligence/contract_atlas_*.py",
            "core/shared_intelligence/contract_atlas_lifecycle.py",
            "core/shared_intelligence/contract_registry.py",
            "core/shared_intelligence/contract_registry_*.py",
            "core/shared_intelligence/maturity_ledger.py",
            "core/module_contracts.py",
            "interfaces/cli/contract_atlas_lifecycle_gate.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/architecture/contract-atlas.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/lint-format-baseline-policy.md",
        ],
        "required_doc_refs": [
            "docs/architecture/contract-atlas.md",
            # docs/README.md removed (Wave 7): O1 README precedent — README accuracy is a
            # release-boundary judgment, not a per-PR mechanical coupling. Stays in docs_refs.
            # docs/operations/lint-format-baseline-policy.md removed (Wave 7): kept gated in
            # release_publication_gate where it belongs; the contract_atlas coupling was a
            # stamp-trap. Stays in docs_refs.
        ],
        "release_blocking": True,
        "freshness_policy": "source_changes_require_same_change_set_contract_or_docs_refresh",
        "public_export_boundary": "sanitized_public_export_only",
    },
    {
        "domain_id": "shared_intelligence_adapters",
        "domain_name": "Shared Intelligence And Adapter Projections",
        "source_patterns": [
            "core/shared_intelligence/adapter_*.py",
            "core/shared_intelligence/context_packets.py",
            "core/shared_intelligence/result_normalization.py",
            "adapter-projections/**",
            "AGENTS.md",
            # CLAUDE.md removed (O1): root project-instruction file, not an adapter-projection
            # file. Every Phase 18.4 substantive fire came from adapter-projections/** changes
            # (real projection regenerations). The 4 CLAUDE.md-triggered fires were content-free
            # stamps ("no adapter boundary change"). The real adapter-routing signal lands in
            # adapter-projections/** which remains in source_patterns.
        ],
        "contract_refs": [
            "docs/contracts/adapter-contract.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
        ],
        "docs_refs": [
            # docs/operations/independent-configuration-model.md removed (Wave 7): doc moved to
            # internal planning docs (.planning/docs/) — a deleted file must not be referenced.
            PRD_DOC,
            "README.md",
        ],
        "required_doc_refs": [
            "docs/architecture/shared-authority-and-adapter-projections.md",
        ],
        "release_blocking": True,
        "freshness_policy": "adapter_surface_changes_require_adapter_boundary_doc_refresh",
        "public_export_boundary": "adapter_configs_are_projection_docs_only",
    },
    {
        "domain_id": "task_attribution_outcomes",
        "domain_name": "AI Adapter Task Attribution And Outcomes",
        "source_patterns": [
            "core/shared_intelligence/task_attribution.py",
            "core/shared_intelligence/usage_accounting.py",
            "core/shared_intelligence/capability_center.py",
            "core/event_store/migrations/045_task_attribution_authority.sql",
            "projections/api/routes/project_intelligence.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            # docs/operations/task-attribution-and-outcomes.md removed (Wave 7): doc moved to
            # internal planning docs (.planning/docs/) — a deleted file must not be referenced.
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "docs_refs": [
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
            PRD_DOC,
            "docs/README.md",
        ],
        "required_doc_refs": [
            # docs/operations/task-attribution-and-outcomes.md removed (Wave 7): List A ungating
            # — doc moved to internal planning docs. Domain keeps DATABASE + MIGRATION_AUTHORITY.
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            # docs/architecture/contract-atlas.md removed (Wave 7): friction-prune fan-out — kept
            # gated only in its home contract_atlas domain. Stays in contract_refs.
            # docs/architecture/dream-studio-dashboard-projection-mapping.md removed (Wave 7):
            # friction-prune fan-out. Doc stays in docs/ (code-coupled in maturity_ledger.py);
            # remains in contract_refs as a non-blocking reference.
        ],
        "release_blocking": True,
        "freshness_policy": "attribution_schema_or_read_model_changes_require_dashboard_and_database_docs_refresh",
        "public_export_boundary": "attribution_examples_synthetic_live_evidence_private",
    },
    {
        "domain_id": "project_prd_authority_lifecycle",
        "domain_name": "Project PRD Authority Lifecycle",
        "source_patterns": [
            "core/shared_intelligence/context_packets.py",
            "core/event_store/migrations/047_prd_lifecycle_authority.sql",
            "core/event_store/migrations/103_drop_prd_cluster.sql",
            "projections/api/routes/project_intelligence.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            # docs/operations/prd-authority-lifecycle.md removed (Wave 7): doc moved to internal
            # planning docs (.planning/docs/) — a deleted file must not be referenced.
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "docs_refs": [
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            PRD_DOC,
            "docs/README.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
        ],
        "required_doc_refs": [
            # docs/operations/prd-authority-lifecycle.md removed (Wave 7): List A ungating — doc
            # moved to internal planning docs. Domain keeps DATABASE + MIGRATION_AUTHORITY.
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            # docs/architecture/contract-atlas.md removed (Wave 7): friction-prune fan-out.
            # docs/architecture/dream-studio-dashboard-projection-mapping.md removed (Wave 7):
            # friction-prune fan-out. Doc stays in docs/ (code-coupled); remains in contract_refs.
        ],
        "release_blocking": True,
        "freshness_policy": "prd_lifecycle_or_route_authority_changes_require_database_dashboard_context_packet_docs_refresh",
        "public_export_boundary": "prd_files_are_exports_sqlite_is_private_authority",
    },
    {
        "domain_id": "sqlite_schema_authority",
        "domain_name": "SQLite Schema And Authority",
        "source_patterns": [
            "core/event_store/migrations/**",
            "core/event_store/studio_db.py",
            "core/config/database.py",
            # O2: migration runner — schema-authority; changes require migration-docs review.
            # Phase 18.4 evidence: every sqlite_bootstrap.py change involved swallow handler
            # or migration ordering behavior, all schema-authority relevant.
            "core/config/sqlite_bootstrap.py",
        ],
        "contract_refs": [
            "docs/MIGRATION_AUTHORITY.md",
            "docs/DATABASE.md",
        ],
        "docs_refs": [
            "docs/architecture/dream-studio-structured-authority-projection-model.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
        ],
        "release_blocking": True,
        "freshness_policy": "schema_or_path_changes_require_database_docs_refresh",
        "public_export_boundary": "schema_docs_public_live_db_private",
    },
    {
        "domain_id": "installed_adapter_runtime",
        "domain_name": "Installed Adapter Runtime And Global Router",
        "source_patterns": [
            "core/installed_runtime.py",
            "core/installed_productization.py",
            "core/module_contracts.py",
            "core/module_profiles.py",
            "core/release/local_dogfood_stability.py",
            "ds.cmd",
            "ds.ps1",
            # interfaces/cli/ds.py removed (O1): 5000+ line catch-all that fired on every CLI
            # change and produced content-free stamps. The installed-runtime/platform-hardening
            # surface is defined in this domain's other source files (installed_runtime.py,
            # ds.cmd, ds.ps1, etc.). KNOWN LIMITATION: a change made PURELY in ds.py's command
            # handler that alters installed-runtime behavior without touching those core files
            # would not fire this domain. Accepted tradeoff — the whole-file coupling was so
            # noisy it trained stamping and caught nothing real. If a ds.py-only behavior change
            # is ever found to have drifted these docs, revisit.
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/installed-adapter-runtime.md",
            "docs/operations/installed-platform-productization.md",
            # docs/operations/long-run-multisession-operational-validation.md removed (Wave 7):
            # doc moved to internal planning docs (.planning/docs/).
            "docs/operations/troubleshooting.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
        ],
        "docs_refs": [
            # docs/operations/independent-configuration-model.md removed (Wave 7): doc moved to
            # internal planning docs (.planning/docs/).
            "docs/operations/installed-platform-productization.md",
            # docs/operations/long-run-multisession-operational-validation.md removed (Wave 7):
            # doc moved to internal planning docs (.planning/docs/).
            "docs/operations/troubleshooting.md",
            "docs/README.md",
        ],
        "required_doc_refs": [
            "docs/operations/installed-adapter-runtime.md",
            "docs/operations/installed-platform-productization.md",
            # docs/operations/long-run-multisession-operational-validation.md removed (Wave 7):
            # List A ungating — doc moved to internal planning docs.
            "docs/operations/troubleshooting.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
            # docs/operations/independent-configuration-model.md removed (Wave 7): List A
            # ungating — doc moved to internal planning docs.
        ],
        "release_blocking": True,
        "freshness_policy": "installed_runtime_or_router_changes_require_runtime_docs_refresh",
        "public_export_boundary": "installed_runtime_paths_private_global_commands_public",
    },
    {
        "domain_id": "dashboard_runtime",
        "domain_name": "Dashboard Runtime And Read Models",
        "source_patterns": [
            "projections/api/routes/**",
            "projections/frontend/dashboard.html",
            "core/telemetry/read_models*.py",
            "core/telemetry/dashboard_freshness.py",
        ],
        "contract_refs": [
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/contracts/dashboard-projection-model-contract.md",
        ],
        "docs_refs": [
            "docs/operator-guide.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            # Anchor swapped (Wave 7): friction-prune moved the gate anchor off
            # dream-studio-dashboard-projection-mapping.md (a build-process map kept in
            # contract_refs as a non-blocking reference) onto the PRODUCT contract doc, which was
            # already in contract_refs. The mapping doc stays in docs/ (code-coupled in
            # maturity_ledger.py).
            "docs/contracts/dashboard-projection-model-contract.md",
        ],
        "release_blocking": True,
        "freshness_policy": "dashboard_contract_changes_require_projection_mapping_refresh",
        "public_export_boundary": "dashboard_derived_not_primary_authority",
    },
    {
        "domain_id": "security_lifecycle_gate",
        "domain_name": "Security-By-Default Lifecycle Gate",
        "source_patterns": [
            "core/security/**",
            "skills/security/**",
            "guardrails/rules/security.yaml",
            "docs/contracts/security-review-*.md",
            "docs/contracts/security-review-*.yaml",
            "projections/api/routes/security.py",
            "projections/api/routes/project_intelligence.py",
            "projections/api/routes/shared_intelligence.py",
            "core/release/versioning.py",
        ],
        "contract_refs": [
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
            "docs/contracts/security-review-source-47-enterprise-scans.md",
            "docs/contracts/security-review-47-scan-crosswalk.md",
            "docs/contracts/security-review-scan-catalog.yaml",
        ],
        "docs_refs": [
            "docs/contracts/security-review-profile-pack-contract.md",
            "docs/contracts/security-review-catalog-governance.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/operations/product-readiness.md",
        ],
        "required_doc_refs": [
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
            "docs/contracts/security-review-profile-pack-contract.md",
            # docs/operations/product-readiness.md removed from required (Wave 7): List A ungating
            # — domain keeps its product contract docs. Doc stays in docs/ (NOT moved): code-coupled
            # to the Phase 14B baseline test (tests/unit/test_product_readiness_baseline.py) and
            # scripts/dev.ps1 product-readiness target. Remains a non-blocking docs_refs entry.
        ],
        "release_blocking": True,
        "freshness_policy": "security_lifecycle_changes_require_control_mapping_and_readiness_docs_refresh",
        "public_export_boundary": "security_findings_public_shape_live_evidence_private",
    },
    {
        "domain_id": "secure_production_readiness_gate",
        "domain_name": "Secure Production Readiness Gate",
        "source_patterns": [
            "core/production_readiness/**",
            "core/event_store/migrations/040_production_readiness_authority.sql",
            "core/release/versioning.py",
            "projections/api/routes/project_intelligence.py",
            "projections/api/routes/shared_intelligence.py",
            "docs/contracts/secure-production-readiness-gate.md",
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
        ],
        "contract_refs": [
            "docs/contracts/secure-production-readiness-gate.md",
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
        ],
        "docs_refs": [
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/operations/product-readiness.md",
            "docs/README.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            "docs/contracts/secure-production-readiness-gate.md",
            # docs/architecture/contract-atlas.md removed from required (Wave 7): friction-prune
            # fan-out. Stays in docs_refs.
            # docs/architecture/dream-studio-dashboard-projection-mapping.md removed from required
            # (Wave 7): friction-prune fan-out. Doc stays in docs/ (code-coupled); non-blocking ref.
            # docs/operations/product-readiness.md removed from required (Wave 7): List A ungating —
            # domain keeps its readiness-gate contract doc. Doc stays in docs/ (code-coupled).
        ],
        "release_blocking": True,
        "freshness_policy": "production_readiness_control_or_sqlite_changes_require_readiness_docs_refresh",
        "public_export_boundary": "readiness_scores_are_derived_private_evidence_not_public_claims",
    },
)
