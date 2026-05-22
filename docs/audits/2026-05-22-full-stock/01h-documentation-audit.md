# Pass 1h — Documentation Audit
*Phase 1 analysis | 2026-05-22*

---

## Stated Architectural Intents

| # | Intent | Description |
|---|--------|-------------|
| 1 | **SQLite-first authority** | All runtime STATE must be SQLite-backed. File-based state is v1 rot. |
| 2 | **Security audit during brownfield onboarding** | Security skills run during project intake; findings stored in SQLite. |
| 3 | **Security as SDLC lifecycle gate** | Greenfield projects must pass security audit before going live. |
| 4 | **Canonical events as the spine** | All state changes flow through canonical_events. |
| 5 | **Marker file authority for attribution** | `.dream-studio-project` markers are the project identity source. |

---

## Documentation Inventory by Category

### docs/contracts/ (34 files)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| adapter-contract.md | boundaries | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Phase 7D; explicitly states local canonical runtime stays authoritative; adapters may not own persistence |
| agent-contract.md | boundaries | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Phase 11Y; agents do not own state; output-only |
| approval-contract.md | governance | MIXED | **DIVERGE** | N/A | N/A | N/A | NO | Phase 16A; explicitly states approval records are **file-backed only**; DB integration is deferred; active divergence with Intent 1 |
| artifact-format-policy.md | policy | CURRENT | ALIGN | N/A | N/A | N/A | NO | SQLite listed as authoritative for local operational store |
| dashboard-projection-model-contract.md | projections | CURRENT | ALIGN | N/A | N/A | N/A | NO | Projections are explicitly read-only over file-backed artifacts; authority stays in Work Orders |
| enterprise-aggregation-contract.md | boundaries | CURRENT | ALIGN | N/A | N/A | N/A | NO | Phase 13B; clear boundary that enterprise may not read studio.db directly |
| eval-artifact-contract.md | evidence | MIXED | **DIVERGE** | N/A | N/A | N/A | NO | Phase 16A; eval artifacts are file-backed only; DB integration deferred; diverges with Intent 1 |
| event-contract.md | core | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Phase 7A; canonical_events is the authoritative persisted stream; emit path is explicit |
| execution-packet-contract.md | execution | CURRENT | ALIGN | N/A | N/A | N/A | NO | Phase 16A; packets are renderings only; no DB writes |
| file-structure-authority-policy.md | policy | CURRENT | ALIGN | N/A | N/A | N/A | NO | Aspirational marker (has TODO); defines where artifacts belong without executing moves |
| governance-contract.md | governance | CURRENT | ALIGN | N/A | ALIGN | ALIGN | NO | Phase 11C; scanner output is evidence not authority; governance signals are local evidence |
| handoff-packet-contract.md | continuity | CURRENT | ALIGN | N/A | N/A | N/A | NO | Handoff is a prompt artifact; must not open runtime DB or write event ledgers |
| hook-contract.md | runtime | CURRENT | ALIGN | N/A | N/A | N/A | NO | Phase 11Y; hooks are portable trigger primitives |
| human-in-the-loop-contract.md | governance | CURRENT | ALIGN | N/A | N/A | N/A | NO | Phase 16A; humans own approval for mutation, escalation, export; manual execution is file-backed in Phase 16 |
| operator-decision-contract.md | governance | CURRENT | ALIGN | N/A | N/A | N/A | NO | Operator decisions are file-backed evidence; written to decision request JSON paths |
| portable-execution-contract.md | execution | CURRENT | ALIGN | N/A | N/A | N/A | NO | Phase 11Y; target files are renderings, not canonical primitive definitions |
| projection-contract.md | projections | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Phase 7C; projection tables are rebuildable from canonical_events; detailed table ownership matrix |
| research-source-contract.md | evidence | CURRENT | ALIGN | N/A | N/A | N/A | NO | Research is advisory evidence only; research_cache is advisory not canonical |
| secure-production-readiness-gate.md | security | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | Describes SQLite authority tables for readiness records; non-executing classification framework |
| security-by-default-development-lifecycle-gate.md | security | CURRENT | ALIGN | ALIGN | ALIGN | N/A | NO | Full applicable 47-control review required at project intake; findings stored in SQLite; lifecycle policy is explicit |
| security-review-47-scan-crosswalk.md | security | CURRENT | ALIGN | N/A | N/A | N/A | NO | Coverage evidence only; documentation/data only; crosswalk from 47-source to catalog |
| security-review-catalog-governance.md | security | CURRENT | ALIGN | N/A | N/A | N/A | NO | Synchronization rules for security review artifacts; drift prevention |
| security-review-profile-pack-contract.md | security | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | Pack is advisory planning and evidence structure; binds to Work Order authority model |
| security-review-report-artifact-contract.md | security | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | File-backed security review report shapes; storage guidance under Work Order paths |
| security-review-scan-catalog.md | security | CURRENT | ALIGN | N/A | N/A | N/A | NO | Catalog is planning data only; non-executing |
| security-review-scan-definition-schema.md | security | CURRENT | ALIGN | N/A | N/A | N/A | NO | Schema authority for scan definitions; execution_status must be non_executing_definition |
| security-review-source-47-enterprise-scans.md | security | CURRENT | N/A | N/A | N/A | N/A | NO | Source list only; documentation/data |
| security-review-tier0-work-order-template.md | security | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | Observe-only template; binds to existing Work Order authority model |
| skill-contract.md | runtime | CURRENT | ALIGN | N/A | N/A | N/A | NO | Phase 11Y; skills do not own local canonical runtime state |
| state-contract.md | core | **MIXED** | **DIVERGE** | N/A | N/A | ALIGN | NO | Phase 7B; workflow state canonical owner listed as `~/.dream-studio/state/workflows.json` (file-based, not SQLite); this is explicit but contradicts Intent 1 direction |
| workflow-contract.md | runtime | CURRENT | ALIGN | N/A | N/A | N/A | NO | Phase 11Y; workflows do not own canonical state; state persisted by named owner in state contract |
| work-ledger-contract.md | execution | MIXED | **DIVERGE** | N/A | N/A | N/A | NO | Phase 16A; ledger is explicitly file-backed only; DB/event integration deferred; active divergence with Intent 1 |
| work-order-contract.md | execution | MIXED | **DIVERGE** | N/A | N/A | N/A | NO | Phase 16A; Work Orders are file_backed only; no DB tables, no schema migrations, no event writes by default |
| work-order-paused-work-contract.md | continuity | CURRENT | ALIGN | N/A | N/A | N/A | NO | PausedWork artifacts are file-backed; must not open runtime databases |
| work-result-contract.md | evidence | MIXED | **DIVERGE** | N/A | N/A | N/A | NO | Phase 16A; Work Results are file-backed local evidence; do not write native runtime DB |

**Intent 1 note on contracts layer:** Six contracts (approval-contract, eval-artifact-contract, work-ledger-contract, work-order-contract, work-result-contract, plus state-contract for workflow state) explicitly describe file-based stores as canonical or defer SQLite integration. These are Phase 16A contracts — the file-based state is intentional per Phase 16 design, not accidental rot. However, the stated intent that "file-based state is v1 rot" is in direct tension with these contracts' ongoing file-backed-only policy.

---

### docs/architecture/ (9 files)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| canonical-event-reconciliation.md | events | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Short doc; describes reconciliation pipeline from backup events; event authority in canonical_events |
| contract-atlas.md | intelligence | CURRENT | ALIGN | N/A | N/A | N/A | NO | Lifecycle status: foundation_active; Contract Atlas is a derived view only; current implementation references are accurate |
| dream-studio-ai-orchestration-architecture.md | architecture | CURRENT | ALIGN | N/A | N/A | N/A | NO | Short overview doc; adapter model; operational intelligence boundary |
| dream-studio-dashboard-projection-mapping.md | projections | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; detailed projection domain mapping; requires mapping fields |
| dream-studio-execution-telemetry-spine.md | telemetry | ASPIRATIONAL | ALIGN | N/A | N/A | ALIGN | NO | Lifecycle status: draft_generated; lists tables that may not all exist yet (e.g., telemetry_entity_registry, blocker_resolution_records, authority_projection_records); presents a direction not fully implemented |
| dream-studio-structured-authority-projection-model.md | projections | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Describes projection record shape and authority; stale/superseded detection |
| event-store.md | events | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Modified 2026-05-22; describes two-layer event storage model accurately; spool pipeline explained; fabricators removed in TA5 noted |
| shared-authority-and-adapter-projections.md | boundaries | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; canonical authority explicitly named; adapter role clearly bounded |
| SYSTEM.md | architecture | ASPIRATIONAL | ALIGN | N/A | N/A | ALIGN | NO | Version 3.0 dated 2026-05-07; aspirational marker (has TODO); some CONTROL layer ingestion items (e.g., "AI chat logs → events", "intent parsing → events") describe a direction not yet fully implemented; overall intent-aligned |

---

### docs/operations/ (25 files)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| adapter-workspace-hygiene.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Clear policy on where adapter scratch belongs; `~/.dream-studio/adapters/` not Git |
| career-ops-capability-center.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Career Ops SQLite tables from migration 044; private by default |
| code-history-impact-guardrail.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Operational policy for code change impact; no state authority claims |
| docker-clean-room.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Docker as optional validation harness only; does not mount host `~/.dream-studio` |
| docker-module-profiles.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Lifecycle status: tested_only; Docker is optional; local-first SQLite must work without Docker |
| expert-workflow-systems.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Lifecycle status: foundation_active; outputs persist through existing authority tables |
| external-project-validation-pipeline.md | operations | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | Lifecycle status: runtime_validated; external targets paused by default; security classification step in pipeline |
| github-repo-intake-evaluation.md | operations | CURRENT | ALIGN | ALIGN | N/A | N/A | NO | Migration 044 SQLite tables; security and supply-chain review step in intake workflow; routes to security_review_required |
| independent-configuration-model.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; security lifecycle gate listed as SQLite + repo docs; configuration areas table is comprehensive |
| installed-adapter-runtime.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; SQLite authority path explicit; source/state separation clear |
| installed-platform-productization.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; install model clearly describes SQLite authority at `state/studio.db` |
| lightweight-github-ci-strategy.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | CI strategy accurately reflects current .github/workflows structure |
| lint-format-baseline-policy.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; Black + Flake8 baseline policy; flake8-baseline.txt path correct |
| local-runtime.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Runtime DB at `~/.dream-studio/state/studio.db` is authoritative; schema version skew explained |
| long-run-multisession-operational-validation.md | operations | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | Lifecycle status: tested_only; security/readiness classification cycle is one of the required cycles |
| platform-hardening-sequence.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; SQLite tables from migration 046 listed; hardening milestones current |
| prd-authority-lifecycle.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | SQLite as durable authority for PRD lifecycle; primary tables listed; files are optional exports |
| product-authority-orchestration-hardening.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-19; workflow/skill contracts for repeatable work |
| product-readiness.md | operations | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | Phase 15 evidence path; security/readiness classification mentioned in posture check |
| repo-publication-privacy.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; publication readiness command accurate |
| task-attribution-and-outcomes.md | operations | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Lifecycle status: runtime_validated; task_attribution_records is current SQLite authority; links to execution_events and process_runs |
| troubleshooting.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; references `ds validate`, `ds router`, `ds adapters` commands; SQLite authority troubleshooting |
| verified-legacy-purge-policy.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Safe purge classifications; requires migration proof before removing rows |
| windows-dev-commands.md | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | PowerShell commands for dev.ps1 targets; accurate |
| work-orders.md | operations | MIXED | **DIVERGE** | N/A | N/A | N/A | NO | Describes Work Orders as file-backed only (consistent with Phase 16A contracts); explicitly says Work Orders are NOT DB tables; diverges with Intent 1 by design |

---

### docs/product/ (6 files)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| dream-studio-architecture-brief.md | product | CURRENT | ALIGN | N/A | N/A | N/A | NO | Architecture overview; accurate product identity |
| dream-studio-artifact-requirements.md | product | CURRENT | ALIGN | N/A | N/A | N/A | NO | Artifact roles and lifecycle; format guidance |
| dream-studio-definition-of-done.md | product | CURRENT | ALIGN | N/A | ALIGN | N/A | NO | Database Authority Done requires explicit SQLite mutation approval; security posture check included in product readiness section |
| dream-studio-human-in-the-loop-policy.md | product | CURRENT | ALIGN | N/A | N/A | N/A | NO | HITL roles; approval for mutation; delegates and non-delegable decisions |
| dream-studio-prd.md | product | CURRENT | ALIGN | N/A | ALIGN | ALIGN | NO | Status: current public product authority; last updated 2026-05-15; track secure production readiness separately; emit telemetry for security findings; intent-aligned throughout |
| dream-studio-research-and-verification-policy.md | product | CURRENT | ALIGN | N/A | N/A | N/A | NO | Research is advisory; verification gates before high-risk actions |
| dream-studio-stack-and-runtime.md | product | CURRENT | ALIGN | N/A | N/A | N/A | NO | Status: draft_generated; SQLite/local database authority labeled current/planned; Sessions, Memory/context are planned |

---

### docs/architecture/ SYSTEM.md and root docs

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| ARCHITECTURE.md (root) | architecture | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-14; Component Map accurate; "SQLite-First Direction" section explicit; Safety Model lists approval requirements |
| CHANGELOG.md (root) | changelog | CURRENT | ALIGN | N/A | N/A | N/A | NO | Accurate history from 0.11.0 to present; granular skill tracking, hook consolidation, YAML mode config described |
| DREAM-STUDIO-ROADMAP.md (root) | roadmap | CURRENT | ALIGN | N/A | N/A | N/A | NO | Last updated 2026-05-17; Slices 1–9e closed; accurate capability overview; three-layer architecture description current |
| DATABASE.md (root) | database | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; SQLite authority areas comprehensive; current schema version 54 migrations stated |
| HOOK_RUNTIME.md (root) | hooks | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; lists orphaned handlers (on-startup-health.py, on-periodic-health.py, on-skill-gate.py) |
| MIGRATION_AUTHORITY.md (root) | schema | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; canonical migration directory accurate; migration 011 gap explained |
| WORKFLOW_RUNTIME.md (root) | workflows | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; 22 workflow inventory; active workflow JSON is transient runtime state |
| WORKFLOWS.md (root) | workflows | CURRENT | ALIGN | N/A | N/A | N/A | NO | Workflow types and approval boundaries; CI/CD strategy accurate |
| RUNTIME_RELIABILITY_GATE.md (root) | gates | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-14; test file list and coverage accurate |
| TRANSACTION_SAFETY_GUIDE.md (root) | database | CURRENT | ALIGN | N/A | N/A | N/A | NO | Before/After pattern for transactions; migration checklist; current |
| UPGRADE_PLAN.md (root) | roadmap | ASPIRATIONAL | ALIGN | N/A | N/A | N/A | NO | Design skill upgrade plan with phased aspirational roadmap; explicitly aspirational; not system state docs |
| PUBLICATION_BOUNDARY.md (root) | publication | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-22; public allowlist and private-by-default list accurate |

---

### docs/ standalone reference files (15 files)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| client-profile-schema.md | security | CURRENT | N/A | N/A | N/A | N/A | NO | Client YAML schema for security skills; `~/.dream-studio/clients/` paths match implementation |
| copilot-setup.md | adapters | **STALE** | N/A | N/A | N/A | N/A | NO | References `.marketplace/adapters/copilot-instructions/` — this path does not exist in the repo; instructions describe committing to `.github/copilot-instructions.md` which may be valid but source artifact is missing |
| coverage-report-phase6.md | qa | STALE | N/A | N/A | N/A | N/A | NO | Dated 2026-05-06; reports 56% coverage against 90% target; current state is significantly beyond Phase 6; this is historical evidence, not current state |
| cursor-setup.md | adapters | **STALE** | N/A | N/A | N/A | N/A | NO | References `.marketplace/adapters/cursor-rules/.cursorrules` — path does not exist; same pattern as copilot-setup |
| DECISION_QUERY_EXAMPLES.md | examples | CURRENT | ALIGN | N/A | N/A | N/A | NO | Query examples for decision log; Python API patterns; current module paths referenced |
| demo-disaster-prevention-scenario.md | demo | CURRENT | N/A | N/A | N/A | N/A | NO | Operational scenario doc for demos |
| demo-script.md | demo | **STALE** | N/A | N/A | N/A | N/A | NO | Dated 2026-05-14; references `think mode` as the first step but pack-based routing was introduced in v0.11.0 (2026-04-30); terminology may be outdated |
| design-skills-guide.md | skills | STALE | N/A | N/A | N/A | N/A | NO | References `ds:design` and `huashu-design` as the two available design skills; `huashu-design` is not a current canonical skill name; two-skill comparison structure suggests pre-consolidation era |
| operator-guide.md (in docs/) | operations | CURRENT | ALIGN | N/A | N/A | N/A | NO | Short 26-line guide; accurate advice; references `.dream-studio` runtime state |
| portfolio-case-study.md | product | CURRENT | ALIGN | N/A | N/A | N/A | NO | Marketing artifact; before/after framing accurate |
| quickstart.md | onboarding | **STALE** | N/A | N/A | N/A | N/A | NO | References `git clone` from GitHub; points to test commands for old dashboard telemetry routes; `claude code link .` syntax may not match current Claude Code CLI; `.claude-plugin/` reference is legacy |
| security-best-practices.md | security | CURRENT | N/A | N/A | N/A | N/A | NO | Best practices for security skills; patterns for correct vs incorrect behavior |
| security-orchestration-pattern.md | security | CURRENT | N/A | N/A | N/A | N/A | NO | 4-phase security skill workflow; references `~/.dream-studio/clients/` paths; consistent with implementation |
| security-skills-redundancy-analysis.md | analysis | STALE | N/A | N/A | N/A | N/A | NO | Dated 2026-04-26; pre-consolidation analysis of 8 security SKILL.md files; pack consolidation happened 2026-04-30; skills no longer have individual SKILL.md files at root; this is historical analysis |
| security-storage-layout.md | security | CURRENT | N/A | N/A | N/A | N/A | NO | `~/.dream-studio/security/` directory structure; paths accurate |
| token-efficient-prompting.md | skills | CURRENT | N/A | N/A | N/A | N/A | NO | Token efficiency guidance; progressive disclosure patterns; current |
| token-overhead.md | telemetry | CURRENT | ALIGN | N/A | N/A | N/A | NO | Describes token overhead methodology; references `on-token-log.py` and `benchmark_tokens.py` |
| token-reduction-summary.md | telemetry | CURRENT | N/A | N/A | N/A | N/A | NO | Token reduction evidence from CHANGELOG-matching improvements |
| UAT-Phase6-Checklist.md | qa | STALE | N/A | N/A | N/A | N/A | NO | Dated Phase 6; references `pi_components` and `pi_dependencies` tables with specific row count expectations; this is historical UAT evidence, not a current test |

---

### docs/setup/ (1 file)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| claude-code-hooks.md | setup | CURRENT | ALIGN | N/A | N/A | ALIGN | **ALIGN** | Describes `.dream-studio-project` marker explicitly; attribution_status table (fully_attributed, partial, orphan) based on marker lookup; marker authority documented here; deferred items noted (auto-install, session capture) |

---

### docs/authoring/ (1 file)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| skills.md | authoring | CURRENT | ALIGN | N/A | N/A | N/A | NO | Modified 2026-05-19; describes `canonical/skills/` path; pack keys and SKILL.md requirements accurate |

---

### docs/schema/ (1 file)

| Doc | Category | State | I1-SQLite | I2-SecIntake | I3-SecGate | I4-Events | I5-Marker | Notes |
|-----|----------|-------|-----------|--------------|------------|-----------|-----------|-------|
| README.md | database | CURRENT | ALIGN | N/A | N/A | ALIGN | NO | Modified 2026-05-19; 54 migrations stated; table glossary covers canonical_events, ds_projects, ds_work_orders, execution_events, and others; accurate |

---

### docs/demo/sanitized/ (5 files)

| Doc | Category | State | Notes |
|-----|----------|-------|-------|
| README.md | demo | CURRENT | sanitized demo packet; status public_demo_ready |
| 5-minute-script.md | demo | CURRENT | goal → milestone → Work Order → validate sequence |
| 15-minute-technical-walkthrough.md | demo | CURRENT | technical walkthrough; observe/assist/operate modes |
| fallback-plan.md | demo | CURRENT | demo fallback procedures |
| rehearsal-report.md | demo | CURRENT | rehearsal evidence |

---

### docs/pilot/company-internal-pilot/ (4 files)

| Doc | Category | State | Notes |
|-----|----------|-------|-------|
| README.md | pilot | CURRENT | status: pilot_packet_ready; analytics_only_observe mode |
| executive-summary.md | pilot | CURRENT | non-invasive; no push/deploy/cloud required |
| feedback-template.md | pilot | CURRENT | structured feedback form |
| technical-appendix.md | pilot | CURRENT | technical setup instructions |

---

### docs/publication/ (4 files)

| Doc | Category | State | Notes |
|-----|----------|-------|-------|
| docs_publication_readiness_report.md | publication | CURRENT | readiness evidence artifact |
| final_history_rewrite_branch_classification_report.md | publication | CURRENT | history rewrite classification report |
| history_rewrite_force_push_plan.md | publication | CURRENT | history rewrite plan |
| history_rewrite_rehearsal_report.md | publication | CURRENT | rehearsal evidence |

---

## Special Focus: Brownfield Onboarding Documentation (Intent #2)

### What exists

**`canonical/workflows/studio-onboard.yaml`** is the only concrete documentation of the brownfield onboarding workflow. It is a workflow YAML, not a written doc. The workflow covers:
- User config setup (config.json)
- Environment discovery
- Gap analysis
- Onboarding fix planning with operator gates

**`docs/operations/github-repo-intake-evaluation.md`** documents a related but distinct capability: evaluating an external GitHub repo before adopting code. The intake workflow explicitly includes a security and supply-chain review step that routes to `security_review_required`, partially satisfying Intent #2 for GitHub targets.

**`docs/contracts/security-by-default-development-lifecycle-gate.md`** states: "Full applicable 47-control review is required at: **project intake**" — this is the clearest statement of security during onboarding.

### What is missing

1. **No dedicated operations doc for brownfield onboarding.** There is no `docs/operations/brownfield-onboarding.md` or equivalent. The `studio-onboard.yaml` workflow is the only source of procedural truth, and it lives in `canonical/workflows/`, not `docs/`.

2. **`studio-onboard.yaml` has no corresponding doc page.** There is a `docs/WORKFLOWS.md` with a workflow type table, but it does not include `studio-onboard`. There is no doc that explains what `studio-onboard` does in prose, what its security gate expectations are, or what findings it stores.

3. **The security-during-intake expectation (Intent #2) lives in the security lifecycle gate contract**, but this is a contract doc, not an operations doc. An operator following the operations docs would not find a clear path from "I want to onboard a brownfield project" to "security audit runs and findings are stored in SQLite."

4. **No doc describes the finding storage path for intake-phase security work.** `security-by-default-development-lifecycle-gate.md` says findings must include project, file, line, severity, control id, status, evidence, remediation path — but does not document which CLI command runs the intake scan or where findings land in the DB.

---

## Special Focus: Security Gate Documentation (Intent #3)

### Docs that describe security as a required lifecycle step

| Doc | Strength of gate description | Where |
|-----|------------------------------|-------|
| `contracts/security-by-default-development-lifecycle-gate.md` | Strong — explicit lifecycle policy; lists all required full-review trigger points including project intake, release, publication, deployment | `docs/contracts/` |
| `contracts/secure-production-readiness-gate.md` | Strong — describes 9 SQLite tables for readiness records; gate is non-executing classification | `docs/contracts/` |
| `operations/product-readiness.md` | Moderate — mentions security/readiness classification in posture check | `docs/operations/` |
| `operations/long-run-multisession-operational-validation.md` | Moderate — security/readiness classification is one required cycle | `docs/operations/` |
| `operations/external-project-validation-pipeline.md` | Moderate — step 6 is "classify security/readiness scope" | `docs/operations/` |
| `product/dream-studio-prd.md` | Moderate — "track secure production readiness separately" is a stated goal | `docs/product/` |
| `product/dream-studio-definition-of-done.md` | Moderate — Database Authority Done section; does not explicitly call out security gate as done criteria |
| `contracts/workflow-contract.md` | **Absent** — does not reference security; workflows may implement a security gate but the contract does not require it |
| `operations/work-orders.md` | **Absent** — no security gate requirement in Work Orders operations doc |

### Gap: Production readiness doc does not reference security gate by name

`docs/operations/product-readiness.md` describes a Phase 15 evidence path but does not name `security-by-default-development-lifecycle-gate.md` as a required input. The security lifecycle gate and secure production readiness gate are separate contracts that are connected in `secure-production-readiness-gate.md`, but this connection is not explained in the operations layer.

### Gap: workflow-contract.md does not mention security

The workflow contract (`docs/contracts/workflow-contract.md`) defines required fields for workflows but does not include a security gate requirement or security classification obligation. A workflow author following the contract could create a workflow with no security consideration and be technically compliant with the contract.

---

## Special Focus: File-Based State Documentation (Intent #1)

### Docs that describe file-based stores as canonical (active divergence from Intent #1)

| Doc | File-based state described as canonical | Scope |
|-----|-----------------------------------------|-------|
| `contracts/state-contract.md` | `~/.dream-studio/state/workflows.json` and `workflow-checkpoint.json` listed as canonical tables for workflow state | Active workflow JSON is explicitly transient/canonical |
| `contracts/work-ledger-contract.md` | Work Ledger is explicitly file-backed only; DB integration deferred | Phase 16A |
| `contracts/work-order-contract.md` | `storage_class: file_backed` is required in Phase 16 | Phase 16A |
| `contracts/approval-contract.md` | Phase 16 approval records are file-backed only | Phase 16A |
| `contracts/eval-artifact-contract.md` | Phase 16 eval artifacts are file-backed only | Phase 16A |
| `contracts/work-result-contract.md` | Work Results are file-backed local evidence | Phase 16A |
| `operations/work-orders.md` | Work Orders described as "file-backed only" in File-Backed Posture section | Operations layer |

### Docs that describe migration path FROM file TO SQLite

| Doc | Migration description |
|-----|-----------------------|
| `contracts/work-ledger-contract.md` | Deferred DB/event integration section lists conditions for migration |
| `contracts/state-contract.md` | States: "Active workflow JSON is transient runtime state. Terminal workflow state is archived locally; projections are rebuildable summaries" — implies future archival |
| `docs/WORKFLOW_RUNTIME.md` | States active workflow JSON is transient runtime state |

### Observation

The Phase 16A "file-backed only" contracts represent intentional architectural scoping, not documentation rot. They acknowledge the current state and explicitly defer DB integration. The stated Intent #1 ("file-based state is v1 rot") describes the direction, not the current position. The documentation accurately reflects where Phase 16A actually is.

---

## Special Focus: Contract vs Implementation Gap

### event-contract.md

- **Contract claims:** `core.events.emitter.emit_event()` is the authoritative emit path; `canonical_events` table is the authoritative persisted stream; `validation_failures` and `activity_log` are companion tables; `execution_event_links` is a relationship table.
- **Implementation check:** `event-store.md` (modified 2026-05-22) confirms this is accurate; fabricators removed in TA5; dashboard now reads from `canonical_events` directly.
- **Gap:** None observed. Contract and implementation aligned.

### hook-contract.md

- **Contract claims:** Active hook implementations live under `runtime/hooks`; retired root hook library path must not be recreated.
- **Implementation check:** `HOOK_RUNTIME.md` confirms canonical location is `runtime/hooks/{pack}/`; lists three orphaned handlers not reachable via dispatchers (`on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py`).
- **Gap:** Three orphaned handlers exist that the hook-contract says should be reachable. The orphans are noted in HOOK_RUNTIME.md but not in hook-contract.md. Contract is silent on their disposition.

### skill-contract.md

- **Contract claims:** Skills use `ds-<slug>` identifier form; skills live in canonical skill paths; skills must not own canonical state.
- **Implementation check:** `authoring/skills.md` confirms `canonical/skills/` as the location; `packs.yaml` as the pack registry.
- **Gap:** The skill-contract does not mention the separation of SKILL.md (instructions) from config.yml (metadata) that was introduced in the YAML mode config work. The contract's "Required Fields" section includes fields that now live in `config.yml`, not `SKILL.md`. The contract was last modified 2026-05-14; the YAML mode config work is in the CHANGELOG as a completed change. Minor drift.

### workflow-contract.md

- **Contract claims:** Workflow state must be persisted only by the owner named in the state contract or by an explicitly contracted workflow runner. Workflow templates remain stateless.
- **Implementation check:** `state-contract.md` names `control.execution.workflow.state` as the canonical owner for active workflows and `~/.dream-studio/state/workflows.json` as the canonical file.
- **Gap:** Workflow-contract.md does not reference the state-contract for the ownership chain. A reader of the workflow-contract alone would not know where state persists. Moderate documentation gap — the contracts are consistent but not cross-linked.

### state-contract.md

- **Contract claims:** Workflow state canonical owner is listed; ownership matrix covers all state categories.
- **Implementation check:** The state-contract's workflow state row lists `workflows.json` and `workflow-checkpoint.json` as canonical files. WORKFLOW_RUNTIME.md confirms this.
- **Gap:** The state-contract ownership matrix lists several tables with "no active writer in Phase 11C" (e.g., `risk_register`, `risk_mitigations`, `sec_cve_matches`, `sec_manual_reviews`, `sec_hook_checks`, `guardrail_rules_audit`). It is unclear if these tables now have active writers as of Phase 18+ work. The contract was last modified 2026-05-14 but these reserved entries may be stale.

### security-by-default-development-lifecycle-gate.md

- **Contract claims:** Full applicable 47-control review required at project intake; findings must include specific fields; lifecycle gate is non-executing.
- **Implementation check:** The security lifecycle gate is referenced in `independent-configuration-model.md` as having a `core.security.lifecycle` module. The contract describes it as "non-executing" — it classifies and routes but does not run scans.
- **Gap:** The contract says "full applicable 47-control review is required at project intake" but there is no CLI command documented anywhere in the operations docs that an operator would run to perform this intake review. The gate is policy, not a command. How intake review gets triggered operationally is undocumented.

---

## Findings

### F1 — Brownfield Onboarding Has No Dedicated Documentation
`studio-onboard.yaml` is the only source of procedural truth for the brownfield onboarding workflow. It has no companion doc page, no operations guide entry, and no explicit connection to the security intake gate. An operator looking at `docs/operations/` would find no document explaining what to do when onboarding an existing project.

### F2 — Security Intake Gate is Policy Without Operational Steps
`security-by-default-development-lifecycle-gate.md` states that security review is required at project intake, but no operations doc provides the steps: what command to run, what evidence to capture, what table the findings land in. The contract is aspirational policy documentation without an operational companion.

### F3 — Phase 16A Contracts Describe File-Based State as Canonical
Six contracts (approval-contract, eval-artifact-contract, work-ledger-contract, work-order-contract, work-result-contract, state-contract workflow row) explicitly describe file-based stores as canonical or defer SQLite integration. This is intentional Phase 16A scoping, but it creates a visible gap between Intent #1 ("SQLite-first") and the current contract layer. The contracts correctly document the current state; the intent describes the target state.

### F4 — `copilot-setup.md` and `cursor-setup.md` Reference a Missing Source Path
Both docs reference `.marketplace/adapters/` which does not exist in the repository. The source adapter files they point to for user installation are absent. These docs cannot be followed as written.

### F5 — Orphaned Hook Handlers Not Addressed in hook-contract.md
Three handlers (`on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py`) are identified as orphaned in `HOOK_RUNTIME.md` but the hook-contract does not address their status or required disposition. The contract does not say whether orphaned handlers are permitted or should be removed.

### F6 — skill-contract.md Does Not Reflect SKILL.md/config.yml Split
The skill-contract's Required Fields section includes metadata fields that were migrated to `config.yml` as part of the YAML mode config work. A skill author reading only the skill-contract would not know that `model_tier`, `version`, and other fields now live in `config.yml` rather than SKILL.md frontmatter.

### F7 — demo-script.md and design-skills-guide.md Use Pre-Consolidation Terminology
`demo-script.md` (2026-05-14) and `design-skills-guide.md` (2026-05-14) use terminology and skill names from before the v0.11.0 pack consolidation (2026-04-30). `design-skills-guide.md` references `huashu-design` which is not a canonical skill name. `demo-script.md` likely references old `ds:think` syntax rather than pack-based `ds-core think` routing.

### F8 — security-skills-redundancy-analysis.md is Pre-Consolidation Historical Evidence
This doc was a pre-consolidation analysis (2026-04-26) of 8 individual skill SKILL.md files. Post-consolidation, skills are in packs with modes subdirectories. The doc describes an architecture that no longer exists. Its current purpose is unclear — it is not labeled as historical.

### F9 — coverage-report-phase6.md and UAT-Phase6-Checklist.md are Unarchived Historical Evidence
These docs reflect Phase 6 state from 2026-05-06. They report specific table row count expectations (`pi_components` 3,408+, `pi_dependencies` 83,272+) that are historical snapshots, not current validation targets. They are not labeled as archived evidence.

### F10 — Three Contracts Have Potentially Stale "No Active Writer" Rows
`state-contract.md` (Phase 7B) and `governance-contract.md` (Phase 11C) both list tables with "no active writer in Phase 11C." As of Phase 18+, some of these (e.g., `sec_cve_matches`, `sec_manual_reviews`, `sec_hook_checks`) may have been wired to active writers through later work. The contracts were last modified 2026-05-14 but may not reflect writer additions from subsequent migrations.

### F11 — workflow-contract.md Contains No Security Requirement
A workflow can be fully compliant with the workflow-contract without any security consideration. Given Intent #3 (security as SDLC gate), the workflow contract is silent on whether workflows should require or integrate with the security lifecycle gate.

### F12 — quickstart.md References Legacy CLI Pattern
`quickstart.md` references `claude code link .` and test commands against `test_actual_dashboard_telemetry_routes.py` and `test_frontend_dashboard_telemetry_surface.py`. These may not be current CLI syntax or test file names. The quickstart was not updated after the v0.11.0 changes.

---

## Intent Divergence Summary

| Intent | Docs that Align | Docs that Diverge | Verdict |
|--------|-----------------|-------------------|---------|
| I1 — SQLite-first authority | ARCHITECTURE.md, DATABASE.md, state-contract (non-workflow state), all operations docs | approval-contract, eval-artifact-contract, work-ledger-contract, work-order-contract, work-result-contract, state-contract (workflow row) | **Phase tension**: Phase 16A explicitly phases in file-based state; Intent #1 names the target; the contracts correctly document Phase 16A as current position |
| I2 — Security during brownfield onboarding | security-by-default-lifecycle-gate (policy), github-repo-intake (partially) | No operations doc, no studio-onboard companion doc, no CLI command documented | **Underdocumented**: policy exists in contracts layer; operations layer has a gap |
| I3 — Security as SDLC gate | security-by-default-lifecycle-gate, secure-production-readiness-gate, dream-studio-prd | workflow-contract (silent), work-orders.md (silent) | **Partial**: gate policy is well-documented; enforcement path in workflows is undocumented |
| I4 — Canonical events as spine | event-contract, event-store.md, state-contract, projection-contract, task-attribution-and-outcomes | None | **Well-aligned**: most current docs explicitly reference canonical_events |
| I5 — Marker file authority | setup/claude-code-hooks.md, event-store.md | Most docs have no mention (not divergence — just not applicable) | **Single-point documentation**: marker file authority is documented only in claude-code-hooks.md; no operations overview doc covers it |

---

## Open Questions

1. **State-contract "no active writer" rows:** Are `sec_cve_matches`, `sec_manual_reviews`, `sec_hook_checks`, `risk_register`, and `guardrail_rules_audit` still without active writers? If later migrations added writers, the state-contract and governance-contract need updates.

2. **`skill-contract.md` field location:** Which Required Fields are now expected in `config.yml` vs `SKILL.md`? The contract should be clarified so skill authors know where to put each field.

3. **`studio-onboard.yaml` security gate:** Does the studio-onboard workflow currently trigger any security classification step? The YAML's node list does not include a security step. Is this intentional (security runs separately) or a gap?

4. **Marker file drift detection:** `setup/claude-code-hooks.md` notes that the "Marker/DB reconciliation" auditor workstream is deferred. Is there documentation planned for the reconciliation process when markers and `ds_projects` diverge?

5. **`.marketplace/adapters/` directory:** Was this intentionally removed or was it never created? `copilot-setup.md` and `cursor-setup.md` both depend on it. Should these docs be updated to point to wherever copilot/cursor adapter files currently live?

6. **`on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py`:** Are these orphaned handlers scheduled for removal, or do they serve a purpose that hasn't been wired up yet? Their presence without wiring is observable technical debt, but whether the docs should acknowledge or ignore them is unclear.

7. **Phase 16A file-backed Work Orders vs Intent #1:** Is there a documented Phase 17 or later that describes the migration from `storage_class: file_backed` to SQLite-backed Work Orders? The work-ledger-contract defers this but does not name when or what the preconditions are.
