# Post-Phase-19 Operational Docket

**Purpose:** Master tracker for all remaining work after Phase 19 (Slice 10) and the
Phase 18.6.2 cleanup PR (#176). Read this to see the full remaining scope and its current
status. Update it as items move.

**Relationship to DREAM-STUDIO-ROADMAP.md:** The roadmap is the vision anchor — what
Dream Studio is, what it becomes, and the high-level phase sequence. This document is the
operational backlog — what's left to do, what's blocked, what order it runs in. When the
roadmap says "Phase 20" or "Slice 11," this document has the specific WOs and their
dependencies.

**Vocabulary note:** Phase 19 in this project's numbering = Slice 10 in the roadmap.
Phase 20 = Slice 11. These are the same milestones under two naming systems. This document
uses the phase numbering (Phase 19, Phase 20) to match git history and PR references.

**How to use this document:**
- Update the `Status` field on each item as it moves through work
- Add `(PR #N)` to the status when a WO ships
- Add new items under the appropriate category with `⚠️ UNCONFIRMED` until the operator
  acknowledges the scope
- Never silently add items — flag them for operator confirmation first
- This is the source of truth for "what's left"

**Discipline reference:** Every cleanup item (Category: Cleanup) is governed by
`docs/operations/cleanup-discipline.md`. Pre-flight before acting, verify before deleting.

---

## Status Legend

| Status | Meaning |
|---|---|
| `NOT STARTED` | Not yet investigated or scoped |
| `PRE-FLIGHT DONE` | Investigation complete; WO not yet run |
| `IN FLIGHT` | WO is actively running |
| `BLOCKED` | Waiting on a named dependency |
| `DONE (PR #N)` | Shipped; PR reference given |

---

## Category: Cleanup (removal)

Items 1–10 are dead-weight removal. Execution order within the category is flexible except
where a dependency is marked. Pre-flight discipline applies to all.

---

### Item 1 — Career Annihilation

**What:** Remove the entire career module from Dream Studio. Includes:
- 14 `career_*` tables (all have minimal/no rows; career data is private operational
  capability, not Dream Studio product data)
- `core/shared_intelligence/career_ops.py` (~300 lines)
- Career section in `core/shared_intelligence/contract_atlas.py`
- Career reference in `core/shared_intelligence/scoped_agents.py`
- Career dashboard panel in `projections/frontend/dashboard.html`
- Career API endpoint in the shared intelligence routes
- `docs/operations/career-ops-capability-center.md` — update to note removal

**Status:** `NOT STARTED`

**Dependencies:** None within this category; independent.

**Source:** Audit 1 (context packets dead-weight sweep), Audit 3 (module/function audit).
Note: this is the **first WO under the codified cleanup discipline** — the discipline doc
was written specifically to prevent recurrence of the patterns that made Phase 18.6.2
cleanup harder than it needed to be. Career annihilation should be the model cleanup WO.

---

### Item 2 — ML Subsystem Deletion

**What:** Remove the entire ML subsystem. Includes:
- `projections/ml/` directory: 8 modules (~3,248 lines total)
- 5 dead API endpoints that forward to ML modules
- `recommendations.py` live-crasher: queries `agg_sessions` which doesn't exist; causes
  500s on the endpoint
- 2 dashboard JS ghost references (lines ~7474, ~7494 in `dashboard.html`)
- ML-related docs updates

**Status:** `NOT STARTED`

**Dependencies:** None; independent.

**Source:** Audit 2 (agent independence + enforcement audit), Audit 3.

---

### Item 3 — Dead Route Files

**What:** Delete 6 route files that have no live routes or are entirely vestigial:
- `projections/api/routes/exports.py`
- `projections/api/routes/reports.py`
- `projections/api/routes/schedules.py`
- `projections/api/routes/realtime.py`
- `projections/api/routes/discovery_external.py`
- `projections/api/routes/discovery_research.py`

**Status:** `NOT STARTED`

**Dependencies:** None; independent.

**Source:** Audit 2, Audit 3.

---

### Item 4 — production_dashboard.py Removal

**What:** Delete `production_dashboard.py` (~1,322 lines). The file is self-marked
deprecated in its module docstring. No production callers confirmed.

**Status:** `NOT STARTED`

**Dependencies:** None; independent.

**Source:** Audit 3.

---

### Item 5 — Remaining DROP CANDIDATE Tables

**What:** Drop approximately 24 tables beyond career that are confirmed empty with no
production callers. Known candidates include:
`pi_waves`, `pi_wave_tasks`, orphaned `prd_*` tables, `automation_*` tables,
`tool_embeddings_cache`, `risk_register`, `risk_mitigations`, and others.

Full list requires a pre-flight — the count of ~24 is from the Audit 1 investigation but
needs verification against current DB state before a drop migration.

**Status:** `PRE-FLIGHT DONE` (partial — Audit 1 inventory exists; formal pre-flight WO
not yet run)

**Dependencies:** None blocking; independent of other cleanup.

**Source:** Audit 1 (database dead-weight sweep).
Pre-flight notes: `.planning/specs/project-star-family-drop-preflight.md` covers the
pattern; a new pre-flight specific to these tables is needed.

---

### Item 6 — Wave 2 Legacy Modules

**What:** Remove the remaining legacy wave executor modules that predate the v2
projection framework:
- `core/shared_intelligence/lineage_cleanup.py`
- `core/shared_intelligence/convergence.py`
- `core/shared_intelligence/wave_executor.py`
- `core/shared_intelligence/wave_executor_enhanced.py`

**Status:** `NOT STARTED`

**Dependencies:** None; independent.

**Source:** Audit 3 (module/function audit).

---

### Item 7 — VESTIGIAL Tables Decisions

**What:** 11 tables that need individual decisions before DROP or KEEP:
- `research_evidence_records` — 9 rows, but suspected test contamination (rows may be
  from test fixtures that weren't cleaned up)
- `raw_token_usage` — rows present but all zeros (WO-B dependency; may need cleanup
  alongside the write-path fix)
- `raw_workflow_nodes` and `raw_workflow_runs` — need module audit
- `raw_skill_telemetry` — needs module audit
- 6 others identified in Audit 1

**Status:** `BLOCKED` (waiting on Item 11 WO-B for raw_token_usage decision; others can
proceed independently)

**Dependencies:** Item 11 (WO-B telemetry write-path) for the raw_token_usage decision.
Other tables independent.

**Source:** Audit 1.

---

### Item 8 — AT-RISK Tables Investigation

**What:** 9 tables that may be live but are structurally similar to dropped tables —
needs a module audit before any DROP decision:
- `capability_center_records` (and associated tables)
- `cor_skill_corrections`
- `model_provider_profiles`
- 6 others identified in Audit 1

These are classified AT-RISK because they have tables and code but the operator-facing
value chain has not been fully traced. They are NOT on the drop list until the audit
confirms they are vestigial.

**Status:** `NOT STARTED`

**Dependencies:** None; this is the pre-flight investigation.

**Source:** Audit 1.

---

### Item 9 — VESTIGIAL/DEAD Endpoint Cleanup

**What:** Remove 26 vestigial endpoints + remaining dead endpoints beyond Items 2 and 3.
The full list is in Audit 2.

**Status:** `NOT STARTED`

**Dependencies:** Items 2 and 3 should ship first (they cover the largest dead endpoint
clusters). Remaining 26 can run as a single sweep WO.

**Source:** Audit 2.

---

### Item 10 — PARTIAL Module Function Removals

**What:** 10 live modules that contain dead functions inside otherwise-active files.
These are not whole-file deletions — they require surgical function removal with caller
verification per the cleanup discipline.

Full list in Audit 3.

**Status:** `NOT STARTED`

**Dependencies:** Items 1–4 should ship first (they establish the cleanup pattern and
reduce the blast radius of what "dead" means in the remaining modules).

**Source:** Audit 3.

---

## Category: Substrate Fixes (data quality)

These are not removals — they are fixes to the write path that makes telemetry honest.
They should run before the dashboard is redesigned (Items 16–17) because dashboard
redesigns built on dishonest substrate will be wrong again.

---

### Item 11 — WO-B Telemetry Write-Path Bugs

**What:** Fix four known substrate bugs in the telemetry write path:
1. `raw_sessions.outcome` — always NULL; session endings aren't writing outcome
2. `raw_token_usage` — all zeros; token counts not being written
3. `skill_invocations.skill_name` — stuck at `'unknown'`; skill specifier resolution
   failing
4. DreamySuite triplicate writes — `ProjectProjection` writing 3 rows per event due to
   a writer-side bug

**Status:** `NOT STARTED`

**Dependencies:** None; this is the substrate work that unlocks honest telemetry.

**Source:** Dashboard truthfulness audit (2026-05 session). Evidence in the dashboard
`Hooks` panel showing 3,026 tool_invocations but skill_invocations stuck at 'unknown'.

---

### Item 12 — WO-D Re-baseline

**What:** After WO-B fixes the write path, recapture the pre_phase_19 baseline for
Phase 19 Decision 6. The adaptive learning loop (Phase 19) validates extensions against
the artifact-baseline; if the baseline was captured against dishonest substrate (zeros,
nulls), the validation is measuring noise.

**Status:** `BLOCKED`

**Dependencies:** Item 11 (WO-B telemetry write-path fixes must be complete first).

**Source:** Dashboard truthfulness audit. Decision 6 threshold logic in
`core/expansion/validation.py`.

---

## Category: Diagnostic Infrastructure

---

### Item 13 — Workstream D Diagnostics

**What:** Four diagnostic capabilities for deep troubleshooting:
- D1: Log swallowed exceptions under `DS_DEBUG` env flag
- D2: Resource-touch tracing under `DS_TRACE` env flag
- D3: Extend `guard_real_homedir` to catch all hermetic violations
- D4: README for the diagnostic layer

**Status:** `BLOCKED`

**Dependencies:** Items 11 and 12 (telemetry must be honest before diagnostic tracing
adds value); Item 7 (research_evidence_records contamination should be resolved first to
avoid tracing through dirty state).

**Source:** 2026-05-20 health audit.

---

## Category: Dashboard

---

### Item 14 — WO-C Operator Confusion Fixes

**What:** Two UX decisions that require operator input before implementation:
1. **Learning tab decision** — the Adaptation tab added in Phase 19 shows extension
   lifecycle data. Operator needs to confirm whether it stays, moves, or the content
   changes.
2. **Current Project selector decision** — the project selector behavior is confusing
   (unclear what "current" means when multiple projects are active). Operator needs to
   define the intended behavior.

**Status:** `NOT STARTED`

**Dependencies:** None blocking; can run independently.

**Source:** Dashboard truthfulness audit.

---

### Item 15 — Dashboard Performance Beyond Popup

**What:** The popup performance fix (PR #175) removed `_repo_stack_evidence()` from the
critical path. Other potentially slow endpoints have not been profiled. This item is an
investigation + fixes pass for remaining performance problems in the dashboard.

**Status:** `NOT STARTED`

**Dependencies:** None blocking.

**Source:** This conversation (popup performance fix phase).

---

### Item 16 — Overview Redesign

**What:** Redesign the dashboard Overview page using a VP-first reference template —
what would a VP of Engineering want to see at a glance. Requires honest substrate to
be meaningful.

**Status:** `BLOCKED`

**Dependencies:** Items 11 and 12 (substrate must be honest; a redesign built on NULL
outcomes and zero token counts will show wrong numbers).

**Source:** This conversation (dashboard truthfulness audit phase).

---

### Item 17 — Per-Page Redesigns

**What:** Depth-layered redesign of each remaining dashboard page following the Overview
pattern established in Item 16. Multiple WOs, one per page cluster.

**Status:** `BLOCKED`

**Dependencies:** Item 16 (Overview pattern must be established first).

**Source:** This conversation.

---

## Category: Phase Completion

---

### Item 18 — Phase 19.8 Extension Lifecycle Management

**What:** The last piece of Phase 19 (Slice 10) that was not completed in the main
Phase 19 workstream. Covers extension lifecycle management — the operational workflow for
promoting, deprecating, and archiving extensions after Decision 6 fires.

**Status:** `NOT STARTED`

**Dependencies:** Phase 19.7 (ExtensionLoader with cache invalidation) is complete
(shipped in this conversation's Phase 19 workstream).

**Source:** Phase 19 plan; Phase 19.8 was explicitly deferred during the workstream.

---

### Item 19 — `_enforcement_check()` Wire-Up (Chain 7)

**What:** Complete the runtime enforcement stub in `emitters/claude_code/run.py`. The
`_enforcement_check()` function currently returns `None` unconditionally with a TODO:
"Slice 10: wire enforcement via runtime intelligence layer once Chain 7 is complete."

Slice 10 substrate (Phase 19) is now complete. This item is the Chain 7 closure —
wiring `_enforcement_check()` to the work order authority so that sessions without an
active work order are blocked at the UserPromptSubmit hook level.

**Status:** `NOT STARTED`

**Dependencies:**
- Item 11 (WO-B substrate honest — enforcement checking work order status needs
  reliable session/project tracking)
- Item 18 (Phase 19.8 complete — the extension lifecycle the enforcement references
  should be stable)

**Source:** Audit 2 (agent-independence pre-flight); `emitters/claude_code/run.py:41`;
DREAM-STUDIO-ROADMAP.md (Chain 7 reference).

---

### Item 20 — Dream Command workflow `studio-onboard`

**What:** The `studio-onboard` workflow is at 11/13 steps — two remaining steps
(`final-report` and `schedule-self-audit`) block Dream Command WO3. WO3 is the adapter
capability card UI component that shows Dream Studio agents, skills, and workflows
working together.

**Status:** `NOT STARTED`

**Dependencies:** Dream Command WO1 and WO2 are complete. WO3 is gated on this.

**Source:** DREAM-STUDIO-ROADMAP.md; Dream Command project state in studio.db
(project a4befdce-bfb6-40ed-9e83-ace93edac44b).

---

## Category: Phase 18.7 Leftovers

These are cleanup items that were planned under Phase 18.7 and not completed.

---

### Item 21 — Phase 18.7.4: Retire ds-security:dashboard Power BI Mode

**What:** The `ds-security:dashboard` skill mode has a Power BI variant that is no
longer relevant to Dream Studio's current security posture. Retire the mode and remove
its routing entry.

**Status:** `NOT STARTED`

**Dependencies:** None.

**Source:** Phase 18 plan; Phase 18.7.4 entry.

---

### Item 22 — Phase 18.7.6: Accumulated Sweep

**What:** A consistency pass covering:
- Pre-v2 file references (files that reference the old `reg_projects`, `ds_milestones`,
  etc. naming that was replaced in v2)
- Doc consistency across `docs/` (docs that reference old API paths or table names)
- Other accumulated minor drift surfaced but deferred during Phase 18

**Status:** `NOT STARTED`

**Dependencies:** Items 1–10 (cleanup) should complete first so the sweep isn't
cleaning docs that will change again when cleanup ships.

**Source:** Phase 18 plan; Phase 18.7.6 entry.

---

## Category: After Cleanup

---

### Item 23 — Phase 20 Multi-Tool Support

**What:** Phase 20 (Slice 11) — expand Dream Studio to support multiple AI tool providers
beyond Claude Code. Includes: multi-tool adapter registration, cross-tool session tracking,
and the Codex adapter completion.

**Status:** `BLOCKED`

**Dependencies:** Most of the above. Specifically:
- Cleanup items 1–10 must be substantially complete (dead code in the adapter layer will
  interfere with multi-tool registration)
- Item 11 and 12 (substrate honest — multi-tool telemetry is meaningless on zero/null substrate)
- Item 19 (`_enforcement_check()` — enforcement must work before adding more adapters)

This is a long-horizon item. It does not block anything else. It surfaces here to make
explicit that Phase 20 cannot start until the substrate is clean.

**Source:** DREAM-STUDIO-ROADMAP.md (Slice 11).

---

## Suggested Execution Clusters

The 23 items naturally cluster into four waves. Within each wave, items are largely
independent and can be parallelized.

### Wave 1 — Cleanup (Items 1–10)

Independent of substrate state. Can run now. Suggested order:

1. **Item 1 (Career annihilation)** first — the model cleanup WO under the new
   discipline. Career is well-bounded, well-audited, and establishes the pattern.
2. **Items 2–4** in parallel or sequence — ML subsystem, dead routes, production_dashboard.
3. **Items 3, 6** alongside Item 2 — small, independent.
4. **Item 5** after a fresh pre-flight against current DB state.
5. **Items 7, 8** require per-table investigation; can run in parallel with Items 2–4.
6. **Items 9, 10** clean up what's left after the larger removals.

### Wave 2 — Substrate (Items 11–12)

Can run in parallel with Wave 1. WO-B (Item 11) does not depend on cleanup. WO-D
re-baseline (Item 12) depends on Item 11.

### Wave 3 — Diagnostics + Dashboard UX (Items 13–17)

After Wave 2 substrate is honest:
- Item 13 (diagnostics) unlocks once telemetry is trustworthy
- Items 14–15 (dashboard UX/performance) can run after Wave 2
- Items 16–17 (redesign) require honest substrate AND Item 14 decisions

### Wave 4 — Phase Completion (Items 18–22)

After Waves 1 and 2:
- Item 18 (Phase 19.8) can run whenever — no substrate dependency
- Item 20 (Dream Command) can run whenever — no substrate dependency
- Items 21, 22 (Phase 18.7 leftovers) can run whenever
- Item 19 (`_enforcement_check()`) requires Items 11, 18

Item 23 (Phase 20) is the exit condition of Wave 4.

---

### Dependency diagram (abbreviated)

```
Wave 1 (Cleanup)           Wave 2 (Substrate)
Items 1-10                 Item 11 → Item 12
     |                          |
     +──────────────────────────+
                                |
                     Wave 3 (Diagnostics/Dashboard)
                     Item 13 (after 11+12+7)
                     Items 14, 15 (after 11+12)
                     Item 16 (after 11+12+14)
                     Item 17 (after 16)
                                |
                     Wave 4 (Phase Completion)
                     Items 18, 20, 21, 22 (parallel)
                     Item 19 (after 11+18)
                                |
                     Item 23 (Phase 20)
```

---

*Created 2026-06-05 — from Phase 18.6.2 post-merge audit + Phase 19 completion + 3-audit
dead-weight sweep. Items sourced from: Audit 1 (context packets / database tables),
Audit 2 (agent independence / enforcement), Audit 3 (module/function sweep), dashboard
truthfulness audit, popup performance pre-flight, health audit 2026-05-20.*

*Audit pre-flights in `.planning/specs/`: `context-packets-production-value-preflight.md`,
`agent-independence-and-enforcement-plan.md`, `contract-atlas-prd-authority-removal-preflight.md`,
`prd-authority-harvest-preflight.md`, `project-star-family-drop-preflight.md`.*
