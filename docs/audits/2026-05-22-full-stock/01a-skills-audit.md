# Pass 1a — Skills Audit
*Phase 1 analysis | 2026-05-22*
*Supplements: Phase 0 inventory in 00-mechanical-inventory.md, 00b-mechanical-inventory-depth.md, 00c-mechanical-inventory-final.md*

---

## Stated Architectural Intents

These are the evaluation criteria applied to every skill below.

1. **SQLite-first authority** — All runtime STATE must be SQLite-backed. File-based state is v1 rot.
2. **Security audit during brownfield onboarding** — Security skills run during project intake; findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** — Greenfield projects must pass a security audit before going live.
4. **Canonical events as the spine** — All state changes flow through canonical_events. Direct table writes without event emission are anomalies.
5. **Marker file authority for attribution** — .dream-studio-project markers are identity source; ds_projects is metadata storage.

---

## Skills Inventory and Assessment

### Canonical Skills (11)

The canonical skill set as defined in `canonical/skills/` and declared in `packs.yaml`:

| Canonical skill dir | Pack name in packs.yaml | Installed in ~/.claude/skills/ |
|---|---|---|
| analyze | analyze | YES (ds-analyze) |
| core | core | YES (ds-core) |
| domains | domains | YES (ds-domains) |
| ds-bootstrap | (passive — not in packs.yaml) | YES (ds-bootstrap) |
| ds-milestone | ds-milestone | NO (function-backed only) |
| ds-project | ds-project | YES (ds-project) |
| ds-workorder | ds-workorder | NO (function-backed only) |
| quality | quality | YES (ds-quality) |
| security | security | YES (ds-security) |
| setup | setup | YES (ds-setup) |
| workflow | meta (packs.yaml maps meta.skill_path → canonical/skills/workflow) | YES (ds-workflow) |

---

#### canonical/skills/analyze (ds-analyze)
- **Modes:** multi, domain-re, repo, intelligence
- **Purpose:** Multi-perspective analysis engine dispatching to specialist sub-modes for idea evaluation, domain real estate analysis, repository pattern analysis, and codebase health intelligence.
- **Current state:** Active (installed, routed in both CLAUDE.md routing tables)
- **Evidence of use:** Zero `skill.invoked` events for ds-analyze or analyze:* specifiers in the 21 observed invocations. No entries in skill_invocations table for this skill. skill-usage.jsonl contains only three "unknown" entries.
- **Intent 1 (SQLite):** Partial — intelligence mode calls `get_project_state` (SQLite read) per ds-project integration. multi/domain-re/repo modes produce outputs as artifacts; no observed SQLite writes from this skill. No tables owned by this pack in module_contracts.
- **Intent 2 (Security intake):** N/A — analyze is not a security skill. ds-project scope mode explicitly references `analyze:intelligence` as a brownfield intake step, not a security check.
- **Intent 3 (Security gate):** N/A
- **Intent 4 (Events):** No direct evidence of canonical event emission from this skill's own execution. The `on-skill-metrics` hook fires on PostToolUse/Skill and would record `execution.completed` via bridge. skill.invoked is emitted by `core.skills.invocation.record_skill_invocation` when the CLI `skill invoke` path is used — not observed in canonical_events for ds-analyze.
- **Intent 5 (Marker):** N/A — analyze does not reference .dream-studio-project markers.
- **Notes:** Byte delta between canonical and installed (+24 bytes) is the smallest in the set. Four sub-modes fully documented with SKILL.md files and supplementary reference docs. intelligence mode has a reference directory with error-handling, health-interpretation, and output-format guides. The skill has a `repo-analyzer.py` and test files (`test_analyzer.py`, `test_domains.py`, `test_remaining_domains.py`) co-located in the canonical directory — unusual for canonical skills, which are otherwise documentation only.

---

#### canonical/skills/core (ds-core)
- **Modes:** think, plan, build, review, verify, ship, handoff, recap, explain
- **Purpose:** Full build lifecycle orchestration covering the span from ideation through deployment, including subagent dispatch, quality gates, and session handoff.
- **Current state:** Active — the most-used skill by observed invocation count.
- **Evidence of use:** 19 of 21 `skill.invoked` events are for core modes. `core:build` observed 5 times (2026-05-17 and 2026-05-18). `core:plan` observed 14 times — 13 of which occurred in a ~3-second burst on 2026-05-20T21:55:47–50 (likely a workflow runner emitting multiple events for the same node dispatch). First invocation: 2026-05-17T23:47:57. Last invocation: 2026-05-20T21:55:50.
- **Intent 1 (SQLite):** Partial — build and plan modes reference `start_work_order`, `mark_task_done` (SQLite writes via core.work_orders.*). ship mode references gate checks. The skill itself does not own any SQLite tables. State artifacts (spec.md, plan artifacts) are file-backed under `.planning/`.
- **Intent 2 (Security intake):** N/A
- **Intent 3 (Security gate):** ship mode is defined as a pre-deploy gate. The workflow contract for ship references `security_scan` as a post-build gate in the `api_endpoint`, `authentication`, `saas_feature`, `data_pipeline`, `deployment`, `infrastructure` work order types. Whether ship mode invokes ds-security explicitly or relies on the `on-security-scan` hook for advisory coverage is not determinable from SKILL.md alone.
- **Intent 4 (Events):** `skill.invoked` events are emitted via `core.skills.invocation.record_skill_invocation` at CLI invocation time. The 19 observed events confirm this path fires. The `on-skill-complete` hook also calls `studio_db.log_skill_execution` and `control.skills.calibration.record_outcome` post-invocation. Two separate write paths exist for skill execution records.
- **Intent 5 (Marker):** `record_skill_invocation` attempts to resolve project_id from marker files as fallback when work_order_id is not supplied. This is consistent with Intent 5.
- **Notes:** The 13-event burst of `core:plan` events at 2026-05-20T21:55:47 has all events with `work_order_id: null` and `target: null`, suggesting the workflow runner was emitting invocations without context linkage. The installed skill is 74 bytes larger than canonical — the largest absolute delta among mode-dispatching skills.

---

#### canonical/skills/domains (ds-domains)
- **Modes:** game-dev, saas-build, mcp-build, dashboard-dev, client-work, design, website, fullstack
- **Purpose:** Stack-specific and domain-specialist build orchestration covering game development, SaaS, MCP servers, dashboards, client deliverables, design artifacts, websites, and full-stack apps.
- **Current state:** Active (installed, routed). website and fullstack modes are also routed as top-level packs (`ds-website`, `ds-fullstack`) via `skill_path` overrides in packs.yaml — so these modes have dual routing.
- **Evidence of use:** Zero `skill.invoked` events for ds-domains or any domains:* specifier. No skill_invocations rows.
- **Intent 1 (SQLite):** dashboard-dev mode references the dashboard API and data sources. The skill itself has no owned tables in module_contracts. client-work, website, fullstack modes produce file artifacts. No observed SQLite writes from this skill.
- **Intent 2 (Security intake):** N/A
- **Intent 3 (Security gate):** website and fullstack modes are referenced as build executors in ds_work_order_types (ui_page uses `website:page`, ui_component uses `fullstack:frontend`). Post-build gates for ui_page and ui_component are `design_critique|anti_slop_passed` — no security gate for these types. api_endpoint uses `fullstack:backend` with `security_scan` as post-build gate. fullstack:secure mode exists for security hardening within the fullstack build flow.
- **Intent 4 (Events):** Same hook path as other skills. No observed emissions in canonical_events.
- **Intent 5 (Marker):** N/A
- **Notes:** Packs.yaml registers fullstack and website as top-level packs with their own `skill_path` overrides pointing into `canonical/skills/domains/modes/website` and `canonical/skills/domains/modes/fullstack`. This means ds-website and ds-fullstack SKILL.md files are inside domains/modes/ — not standalone canonical skill directories. The domains canonical directory contains sub-skill infrastructure: design-systems (5 design systems), powerbi references, data-visualization references, game rules (7 files), and domain-specific data directories.

---

#### canonical/skills/ds-bootstrap
- **Modes:** None (passive context, not user-invocable)
- **Purpose:** Passive bootstrap skill that installs context into the host AI tool's awareness that Dream Studio is present; instructs the AI to prefer DS skills and workflows.
- **Current state:** Active (installed passively at `~/.claude/skills/ds-bootstrap/SKILL.md`)
- **Evidence of use:** Not invocable via Skill tool. No `skill.invoked` events. No skill_invocations rows. Presence is architectural — the SKILL.md is read as context.
- **Intent 1 (SQLite):** N/A — no state, advisory only.
- **Intent 2 (Security intake):** N/A
- **Intent 3 (Security gate):** N/A
- **Intent 4 (Events):** N/A — not a dispatched skill.
- **Intent 5 (Marker):** N/A
- **Notes:** SKILL.md explicitly states it does not appear in packs.yaml or the Skill-tool routing table. It uses no directives ("MUST", "MUST NOT") — advisory scope only. The SKILL.md is installed into canonical/ in the repo and unconditionally included in all integration packs by the provisioner. The installed version is 54 bytes larger than canonical (+54 — second-largest relative delta by percentage).

---

#### canonical/skills/ds-milestone
- **Modes:** status, close
- **Purpose:** Function-backed skill that wraps `core.milestones.*` for reading milestone status and executing milestone close with four gate checks (design audit, security audit, hardening, Core Web Vitals for UI milestones).
- **Current state:** Active (callable via skill routing) but NOT installed as a standalone `~/.claude/skills/` file. Function-backed only.
- **Evidence of use:** Zero `skill.invoked` events for ds-milestone. No skill_invocations rows.
- **Intent 1 (SQLite):** Aligned — explicitly designed as a SQLite authority wrapper. SKILL.md states "The Dream Studio SQLite authority is the source of truth for milestone state. This pack does not narrate milestone status from session memory; every mode calls a query or close function." Status mode wraps `core.milestones.queries.get_milestone_status`. Close mode wraps `core.milestones.close.close_milestone`.
- **Intent 2 (Security intake):** N/A
- **Intent 3 (Security gate):** Partial alignment — close mode runs a "security audit" gate check as one of its four pre-close gates. However, this gate is not defined as calling ds-security explicitly. Whether the gate check is a query against `security_findings` table or an invocation of ds-security is not determinable from SKILL.md alone.
- **Intent 4 (Events):** SKILL.md references calling `core.milestones.*` functions. Whether those functions emit canonical events is not determinable from this skill's definition.
- **Intent 5 (Marker):** N/A — function-backed, no marker file references.
- **Notes:** This is one of two function-backed skills (along with ds-workorder) that are NOT installed as standalone skill files in `~/.claude/skills/`. They are registered in packs.yaml as `ds-milestone` and `ds-workorder` packs with their own mode tables. The 1,881-byte canonical SKILL.md is entirely consumed by function invocation contracts and display rules.

---

#### canonical/skills/ds-project
- **Modes:** scope, resume, brief, manage
- **Purpose:** Project lifecycle skill covering scoped project creation (scope), session orientation and work order start (resume), design brief management (brief), and project portfolio operations (manage).
- **Current state:** Active — the only non-core skill with a confirmed `skill.invoked` event.
- **Evidence of use:** 1 `skill.invoked` event for `ds-project:scope` at 2026-05-17T01:19:44. This is the earliest skill invocation in the DB. The single row in `skill_invocations` table has `skill_id: "unknown"` and `purpose: "session skill telemetry"` — the metadata does not confirm which skill, only that a session-level telemetry record was created.
- **Intent 1 (SQLite):** Strong alignment — scope mode calls `register_project`, `create_milestone`, `create_work_order`, `create_task` (all SQLite writes). resume mode calls `get_project_state` (SQLite read). Both modes explicitly instruct the AI to use the returned dict and not narrate from session memory.
- **Intent 2 (Security intake):** Partial alignment with a gap. scope mode references `analyze:intelligence` as a brownfield intake prerequisite ("Run `ds-analyze intelligence: <path>` and come back with output"). No security audit is referenced during intake for either brownfield or greenfield projects. The brownfield check is a codebase health/intelligence check, not a security scan.
- **Intent 3 (Security gate):** N/A at the scope level. The work order types embedded in scope mode reference security gates in post-build phase, not during scoping.
- **Intent 4 (Events):** scope mode Phase 5 calls core.* mutation functions — whether those emit canonical events is in the function implementations, not the SKILL.md. The `skill.invoked` event for this skill was observed in canonical_events (event at 2026-05-17T01:19:44).
- **Intent 5 (Marker):** Not observed in SKILL.md. The `record_skill_invocation` function in `core.skills.invocation` has marker file fallback for project_id resolution — this is a CLI-layer behavior, not defined in the skill itself.
- **Notes:** ds-project is the largest skill by byte count at 19,063 bytes (canonical) / 19,287 bytes (installed). The 224-byte delta is the largest absolute delta in the set. The SKILL.md is fully self-contained — scope mode (Phases 1–5), resume mode, brief (delegated to modes/brief/SKILL.md), and manage (delegated to modes/manage/SKILL.md). The `.planning/PROJECT.md` artifact written in Phase 5 is a file-backed artifact — divergence from Intent 1 for human-readable output specifically.

---

#### canonical/skills/ds-workorder
- **Modes:** start, execute, close, block, status
- **Purpose:** Function-backed skill that wraps `core.work_orders.*` for work order lifecycle management; all modes call named mutation or query functions and surface returned dicts.
- **Current state:** Active (callable) but NOT installed as a standalone `~/.claude/skills/` file. Function-backed only.
- **Evidence of use:** Zero `skill.invoked` events for ds-workorder. No skill_invocations rows for this skill specifically. 15 `work_order.started` events in canonical_events confirm work orders have been started — but whether via this skill or via CLI direct calls is not determinable from events alone.
- **Intent 1 (SQLite):** Strong alignment — SKILL.md explicitly states "The Dream Studio source-of-truth is the SQLite authority. This pack does not reason about work-order state from session memory." All five modes wrap specific `core.work_orders.*` functions.
- **Intent 2 (Security intake):** N/A
- **Intent 3 (Security gate):** close mode wraps `check_close_gates` — the post-build gates for typed work orders include `security_scan` for api_endpoint, authentication, saas_feature, data_pipeline, deployment, and infrastructure types. Whether `check_close_gates` queries the security_findings table or invokes ds-security is not determinable from SKILL.md alone.
- **Intent 4 (Events):** The wrapped functions (`core.work_orders.*`) emit events — `work_order.started` (15 events), `work_order.closed` (4 events), `work_order.created` (14 events) are all observed in canonical_events. Events are emitted by the function layer, not the skill itself.
- **Intent 5 (Marker):** N/A — function-backed.
- **Notes:** The 2,264-byte canonical SKILL.md is entirely composed of function invocation contracts and operator-display rules. The skill's only specification is which core.* function each mode calls. No behavioral logic is defined in the skill layer itself.

---

#### canonical/skills/quality (ds-quality)
- **Modes (canonical SKILL.md):** debug, polish, harden, secure, structure-audit, learn, coach
- **Purpose:** Code quality and learning discipline covering debugging, UI polish, security hardening, security review, structure auditing, lesson capture, and coaching.
- **Current state:** Active (installed). Mode name discrepancy: canonical SKILL.md lists mode `secure` pointing to `modes/secure/SKILL.md`, but installed pack and packs.yaml register the mode as `pr-security-scan`. The routing tables in CLAUDE.md reference `pr-security-scan`, not `secure`.
- **Evidence of use:** Zero `skill.invoked` events for ds-quality or quality:* specifiers. No skill_invocations rows.
- **Intent 1 (SQLite):** Partial — harden and structure-audit modes reference the codebase/files. coach mode may read project state. No tables owned by quality in module_contracts. The `on-security-scan` hook (quality pack) does not write to SQLite — it prints advisory warnings to stdout.
- **Intent 2 (Security intake):** N/A
- **Intent 3 (Security gate):** `pr-security-scan` mode is the security review gate used in workflow nodes. It appears in three canonical workflows: comprehensive-review.yaml (node `review-security`), idea-to-pr.yaml (nodes `review-security` and `triage-security`), and project-audit.yaml. This is Intent 3 alignment via workflow integration — but the mode name mismatch (canonical says `secure`, routing says `pr-security-scan`) creates a surface-level navigation ambiguity.
- **Intent 4 (Events):** Same hook path as other skills. `on-security-scan` hook is advisory-only (stdout warnings), no DB writes. No observed emissions in canonical_events for quality skill invocations.
- **Intent 5 (Marker):** N/A
- **Notes:** The canonical SKILL.md references `modes/secure/SKILL.md` but the installed version and packs.yaml name this `pr-security-scan`. This is a documented discrepancy noted in Phase 0b. The quality pack's `on-security-scan` hook fires on every Edit/Write via the `on-edit-dispatch` chain — this is the passive security coverage layer, separate from the explicit `pr-security-scan` skill mode. Two co-existing security coverage mechanisms: (a) the lightweight advisory hook on every write, and (b) the explicit pr-security-scan mode invoked in workflows.

---

#### canonical/skills/security (ds-security)
- **Modes:** scan, review, dast, binary-scan, mitigate, comply, netcompat, dashboard
- **Purpose:** Enterprise security analysis covering GitHub Actions scan orchestration, code-level vulnerability review, DAST web testing, binary analysis, mitigation generation, compliance mapping, network compatibility checking, and Power BI dashboard dataset generation.
- **Current state:** Active (installed, routed). Zero observed invocations. All security tables in studio.db have 0 rows (security_findings, sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks, hook_findings).
- **Evidence of use:** Zero `skill.invoked` events for ds-security or security:* specifiers. No skill_invocations rows. All security-specific tables empty.
- **Intent 1 (SQLite):** Partial — the DB schema has extensive security tables (security_findings, sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks, vw_security_summary), all with 0 rows. The scan mode stores results in the filesystem under `~/.dream-studio/security/scans/{client}/{repo}/{date}/` — file-backed storage, not SQLite. The scan SKILL.md references writing `scan-meta.json` to a directory tree. The dashboard mode reads from file-backed scan results to produce Power BI datasets. SQLite tables exist but are unpopulated; file system is the live storage path per SKILL.md specification.
- **Intent 2 (Security intake):** NOT aligned. No ds-security mode is wired into any project intake flow. The studio-onboard.yaml workflow does not invoke ds-security. ds-project scope mode references only `analyze:intelligence` for brownfield intake, not a security scan.
- **Intent 3 (Security gate):** NOT directly wired as a gate. The `security_scan` post-build gate defined in ds_work_order_types (for api_endpoint, authentication, saas_feature, data_pipeline, deployment, infrastructure) is a gate name but its resolver is not confirmed to invoke ds-security. The canonical workflows reference `pr-security-scan` (a ds-quality mode) in their security review nodes, not `security:scan` or `security:review`. The security-audit.yaml workflow exists and orchestrates a full client security pipeline, but it is an on-demand workflow, not an automatically triggered SDLC gate.
- **Intent 4 (Events):** The emitter infra exists (on-skill-metrics, on-skill-complete hooks fire on Skill tool use). The security SKILL.md modes produce file artifacts, not SQLite records. No security-namespace canonical events in the 1,835 observed events.
- **Intent 5 (Marker):** N/A — security modes are client/org-level operations, not project-attribution operations.
- **Notes (detailed analysis in Special Focus section below).**

---

#### canonical/skills/setup (ds-setup)
- **Modes:** wizard, status, jit
- **Purpose:** Platform first-run experience providing interactive tool setup (wizard), tool status reporting (status), and just-in-time tool installation prompts triggered by other skills (jit).
- **Current state:** Active (installed). wizard mode was executed during initial studio-onboard workflow (setup was one of the studio-onboard nodes per the 2026-05-18 run).
- **Evidence of use:** Zero `skill.invoked` events for ds-setup. The studio-onboard run node records show the workflow completed 13 nodes; setup-related work was part of that workflow but no discrete skill.invoked events were emitted for setup.
- **Intent 1 (SQLite):** Partial — wizard mode writes tool states to `.dream-studio/setup-prefs.json` (file-backed). status mode reads from `.dream-studio/setup-prefs.json`. The 8,028-byte canonical SKILL.md makes no reference to SQLite reads or writes. Setup state is file-backed, not SQLite-backed.
- **Intent 2 (Security intake):** N/A
- **Intent 3 (Security gate):** N/A
- **Intent 4 (Events):** No observed canonical events for setup. setup-prefs.json writes are not emitted as events.
- **Intent 5 (Marker):** N/A
- **Notes:** The jit mode is an internal protocol — invoked by other skills programmatically when they detect a missing tool. The SKILL.md documents a `promptForSetupPath()` pseudocode contract that other skills call. This is a skill-to-skill dependency that has no event trace. ds-setup has the second-largest canonical SKILL.md at 8,028 bytes, primarily due to the full inline documentation of all three modes in a single file (unlike other skills that delegate to modes/*/SKILL.md).

---

#### canonical/skills/workflow (ds-workflow)
- **Modes:** No user-invocable modes. Invoked by workflow name from canonical/workflows/.
- **Purpose:** YAML pipeline orchestration skill that discovers, validates, and executes named workflow templates from `canonical/workflows/` using the maintained workflow runner.
- **Current state:** Active (installed as ds-workflow). Two workflow runs recorded in DB (both studio-onboard runs from 2026-05-18).
- **Evidence of use:** Zero `skill.invoked` events for ds-workflow specifically. 2 `workflow_invocations` rows and 2 `workflow.completed`/`workflow.node.completed` event series in canonical_events confirm workflow execution. The skill itself is the entry point; workflow execution is tracked via raw_workflow_runs and raw_workflow_nodes, not via skill.invoked.
- **Intent 1 (SQLite):** Aligned — workflow state is persisted to `raw_workflow_runs`, `raw_workflow_nodes`, `outcome_records`. The workflow runner calls `spool.ingestor.ingest_pending()` which flushes to SQLite. State files (`workflow-checkpoint.json`, `workflows.json`) are file-backed checkpoints but are secondary to SQLite.
- **Intent 2 (Security intake):** N/A — ds-workflow is an orchestration layer, not itself a content layer.
- **Intent 3 (Security gate):** Workflows in canonical/workflows/ include security gate nodes (comprehensive-review.yaml, idea-to-pr.yaml, project-audit.yaml all reference `pr-security-scan` as a workflow node). The workflow runner enforces these nodes as part of execution. This is the primary mechanism by which security operates as a lifecycle gate.
- **Intent 4 (Events):** `workflow.node.completed` (25 events), `workflow.completed` (2 events) observed in canonical_events. The runner emits `skill.invoked` for each skill node dispatch (per `control.execution.workflow.runner.py:382`). Events are emitted from the runner layer.
- **Intent 5 (Marker):** N/A — workflow runner resolves project context via work order or active project query, not marker files.
- **Notes:** The canonical SKILL.md references an `examples.md` file for detailed schema, templates, and integration points. packs.yaml maps the `meta` pack to this skill (`skill: workflow`, `skill_path: canonical/skills/workflow`). The meta pack name in packs.yaml differs from the ds-workflow installed name — this is an intentional alias. The second studio-onboard run had a "no skill defined" skip on the config-setup node, suggesting the workflow YAML referenced a skill specifier that the runner couldn't resolve.

---

### Installed Skills (.claude/skills/) — Comparison to Canonical

9 skills are installed as standalone SKILL.md files at `~/.claude/skills/`:

| Installed name | Canonical source | Delta (bytes) | Status |
|---|---|---|---|
| ds-analyze | canonical/skills/analyze | +24 | Minor divergence |
| ds-bootstrap | canonical/skills/ds-bootstrap | +54 | Minor divergence |
| ds-core | canonical/skills/core | +74 | Minor divergence |
| ds-domains | canonical/skills/domains | +31 | Minor divergence |
| ds-project | canonical/skills/ds-project | +224 | Largest divergence |
| ds-quality | canonical/skills/quality | +22 | Minor divergence; mode name mismatch (secure vs pr-security-scan) |
| ds-security | canonical/skills/security | +23 | Minor divergence |
| ds-setup | canonical/skills/setup | +175 | Notable divergence |
| ds-workflow | canonical/skills/workflow | +84 | Minor divergence |

**Two canonical skills NOT installed as standalone files:**
- `ds-milestone` — function-backed, operates without a standalone SKILL.md in ~/.claude/skills/
- `ds-workorder` — function-backed, operates without a standalone SKILL.md in ~/.claude/skills/

**Direction of delta:** All installed files are larger than canonical. No installed file is smaller. The delta direction is uniform.

**Nature of delta:** Not determinable from file sizes alone — the deltas may represent additional context injected during installation compilation (e.g., director_name resolution, adapter-specific routing additions) or accumulated edits not synced back to canonical.

---

### Special Focus: ds-security Security Integration

All 8 modes analyzed against lifecycle integration status:

#### scan
- **Lifecycle wiring:** NOT wired into any lifecycle gate or intake workflow. The security-audit.yaml workflow uses `skill: scan` as a node (`generate-rules` and `ingest-results`), but security-audit.yaml is an on-demand client-facing workflow, not an SDLC gate.
- **Workflow references:** security-audit.yaml only.
- **Findings persistence:** SKILL.md specifies file-based storage at `~/.dream-studio/security/scans/{client}/{repo}/{date}/` with `scan-meta.json`. SQLite tables exist (`sec_sarif_findings`, `sec_cve_matches`) but have 0 rows and are not referenced in the scan mode SKILL.md.
- **Invocation status:** Zero observed invocations.

#### review
- **Lifecycle wiring:** NOT wired as a standalone gate. The mode is referenced in the routing table and has a complete SKILL.md specifying a 3-phase methodology. The workflow nodes in comprehensive-review.yaml and idea-to-pr.yaml use `skill: pr-security-scan` — which resolves to the ds-quality `pr-security-scan` mode, not ds-security review.
- **Workflow references:** None that use `security:review` or `ds-security review` as a node.
- **Findings persistence:** SKILL.md does not specify SQLite writes. Output is a markdown findings report.
- **Invocation status:** Zero observed invocations.

#### dast
- **Lifecycle wiring:** NOT wired into any lifecycle gate or workflow.
- **Workflow references:** None.
- **Findings persistence:** SKILL.md specifies ingestion into unified findings store (file path `~/.dream-studio/security/scans/{client}/{target}/{date}/`). SQLite tables exist (`sec_sarif_findings`) but have 0 rows.
- **Invocation status:** Zero observed invocations.

#### binary-scan
- **Lifecycle wiring:** NOT wired into any lifecycle gate or workflow.
- **Workflow references:** None.
- **Findings persistence:** File-based (per scan mode pattern).
- **Invocation status:** Zero observed invocations.

#### mitigate
- **Lifecycle wiring:** Referenced as a downstream step in security-audit.yaml (`depends_on: [ingest-results, post-scan-review]`).
- **Workflow references:** security-audit.yaml only (as on-demand client workflow).
- **Findings persistence:** Writes to `~/.dream-studio/security/reports/{client}/mitigations.json`.
- **Invocation status:** Zero observed invocations.

#### comply
- **Lifecycle wiring:** Referenced as a downstream step in security-audit.yaml (parallel with mitigate and netcompat-analyze).
- **Workflow references:** security-audit.yaml only.
- **Findings persistence:** Writes to `~/.dream-studio/security/reports/{client}/compliance-map.json`.
- **Invocation status:** Zero observed invocations.

#### netcompat
- **Lifecycle wiring:** Referenced in security-audit.yaml.
- **Workflow references:** security-audit.yaml only.
- **Findings persistence:** Writes to `~/.dream-studio/security/reports/{client}/netcompat-findings.json`.
- **Invocation status:** Zero observed invocations.

#### dashboard
- **Lifecycle wiring:** Final reporting step in security-audit.yaml.
- **Workflow references:** security-audit.yaml only.
- **Findings persistence:** Exports CSVs to `~/.dream-studio/security/data/{client}/` and writes executive report to `~/.dream-studio/security/reports/{client}/executive-report-{date}.md`.
- **Invocation status:** Zero observed invocations.

**Summary of security lifecycle integration:**

ds-security as a whole operates as a standalone, operator-invoked client security pipeline. All 8 modes are connected only via security-audit.yaml — an on-demand workflow designed for client org-level work (Kroger/PLMarketing context per the review mode's PLMarketing/Kroger examples). No mode of ds-security is wired into:
- The studio-onboard.yaml intake workflow
- Any work order type pre-build gate
- Any work order type post-build gate (those gates use the `security_scan` gate name, which has an unconfirmed resolver)
- Any project scoping flow in ds-project

The `on-security-scan` hook (quality pack, not security pack) provides the only automatic security coverage — it fires on every Edit/Write tool use and emits advisory stdout warnings. This hook is advisory-only, never blocks, and does not persist findings to any table.

The passive advisory coverage (hook) and the active security pipeline (ds-security skill) are two distinct layers with no data handoff between them.

---

### ds-project Scope Mode: Security Intake Check

The ds-project scope mode SKILL.md contains the following security-relevant references:

**Brownfield intake (Phase 1 Brownfield Check):** References `analyze:intelligence` as a prerequisite for existing codebases. The intelligence check is a codebase health and architecture scan, not a security scan. Security is not mentioned in the brownfield check.

**Phase 3 — Work Order Generation (Valid Work Order Types table):** The 10 valid work order types are listed. The type `authentication` references "Implementing login, session management, OAuth, or token handling." No security review step is prescribed as part of authentication work order creation.

**Phase 5 — Write Output:** Calls `register_project`, `create_milestone`, `create_work_order`, `create_task`. No security audit or review step appears in Phase 5.

**No reference to ds-security in scope mode.** The entire 19,063-byte SKILL.md makes zero references to `ds-security`, `security:scan`, `security:review`, or any security audit as part of intake.

**Intent 2 assessment:** The scope mode aspirationally references codebase health (via analyze:intelligence for brownfield), but does not reference security audit as part of intake. Intent 2 (security audit during brownfield onboarding) is not implemented in the scope mode.

---

### Skill Invocation Evidence

**21 `skill.invoked` events** in canonical_events:

| skill_specifier | Count | Date range |
|---|---|---|
| ds-project:scope | 1 | 2026-05-17T01:19:44 |
| core:build | 5 | 2026-05-17T23:47:57 – 2026-05-18T00:12:55 |
| core:plan | 14 | 2026-05-18T00:49:38 – 2026-05-20T21:55:50 |

**1 row** in `skill_invocations` table:
- `skill_id: "unknown"`, `status: "completed"`, `purpose: "session skill telemetry"`, `metadata_json: {"skill": {"name": "unknown", "ts": "2026-05-19T00:15:03..."}, "success": true}`
- This row does not correlate to a specific skill specifier — it represents a telemetry capture where the skill name resolution failed.

**3 entries** in `skill-usage.jsonl`:
- All three entries have `skill: "unknown"`, `mode: ""`. The skill name extractor in `on-skill-metrics` returned "unknown" for all three hook-captured invocations. Timestamps: 2026-05-19T00:15:03, 00:18:06, 00:21:06.

**1 entry** in `telemetry-buffer.jsonl`:
- `{"skill_name": "unknown", "invoked_at": "2026-05-19T00:15:03..."}` — same "unknown" resolution failure.

**Skills with zero invocations (by skill.invoked events):**
ds-analyze, ds-domains, ds-quality, ds-security, ds-setup, ds-workflow, ds-milestone, ds-workorder, ds-bootstrap (passive)

**Observation on the 13-event core:plan burst:**
Events at 2026-05-20T21:55:47–50 (13 events in ~3 seconds) all have `work_order_id: null` and `target: null`. The timestamps are sub-second apart, consistent with a workflow runner loop emitting multiple `skill.invoked` events in rapid succession for repeated plan dispatches. This is the only such burst pattern in the event log. It accounts for 62% of all skill.invoked events.

---

## Findings

1. **Only 3 of 11 skills have confirmed invocations.** ds-core (19 events), ds-project (1 event), and ds-workflow (inferred via workflow run records) are the only skills with evidence of execution. The remaining 8 skills (ds-analyze, ds-domains, ds-quality, ds-security, ds-setup, ds-milestone, ds-workorder, ds-bootstrap-passive) have zero `skill.invoked` events in the 6-day observation window (2026-05-17 to 2026-05-20).

2. **Skill name resolution fails for hook-captured invocations.** The `on-skill-metrics` hook extracts skill name from `tool_input.skill` or `tool_input.name`, but all three observed entries in skill-usage.jsonl return "unknown". The 21 `skill.invoked` events in canonical_events are populated correctly via `core.skills.invocation.record_skill_invocation`. Two separate skill tracking paths produce different results: the hook path fails to resolve names; the spool path succeeds.

3. **ds-security is fully standalone — no wiring to SDLC gates or intake flows.** None of the 8 ds-security modes are invoked by any intake workflow, work order lifecycle gate, or project scoping step. The `security_scan` gate name referenced in ds_work_order_types has no confirmed resolver pointing to ds-security. Security workflow integration routes to `pr-security-scan` (ds-quality) in existing workflow YAML files, not to ds-security modes.

4. **Security findings tables are empty despite 6 days of operation.** All security-specific tables (security_findings, sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks, hook_findings) have 0 rows. The `on-security-scan` hook fires on every Edit/Write but only emits stdout advisory warnings — no persistent record of any advisory finding exists.

5. **ds-quality canonical SKILL.md lists mode `secure`; installed/routing uses `pr-security-scan`.** The canonical SKILL.md at `canonical/skills/quality/SKILL.md` references `modes/secure/SKILL.md` and the keyword `secure:`, but packs.yaml, CLAUDE.md routing tables, and the installed version all register `pr-security-scan`. The canonical source file has not been updated to match the renamed mode.

6. **All installed skill files are larger than their canonical sources.** Deltas range from +22 bytes (ds-quality) to +224 bytes (ds-project). All 9 installed skills have positive byte deltas. The direction is uniform. The source of the additions is not visible from file sizes alone — it may be installation-time context injection, accumulated edits, or adapter-specific additions.

7. **ds-project scope mode has no security audit step during project intake.** The scope mode's Brownfield Check references `analyze:intelligence` for codebase health, but no security scan is prescribed. Intent 2 (security during brownfield onboarding) is aspirational in the stated intents but absent from the scope mode implementation.

8. **The 13-event burst of core:plan skill.invoked events suggests workflow runner over-emitting.** 14 of the 15 `core:plan` events have sub-second timestamp gaps and `work_order_id: null`, `target: null`. This is consistent with a loop dispatching the same skill multiple times without context linkage, rather than 14 distinct plan invocations.

9. **ds-security storage layer uses file system, not SQLite, as the live path.** The scan SKILL.md specifies `~/.dream-studio/security/scans/{client}/{repo}/{date}/` file paths as the primary storage mechanism. SQLite tables (sec_sarif_findings, etc.) exist in schema but are not referenced as write targets in any security SKILL.md. The two storage paths are not connected by a write routine visible in the skill definitions.

10. **Two function-backed skills (ds-milestone, ds-workorder) are NOT installed as standalone skill files.** They depend on the routing table in packs.yaml to be reached. If packs.yaml is not loaded by the adapter, these skills are unreachable without the CLI.

11. **The `skill_invocations` table has 1 row with `skill_id: "unknown"`.** The single row was created by session telemetry capture, not by a confirmed skill invocation. The table's purpose (tracking invocations with project/milestone/task linkage) is unfulfilled in the observed data.

---

## Intent Divergence

### Intent 1 — SQLite-first authority

**Alignment:** ds-workorder, ds-milestone, and ds-project are strongly aligned — they are explicitly designed as SQLite authority wrappers. The workflow runner persists state to SQLite (raw_workflow_runs, raw_workflow_nodes). Work order lifecycle events (work_order.started, work_order.created, work_order.closed) are in canonical_events.

**Divergence:** ds-setup stores tool preferences in `.dream-studio/setup-prefs.json` (file-backed). ds-security stores scan results in `~/.dream-studio/security/scans/` directory tree (file-backed). ds-core stores plan artifacts in `.planning/` (file-backed). These are persistent state items outside SQLite. The setup-prefs.json and scan result files are not shadowed by SQLite records.

### Intent 2 — Security audit during brownfield onboarding

**Alignment:** None confirmed. No skill in the set invokes ds-security during intake.

**Divergence:** ds-project scope mode's brownfield check references `analyze:intelligence` (codebase health), not a security scan. studio-onboard.yaml does not invoke ds-security. The intake pathway has no security audit step in any observed or documented flow.

### Intent 3 — Security audit as SDLC lifecycle gate

**Alignment:** Partial. The `security_scan` post-build gate exists in ds_work_order_types for 6 of 10 work order types. The `pr-security-scan` quality mode is wired into the idea-to-pr.yaml, comprehensive-review.yaml, and project-audit.yaml workflow nodes. ds-milestone close mode has a "security audit" gate check listed.

**Divergence:** The relationship between the `security_scan` gate name and ds-security is unconfirmed — no code path from gate resolution to ds-security invocation is documented in any SKILL.md. The workflow nodes using security coverage reference `pr-security-scan` (a lightweight code-review mode) rather than the full ds-security scanning suite. The milestone security audit gate mechanism is not defined in the SKILL.md.

### Intent 4 — Canonical events as the spine

**Alignment:** `skill.invoked`, `work_order.started`, `work_order.created`, `work_order.closed`, `milestone.created`, `workflow.completed`, `workflow.node.completed` are all observed in canonical_events. The spool → ingestor → SQLite pipeline is operational.

**Divergence:** The `on-skill-metrics` hook emits `execution.completed` via `bridge.emit_from_legacy` — this event type is not in the taxonomy and is not observable in canonical_events with that name. Three hook-captured skill usages in skill-usage.jsonl have no canonical event counterpart. setup-prefs.json writes, security scan file writes, and advisory security hook findings have no canonical event emissions.

### Intent 5 — Marker file authority for attribution

**Alignment:** `core.skills.invocation.record_skill_invocation` includes marker file fallback for project_id resolution when work_order_id is not provided. This is consistent with Intent 5.

**Divergence:** Only ds-project:scope (1 event) has a confirmed skill invocation in the data. The 14 core:plan burst events all have `work_order_id: null`, `target: null` — the marker file fallback was either not triggered or produced null results. The single `skill_invocations` table row has `project_id: null`. The marker file attribution mechanism exists in code but has not produced linked attribution in the observed data.

---

## Open Questions

1. What is the resolver for the `security_scan` post-build gate in ds_work_order_types? Is it a query against the `security_findings` table, an invocation of ds-security, or something else? This determines whether Intent 3 is actually implemented or only named.

2. What is the source of the +22 to +224 byte deltas between canonical and installed skill files? Is the installer injecting adapter-specific context, or are the installed files accumulated drift from manual edits?

3. The `on-skill-metrics` hook fails to resolve skill names (returns "unknown" for all hook-captured invocations). What is the expected `tool_input` structure for the Skill tool that the hook reads `tool_input.skill` from? Is the Skill tool's payload format compatible with what the hook expects?

4. The 13-event `core:plan` burst on 2026-05-20T21:55:47–50 — was this a runaway workflow dispatch loop, a test scenario, or an intentional multi-dispatch? The `work_order_id: null` on all events suggests context was not passed.

5. Does `core.milestones.close.close_milestone` invoke ds-security for the "security audit" gate check, or does it query the `security_findings` table directly? The SKILL.md references a gate but does not specify the resolver.

6. The `ds-security scan` mode stores results at `~/.dream-studio/security/scans/{client}/` on the filesystem. Are there any ETL scripts or hooks that ingest these file-backed results into `sec_sarif_findings` or `security_findings` SQLite tables? If not, the SQLite schema is orphaned relative to the skill's actual storage path.

7. ds-setup's `isFirstRun()` is described in SKILL.md as checking for `setup-prefs.json`. Was setup-prefs.json created during the studio-onboard run, and does it gate first-run prompts for other skills?

8. The `audit` mode keyword is listed in CLAUDE.md routing for ds-quality but does not appear in the canonical SKILL.md mode table. Is `audit` a mode alias for an existing mode, or a mode that exists in the installed version's expanded content?
