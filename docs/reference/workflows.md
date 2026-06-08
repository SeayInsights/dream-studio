# Dream Studio Workflows Reference

Complete catalog of all 25 canonical workflows.

**Source:** `canonical/workflows/`  
**Invocation:** `ds workflow run <slug>` or via `ds-workflow` skill  
**State:** `~/.dream-studio/state/workflows.json`

---

## Workflow Catalog

### `audit-to-fix`
Generic audit → synthesize → plan → build → verify → report chain. Parameterized by audit type.

**Phases:** audit → synthesize → plan → approve _(gate: director-approval)_ → build → verify → report  
**Notes:** Uses retry logic on build (max 1), output compression on synthesize. Parameterized by audit type: `harden`, `secure`, `structure-audit`, `scan`.

---

### `client-deliverable`
Client delivery pipeline for Power BI, Power Automate, Power Apps deliverables.

**Phases:** intake → plan → build → validate → screenshot → summary → deliver _(gate: director-approval)_  
**Notes:** Deliverable-type-specific validation, Playwright-based screenshot capture. Gate on Director approval before commit.

---

### `comprehensive-review`
Five-way parallel review with synthesis report.

**Phases:** review-code, review-security, review-tests, review-perf, review-docs _(parallel)_ → synthesize → report  
**Notes:** All reviews run in parallel. Creates GitHub Issues for HIGH/CRITICAL findings.

---

### `daily-close`
End-of-day routine — harvest daily learnings, check WIP, audit memory, produce day summary.

**Phases:** daily-learn, check-wip, memory-check _(parallel)_ → day-summary  
**Notes:** `on_failure: continue` on all nodes — never blocks close.

---

### `daily-standup`
Morning briefing — check open PRs, pending lessons, latest handoff, stale research.

**Phases:** check-prs, check-lessons, check-handoffs, check-research _(parallel)_ → synthesize _(gate: priorities-confirmed)_  
**Notes:** Reads GitHub PR state and project state to build the morning briefing.

---

### `domain-ingest`
4-phase domain synthesis pipeline — find sources, score, synthesize YAML + persona MD, register.

**Phases:** find-sources → score-and-compare → synthesize → register _(gate: director-review)_  
**Notes:** Uses GitHub code search and `ds-analyze`. Writes to `ingest-log.yml`.

---

### `domain-refresh`
Automated re-synthesis of stale domain agents.

**Phases:** scan → re-synthesize _(conditional)_ → update-dates → commit  
**Notes:** Reads `ingest-log.yml` to find overdue entries. Commits updated refresh dates.

---

### `execute-work-orders`
Autonomous work-order execution loop — implements tasks, gates, PRs, merges, closes, advances.

**Phases:** capability-probe → preflight-check → migration-class-check → implement-tasks → run-gates → create-branch _(conditional)_ → push-and-pr _(conditional)_ → watch-ci _(conditional)_ → merge _(conditional)_ → close-work-order-github / close-work-order-local → next-iteration  
**Notes:** Conditional GitHub path (skipped if not available). Checks migration risk. Watches all 3 CI platforms before merge.

---

### `feature-research`
GitHub research pipeline for any Claude feature, integration, MCP server, hook, skill, or plugin.

**Phases:** intake → research-repos, research-issues, research-prs, research-code _(4 parallel)_ → research-synthesis _(gate: post-synthesis)_ → breakpoint-analysis, gap-analysis _(parallel)_ → implementation-plan, risk-matrix _(parallel)_ → mission-briefing _(gate: mission-commander)_ → final-report  
**Notes:** Two director gates (post-synthesis and mission-commander). Extensive multi-phase research workflow.

---

### `fix-issue`
Diagnose a bug, plan a fix, implement, review, and verify. Resume-safe.

**Phases:** diagnose → create-issue → write-failing-test _(conditional)_ → plan-fix → implement-fix _(gate: director-approval)_ → review _(gate: auto-pass)_ → verify _(gate: evidence-required)_ → report  
**Notes:** Conditional test write. Auto-pass gate on quality score. Creates GitHub issue. Resume-safe: re-run to continue from last completed node.

---

### `game-feature`
Game feature from design through implementation with Godot-specific QA.

**Phases:** think _(gate: director-approval)_ → plan _(gate: director-approval)_ → build → review-gameplay, review-data, validate-engine _(parallel)_ → synthesize → fix-findings _(conditional)_ → verify _(gate: qa-gate)_ → record  
**Notes:** Godot-specific engine validation. Review synthesis with severity filtering. Conditional fix task.

---

### `hotfix`
Fast debug-fix-verify cycle for production issues.

**Phases:** debug → build _(retry: max 1)_ → verify _(gate: evidence-required)_ → ship → record  
**Notes:** Minimal gates optimized for speed. Logs hotfix PRs to persistent state file.

---

### `idea-to-pr`
Feature concept through implementation to merged PR.

**Phases:** think _(gate: director-approval)_ → plan _(gate: director-approval)_ → build _(gate: auto-pass)_ → review-code, review-security, review-tests, review-perf, review-docs _(5 parallel)_ → synthesize → fix-findings _(conditional)_ → triage-security _(conditional)_ → mitigate-findings _(conditional)_ → verify _(gate: evidence-required)_ → ship → record  
**Notes:** Complex review synthesis with conditional security triage. Logs merged PR to `idea-to-pr.log`.

---

### `optimize`
Profile, audit, and reduce bloat — bundle size, dead code, deps, infra, queries — with baseline measurement.

**Phases:** context-check → profile → audit-deps, audit-code, audit-infra _(conditional)_, audit-queries _(conditional)_ → synthesize → plan _(gate: director-approval)_ → apply → verify _(gate: evidence-required)_ → report  
**Notes:** 8-stage pipeline. Conditional audits based on project type. Creates GitHub Issues for Priority 1–2 findings.

---

### `pre-push`
Pre-push gate definitions that block `git push` on regressions.

**Phases:** _No execution nodes — pure gate definitions_  
**Gates:**

| Gate | Tier | Checks |
|------|------|--------|
| `format-check` | blocking | Black formatting |
| `lint-check` | blocking | Lint baseline |
| `skill-sync` | blocking | Source-skill integrity |
| `test-suite` | blocking | Eval test suite |
| `atlas-leak` | blocking | Contract Atlas leakage |
| `docs-drift` | advisory | WORKFLOW_RUNTIME.md + HOOK_RUNTIME.md review markers |
| `migration-risk` | escalation | Prints matrix-watch reminder; blocks push until acknowledged |

---

### `production-readiness`
Secure production readiness: classify impact, select controls, run reviews, persist records, route remediation WOs.

**Phases:** classify-impact → build-gate → persist-authority-records → project-dashboard-hydration → remediation-routing  
**Notes:** Enterprise security controls. SQLite persistence. No external project mutation allowed.

---

### `project-audit`
Full project audit — harden, secure, review — run in parallel with one director gate before report.

**Phases:** harden, secure, review _(3 parallel)_ → report _(gate: review-findings)_  
**Notes:** Synthesizes findings with severity filtering. Creates GitHub Issues for HIGH/CRITICAL.

---

### `prototype`
Fast prototype — think then build, skip formal review. For game jams and quick experiments.

**Phases:** think _(gate: director-approval)_ → build → verify → snapshot  
**Notes:** Minimal gates. Saves prototype snapshot to persistent state with known limitations.

---

### `safe-refactor`
Plan a refactor, implement, validate with type checks and tests, review, and verify.

**Phases:** plan-refactor _(gate: director-approval)_ → implement → type-check, test _(parallel)_ → review _(gate: auto-pass)_ → verify _(gate: evidence-required)_ → report  
**Notes:** Type and test validation before review. Session-scoped reporting.

---

### `security-audit`
Enterprise security analysis pipeline — intake, custom rules, DAST, binary scan, mitigate, comply, netcompat, Power BI dashboard, executive report.

**Phases:** intake → generate-rules, dast-scan, binary-scan _(3 parallel)_ → ingest-scans _(gate: post-scan-review)_ → mitigate, comply, netcompat-analyze _(3 parallel)_ → analysis-sync _(gate: pre-dashboard)_ → generate-dashboard → executive-report  
**Notes:** Enterprise-grade. 3 parallel analysis branches. Power BI dataset generation.

---

### `self-audit`
Audit Dream Studio's own internals — noisy hooks, dead routing rules, oversized SKILL.md files, duplicated gotchas.

**Phases:** collect-signal → audit-hooks, audit-routing, audit-skill-size, audit-gotchas _(4 parallel)_ → synthesize → publish-and-reschedule  
**Notes:** Self-referential audit. Uses CronCreate for weekly scheduling. Publishes GitHub issue.

---

### `studio-analytics`
Interactive analytics dashboard setup and launch.

**Phases:** mode-detect → healthcheck _(gate: post-healthcheck)_ → bootstrap → harvest _(gate: post-harvest)_ → launch  
**Notes:** Supports Guided (default) and Auto modes. Initializes DB and launches FastAPI server at `http://localhost:8000/dashboard`.

---

### `studio-onboard`
Dream Studio onboarding audit — discover environment, compare against baseline, plan fixes, produce onboarding report.

**Phases:** config-setup → discovery _(gate: post-discovery)_ → baseline-fetch → breakpoint-analysis, gap-analysis, improvement-scan _(3 parallel)_ → synthesis _(gate: post-synthesis)_ → fix-plan, risk-matrix _(2 parallel)_ → mission-briefing-generate _(gate: mission-commander)_ → mission-briefing-approve → final-report → smoke-test → schedule-self-audit  
**Notes:** 22 nodes. 4-layer readiness scoring. 12-point smoke test suite. CronCreate integration for self-audit scheduling.

---

### `ui-feature`
UI-aware feature pipeline — think → plan → build → polish (conditional) → review → verify → ship.

**Phases:** think _(gate: director-approval)_ → plan _(gate: director-approval)_ → build → polish _(conditional: ui_files_changed)_ → review → verify _(gate: evidence-required)_ → ship  
**Notes:** Polish phase only runs when build touches `.tsx`, `.vue`, `.svelte`, `.astro`, `.css` files. Uses `estimated_tokens` for model routing.

---

## Gate Types

| Gate | Behavior |
|------|----------|
| `director-approval` | Pauses execution; requires operator confirmation to proceed |
| `auto-pass` | Passes automatically based on quality score threshold |
| `evidence-required` | Requires concrete evidence artifact (test output, diff) before proceeding |
| `post-synthesis` | Pauses after research synthesis for direction confirmation |
| `mission-commander` | Final human gate before mission briefing is committed |
| Advisory gates | Surface signals without blocking execution |

---

## Cross-references

- Invoking workflows: [`docs/reference/cli.md`](cli.md) — `ds workflow` commands
- Hooks that monitor workflows: [`docs/reference/hooks.md`](hooks.md) — `on-workflow-progress`
- Events emitted: [`docs/reference/events.md`](events.md) — `workflow.*` types
