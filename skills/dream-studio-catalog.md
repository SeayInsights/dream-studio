# Dream-Studio Skill Catalog

**Generated:** 2026-04-29 07:03
**Total Skills:** 38

---

## Skills by Pack
### Analyze Pack (2 skills)
- **analyze** (v1.0.0) — tested, active ✅
  Multi-perspective analysis engine — parallel analyst subagents evaluate input from different angles, then synthesis resolves conflicts into a decision memo. Trigger on /analyze or analyze:.

- **domain-re** (v1.0.0) — tested, active ✅
  Real estate domain expert — parallel analyst lenses (forensic skeptic, diplomatic executor, strategic realist) evaluate leases, credit, renewals, and portfolio risk. Trigger on /domain-re or re:.

### Career Pack (6 skills)
- **career-apply** (v1.0.0) — tested, active ✅
  Live application assistant (form fill + answer generation) and batch processing. Modes: apply (single), batch (parallel workers). Trigger via /career-ops apply or /career-ops batch.

- **career-evaluate** (v1.0.0) — tested, active ✅
  Evaluate job offers, freelance gigs, or compare multiple opportunities. Modes: auto-pipeline, oferta, ofertas, gig, proposal, sow. Trigger via /career-ops routing.

- **career-ops** (v1.0.0) — tested, active ✅
  AI job search command center — routes to career sub-skills (evaluate, scan, apply, track, pdf). Trigger on /career-ops or career-related commands.

- **career-pdf** (v1.0.0) — tested, active ✅
  Generate ATS-optimized CV PDFs and LinkedIn outreach messages. Modes: pdf (CV generation), contacto (LinkedIn outreach). Trigger via /career-ops pdf or /career-ops contact.

- **career-scan** (v1.0.0) — tested, active ✅
  Scan job portals for new offers, deduplicate against history, add to pipeline. Always runs as subagent (long-running, Playwright-dependent). Trigger via /career-ops scan.

- **career-track** (v1.0.0) — tested, active ✅
  Pipeline management, application tracking, pattern analysis, and follow-up cadence. Modes: tracker, pipeline, patterns, followup. Trigger via /career-ops tracker|pipeline|patterns|followup.

### Core Pack (9 skills)
- **build** (v1.0.0) — tested, active ✅
  Execute a plan with subagent-driven development — fresh agent per task, two-stage review, isolated context, parallel wave execution. Trigger on `build:`, `execute plan:`, or after `plan`.

- **explain** (v1.0.0) — draft, active ✅
  Trace how X works — from entry point through layers to output, at the depth the Director needs.
  Triggers: "explain:", "how does", "walk me through"

- **handoff** (v1.0.0) — tested, active ✅
  Session continuity — capture structured state (current task, progress, phase, decisions, active files, next action) to both markdown and JSON. A fresh session resumes from the file alone. Trigger on `handoff:`, at compact threshold, or session end with WIP.

- **plan** (v1.0.0) — tested, active ✅
  Break an approved spec into atomic, dependency-ordered tasks with per-task acceptance criteria. Trigger on `plan:` or after `think` is approved.

- **recap** (v1.0.0) — tested, active ✅
  Capture structured build memory — what was built, decisions, risks, stack, remaining work, next step — to `.sessions/YYYY-MM-DD/recap-<topic>.md`. Trigger on `recap:`, `session recap:`, or auto after substantive builds (3+ files, multi-task plans).

- **review** (v1.0.0) — tested, active ✅
  Two-stage quality check — spec compliance first (did we build what was asked?), then code quality (is it well-built?) — with severity-tagged findings. Trigger on `review:`, `review code`, or after `build`.

- **ship** (v1.0.0) — tested, active ✅
  Pre-deploy gate — audit (a11y, perf, technical), harden (error/empty/loading states), optimize (bundle/render/animation/images), test (Playwright + regression). Any FAIL blocks deploy. Trigger on `ship:`, `pre-deploy:`, `deploy:`, or before any deployment command.

- **think** (v1.0.0) — tested, active ✅
  Clarify an idea, explore 2-3 approaches with trade-offs, write a spec, and get approval before any code. Trigger on `think:`, `spec:`, `shape ux:`, `design brief:`, `research:`.

- **verify** (v1.0.0) — tested, active ✅
  Evidence-based verification — run the app, test golden path + edges, capture proof (screenshots, logs, Playwright results), check regressions. Trigger on `verify:`, `prove it:`, or after `review` passes.

### Domains Pack (6 skills)
- **client-work** (v1.1.0) — tested, active ✅
  Power Platform client lifecycle — intake, SOW, build (Power BI, Power Apps, Power Automate), review, handoff — with DAX/M-query patterns, delegation rules, .pbip/TMDL format, and flow error handling.
  Success: 70% (3 uses) | Tokens: 0 avg

- **dashboard-dev** (v1.0.0) — tested, active ✅
  Tauri + React desktop dashboard patterns — feed contract (hooks write JSON, dashboard reads), multi-panel architecture, additive schema evolution. Trigger on `dashboard:`, `feed contract:`, or related dashboard-dev commands.

- **design** (v1.0.0) — tested, active ✅
  Visual design capability — brand tokens, anti-slop rules, visual hierarchy, generative art (p5.js), theme application to projects, and ad-creative guidance. Trigger on `design art:`, `design poster:`, `canvas:`, `generative art:`, `apply theme:`, `brand:`, `ad creative:`, and related commands.

- **game-dev** (v1.0.0) — tested, active ✅
  Godot 4 consolidated patterns — 2D/3D player controllers, scene hierarchies, CSG blockouts, Blender→GLB pipeline with QA gates, two-tier automated/manual QA, and game design scaffolding. Trigger on any game build, review, QA, design, or asset-pipeline command.

- **mcp-build** (v1.0.0) — tested, active ✅
  4-phase MCP server development — research, implement (Zod schemas, structured errors, stdio/SSE transport), test (valid/invalid/edge), evaluate. Trigger on `build mcp:`, `new mcp:`, `extend mcp:`.

- **saas-build** (v1.0.0) — tested, active ✅
  React 19 + React Router 7 + Cloudflare Workers + D1/Kysely stack patterns for SaaS builds — API contract-first, loaders/actions, migrations, CI-only deploys. Trigger on `build feature:`, `build api:`, `build page:`, `deploy:`, `build supabase:`, and related web commands.

### Meta Pack (1 skills)
- **workflow** (v1.0.0) — tested, active ✅
  YAML workflow orchestration — validate, execute DAG nodes through existing skills with gates and parallel spawning, track state via CLI. Trigger on `workflow:`, `workflow status`, `workflow resume`, `workflow abort`.

### Quality Pack (11 skills)
- **coach** (v1.0.0) — tested, active ✅
  Claude Code workflow coach — evaluates HOW you're using Claude Code, not WHAT you're building. Surfaces non-obvious best practices for context management, PR hygiene, agent dispatch, and skill routing. Trigger on /coach or coach:.

- **comply** (v1.0.0) — tested, active ✅
  Map findings to SOC 2, NIST CSF, OWASP ASVS controls. Identify coverage gaps. Generate audit-ready evidence. Trigger on comply:, compliance map, audit evidence.

- **debug** (v1.0.0) — tested, active ✅
  Systematic problem solving — reproduce, hypothesize, test one variable at a time, narrow, fix, document. No shotgun debugging. Trigger on `debug:`, `diagnose:`, or on build/verify failure.

- **harden** (v1.0.0) — tested, active ✅
  Project hardening audit and fix — checks 20 best-practice items (Makefile, pyproject.toml, UTC enforcement, Pydantic validation, SECURITY.md, CONTRIBUTING.md, test tooling, audit log, pre-commit, etc.) and fills gaps from templates. Trigger on `/harden`, `/harden audit`, `/harden fix tier1`, `/harden fix #N`.

- **learn** (v1.0.0) — tested, active ✅
  Capture and promote lessons from builds — draft to `meta/draft-lessons/`, Director review, promote to memory / skill / agent updates, archive to `meta/lessons/`. Trigger on `learn:`, `capture lesson:`, or when something notably works or breaks.

- **mitigate** (v1.0.0) — tested, active ✅
  Per-finding fix recommendations with code before/after, verification tests, effort estimates. Trigger on mitigate:, how to fix, generate mitigations.

- **netcompat** (v1.0.0) — tested, active ✅
  Zscaler/proxy compatibility analysis — detect cert pinning, custom SSL, non-standard ports, DLP conflicts. Trigger on netcompat:, zscaler check, proxy compat.

- **polish** (v1.0.0) — tested, active ✅
  UI quality decision tree — critique seven dimensions (layout, typography, color, animation, copy, responsive, edge cases), score 1-5, fix by priority, re-score. Trigger on `polish ui:`, `critique design:`, `redesign:`, `make it premium:`, or auto after `build page:`/`build component:`.

- **scan** (v1.0.0) — tested, active ✅
  Security scanning orchestrator — generates GitHub Actions workflows and Semgrep custom rules from client profiles, ingests SARIF/JSON results into structured storage, and reports scan coverage across a client's GitHub org. Trigger on scan:, scan org:, run security scan.

- **secure** (v1.0.0) — tested, active ✅
  Security review — parallel OWASP+STRIDE analyst subagents produce severity-tagged findings with specific fixes. Trigger on secure:, /secure, check security, review architecture, or PRs touching auth/payments/user data/APIs.

- **structure-audit** (v1.0.0) — tested, active ✅
  No description

### Security Pack (3 skills)
- **binary-scan** (v1.0.0) — tested, active ✅
  Binary/executable analysis — checksec hardening, YARA malware signatures, PE/ELF metadata extraction. Trigger on binary-scan:, scan binary, analyze exe, checksec.

- **dast** (v1.0.0) — tested, active ✅
  Web application dynamic testing — generate ZAP/Nuclei configs, ingest DAST results, score web-specific vulnerabilities. Trigger on dast:, web scan, pen test web, zap scan.

- **security-dashboard** (v1.0.0) — tested, active ✅
  ETL orchestration + Power BI dataset export — runs the full security ETL pipeline (SARIF → scored → compliance-mapped → mitigated → Power BI CSVs), calculates org risk score from client profile weights, and manages the Power BI template lifecycle. Trigger on security dashboard:, refresh dashboard, export dataset.


---

## Quality Metrics
### Top 10 by Success Rate
1. **client-work** — 70% (3 uses) ⚠️

### Top 10 by Token Usage (avg)
1. **client-work** — 0 tokens (light)

### Top 10 by Usage Count
1. **client-work** — 3 uses


---

## Dependency Graph
### Core Module Usage
- **core/format.md** → 5 skills: build, plan, review, ship, verify
- **core/git.md** → 5 skills: build, plan, review, ship, verify
- **core/orchestration.md** → 2 skills: build, review
- **core/quality.md** → 4 skills: build, review, ship, verify
- **core/traceability.md** → 3 skills: build, plan, verify

### Tool Dependencies
- **gh** → 5 skills
- **git** → 5 skills


---

## Health Dashboard
### By Health Status
- Active: 38 skills ✅
- Maintenance: 0 skills ⚠️
- Deprecated: 0 skills ❌

### By Development Status
- Stable: 0 skills
- Tested: 37 skills
- Experimental: 0 skills
- Deprecated: 0 skills

