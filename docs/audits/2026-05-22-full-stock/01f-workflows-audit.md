# Pass 1f — Workflows Audit
*Phase 1 analysis | 2026-05-22*

---

## Stated Architectural Intents

1. **SQLite-first authority** — all runtime STATE must be SQLite-backed. File-based state is v1 rot.
2. **Security audit during brownfield onboarding** — security skills run during project intake, findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** — greenfield projects must pass security audit before going live.
4. **Canonical events as the spine** — all state changes flow through canonical_events.
5. **Marker file authority for attribution** — .dream-studio-project markers are identity source.

---

## Workflow Inventory and Assessment

### 1. audit-to-fix.yaml

**What it is:** Generic parameterized audit-then-fix loop. Audit type passed via `{{params.audit}}` parameter (harden, secure, structure-audit, scan).

**What it does:** audit → synthesize findings → plan → director approval gate → build (apply fixes) → verify → report

**Current state:** DORMANT — no execution records in raw_workflow_runs or workflow_invocations.

**Evidence of recent use:** None. Zero rows in execution history.

**Steps:**
1. `audit` — invokes `{{params.audit}}` skill (sonnet, 600s)
2. `synthesize` — reads `review-*-findings.md`, extracts severity-tagged findings, emits VERDICT line (haiku)
3. `plan` — invokes `plan` skill with synthesize output (sonnet)
4. `approve` — director-approval gate pause
5. `build` — invokes `build` skill with plan output, retry max 1 (sonnet)
6. `verify` — invokes `verify` skill (haiku)
7. `report` — saves to `~/.dream-studio/state/audit-fix-<project-slug>-<YYYY-MM-DD>.md` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Report saves to `~/.dream-studio/state/` flat file, not SQLite. NO.
- Intent 2 (Security intake): Not an intake workflow. N/A.
- Intent 3 (Security gate): If invoked with `audit=secure`, this IS a security gate. Conditional YES — depends on caller passing the right param.
- Intent 4 (Events): No explicit canonical_events emission in YAML. Execution would write to raw_workflow_runs/nodes if run via CLI. NO direct event emission.
- Intent 5 (Marker): No marker file reference. N/A.

**Notes:** The `audit=secure` path routes through `pr-security-scan` skill (mapped as `secure` → `quality:pr-security-scan` per runner.py), making this the parameterized security gate pattern. However, it's dormant and the `params.audit` mechanism requires the caller to explicitly pass the right value — there's no default behavior that makes this a gate.

---

### 2. client-deliverable.yaml

**What it is:** PLMarketing client delivery pipeline. Supports Power BI, Power Automate, Power Apps deliverables.

**What it does:** intake (extract requirements) → plan → build → validate (domain-specific checks) → screenshot → summary (delivery doc) → deliver (commit + PR, director gate)

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `intake` — extract delivery requirements into structured format, save to `.sessions/<YYYY-MM-DD>/intake-requirements.md` (haiku)
2. `plan` — invokes `plan` skill (sonnet)
3. `build` — invokes `build` skill, retry max 1 (sonnet)
4. `validate` — domain-specific checks (Power BI DAX, Power Automate triggers, Power Apps delegation) (haiku)
5. `screenshot` — captures visuals via Playwright or provides instructions (haiku)
6. `summary` — generates delivery summary doc, saves to `.sessions/<YYYY-MM-DD>/delivery-summary.md` (haiku)
7. `deliver` — director-approval gate → commit + push + create PR (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Output to `.sessions/` flat files, not SQLite. NO.
- Intent 2 (Security intake): No security step anywhere in this pipeline. NO.
- Intent 3 (Security gate): No security gate before PR creation. NO.
- Intent 4 (Events): No explicit canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** Delivery workflow with no security step before creating a PR for client work. This is a real gap — client deliverables go out without any security check.

---

### 3. comprehensive-review.yaml

**What it is:** Five-way parallel review with synthesis and GitHub issue creation.

**What it does:** Runs review-code, review-security (pr-security-scan), review-tests, review-perf, review-docs in parallel → synthesize → report (saves to `~/.dream-studio/secure/reports/`, creates GitHub issues for HIGH/CRITICAL)

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `review-code` — invokes `review` skill (sonnet)
2. `review-security` — invokes `pr-security-scan` skill (sonnet) — SECURITY STEP PRESENT
3. `review-tests` — invokes `review` skill, focus: test-coverage-only (haiku)
4. `review-perf` — invokes `review` skill, focus: performance-only (haiku)
5. `review-docs` — invokes `review` skill, focus: docs-impact-only (haiku)
6. `synthesize` (trigger_rule: all_done) — reads all findings files, de-duplicates, sorts by severity (sonnet)
7. `report` — saves to `~/.dream-studio/secure/reports/review-<project-slug>-<YYYY-MM-DD>.md`, creates GitHub issues for HIGH/CRITICAL (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Report saved to `~/.dream-studio/secure/reports/` flat file. NO.
- Intent 2 (Security intake): Has dedicated `review-security` node using `pr-security-scan`. YES.
- Intent 3 (Security gate): Does include a security review as part of the gate. YES — PARTIAL (no hard block, just findings).
- Intent 4 (Events): No canonical_events emission. Report saves and GitHub issue creation happen directly. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** This is the most complete review workflow. The `review-security` node is explicit and parallel. GitHub issue creation for HIGH/CRITICAL is implemented in the `report` node — this partially satisfies TRACKING_GAP.

---

### 4. daily-close.yaml

**What it is:** End-of-day routine — harvest learnings, check WIP, audit memory, produce day summary.

**What it does:** daily-learn + check-wip + memory-check (parallel) → day-summary

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `daily-learn` — reads `today.md`, scans `.sessions/`, checks git log, extracts patterns, writes to `meta/draft-lessons/` (sonnet)
2. `check-wip` — `git status`, `git stash list`, checks `.planning/` for incomplete tasks (haiku)
3. `memory-check` — scans `.sessions/` for corrections without matching memory files, drafts suggestions (sonnet)
4. `day-summary` (trigger_rule: all_done) — produces 5-line summary, saves to `~/.dream-studio/meta/daily/YYYY-MM-DD-summary.md` (sonnet)

**Intent Alignment:**
- Intent 1 (SQLite): Saves to `~/.dream-studio/meta/daily/` flat files. NO.
- Intent 2 (Security intake): No security step. NO.
- Intent 3 (Security gate): Not a code deployment workflow. N/A.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** Pure operational hygiene workflow. No security relevance. File-based output exclusively.

---

### 5. daily-standup.yaml

**What it is:** Morning briefing — check open PRs, pending lessons, latest handoff, stale research.

**What it does:** check-prs + check-lessons + check-handoffs + check-research (parallel, all depend on nothing) → synthesize (director pause gate)

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `check-prs` — `gh pr list`, scans repos (haiku)
2. `check-lessons` — `py scripts/lesson_queue.py list --pending` (haiku)
3. `check-handoffs` — `py scripts/resume_from_handoff.py --brief` (haiku)
4. `check-research` — `py interfaces/cli/research_cache.py stale` (haiku)
5. `synthesize` (trigger_rule: all_done, gate: priorities-confirmed) — produces MORNING BRIEFING, saves to `~/.dream-studio/meta/daily/YYYY-MM-DD-standup.md` (sonnet)

**Intent Alignment:**
- Intent 1 (SQLite): Saves to `~/.dream-studio/meta/daily/` flat files. NO.
- Intent 2 (Security intake): No security step. NO.
- Intent 3 (Security gate): Not a code deployment workflow. N/A.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** Calls scripts `lesson_queue.py` and `resume_from_handoff.py` that may or may not exist in the repo. Not verified.

---

### 6. domain-ingest.yaml

**What it is:** 4-phase domain synthesis pipeline — find sources, score, synthesize domain YAML + persona MD, register in ingest-log.

**What it does:** find-sources (GitHub research) → score-and-compare (Opus analysis) → synthesize (writes domain files) → register (director gate, updates ingest-log.yml, commits)

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `find-sources` — GitHub search via `mcp__github__search_code`, VoltAgent catalog, builds candidate list (haiku, 300s)
2. `score-and-compare` — reads eval-rubric.yml, scores each candidate 0-8, synthesis recommendation (opus, 600s)
3. `synthesize` — writes `skills/domains/{{workflow.input}}/patterns.yml` and `agents/{{workflow.input}}-expert.md` (sonnet, 600s)
4. `register` — director-review gate → updates `skills/domains/ingest-log.yml`, commits (haiku, 300s)

**Intent Alignment:**
- Intent 1 (SQLite): No SQLite writes. All output to filesystem files. NO.
- Intent 2 (Security intake): No security step. N/A (knowledge pipeline, not code intake).
- Intent 3 (Security gate): No security gate. N/A.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** Uses Opus for score-and-compare (only workflow in the corpus to use Opus for analysis). The register step has a director-review gate before committing.

---

### 7. domain-refresh.yaml

**What it is:** Automated stale domain agent re-synthesis — reads ingest-log, re-runs phases 1-3 of domain-ingest for overdue entries.

**What it does:** scan (find stale entries) → re-synthesize (conditional on stale found) → update-dates → commit

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `scan` — reads `skills/domains/ingest-log.yml`, finds entries with `refresh_due` < today (haiku)
2. `re-synthesize` (condition: stale found) — for each stale domain, runs phases 1-3 of domain-ingest inline (sonnet, 900s)
3. `update-dates` (trigger_rule: all_done) — updates refresh_due + last_updated in ingest-log (haiku)
4. `commit` — stages and commits changed domain files (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): No SQLite writes. NO.
- Intent 2 (Security intake): N/A.
- Intent 3 (Security gate): N/A.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** The `re-synthesize` node has a 900-second timeout — the longest in the entire corpus. Commits directly without a director gate (unlike domain-ingest's register phase which has one).

---

### 8. feature-research.yaml

**What it is:** 7-phase GitHub research pipeline for any Claude feature, integration, MCP server, hook, skill, or plugin. One of the most complex workflows in the corpus.

**What it does:** intake → 4-way parallel GitHub research (repos/issues/PRs/code) → synthesis (gate) → parallel breakpoint + gap analysis → implementation-plan → risk-matrix → mission-briefing (gate) → final-report

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `intake` — parses conversation, reads `~/.claude/CLAUDE.md`, `settings.json`, `~/.dream-studio/state/workflows.json` (last 3 entries), produces structured intake report (sonnet)
2. `research-repos` — `mcp__github__search_repositories` × 3 searches, reads top-3 repo content (sonnet)
3. `research-issues` — `mcp__github__search_issues` × 4 searches (sonnet)
4. `research-prs` — `mcp__github__search_pull_requests`, inspects merge commits (sonnet)
5. `research-code` — `mcp__github__search_code` × 5 searches (sonnet)
6. `research-synthesis` (trigger_rule: all_done, gate: post-synthesis) — produces RESEARCH INTELLIGENCE BRIEF, saves to `~/.dream-studio/planning/research-synthesis-<YYYY-MM-DD>.md` (sonnet)
7. `breakpoint-analysis` — maps failure modes (sonnet)
8. `gap-analysis` — maps all missing gaps including PERSISTENCE_GAP and TRACKING_GAP categories (sonnet)
9. `implementation-plan` — invokes `plan` skill (sonnet)
10. `risk-matrix` — RPN-scored risk assessment (sonnet)
11. `mission-briefing` (gate: mission-commander) — executive briefing, presents Path A (native) vs Path B (drop-in) (sonnet, context: inherit)
12. `final-report` — saves to `~/.dream-studio/planning/claude-integration-<subject-slug>-<YYYY-MM-DD>.md` (sonnet)

**Intent Alignment:**
- Intent 1 (SQLite): All output to `~/.dream-studio/planning/` flat files. NO.
- Intent 2 (Security intake): The `breakpoint-analysis` and `gap-analysis` nodes include security-flavored checks (PERMISSION_GAP, CONFIG_GAP), but no explicit security skill invocation. NO.
- Intent 3 (Security gate): No security skill invocation. NO.
- Intent 4 (Events): The `intake` node reads `workflows.json` — not a writer. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** Notable that the `intake` node reads `~/.dream-studio/state/workflows.json` for context — this is a dependency on the file-based state format.

---

### 9. fix-issue.yaml

**What it is:** Bug fix pipeline — diagnose, GitHub issue, failing test, plan, implement, review, verify.

**What it does:** diagnose → create-issue → write-failing-test (conditional) → plan-fix → implement-fix (director gate) → review (auto-pass gate) → verify (evidence gate) → report

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `diagnose` — invokes `debug` skill (sonnet)
2. `create-issue` — `gh issue create` with debug output (haiku)
3. `write-failing-test` (condition: `{{diagnose.testable}} == true`) — writes test file, commits it (sonnet)
4. `plan-fix` — invokes `plan` skill (haiku, unusual model choice)
5. `implement-fix` — invokes `build` skill, director-approval gate, retry max 1 (sonnet)
6. `review` — invokes `review` skill, auto-pass gate (sonnet)
7. `verify` — invokes `verify` skill, evidence-required gate, retry max 1 (sonnet)
8. `report` — saves to `.sessions/<YYYY-MM-DD>/fix-report.md` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Output to `.sessions/` flat file. NO.
- Intent 2 (Security intake): No security review step. NO.
- Intent 3 (Security gate): No security gate. NO.
- Intent 4 (Events): GitHub issue creation is durable but not canonical_events. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** The `plan-fix` node uses `haiku` for planning — unusual, most plan nodes use sonnet. The `create-issue` node uses bash heredoc syntax (`head -1 <<<`) which is Unix-only and would fail on Windows PowerShell.

---

### 10. game-feature.yaml

**What it is:** Game feature pipeline with Godot-specific QA — review-gameplay, review-data, validate-engine in parallel.

**What it does:** think → plan → build → [review-gameplay + review-data + validate-engine in parallel] → synthesize (auto-fix if BLOCKED) → fix-findings (conditional) → verify (qa-gate) → record

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `think` — invokes `think` skill, director-approval gate (opus)
2. `plan` — invokes `plan` skill, director-approval gate (opus)
3. `build` — invokes `build` skill, retry max 1 (sonnet)
4. `review-gameplay` — invokes `review` skill, focus: gameplay-code (sonnet)
5. `review-data` — invokes `review` skill, focus: data-files (haiku)
6. `validate-engine` — checks GDScript against engine docs, flags deprecated APIs (haiku)
7. `synthesize` — reads all `review-*-findings.md`, de-duplicates, any Critical/High → BLOCKED (sonnet)
8. `fix-findings` (condition: BLOCKED) — invokes `build` skill (sonnet)
9. `verify` — invokes `verify` skill, qa-gate (sonnet)
10. `record` — saves to `~/.dream-studio/state/game-feature-<project-slug>-<YYYY-MM-DD>.md` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Output to `~/.dream-studio/state/` flat file. NO.
- Intent 2 (Security intake): No security step. NO.
- Intent 3 (Security gate): No security gate. NO.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** `think` and `plan` both use Opus — one of two workflows in the corpus that routes planning to Opus.

---

### 11. hotfix.yaml

**What it is:** Fast debug-fix-verify cycle for production issues. Version 2.

**What it does:** debug → build → verify (evidence gate) → ship → record

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `debug` — invokes `debug` skill (sonnet)
2. `build` — invokes `build` skill, retry max 1 (sonnet)
3. `verify` — invokes `verify` skill, evidence-required gate, retry max 1 (sonnet)
4. `ship` — invokes `ship` skill (sonnet)
5. `record` — extracts PR URL, saves one-line record to `~/.dream-studio/state/hotfix-prs.log` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Log written to `~/.dream-studio/state/hotfix-prs.log` flat file. NO.
- Intent 2 (Security intake): No security step. NO.
- Intent 3 (Security gate): NO — hotfix is the one workflow where speed trumps process. This is an intentional omission, but it means production hotfixes bypass security review.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** No security step is a deliberate speed tradeoff for production emergencies, but it's notable that the fastest path to production has no security check.

---

### 12. idea-to-pr.yaml

**What it is:** Full feature pipeline from concept to merged PR. Has both security and mitigation nodes.

**What it does:** think → plan → build → [review-code + review-security + review-tests + review-perf + review-docs in parallel] → synthesize → [fix-findings if BLOCKED] → [triage-security + mitigate-findings if security blocked] → verify (evidence gate) → ship → record

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `think` — invokes `think` skill, director-approval gate (opus)
2. `plan` — invokes `plan` skill, director-approval gate, auto-pass gate (sonnet)
3. `build` — invokes `build` skill, auto-pass gate, retry max 1 (sonnet)
4. `review-code` — invokes `review` skill (sonnet)
5. `review-security` — invokes `pr-security-scan` skill — SECURITY STEP PRESENT (sonnet)
6. `review-tests` — invokes `review` skill, focus: test-coverage-only (haiku)
7. `review-perf` — invokes `review` skill, focus: performance-only (haiku)
8. `review-docs` — invokes `review` skill, focus: docs-impact-only (haiku)
9. `synthesize` (trigger_rule: all_done) — reads all findings, Any Critical/High → BLOCKED (sonnet)
10. `fix-findings` (condition: BLOCKED) — invokes `build` skill (sonnet)
11. `triage-security` (condition: `{{synthesize.security_signal}} == blocked or strong_reject`) — invokes `pr-security-scan` skill — SECURITY STEP (sonnet)
12. `mitigate-findings` (condition: same) — invokes `mitigate` skill (sonnet)
13. `verify` — invokes `verify` skill, evidence-required gate, retry max 1 (sonnet)
14. `ship` — invokes `ship` skill (sonnet)
15. `record` — saves one-line record to `~/.dream-studio/state/idea-to-pr.log` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Log to `~/.dream-studio/state/idea-to-pr.log` flat file. NO.
- Intent 2 (Security intake): Parallel `review-security` + conditional `triage-security` + `mitigate-findings`. YES — this is the most complete security integration in any workflow.
- Intent 3 (Security gate): YES — security findings CAN block via `synthesize.security_signal`. This is effectively a security gate in the SDLC.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** This is the most security-complete workflow in the corpus. The two-phase security model (parallel review + conditional deep triage + mitigation) is the intended pattern. Also uses Opus for `think`.

---

### 13. optimize.yaml

**What it is:** Profile, audit, and reduce bloat — bundle size, dead code, deps, infra, queries.

**What it does:** context-check (seed from prior review) → profile → [audit-deps + audit-code + audit-infra(conditional) + audit-queries(conditional) in parallel] → synthesize → plan (director gate) → apply (build skill) → verify (evidence gate) → report

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `context-check` — looks for recent review reports in `~/.dream-studio/secure/reports/` (haiku)
2. `profile` — baseline metrics for bundle/Python/infra/DB, sets `has_infra` and `has_data_layer` flags (haiku)
3. `audit-deps` — finds unused, duplicate, heavy dependencies (haiku)
4. `audit-code` — finds dead exports, unreachable code, oversized assets (sonnet)
5. `audit-infra` (condition: `{{profile.has_infra}} == true`) — Cloudflare Workers, caching, build output (haiku)
6. `audit-queries` (condition: `{{profile.has_data_layer}} == true`) — N+1 patterns, overfetching, missing indexes (haiku)
7. `synthesize` (trigger_rule: all_done) — de-duplicates, ranks by impact/effort, saves to `.sessions/<YYYY-MM-DD>/optimize-synthesis.md` (sonnet)
8. `plan` (director-approval gate) — produces Wave 0 (auto-apply) and Wave 1+ (manual) plan (sonnet)
9. `apply` — invokes `build` skill for Wave 0 items, retry max 1 (sonnet)
10. `verify` (evidence-required gate) — before/after metrics comparison (haiku)
11. `report` — saves to `~/.dream-studio/state/optimize-<project-slug>-<YYYY-MM-DD>.md`, creates GitHub issues for Priority 1/2 items not applied (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Report to `~/.dream-studio/state/` flat file. NO.
- Intent 2 (Security intake): `context-check` reads from `~/.dream-studio/secure/reports/` to seed findings — indirect security feed. Partial YES.
- Intent 3 (Security gate): No direct security check. NO.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** `context-check` creating a cross-workflow dependency on prior review output is the only workflow that actively seeds from prior security findings — a useful pattern.

---

### 14. pre-push.yaml

**What it is:** Pre-push gate — blocks `git push` on regression in formatting, lint, skill-sync, evals, contract atlas, docs drift.

**What it does:** 6 sequential gates: format-check → lint-check → skill-sync → test-suite → atlas-leak → docs-drift

**Current state:** ACTIVE in concept, but no `nodes:` execution model — this workflow uses a `gates:` block instead of `nodes:`. The runner uses a different execution path for `pre-push` style workflows. No rows in raw_workflow_runs for this workflow.

**Evidence of recent use:** None in raw_workflow_runs. The gates are invoked by `hooks/git/pre-push.py` per the description.

**Steps (gates, not nodes):**
1. `format-check` — `py -m black --check .` — fail_hint: run black to fix
2. `lint-check` — `py interfaces/cli/lint_baseline.py check` — fail_hint: fix lint
3. `skill-sync` — `py -m core.gates.skill_sync_source` — checks enforcement block regression
4. `test-suite` — `py -m pytest tests/evals/ -q` — scoped to evals only (OOM-safe)
5. `atlas-leak` — `py interfaces/cli/contract_atlas_lifecycle_gate.py`
6. `docs-drift` — `py interfaces/cli/contract_docs_drift_gate.py`

**Intent Alignment:**
- Intent 1 (SQLite): No runtime state written. N/A (gate-only workflow).
- Intent 2 (Security intake): No security check. NO.
- Intent 3 (Security gate): `atlas-leak` is a contract integrity check — tangentially security-relevant. But no `pr-security-scan` or equivalent. NO.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** This is structurally different from all other workflows — it uses `gates:` not `nodes:`. The runner/state machinery does not apply. It is a shell gate dispatcher, not a YAML workflow. No security skill in this gate chain.

---

### 15. production-readiness.yaml

**What it is:** Secure production readiness workflow — classify impact, select controls, run reviews, persist to SQLite, hydrate dashboard, route remediation Work Orders.

**What it does:** classify-impact → build-gate → persist-authority-records → project-dashboard-hydration → remediation-routing

**Current state:** DORMANT — no execution records. Notably different from all other workflows: has an `authority_boundary` block and `run_policy` block.

**Evidence of recent use:** None.

**Steps:**
1. `classify-impact` — invokes `verify` skill, builds lightweight impact classification (no model/timeout specified)
2. `build-gate` — invokes `verify` skill, builds `secure_production_readiness_gate` using 47-enterprise-control catalog (timeout: 120s)
3. `persist-authority-records` — invokes `verify` skill, persists assessment/findings/remediation WO candidates to SQLite via Dream Studio connection (timeout: 120s) — EXPLICIT SQLite WRITE
4. `project-dashboard-hydration` — invokes `verify` skill, exposes readiness summary via project detail routes (timeout: 120s)
5. `remediation-routing` — invokes `verify` skill, creates proposed remediation Work Order records for failing controls (timeout: 120s)

**Intent Alignment:**
- Intent 1 (SQLite): `persist-authority-records` explicitly writes to SQLite. YES — this is the one workflow where the SQLite-first intent is explicitly called out.
- Intent 2 (Security intake): Has `run_policy.full_review_events` including `project_intake` and `external_project_onboarding`. YES in policy, but requires invocation with the right event type.
- Intent 3 (Security gate): YES — `run_policy.full_review_events` includes `release_merge`, `publication`, `deployment`, `live_cutover`. This IS the intended SDLC security gate.
- Intent 4 (Events): `project-dashboard-hydration` exposes data through routes but no explicit canonical_events. PARTIAL.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** This is architecturally the most intentional workflow in the corpus. `authority_boundary.execution_authorized_by_default: false` is a notable constraint. All 5 nodes use the `verify` skill — this workflow drives all security review through a single skill entry point. Despite being the intended production gate, it has ZERO execution history. This is a significant gap: the most important workflow has never run.

---

### 16. project-audit.yaml

**What it is:** Full project audit — harden + secure + review in parallel, director gate, report with GitHub issue creation.

**What it does:** [harden + secure + review in parallel] → report (director gate)

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `harden` — invokes `harden` skill (sonnet, 600s)
2. `secure` — invokes `pr-security-scan` skill — SECURITY STEP PRESENT (sonnet, 600s)
3. `review` — invokes `review` skill (sonnet, 600s)
4. `report` (trigger_rule: all_done, gate: review-findings) — reads all findings files, synthesizes, saves to `~/.dream-studio/secure/reports/audit-<project-slug>-<YYYY-MM-DD>.md`, creates GitHub issues for HIGH/CRITICAL (sonnet, 300s)

**Intent Alignment:**
- Intent 1 (SQLite): Report to `~/.dream-studio/secure/reports/` flat file. NO.
- Intent 2 (Security intake): `secure` node runs `pr-security-scan`. YES.
- Intent 3 (Security gate): Report produces PASSED/BLOCKED verdict based on Critical/High findings. YES — effective gate.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** The `report` node saves to `~/.dream-studio/secure/reports/` which is also where `optimize.yaml`'s `context-check` reads from. These two workflows form a cross-workflow data pipeline: project-audit → optimize.

---

### 17. prototype.yaml

**What it is:** Fast prototype pipeline — think → build → verify → snapshot. For game jams and quick experiments. Version 2.

**What it does:** think (director gate) → build → verify → snapshot (saves to `~/.dream-studio/state/`)

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `think` — invokes `think` skill, director-approval gate (sonnet)
2. `build` — invokes `build` skill, retry max 1 (sonnet)
3. `verify` — invokes `verify` skill, retry max 1 (sonnet)
4. `snapshot` — saves to `~/.dream-studio/state/prototype-<project-slug>-<YYYY-MM-DD>.md` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): State to flat file. NO.
- Intent 2 (Security intake): No security step. N/A (prototype, not production).
- Intent 3 (Security gate): No security gate. Intentionally fast/light.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** `think` uses sonnet (not opus like game-feature and idea-to-pr). Intentionally lightweight.

---

### 18. safe-refactor.yaml

**What it is:** Refactor with type checks and tests — plan → implement → [type-check + test in parallel] → review → verify → report.

**What it does:** plan-refactor (director gate) → implement → [type-check + test parallel] → review (auto-pass gate) → verify (evidence gate) → report

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `plan-refactor` — invokes `think` skill, director-approval gate (opus)
2. `implement` — invokes `build` skill, retry max 1 (sonnet)
3. `type-check` — runs `tsc`, `pyright`, `mypy`, reports pass/fail (haiku)
4. `test` — runs `npm test` or `pytest`, reports pass/fail (haiku)
5. `review` — invokes `review` skill, auto-pass gate (sonnet)
6. `verify` — invokes `verify` skill, evidence-required gate, retry max 1 (sonnet)
7. `report` — saves to `.sessions/<YYYY-MM-DD>/refactor-report.md` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): Output to `.sessions/` flat file. NO.
- Intent 2 (Security intake): No security step. NO.
- Intent 3 (Security gate): No security step. NO — safe-refactor has no security review despite touching potentially security-sensitive code.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** `plan-refactor` invokes `think` skill (not a separate `plan` skill) using Opus. This aligns with feature workflows that use Opus for planning phases. Notably: refactors can introduce security vulnerabilities but this workflow has no security review step.

---

### 19. security-audit.yaml

**What it is:** Enterprise security analysis pipeline — intake client profile, generate Semgrep rules, DAST, binary scan, ingest, parallel mitigate + comply + netcompat, Power BI dashboard, executive report.

**What it does:** intake → [generate-rules + dast-scan + binary-scan in parallel] → ingest-scans (post-scan-review gate) → [mitigate + comply + netcompat-analyze in parallel] → analysis-sync (pre-dashboard gate) → generate-dashboard → executive-report

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `intake` — reads `~/.dream-studio/clients/{name}.yaml`, validates client profile (sonnet, context: inherit)
2. `generate-rules` — invokes `scan` skill mode:setup, generates Semgrep rules + GitHub Actions (sonnet)
3. `dast-scan` — invokes `dast` skill mode:run, ZAP + Nuclei against web_app targets (sonnet, 900s)
4. `binary-scan` — invokes `binary-scan` skill mode:analyze, checksec + YARA + strings (sonnet, 600s)
5. `ingest-scans` — invokes `scan` skill mode:ingest, parses SARIF/JSON → unified-findings.json (sonnet, gate: post-scan-review)
6. `mitigate` — invokes `mitigate` skill, generates mitigations per finding (sonnet, 600s)
7. `comply` — invokes `comply` skill, maps to SOC2/NIST CSF/OWASP ASVS controls (sonnet, 300s)
8. `netcompat-analyze` — invokes `netcompat` skill, Zscaler/proxy compat analysis (sonnet, 300s)
9. `analysis-sync` (trigger_rule: all_done, gate: pre-dashboard) — sync checkpoint (sonnet)
10. `generate-dashboard` — invokes `dashboard` skill, ETL → Power BI CSV exports (sonnet, 300s)
11. `executive-report` — compiles markdown report, saves to `~/.dream-studio/security/reports/{client}/executive-report-{YYYY-MM-DD}.md` (sonnet)

**Intent Alignment:**
- Intent 1 (SQLite): All output to `~/.dream-studio/security/` flat files (JSON, CSV, MD). NO.
- Intent 2 (Security intake): This IS the enterprise security intake workflow. YES.
- Intent 3 (Security gate): This workflow produces findings but does not itself gate anything — it's a reporting pipeline. PARTIAL (findings feed into remediation, but no hard code-gate).
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** This is the Kroger/PLMarketing client security workflow. Heavy dependency on `~/.dream-studio/clients/{name}.yaml` — requires client profile setup before invocation. Longest potential duration in corpus: `dast-scan` has a 900-second timeout.

---

### 20. self-audit.yaml

**What it is:** Dream Studio self-audit — hook noise, dead routing, oversized SKILL.md files, duplicated gotchas. Weekly scheduled via CronCreate.

**What it does:** collect-signal → [audit-hooks + audit-routing + audit-skill-size + audit-gotchas parallel] → synthesize → publish-and-reschedule (GitHub issue + CronCreate)

**Current state:** SCHEDULED — the studio-onboard run on 2026-05-18 registered a weekly Monday 09:00 cron. But the cron prompt was "workflow: studio-onboard" (not "workflow: run self-audit") per node output row 25. This is likely a mistake — the self-audit was scheduled to re-run studio-onboard instead of itself.

**Evidence of recent use:** Raw node record (25): `schedule-self-audit` completed on 2026-05-18 with output `SELF_AUDIT_CRON_CREATED: weekly Monday 09:00, prompt=workflow: studio-onboard`. No self-audit runs found in raw_workflow_runs.

**Steps:**
1. `collect-signal` — reads `~/.dream-studio/state/skill-usage.jsonl`, `~/.dream-studio/audit.jsonl`, `meta/draft-lessons/`, `.sessions/`, writes signal to `.sessions/<YYYY-MM-DD>/self-audit-signal.json` (haiku)
2. `audit-hooks` — cross-references hook_events_30d, flags SILENT/NOISY/BROAD hooks (haiku)
3. `audit-routing` — identifies DORMANT skills, OBSCURE_TRIGGER, AMBIGUOUS_ROUTE (haiku)
4. `audit-skill-size` — flags SKILL.md files > 800 words (haiku)
5. `audit-gotchas` — detects cross-skill duplication (PROMOTE_TO_CORE), checks gotcha hit frequency from `handoff-*.json` (haiku)
6. `synthesize` (trigger_rule: all_done) — ranks by impact/effort P1-P4, saves to `~/.dream-studio/state/self-audit-<YYYY-MM-DD>.md` (sonnet)
7. `publish-and-reschedule` — creates GitHub issue with P1 items, calls CronCreate tool, writes `~/.dream-studio/state/self-audit-schedule.json` (sonnet)

**Intent Alignment:**
- Intent 1 (SQLite): Output to `~/.dream-studio/state/` flat file. NO.
- Intent 2 (Security intake): No security step. N/A.
- Intent 3 (Security gate): N/A.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** The `publish-and-reschedule` node calls `CronCreate` directly from within the workflow — this is the only workflow that calls a deferred tool. The scheduled prompt value ("workflow: studio-onboard") in the 2026-05-18 run appears incorrect — it should be "workflow: self-audit" or "workflow: run self-audit".

---

### 21. studio-analytics.yaml

**What it is:** Interactive analytics dashboard setup and launch. DB init, data harvest, dashboard server.

**What it does:** mode-detect → healthcheck (post-healthcheck gate) → bootstrap → harvest (post-harvest gate) → launch

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `mode-detect` — detects GUIDED vs AUTO mode from invocation args (haiku, context: inherit)
2. `healthcheck` (gate: post-healthcheck) — checks `studio.db`, scans data sources, checks port 8000 (haiku)
3. `bootstrap` — runs `py -3.12 -c "from lib.studio_db import _connect; ..."` inline Python to init DB (haiku)
4. `harvest` (gate: post-harvest) — runs `backfill_pulse.py`, `backfill_token_sessions.py`, `migrate_to_db.py` (sonnet)
5. `launch` — runs `make dashboard`, prints `http://localhost:8000/dashboard` (haiku)

**Intent Alignment:**
- Intent 1 (SQLite): `bootstrap` and `harvest` steps directly create/populate `studio.db`. YES — this workflow's explicit purpose is SQLite bootstrapping.
- Intent 2 (Security intake): No security step. N/A.
- Intent 3 (Security gate): N/A.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** Uses `py -3.12` explicitly (Python version pin) in bootstrap node. The `context: inherit` on `mode-detect` is intentional — it needs to read the conversation to detect "auto" keyword.

---

### 22. studio-onboard.yaml

**What it is:** Dream Studio brownfield onboarding — discovers user environment, compares to baseline, runs parallel breakpoint + gap + improvement analysis, plans fixes, produces full onboarding report.

**Status:** ACTIVE — 2 historical runs (2026-05-17 aborted, 2026-05-18 completed)

**Evidence of recent use:**
- Run 1 (`studio-onboard-1779058590`): Started 2026-05-17 22:56:30, ABORTED. `config-setup` skipped (no skill defined), `discovery` FAILED (Unknown skill: ds-core:build), `baseline-fetch`/`breakpoint-analysis`/`gap-analysis`/`improvement-scan` completed, then aborted before synthesis.
- Run 2 (`studio-onboard-1779063188`): Started 2026-05-18 00:13:08, COMPLETED. All 13 nodes completed including `schedule-self-audit`. Readiness score: 79/100. Final report written to `C:\Users\Dannis Seay\.dream-studio\planning\onboard-report-2026-05-18.md`.

**Steps (15 nodes):**
1. `config-setup` — sets `harvest.projects_root` + `claude_memory_path` in `~/.dream-studio/config.json`, self-reports via `py -m control.execution.workflow.state update` (sonnet, context: inherit)
2. `discovery` — full environment inventory across 9 sections (A-I), runs `ds doctor` (sonnet, 300s)
3. `baseline-fetch` — reads canonical skill/workflow list, packs.yaml, VERSION, runs `--dry-run` (sonnet, 180s)
4. `breakpoint-analysis` — parallel with gap/improvement, finds conflicts (sonnet, 300s)
5. `gap-analysis` — parallel, 12 gap categories including PERSISTENCE_GAP/TRACKING_GAP (sonnet, 300s)
6. `improvement-scan` — parallel, custom assets + workflow audit (sonnet, 300s)
7. `synthesis` (trigger_rule: all_done, gate: post-synthesis) — readiness score 0-100 across 4 layers, saves to `~/.dream-studio/planning/onboard-synthesis-<YYYY-MM-DD>.md` (sonnet)
8. `fix-plan` — invokes `plan` skill with onboarding constraints (sonnet)
9. `risk-matrix` — RPN matrix, GO/NO-GO criteria (sonnet)
10. `mission-briefing-generate` — executive briefing with asset adoption options (sonnet, context: inherit)
11. `mission-briefing-approve` — gate: mission-commander (sonnet, context: inherit, timeout: 600s)
12. `final-report` — saves to `~/.dream-studio/planning/onboard-report-<YYYY-MM-DD>.md` (sonnet)
13. `smoke-test` — 12-check validation suite including spool pipeline, skill invocation, CLAUDE.md routing integrity (sonnet)
14. `schedule-self-audit` — loads CronCreate via ToolSearch, registers weekly self-audit (sonnet)

**Security step assessment:** NO — no security skill (`pr-security-scan`, `harden`, `secure`) is invoked at any point during onboarding. The `improvement-scan` node produces a `TRACKING_GAP` audit that flags existing workflows for lacking security tracking, but does not itself run a security check on the user's environment.

**Intent Alignment:**
- Intent 1 (SQLite): Run state written to `raw_workflow_runs` and `raw_workflow_nodes` in SQLite. Also `workflow_invocations` table has 2 rows. YES — the only workflow with confirmed SQLite state persistence.
- Intent 2 (Security intake): NO — no security scan during onboarding. Gap confirmed.
- Intent 3 (Security gate): N/A.
- Intent 4 (Events): `workflow.completed` (2 events) and `workflow.node.completed` (25 events) in canonical_events. These appear to be backfilled from raw tables (event_id prefix: `backfill-activity-log-*`). PARTIAL — events exist but were backfilled, not emitted in real-time during execution.
- Intent 5 (Marker): No marker file reference. N/A.

**Notes:** This is the only workflow with confirmed real execution in the runtime database. The `discovery` failure on Run 1 (Unknown skill: ds-core:build) reveals that the workflow engine dispatches skill references by name and a naming mismatch causes a hard failure.

---

### 23. ui-feature.yaml

**What it is:** UI-aware feature pipeline — think → plan → build → polish (conditional on UI files changed) → review → verify → ship.

**What it does:** think (director gate) → plan (director gate) → build → polish (condition: UI files changed) → review → verify (evidence gate) → ship

**Current state:** DORMANT — no execution records.

**Evidence of recent use:** None.

**Steps:**
1. `think` — invokes `think` skill, director-approval gate (opus, 300s)
2. `plan` — invokes `plan` skill, director-approval gate (sonnet)
3. `build` — invokes `build` skill, retry max 1 (sonnet)
4. `polish` (condition: `{{build.ui_files_changed}} == true`) — invokes `polish` skill (sonnet)
5. `review` (trigger_rule: all_done, depends on build + polish) — invokes `review` skill (sonnet)
6. `verify` — invokes `verify` skill, evidence-required gate, retry max 1 (sonnet)
7. `ship` — invokes `ship` skill (sonnet)

**Intent Alignment:**
- Intent 1 (SQLite): No output persistence at all — no record/report node. NO.
- Intent 2 (Security intake): No security step. NO.
- Intent 3 (Security gate): No security step. NO.
- Intent 4 (Events): No canonical_events emission. NO.
- Intent 5 (Marker): No marker reference. N/A.

**Notes:** `ui-feature.yaml` has no terminal record/report node — it ends with `ship`. This is a PERSISTENCE_GAP: there is no record of what was built or shipped. Also has no security review, which is unusual for a workflow that ends in shipping code. Uses Opus for `think`.

---

## Special Focus: Security in SDLC Workflows

### Security Step Presence by Workflow

| Workflow | Has Security Step | Security Skills Referenced | Notes |
|---------|------------------|--------------------------|-------|
| production-readiness.yaml | YES | `verify` skill (drives 47-control catalog) | All nodes use `verify`; SQLite write in node 3 |
| security-audit.yaml | YES | `scan`, `dast`, `binary-scan`, `mitigate`, `comply`, `netcompat` | Full enterprise security pipeline |
| idea-to-pr.yaml | YES | `pr-security-scan` (node: review-security), `pr-security-scan` (node: triage-security), `mitigate` | Most complete security integration |
| comprehensive-review.yaml | YES | `pr-security-scan` (node: review-security) | Parallel review |
| project-audit.yaml | YES | `pr-security-scan` (node: secure) | Parallel audit |
| audit-to-fix.yaml | CONDITIONAL | `{{params.audit}}` — only if caller passes `audit=secure` | Not intrinsic; depends on invocation |
| daily-close.yaml | NO | none | Operational hygiene only |
| daily-standup.yaml | NO | none | Morning briefing only |
| domain-ingest.yaml | NO | none | Knowledge pipeline |
| domain-refresh.yaml | NO | none | Knowledge refresh |
| feature-research.yaml | NO | none | Research pipeline |
| fix-issue.yaml | NO | none | Bug fix — no security review |
| game-feature.yaml | NO | none | Game domain only |
| hotfix.yaml | NO | none | Intentional omission (speed) |
| optimize.yaml | NO (indirect) | none direct; reads prior security reports via `context-check` | Indirect seed only |
| pre-push.yaml | NO | none (atlas-leak is contract integrity, not security) | Gate workflow |
| prototype.yaml | NO | none | Intentional (fast/experimental) |
| safe-refactor.yaml | NO | none | Gap — refactors can introduce vulnerabilities |
| self-audit.yaml | NO | none | Internal housekeeping |
| studio-analytics.yaml | NO | none | N/A |
| studio-onboard.yaml | NO | none | **Gap confirmed** — brownfield onboarding has no security scan |
| ui-feature.yaml | NO | none | **Gap** — ships code without security review |
| client-deliverable.yaml | NO | none | **Gap** — client deliverables ship without security review |

### SDLC Security Coverage Assessment

**Workflows that ship code with NO security step:**
- `hotfix.yaml` (intentional, speed tradeoff)
- `safe-refactor.yaml` (unintentional — refactors can introduce vulnerabilities)
- `ui-feature.yaml` (unintentional — ships via `ship` skill with no security review)
- `client-deliverable.yaml` (unintentional — client work shipped without any security check)
- `prototype.yaml` (acceptable — prototype context)

**Summary:** 5 of the 9 SDLC-flavored workflows (those that end in code changes or PR creation) have no security step. Only `idea-to-pr.yaml` and `comprehensive-review.yaml` have explicit security reviews. `hotfix.yaml` and `prototype.yaml` are justifiable omissions. `safe-refactor.yaml`, `ui-feature.yaml`, and `client-deliverable.yaml` are unintentional gaps.

---

## Special Focus: Workflow Execution State — SQLite vs File

### workflows.json (current file-based state)

**Location:** `C:\Users\Dannis Seay\.dream-studio\state\workflows.json`

**Current content:**
```json
{
  "schema_version": 1,
  "active_workflows": {}
}
```

**Who writes it:** `control/execution/workflow/state.py` — `_write_state()` function writes to `paths.state_dir() / "workflows.json"`. Called by `workflow_state start`, `workflow_state update`, `workflow_state pause`, `workflow_state abort`.

**Format:** JSON with `schema_version` and `active_workflows` dictionary keyed by workflow run key. Each entry is a full state snapshot including all node statuses, gate states, and node outputs. Active workflows remain in this dict until terminal state (completed/aborted).

**Current active_workflows is empty:** Both studio-onboard runs are in terminal state and appear to have been removed from active_workflows (both are stored in `raw_workflow_runs`/`workflow_invocations` instead).

**Intent 1 alignment:** This is explicitly the v1 rot that the SQLite-first intent is meant to replace. State.py notes in its docstring that this is the primary state store. No automatic sync to SQLite during execution.

### workflow-checkpoint.json (current file-based state)

**Location:** `C:\Users\Dannis Seay\.dream-studio\state\workflow-checkpoint.json`

**Current content:**
```json
{
  "workflow_key": "wf-fail-1",
  "last_node": "n1",
  "status": "failed",
  "timestamp": "2026-05-20T21:59:02.080314+00:00"
}
```

**Who writes it:** `control/execution/workflow/state.py` — `_write_checkpoint()` function. Written on each node completion/failure.

**Purpose:** Crash recovery — records the last known node and status so interrupted workflows can resume. The value `wf-fail-1` / `n1` / `failed` is a test artifact (pytest wrote this), not a real workflow run.

**Intent 1 alignment:** File-based. Not in SQLite. Pure v1 rot.

### workflow_invocations (SQLite table — 2 rows)

**Schema:**
- `invocation_id` (TEXT, PK)
- `project_id`, `milestone_id`, `task_id`, `process_run_id`, `event_id` (TEXT, all nullable)
- `workflow_id` (TEXT, required)
- `status` (TEXT, required)
- `purpose` (TEXT, nullable)
- `metadata_json` (TEXT, required, default `'{}'`)
- `created_at` (TEXT, required, default `datetime('now')`)

**Current rows:** 2 rows, both for studio-onboard runs. The metadata_json contains the FULL node state snapshot — the same data that lives in workflows.json but serialized into the SQLite row. Both the `workflow_invocations` and `raw_workflow_runs` tables hold the same studio-onboard state.

**Why it has data:** The studio-onboard workflow itself called `py -m control.execution.workflow.state update <key> ...` which appears to have written to both the file state and triggered SQLite persistence. This is not a general mechanism — it was called explicitly by studio-onboard's nodes.

**Intended purpose:** SQLite-backed authority record of workflow invocations, replacing workflows.json. The table has a foreign-key-style relationship to projects/milestones/tasks but all those FK fields are NULL — the invocations are not linked to project management records.

### raw_workflow_runs / raw_workflow_nodes (SQLite — 2/25 rows)

**raw_workflow_runs schema:** `run_id` (INT PK), `run_key` (TEXT unique), `workflow_name`, `yaml_path`, `status`, `started_at`, `ended_at`, `total_nodes`, `completed_nodes`, `estimated_tokens`, `actual_tokens`, `cost_usd`

**raw_workflow_nodes schema:** `node_id` (INT PK), `run_key` (FK), `node_name`, `status`, `started_at`, `finished_at`, `duration_s`, `output_summary`, `canonical_event_id`

**Are these the same system as workflows.json?** Different path. `raw_workflow_runs` and `raw_workflow_nodes` appear to be an analytics/telemetry ingest layer that receives backfilled data. The `canonical_event_id` column links each node to a `canonical_events` entry. The 25 node entries in `raw_workflow_nodes` match exactly the 25 `workflow.node.completed` entries in `canonical_events` (all prefixed `backfill-activity-log-*`), confirming these were written by a backfill process, not by the workflow runner directly.

**The two SQLite paths:**
1. `workflow_invocations` — written by studio-onboard's explicit `py -m control.execution.workflow.state update` calls during node execution. This is the intended live-write path.
2. `raw_workflow_runs` + `raw_workflow_nodes` + `canonical_events` — written by a backfill process after the fact (event_id prefix pattern confirms this).

**Conclusion:** There are TWO separate SQLite systems for workflow state:
- `workflow_invocations` = the intended authority table (project-linked, live-write via state CLI)
- `raw_workflow_runs/nodes` = the analytics telemetry layer (backfill-based, linked to canonical_events)

These are not synchronized. The `workflows.json` file remains the live state store during execution, with SQLite receiving data either via explicit node-level CLI calls (studio-onboard pattern) or post-hoc backfill. No general mechanism auto-writes workflow state to SQLite during execution.

---

## Findings

1. **23 workflow files in canonical/workflows/ but studio-onboard expects 22.** The `baseline-fetch` node in the completed studio-onboard run reported "22 workflows" in its output summary. There are now 23. One workflow was added after the 2026-05-18 onboarding run.

2. **22 of 23 workflows are DORMANT.** Only `studio-onboard.yaml` has confirmed execution history. All other workflows exist as definitions only.

3. **The most important SDLC workflow has never run.** `production-readiness.yaml` is the intended production gate with SQLite persistence and the 47-control security catalog, yet has zero execution records.

4. **Brownfield onboarding (studio-onboard) has no security scan.** Intent 2 states security runs during project intake. The studio-onboard workflow, which ran twice, never invokes any security skill. The improvement-scan node flagged TRACKING_GAP in other workflows but did not trigger a security scan of the user's own environment.

5. **Pre-push gate has no security check.** The 6-gate pre-push chain (format, lint, skill-sync, evals, atlas-leak, docs-drift) does not include a security scan. Code can reach push state without any security review.

6. **workflows.json is still the live state store.** The SQLite-first intent is not implemented for general workflow execution. The file `~/.dream-studio/state/workflows.json` is the authoritative runtime state. SQLite receives data only via (a) studio-onboard's explicit self-update calls or (b) post-hoc backfill.

7. **workflow-checkpoint.json contains a test artifact.** The current content references `wf-fail-1`/`n1`/`failed` — written by pytest, not a real workflow run. This is state directory pollution from tests.

8. **CronCreate scheduling bug in self-audit.** The `schedule-self-audit` node in studio-onboard registered the cron with `prompt=workflow: studio-onboard` instead of `prompt=workflow: self-audit`. The weekly Monday cron will re-run studio-onboard, not self-audit.

9. **client-deliverable.yaml ships client work without security review.** No security step at any point before the PR creation gate.

10. **ui-feature.yaml has no persistence node.** It ends with `ship` — no record/report node saves what was built or shipped.

11. **safe-refactor.yaml has no security step.** Refactors can introduce vulnerabilities. This is an unintentional gap versus the intentional omission in hotfix.yaml.

12. **fix-issue.yaml uses Unix-only bash syntax.** The `create-issue` node uses `` head -1 <<< '...' `` which fails on Windows PowerShell (the user's platform).

13. **feature-research.yaml reads workflows.json during intake.** The `intake` node reads `~/.dream-studio/state/workflows.json` — creating a dependency on the file-based state format that would break if the file is migrated to SQLite-only.

14. **canonical_events workflow entries are all backfilled.** The 2 `workflow.completed` and 25 `workflow.node.completed` events have event_id prefix `backfill-activity-log-*` — they are not emitted in real-time by the workflow runner. Intent 4 (canonical events as spine) is not satisfied for workflow execution.

---

## Intent Divergence

| Intent | Status | Gap |
|--------|--------|-----|
| 1 — SQLite-first authority | DIVERGED | workflows.json is the live state store. SQLite receives data via explicit node-level calls or backfill. No general auto-write during execution. |
| 2 — Security during brownfield onboarding | NOT IMPLEMENTED | studio-onboard has no security node. The 2 confirmed runs both skipped security scanning. |
| 3 — Security gate in SDLC | PARTIAL | production-readiness.yaml IS the intended gate but has 0 executions. idea-to-pr.yaml is functional when used. 3 shipping workflows (safe-refactor, ui-feature, client-deliverable) have no security step. |
| 4 — Canonical events as spine | NOT SATISFIED for workflows | Workflow events exist in canonical_events but are backfilled, not real-time. No workflow YAML emits events during node execution. |
| 5 — Marker file authority | N/A | No workflow references .dream-studio-project markers. Not relevant to this subsystem. |

---

## Open Questions

1. Which of the 23 workflows was added after the 2026-05-18 onboarding run (that expected 22)?

2. Is the `schedule-self-audit` CronCreate bug (wrong prompt value) already known? The weekly cron fires next Monday and will run studio-onboard again instead of self-audit.

3. `production-readiness.yaml` uses only the `verify` skill for all 5 nodes. Is this intentional — meaning the `verify` skill internally routes to the 47-control catalog? Or is this a placeholder where the nodes should invoke specific security skills?

4. `pre-push.yaml` uses a structurally different format (`gates:` block, not `nodes:`). Is this workflow run by the same engine as all others? Or does `core/gates/pre_push.py` handle it independently?

5. What backfill process writes to `raw_workflow_runs`/`raw_workflow_nodes`/`canonical_events`? When does it run? Is it the `ds spool ingest` command?

6. The `workflow_invocations` table has FK columns (`project_id`, `milestone_id`, `task_id`) that are all NULL in the 2 rows. When are these expected to be populated?

7. `fix-issue.yaml` uses `` head -1 <<< `` bash syntax — is there a Windows-compatible version of this workflow, or is it a known Windows portability issue?
