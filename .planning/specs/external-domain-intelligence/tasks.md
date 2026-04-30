# Tasks: External Domain Intelligence
**Input**: `.planning/specs/external-domain-intelligence/plan.md`  
**Spec approved**: 2026-04-29

---

## Phase 1: Foundation — Schema + Rubric + Directory (Blocking)

**Purpose**: Everything else depends on these three files existing. No domain synthesis can run without the extended ingest-log schema, no evaluation without the rubric, no agents without the directory.

**⚠️ CRITICAL**: Phases 2–5 cannot start until Phase 1 is complete.

- [ ] T001 Extend `skills/domains/ingest-log.yml` schema — add `keywords`, `persona_md_path`, `quality_score`, `sources_evaluated[]`, `enhancement_notes` fields with documentation comments. No entries yet — schema only.  
  **Acceptance**: Schema section at top of ingest-log.yml documents all new fields with examples; existing entries are untouched; YAML validates.

- [ ] T002 Create `skills/domains/eval-rubric.yml` — 8 quality signals (has_gotchas, has_anti_patterns, has_specific_commands, has_version_specifics, battle_tested, workflow_integrable, has_concrete_examples, maintained_recently) with descriptions, scoring guidance, and thresholds (≥5 for bundling, ≥4 for domain YAML extraction).  
  **Acceptance**: File exists, YAML validates, all 8 signals documented with description + how-to-score, thresholds stated.

- [ ] T003 Create `agents/` directory at repo root with `README.md` — explains this is the bundled specialist layer, how it integrates with dream-studio (Mode A vs Mode B), how to install (`cp agents/* ~/.claude/agents/`), and how new specialists get added (via domain-ingest workflow).  
  **Acceptance**: Directory exists, README explains both usage modes, install instruction is one command with no auth required.

**Checkpoint**: Foundation ready — Phase 2 (workflow) and Phase 3 (domain synthesis) can now proceed in parallel.

---

## Phase 2: Evaluation Pipeline — domain-ingest Workflow

**Purpose**: Build the workflow that will be used to synthesize all domains. Must exist before any domain synthesis tasks run. T004 owns one file; no conflicts.

*Depends on: T001, T002, T003*

- [ ] T004 Create `workflows/domain-ingest.yaml` — 4-phase workflow: (1) find-sources: search GitHub code search + VoltAgent catalog for domain; (2) score-and-compare: dispatches `analyze` skill against eval-rubric; (3) synthesize: `build` skill produces domain YAML + enhanced persona MD; (4) register: adds entry to ingest-log with provenance. Include `director-review` gate before Phase 4 (register).  
  **Acceptance**: Workflow validates via `workflow_validate.py`; all 4 phases defined; gate present before register step; `analyze` and `build` referenced correctly as skill nodes.

**Checkpoint**: Evaluation pipeline ready — domain synthesis tasks can now run.

---

## Phase 3: Domain Synthesis — Run domain-ingest Per Domain

**Purpose**: Produce the actual domain knowledge and specialist agents. Each domain runs independently through the domain-ingest workflow. Tasks in this phase can run in parallel since each owns distinct files.

*Depends on: T001, T002, T003, T004*

- [ ] T005 [P] [INFRA] Run `workflow: domain-ingest` for infrastructure domain — evaluate sources for kubernetes-expert, devops-engineer, terraform-architect. Synthesize into `skills/domains/infra/kubernetes.yml`, `skills/domains/infra/terraform.yml`, `skills/domains/infra/devops.yml`. Create `agents/kubernetes-expert.md`, `agents/devops-engineer.md`, `agents/terraform-architect.md`. Add 3 ingest-log entries.  
  **Acceptance**: 3 domain YAMLs exist and validate; 3 agent MDs exist with persona framing stripped; 3 ingest-log entries with `sources_evaluated` and `quality_score ≥ 5`; domain YAMLs have `patterns:`, `anti_patterns:`, `gotchas:` sections.

- [ ] T006 [P] [MOBILE] Run `workflow: domain-ingest` for mobile domain — evaluate sources for mobile-developer, swift-developer, kotlin-developer, react-native patterns. Synthesize into `skills/domains/mobile/patterns.yml`. Create `agents/mobile-developer.md`. Add 1 ingest-log entry.  
  **Acceptance**: Domain YAML exists and validates; agent MD exists; ingest-log entry present; YAML covers iOS/Android/RN/Flutter patterns with gotchas.

- [ ] T007 [P] [DATA] Run `workflow: domain-ingest` for data pipelines domain — evaluate sources for data-engineer, analytics-engineer, dbt patterns. Synthesize into `skills/domains/data/pipelines.yml`. Create `agents/data-engineer.md`. Add 1 ingest-log entry.  
  **Acceptance**: Domain YAML exists and validates; agent MD exists; ingest-log entry present; YAML covers dbt, warehouse, pipeline patterns.

- [ ] T008 [P] [RESEARCH] Run `workflow: domain-ingest` for research/analysis domain — evaluate project-idea-validator (prioritize: anti-sycophancy, go/no-go structure), research-analyst, competitive-analyst. Synthesize into `skills/domains/research/analysis.yml`. Create `agents/research-analyst.md`, `agents/idea-validator.md`. Add 2 ingest-log entries.  
  **Acceptance**: Domain YAML exists; 2 agent MDs exist; idea-validator preserves anti-sycophancy signals (fatal flaw hunting, proof demanding) in dream-studio format; ingest-log entries present.

- [ ] T009 [P] [QUALITY] Run `workflow: domain-ingest` for accessibility + technical writing — evaluate accessibility-expert, technical-writer, documentation-engineer. Synthesize into `skills/domains/quality/accessibility.yml`, `skills/domains/quality/documentation.yml`. Create `agents/accessibility-expert.md`, `agents/technical-writer.md`. Add 2 ingest-log entries.  
  **Acceptance**: 2 domain YAMLs exist; 2 agent MDs exist; a11y YAML has WCAG-specific patterns; ingest-log entries present.

**Checkpoint**: Core domain knowledge synthesized. Phase 4 (routing updates) can now use ingest-log entries.

---

## Phase 4: Routing Updates — Skill Integration

**Purpose**: Wire the new domain knowledge and specialists into dream-studio's routing layer. T010 and T011 write to different files — can run in parallel.

*Depends on: T001 (ingest-log schema), T003 (agents/ dir). Does NOT need Phase 3 complete — routing reads the schema, not specific entries.*

- [ ] T010 [P] Update `skills/coach/SKILL.md` — add to `route-classify` mode: when no dream-studio skill matches, check ingest-log `keywords` fields; if match found and agent not in `~/.claude/agents/`, output install suggestion with curl command using `remote_url` from ingest-log; if no match, fall through to existing generic guidance.  
  **Acceptance**: New behavior documented in route-classify section; install suggestion format uses raw GitHub URL (no auth); existing route-classify behavior unchanged; no auto-dispatch added (native Claude Code handles installed agents).

- [ ] T011 [P] Update `skills/workflow/SKILL.md` — add `type: specialist` node to Execution Protocol section: resolves agent name against ingest-log entries, checks `persona_md_path` exists in `~/.claude/agents/`, dispatches via Task tool with agent content + workflow input. Add graceful failure: if agent not installed, pause workflow and surface install command.  
  **Acceptance**: `type: specialist` documented alongside existing `type: skill` and `type: command`; resolution logic references ingest-log by name; graceful failure path documented; no collision with existing `agent:` persona field.

**Checkpoint**: Routing live. Domain specialists accessible via coach suggestions and workflow dispatch.

---

## Phase 5: Maintenance Automation

**Purpose**: Keep domain knowledge current without manual effort. Two files, no conflicts, can run in parallel.

*Depends on: T001 (ingest-log schema with refresh_due)*

- [ ] T012 [P] Extend `packs/meta/hooks/on-pulse.py` — add check: read ingest-log entries where `persona_md_path` is not null; collect entries where `refresh_due` < today; if any found, include in pulse report under "Stale domain knowledge" section; do not auto-refresh (surface only).  
  **Acceptance**: on-pulse.py reads ingest-log; stale agent entries appear in pulse report under new section; pulse still runs if ingest-log is missing or malformed (graceful fallback); existing pulse checks unchanged.

- [ ] T013 [P] Create `workflows/domain-refresh.yaml` — lightweight workflow: (1) reads ingest-log for entries past `refresh_due`; (2) for each stale entry, re-runs `domain-ingest` phases 1–3 (skip register gate for non-substantive changes); (3) updates `last_updated` and `refresh_due` in ingest-log; (4) commits changed files. Triggered manually or via schedule skill.  
  **Acceptance**: Workflow validates; reads ingest-log refresh_due dates; dispatches domain-ingest sub-workflow correctly; updates ingest-log dates after refresh; no-op if nothing is stale.

---

## Phase 6: Setup Documentation

**Purpose**: One README section so end users who clone dream-studio get the bundled specialists without any configuration.

*Depends on: T003 (agents/ dir must exist)*

- [ ] T014 Update `README.md` — add "Bundled Specialists" section after install instructions: one-command setup (`cp agents/* ~/.claude/agents/` or `Copy-Item agents\* ~/.claude/agents/` for Windows), explanation of what this enables, note that specialists are auto-updated by the domain-refresh workflow.  
  **Acceptance**: README section added; install command works on both Unix and Windows; no GitHub API auth required for the documented setup; section is under 10 lines.

---

## Dependencies & Execution Order

```
T001 ──┐
T002 ──┼── T004 ── T005 [P]
T003 ──┘         ├── T006 [P]
                 ├── T007 [P]
                 ├── T008 [P]
                 └── T009 [P]

T001 ──── T010 [P]  (parallel — reads schema, not entries)
T001 ──── T011 [P]  (parallel — reads schema, not entries)

T001 ──── T012 [P]  (parallel — reads ingest-log structure)
T001 ──── T013 [P]  (parallel — reads ingest-log structure)

T003 ──── T014      (agents/ dir must exist for README to reference it)
```

### Parallel opportunities

- T005–T009: All domain synthesis tasks — different files, no shared writes
- T010–T011: Routing updates — different SKILL.md files
- T012–T013: Maintenance automation — different files (hook vs workflow)
- T004 can start as soon as T001–T003 complete, before domain tasks begin

### File ownership (no conflicts)

| Task | Files owned |
|---|---|
| T001 | `skills/domains/ingest-log.yml` |
| T002 | `skills/domains/eval-rubric.yml` |
| T003 | `agents/README.md` |
| T004 | `workflows/domain-ingest.yaml` |
| T005 | `skills/domains/infra/*.yml`, `agents/kubernetes-expert.md`, `agents/devops-engineer.md`, `agents/terraform-architect.md` |
| T006 | `skills/domains/mobile/patterns.yml`, `agents/mobile-developer.md` |
| T007 | `skills/domains/data/pipelines.yml`, `agents/data-engineer.md` |
| T008 | `skills/domains/research/analysis.yml`, `agents/research-analyst.md`, `agents/idea-validator.md` |
| T009 | `skills/domains/quality/accessibility.yml`, `skills/domains/quality/documentation.yml`, `agents/accessibility-expert.md`, `agents/technical-writer.md` |
| T010 | `skills/coach/SKILL.md` |
| T011 | `skills/workflow/SKILL.md` |
| T012 | `packs/meta/hooks/on-pulse.py` |
| T013 | `workflows/domain-refresh.yaml` |
| T014 | `README.md` |

---

## Summary

| Phase | Tasks | Parallel? | Blocking? |
|---|---|---|---|
| 1: Foundation | T001–T003 | No (sequential) | Blocks all |
| 2: Workflow | T004 | No | Blocks Phase 3 |
| 3: Domain synthesis | T005–T009 | Yes (all parallel) | Blocks nothing |
| 4: Routing | T010–T011 | Yes | — |
| 5: Maintenance | T012–T013 | Yes | — |
| 6: Setup | T014 | — | — |

**Total**: 14 tasks, 5 parallel opportunities, 2 blocking phases  
**MVP cutoff**: T001–T005 (infra domain live, coach routing updated) — ship after T005+T010+T011
