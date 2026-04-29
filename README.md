# dream-studio

[![CI](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.10.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-73%25-green.svg)](pyproject.toml)

An opinionated Claude Code plugin that adds a **Build Pipeline**, **38 skills**, automated hooks, agent personas, and a context-aware status bar — portable across every project.

---

## Table of Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Skills](#skills)
- [Hooks](#hooks)
- [Status Bar](#status-bar)
- [Workflows](#workflows)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## What it does

dream-studio wraps Claude Code with a structured developer workflow:

- **Think → Plan → Build → Review → Verify → Ship** — a gated pipeline that prevents skipping steps
- **Context budget management** — warns at 65%, hands off at 75%, blocks at 82% with progressive messaging and auto-handoff notes
- **Session memory** — structured handoff notes and recaps written automatically to `.sessions/<date>/`
- **Project health** — pulse checks, CI status, stale branch detection, and a draft lesson queue
- **Domain skills** — Godot 4, SaaS (React 19 + Cloudflare Workers), Power Platform, MCP servers, career ops

---

## Requirements

| Requirement | Version |
|---|---|
| Claude Code | latest |
| Python | 3.10, 3.11, or 3.12 |
| OS | Windows, macOS, Linux |

> Python 3.14+ is not recommended — use 3.12 for full compatibility.

---

## Installation

**From GitHub (recommended — works now):**

```bash
claude plugin install github:SeayInsights/dream-studio
```

**From source (local clone):**

```bash
git clone https://github.com/SeayInsights/dream-studio.git
claude plugin install file://path/to/dream-studio
```

> **Note:** dream-studio is not yet listed in the official Claude Code plugin registry.
> Use the GitHub install command above. Registry install (`claude plugin install dream-studio`) will not work until the plugin is submitted to Anthropic.

**After installing, merge the project hooks into your global settings:**

The `.claude/settings.json` in this repo contains PreToolUse guard hooks (blocks direct pushes to main, force-push, and wrangler deploy). Merge these into your global `~/.claude/settings.json` so they apply across all your projects:

```bash
# View the hooks to add:
cat path/to/dream-studio/.claude/settings.json
# Then manually merge the "hooks" block into ~/.claude/settings.json
```

Skill usage metrics are collected automatically via `hooks/hooks.json` at the plugin level — no extra setup needed.

**Install dev dependencies (for contributing):**

```bash
make install-dev
# or: pip install -r requirements-dev.txt
```

---

## Bundled Specialists

dream-studio ships with 9 synthesized specialist agents in the `agents/` directory. Copy them to Claude Code's agent directory and they auto-invoke on matching tasks:

**Unix / macOS**
```bash
cp agents/* ~/.claude/agents/
```

**Windows (PowerShell)**
```powershell
Copy-Item agents\* $HOME\.claude\agents\
```

| Agent | Domain | Keywords |
|---|---|---|
| `kubernetes-expert` | Infrastructure | k8s, pod, helm, kubectl, cluster |
| `devops-engineer` | Infrastructure | GitHub Actions, CI/CD, OIDC, Docker |
| `terraform-architect` | Infrastructure | Terraform, IaC, state, modules |
| `mobile-developer` | Mobile | iOS, Android, React Native, Flutter |
| `data-engineer` | Data | dbt, Snowflake, BigQuery, Airflow |
| `research-analyst` | Research | market research, competitive analysis |
| `idea-validator` | Research | idea validation, go/no-go, fatal flaw |
| `accessibility-expert` | Quality | WCAG, ARIA, screen reader, a11y |
| `technical-writer` | Quality | docs, Diataxis, API reference |

Stale agents are flagged by the on-pulse hook. Re-synthesize with `workflow: domain-refresh`.

---

## Quick Start

Once installed, dream-studio activates automatically in every Claude Code session.

**First time? Run the onboarding walkthrough:**

```
workflow: run studio-onboard
```

This audits your setup, customises dream-studio to your project, and walks you through the Director profile (name, domain, primary use). Run it once after install — subsequent sessions skip it automatically once your profile is set.

```
/think   Shape a feature idea into a spec
/plan    Break the approved spec into ordered tasks
/build   Execute the plan with subagent-per-task
/review  Two-stage quality check
/verify  Evidence-based proof it works
/ship    Pre-deploy gate — blocks on any FAIL
```

**Harden a project** (run once to scaffold missing standards files):

```
/harden
```

**Run the test suite:**

```bash
make test
```

---

## Skills

Skills are invoked as `/skill-name` or via natural-language triggers listed below.

### Build Pipeline

| Skill | Trigger | What it does |
|---|---|---|
| `think` | `/think`, `think:`, `spec:` | Clarify + spec an idea; get explicit approval before any code |
| `plan` | `/plan`, `plan:` | Break an approved spec into atomic, dependency-ordered tasks |
| `build` | `/build`, `build:`, `execute plan:` | Execute plan with a fresh subagent per task, parallel wave execution |
| `review` | `/review`, `review:` | Two-stage check: spec compliance first, then code quality |
| `verify` | `/verify`, `verify:` | Evidence-based verification with screenshots + Playwright results |
| `ship` | `/ship`, `ship:`, `pre-deploy:` | Pre-deploy gate: a11y, perf, error states, regression — any FAIL blocks |

### Code Quality

| Skill | Trigger | What it does |
|---|---|---|
| `debug` | `/debug`, `debug:`, `diagnose:` | Reproduce → hypothesize → test one variable at a time → fix |
| `explain` | `explain:`, `how does X work`, `walk me through` | Trace entry point through layers to output; depth adapts to the question |
| `polish` | `/polish`, `polish ui:`, `critique design:` | Critique 7 UI dimensions (layout, typography, color…), scored 1–5 |
| `secure` | `/secure`, `secure:`, `check security` | OWASP Top 10 checklist + STRIDE threat model |
| `analyze` | `/analyze` | Parallel multi-perspective analyst subagents → synthesized decision memo |

### Security

| Skill | Trigger | What it does |
|---|---|---|
| `scan` | `scan org:`, `run security scan` | SAST scanning — Semgrep rule generation, scan execution, SARIF ingestion |
| `dast` | `dast:`, `web scan`, `zap scan` | DAST scanning — ZAP + Nuclei setup, run, ingest for web app targets |
| `binary-scan` | `binary-scan:`, `scan binary`, `checksec` | Binary analysis — checksec + YARA + strings against compiled artifacts |
| `mitigate` | `mitigate:`, `how to fix` | Generate fix snippets + effort estimates for every finding |
| `comply` | `comply:`, `compliance map` | Map findings → SOC 2, NIST CSF, OWASP ASVS controls; identify gaps |
| `netcompat` | `netcompat:`, `zscaler check` | Detect cert pinning, custom TLS, non-standard ports that break enterprise proxies |
| `security-dashboard` | `security dashboard:`, `export dataset` | ETL pipeline → Power BI-ready CSVs (findings, mitigations, compliance, risk scores) |

### Domain

| Skill | Trigger | What it does |
|---|---|---|
| `game-dev` | game build/QA/design commands | Godot 4: controllers, scenes, CSG blockouts, Blender→GLB pipeline, QA gates |
| `saas-build` | `build feature:`, `build api:`, `build page:` | React 19 + React Router 7 + Cloudflare Workers + D1/Kysely |
| `mcp-build` | `build mcp:`, `new mcp:`, `extend mcp:` | 4-phase MCP server dev: research → implement → test → evaluate |
| `dashboard-dev` | `dashboard:`, `feed contract:` | Tauri + React desktop dashboards, feed contract pattern |
| `client-work` | `intake:`, `build report:`, `build app:`, `build flow:` | Power BI, Power Apps, Power Automate — DAX/M-query + delegation rules |
| `design` | `design art:`, `canvas:`, `apply theme:`, `brand:` | Brand tokens, p5.js generative art, theme application, ad creative |

### Session & Meta

| Skill | Trigger | What it does |
|---|---|---|
| `handoff` | `handoff:`, auto at context limit | Structured state capture (task, progress, decisions, next action) for continuity |
| `recap` | `recap:`, auto after builds | Build memory snapshot — decisions, risks, stack, remaining work |
| `learn` | `learn:`, `capture lesson:` | Draft → Director review → promote to memory / skill / agent updates |
| `workflow` | `workflow:`, `workflow status`, `workflow resume` | YAML DAG orchestration with gates and parallel node spawning |
| `harden` | `/harden` | 20-item project audit + gap-fill from `templates/project-standards/` |
| `structure-audit` | `/structure-audit` | Folder structure audit scored against FSC + architecture conventions |
| `coach` | `/coach`, `coach:` | Workflow coaching — evaluates workflow-fit, context-health, pr-hygiene, agent-dispatch; `route-classify` mode maps unmatched intents to the nearest skill |

### Career Ops

`/career-ops` routes to sub-skills:

| Sub-skill | Mode | What it does |
|---|---|---|
| `career-scan` | `scan` | Scrape job portals, deduplicate against history, add to pipeline |
| `career-evaluate` | `evaluate`, `oferta`, `gig` | Score offers, freelance gigs, proposals |
| `career-apply` | `apply`, `batch` | Form fill + answer generation (single job or parallel batch) |
| `career-track` | `tracker`, `pipeline`, `patterns`, `followup` | Pipeline management + follow-up cadence |
| `career-pdf` | `pdf`, `contact` | ATS-optimized CV generation + LinkedIn outreach messages |

---

## Hooks

Hooks run automatically on every session — no user action required.

| Hook | Trigger | What it does |
|---|---|---|
| `on-context-threshold` | UserPromptSubmit | Context budget bands (warn/compact/handoff/urgent), milestone boost, auto-handoff |
| `on-pulse` | UserPromptSubmit | Project health: stale branches, CI status, overdue milestones, draft lessons |
| `on-token-log` | Stop | Logs token usage to `~/.dream-studio/token-log.jsonl` |
| `on-milestone-start` | UserPromptSubmit | Records milestone start time + metadata |
| `on-milestone-end` | PostToolUse | Clears milestone marker; drafts lesson on long milestones |
| `on-meta-review` | UserPromptSubmit | Surfaces pending draft lessons for Director review |
| `on-agent-correction` | UserPromptSubmit | Tracks corrections to `~/.dream-studio/corrections.jsonl` |
| `on-quality-score` | PostToolUse | Records quality scores per session |
| `on-tool-activity` | PostToolUse | Tracks tool use; nudges `/harden` on first Edit/Write in an unhardened project |
| `on-skill-load` | UserPromptSubmit | Logs skill invocations |
| `on-skill-metrics` | PostToolUse | Appends skill usage records (name, duration, tokens) to `~/.dream-studio/skill-metrics.jsonl` |
| `on-game-validate` | PostToolUse | Validates Godot scene/script changes |
| `on-workflow-progress` | PostToolUse | Advances workflow DAG state |

---

## Status Bar

dream-studio ships a status bar that renders on every prompt:

```
Claude Sonnet 4.6  ⬢ dream-studio:main●  ████████░░ 78%  Effort ◉
```

| Segment | Meaning |
|---|---|
| Model name | Active Claude model |
| `⬢ repo:branch` | Git branch; color = pulse health (green/yellow/red) |
| `●` | Uncommitted changes present |
| Context bar `%` | Normalized against Claude's ~83% auto-compact trigger — so 100% = compact point, not full window. Displayed value is ~20% higher than raw token fill. Green < 65%, yellow 65–80%, red > 80% |
| `Effort ◉/◐/○` | Current thinking effort (high/medium/low) |

After `/compact`, the bar resets to `0%` on the next prompt.

### Setup

**Prerequisites:** Python 3.10+ and `git` on PATH.

```bash
make install-statusline
```

Then add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash \"~/.claude/statusline-command.sh\""
  }
}
```

On Windows, use the full path:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash \"C:/Users/<you>/.claude/statusline-command.sh\""
  }
}
```

---

## Workflows

Pre-built YAML DAG workflows in `workflows/`:

<!-- workflows-table-start -->
| Workflow | Nodes | Purpose |
|---|---|---|
| `comprehensive-review` | review-code → review-security → review-tests → review-perf → review-docs → synthesize → report | Five-way parallel review with synthesis report — HIGH/CRITICAL findings saved to `~/.dream-studio/secure/reports/` and create GitHub Issues automatically |
| `feature-research` | intake → research-repos → research-issues → research-prs → research-code → research-synthesis → … | GitHub research pipeline — native integration strategy (make it your own) with drop-in alternative. Gap analysis includes PERSISTENCE_GAP and TRACKING_GAP checks. |
| `fix-issue` | diagnose → plan-fix → implement-fix → review → verify → report | Diagnose a bug, plan a fix, implement, review, and verify — fix summary saved to `.sessions/<date>/` |
| `game-feature` | think → plan → build → review-gameplay → review-data → validate-engine → record | Game feature through implementation with Godot-specific QA — feature record saved to `~/.dream-studio/state/` |
| `hotfix` | debug → build → verify → ship → record | Fast debug-fix-verify cycle — PR URL recorded to `~/.dream-studio/state/hotfix-prs.log` |
| `idea-to-pr` | think → plan → build → review-code → review-security → review-tests → ship → record | Feature concept through merged PR — PR URL recorded to `~/.dream-studio/state/idea-to-pr.log` |
| `project-audit` | harden → secure → review → report | Full project audit — report saved to `~/.dream-studio/secure/reports/`, HIGH/CRITICAL findings create GitHub Issues automatically |
| `prototype` | think → build → verify → snapshot | Fast prototype — what-was-built snapshot saved to `~/.dream-studio/state/` |
| `safe-refactor` | plan-refactor → implement → type-check → test → review → verify → report | Refactor with type checks and tests — summary saved to `.sessions/<date>/` |
| `security-audit` | intake → generate-rules + dast-scan + binary-scan → ingest-scans → mitigate + comply + netcompat → generate-dashboard → executive-report | Enterprise security pipeline — SAST/DAST/binary scanning, parallel analysis (mitigate + comply + netcompat), Power BI dataset export, executive report. Supports three target types: repos, web apps, binaries. |
| `studio-onboard` | discovery → baseline-fetch → breakpoint-analysis → gap-analysis → improvement-scan → synthesis → … | Dream-studio onboarding audit — gap analysis includes PERSISTENCE_GAP and TRACKING_GAP checks, improvement-scan audits all installed workflows for ephemeral output |
<!-- workflows-table-end -->

**Usage:**

```
workflow: run hotfix
workflow status
workflow resume
workflow abort
```

---

## Development Workflow

dream-studio enforces a structured Issue → PR workflow for all regular work (bug fixes, features, improvements). This ensures proper tracking and traceability.

### Issue → PR Workflow

When implementing features, fixes, or improvements:

1. **Create GitHub issue** via `gh issue create --title "..." --body "..."`
2. **Create feature branch** named after issue (e.g., `fix/issue-123-description`)
3. **Implement** the fix/feature
4. **Run build** and verify it works
5. **Commit** with message referencing issue: `"fix: description (fixes #123)"`
6. **Push branch** and create PR via `gh pr create` with issue reference in body: `"Fixes #123"`
7. **Verify PR is green**, then merge via `gh pr merge`
8. **Report** PR URL and issue closure

### Debug Workflow Integration

When `dream-studio:debug` is invoked for a bug:

1. Run systematic debug process (reproduce, hypothesize, test, narrow)
2. Once root cause is identified, **create GitHub issue** with full debug log
3. Follow Issue → PR workflow above to implement the fix
4. Include debug log summary in PR description for traceability

**Never debug without creating an issue** — bugs need tracking even if the fix is trivial.

### When to use `dream-studio:ship`

Regular PRs do NOT need the full ship gate. Use `/ship` (comprehensive quality gate) only when:

- User explicitly says "ship it" or "ready to ship"
- Before major version releases (v2.0, big feature launches)
- Before client demos or presentations
- After risky refactors when full regression check is needed
- When comprehensive audit is required (a11y, perf, bundle size, e2e tests)

Regular PRs auto-deploy via CI after merge.

### Recommended Hooks Setup

To enforce dream-studio workflow patterns, add these hooks to your global `~/.claude/settings.json`:

#### PreToolUse Guards

Prevent accidental use of built-in tools that dream-studio replaces:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "EnterPlanMode",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'BLOCKED: Use dream-studio:plan instead of built-in plan mode.' >&2; exit 2"
          }
        ]
      },
      {
        "matcher": "Skill",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"~/.claude/hooks/guard-skills.sh\""
          }
        ]
      },
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"~/.claude/hooks/guard-agent.sh\""
          }
        ]
      }
    ]
  }
}
```

#### PostToolUse Build Checks

Auto-run builds after code edits to catch errors early:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "case \"$CLAUDE_FILE_PATH\" in *.py) py -m py_compile \"$CLAUDE_FILE_PATH\" 2>&1 | head -3 || true ;; esac"
          },
          {
            "type": "command",
            "command": "case \"$CLAUDE_FILE_PATH\" in *.ts|*.tsx|*.jsx|*.js|*.css|*.astro|*.vue) ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo \"$PWD\"); if [ -f \"$ROOT/package.json\" ] && grep -q '\"build\"' \"$ROOT/package.json\" 2>/dev/null; then echo \"[PostToolUse] Running build check...\"; (cd \"$ROOT\" && npm run build --silent 2>&1 | tail -20) || echo \"Build failed - check errors above\"; fi ;; esac"
          }
        ]
      }
    ]
  }
}
```

#### Guard Scripts

Create `~/.claude/hooks/guard-skills.sh`:

```bash
#!/bin/bash
# Block built-in review/security-review/init when dream-studio alternatives exist

SKILL_ARGS="$CLAUDE_SKILL_ARGS"

case "$SKILL_ARGS" in
  review|security-review|init)
    echo "BLOCKED: Use dream-studio:$SKILL_ARGS instead of built-in skill." >&2
    exit 2
    ;;
esac
```

Create `~/.claude/hooks/guard-agent.sh`:

```bash
#!/bin/bash
# Block Plan subagent when dream-studio:plan exists

AGENT_TYPE="$CLAUDE_AGENT_SUBAGENT_TYPE"

if [ "$AGENT_TYPE" = "Plan" ]; then
  echo "BLOCKED: Use dream-studio:plan instead of Plan subagent." >&2
  exit 2
fi
```

Make scripts executable:

```bash
chmod +x ~/.claude/hooks/*.sh
```

---

## Configuration

### Context Thresholds

Defined in `hooks/lib/context_handoff.py`.

**How the numbers work:** Claude Code's auto-compact fires at roughly 83% of the raw context window. dream-studio normalizes all context usage against that 83% trigger point — so `100%` on this scale = the moment Claude would auto-compact. This is the **same scale the status bar displays**, which means the percentage shown in the bar is approximately 20% higher than the raw token fill level (e.g., status bar shows 70% when the window is ~58% full). The threshold constants below are in this normalized scale and match exactly what you see on screen.

| Constant | Status bar value | ≈ Raw fill | Behavior |
|---|---|---|---|
| `WARN_PCT` | 55% | ~46% | "Growing" — fires once per 5% increment as context climbs |
| `COMPACT_PCT` | 70% | ~58% | "Run /compact soon" — once per session |
| `HANDOFF_PCT` | 75% | ~62% | Auto-writes handoff + recap to `.sessions/<date>/` |
| `URGENT_PCT` | 82% | ~68% | Blocks prompt; requires `/compact` to continue |
| Auto-compact | 100% | ~83% | Claude Code compacts automatically (not configurable here) |

Active milestones add a **+10 pp boost**: effective trigger points shift to 65 / 80 / 85 / 92% on the status bar, so milestone work is not interrupted.  
Post-`/compact`, warnings are suppressed for 2 turns and the WARN increment counter resets.

### Environment Variables

| Variable | Effect |
|---|---|
| `SENTRY_DSN` | Enable Sentry error tracking in hooks |
| `CLAUDE_PROJECTS_DIR` | Override default `~/.claude/projects/` path (useful for tests) |

### Runtime Data (`~/.dream-studio/`)

| Path | Contents |
|---|---|
| `audit.jsonl` | Append-only hook event log |
| `token-log.jsonl` | Per-session token usage |
| `corrections.jsonl` | Agent correction history |
| `meta/pulse-<date>.md` | Daily health report |
| `meta/draft-lessons/` | Unreviewed lesson drafts pending Director review |
| `career-ops/` | Career pipeline state |
| `state/` | Sentinel files (milestone-active, harden-nudge, compact-cooldown, etc.) |
| `clients/` | Client profiles (`_schema.yaml` + per-client YAML) for security audits |
| `security/rules/` | Generated Semgrep rules per client |
| `security/scans/` | Scan results (SARIF, ZAP JSON, Nuclei JSONL, checksec, YARA) |
| `security/reports/` | Mitigations, compliance maps, netcompat findings, executive reports |
| `security/data/` | Power BI-ready CSVs (findings, mitigations, compliance, risk scores) |

Session notes are written to `.sessions/<YYYY-MM-DD>/` inside each project.

---

## Project Structure

dream-studio organizes non-skill assets into **packs** — domain-grouped bundles of hooks, agents, rules, and context. Skills stay in `skills/` (Claude Code discovery requirement) but each SKILL.md declares its `pack:` in frontmatter.

### Packs

| Pack | Purpose | Skills | Hooks | Other |
|---|---|---|---|---|
| **core** | Build lifecycle | think, plan, build, review, verify, ship, handoff, recap | milestone-start/end, workflow-progress, changelog-nudge, stop-handoff | Agents: director, engineering, chief-of-staff. Context: session, director prefs |
| **quality** | Code quality & learning | debug, polish, harden, secure, structure-audit, learn, coach | security-scan, quality-score, structure-check, agent-correction | Rules: FSC, architecture |
| **career** | Job search pipeline | career-ops, -scan, -evaluate, -apply, -track, -pdf | — | Config: career-ops/config.yml |
| **analyze** | Multi-perspective analysis | analyze, domain-re | — | 27 analyst personas |
| **domains** | Stack-specific builders | game-dev, saas-build, mcp-build, dashboard-dev, client-work, design | game-validate | Agents: game, client. Rules: game/*. Templates: project-standards/ |
| **security** | Enterprise security analysis | scan, dast, binary-scan, mitigate, comply, netcompat, security-dashboard | — | ETL pipeline, Semgrep/ZAP/Nuclei/YARA templates, compliance mappings, Power BI dashboard spec |
| **meta** | Observability & sessions | workflow | pulse, meta-review, context-threshold, post-compact, token-log, tool-activity, skill-load | Shared hook lib (hooks/lib/) |

### Directory Layout

```
dream-studio/
├── .claude-plugin/
│   └── plugin.json                  # Plugin manifest
├── packs/                           # Domain-grouped non-skill assets
│   ├── core/
│   │   ├── agents/                  # director, engineering, chief-of-staff
│   │   ├── context/                 # session-context, director-preferences, fullstack-standards
│   │   └── hooks/                   # on-milestone-start, on-stop-handoff, etc.
│   ├── quality/
│   │   ├── hooks/                   # on-security-scan, on-quality-score, etc.
│   │   └── rules/structure/         # fsc.md, architecture.md
│   ├── career/                      # Skills-only pack (no hooks/agents/rules)
│   ├── analyze/                     # Skills-only pack (analysts live inside skill dirs)
│   ├── domains/
│   │   ├── agents/                  # game, client
│   │   ├── hooks/                   # on-game-validate
│   │   ├── rules/game/              # Godot 4 coding rules (6 files)
│   │   └── templates/               # project-standards/ scaffold
│   └── meta/
│       └── hooks/                   # on-pulse, on-context-threshold, on-token-log, etc.
├── hooks/
│   ├── lib/                         # Shared Python library (imported by all handlers)
│   │   ├── paths.py                 # Cross-platform path resolution
│   │   ├── models.py                # Pydantic v2 payload models
│   │   ├── context_handoff.py       # Threshold constants + handoff writers
│   │   ├── workflow_engine.py       # DAG execution engine
│   │   └── ...                      # audit, telemetry, time_utils, etc.
│   ├── hooks.json                   # Hook event -> handler registrations
│   ├── run.sh                       # Unix launcher (searches packs/*/hooks/)
│   └── run.cmd                      # Windows launcher
├── skills/                          # 38 skill definitions (each has SKILL.md with pack: field)
├── workflows/                       # YAML workflow DAG definitions
├── packs.yaml                       # Pack manifest — defines all 6 packs and their members
├── scripts/
│   ├── bom.py                       # Bill of materials
│   ├── statusline-command.sh        # Status bar script (make install-statusline)
│   ├── sync_docs.py                 # Regenerate workflow table in README
│   └── sync-cache.ps1               # PowerShell cache sync utility
├── tests/
├── CHANGELOG.md
├── Makefile
├── pyproject.toml
├── requirements.txt                 # Runtime: pydantic>=2.0, sentry-sdk
└── requirements-dev.txt
```

---

## Skill Architecture

As of **v0.8.0 (2026-04-29)**, all 38 skills follow a structured architecture with evolution tracking, quality metrics, and auto-generated documentation.

### Standardized Skill Structure

Every skill has:
- **metadata.yml** — Evolution tracking, quality metrics (success rate, token usage), dependencies
- **gotchas.yml** — Structured lessons learned (avoid patterns, best practices, edge cases)
- **config.yml** — Runtime configuration and performance budgets
- **changelog.md** — Version history

Core skills (build, plan, review, verify, ship) additionally have:
- **examples/** — Simple + complex usage scenarios with input/output
- **templates/** — Agent prompts and output format templates
- **smoke-test.md** — Quick validation tests
- **core-imports.md** — Module dependency documentation

### Auto-Generated Catalog

The skill catalog is auto-generated from metadata:

```bash
cd skills/
py generate-catalog.py
```

Produces `dream-studio-catalog.md` with:
- **Skills by pack** — Organized by core, security, career, design, domains, etc.
- **Quality metrics** — Success rates, token usage, times used
- **Dependency graph** — Which skills use which core modules
- **Health dashboard** — Active, maintenance, deprecated status

**Search the catalog:**
```bash
grep "security" skills/dream-studio-catalog.md
grep "build" skills/dream-studio-catalog.md
```

### Core Modules (SSOT Pattern)

Skills compose from reusable building blocks in `skills/core/`:

| Module | Used By | Patterns |
|---|---|---|
| **git.md** | 7 skills | Commit formatting, branch operations, diff reading |
| **traceability.md** | 3 skills | TR-ID validation, status tracking |
| **quality.md** | 4 skills | Build/test execution, linting, evidence patterns |
| **orchestration.md** | 6 skills | Subagent spawning, model selection, review loops |
| **format.md** | ALL skills | Markdown tables, severity tags, verdict statements |

**Impact visibility:** Before changing a core module, check `skills/core/REGISTRY.md` to see affected skills.

### Creating New Skills

1. Copy templates from `skills/templates/`
2. Edit `metadata.yml` with skill info
3. Create `SKILL.md` with orchestration logic
4. Add `changelog.md` entry
5. Regenerate catalog: `py generate-catalog.py`

See `skills/STRUCTURE.md` for complete guide.

---

## Planning Templates & Domain Library

As of **v0.7.0 (Repository Integration v2)**, dream-studio includes production-ready planning templates adapted from GitHub's [spec-kit](https://github.com/github/spec-kit) and a curated domain knowledge library.

### Planning Templates

Located in `skills/think/templates/` and `skills/plan/templates/`:

| Template | Used By | What it provides |
|---|---|---|
| **spec-template.md** | `dream-studio:think` | User stories prioritized by value (P1 MVP → P2 → P3), functional requirements (FR-XXX), success criteria (SC-XXX), edge cases |
| **plan-template.md** | `dream-studio:plan` | Technical context, architecture decisions, requirements traceability, risk analysis |
| **tasks-template.md** | `dream-studio:plan` | Phase-based task breakdown with [P] parallel markers, user story grouping, dependency chains |
| **constitution-template.md** | `.planning/` | Project principles and governance framework |

**Workflow**: `think:` generates `.planning/specs/<topic>/spec.md` → `plan:` generates `plan.md` + `tasks.md` → `build:` executes tasks.

See `.planning/README.md` for complete workflow documentation and `.planning/specs/sample-user-auth/` for a working example.

### Domain Knowledge Library

9 curated domains in `skills/domains/` with patterns, standards, and references:

| Domain | Files | Key References |
|---|---|---|
| **devops** | github-actions-patterns.yml | awesome-actions (21.7k ⭐) — CI/CD security, OIDC, SHA pinning |
| **testing** | playwright-patterns.yml | awesome-playwright (1.4k ⭐) — Page Object Model, locator strategies |
| **documentation** | technical-writing-standards.yml | Diátaxis framework, Google/Microsoft style guides |
| **design** | 5 standards (fluent, material, typography, color, layout) | Fluent Design, Material Design 3, WCAG 2.1 |
| **bi** | dax-patterns.md, m-query-patterns.md | DAX calculation patterns, M-query data transformation recipes for Power BI |
| **powerbi** | 3 patterns (storytelling, accessibility, design) + pbip-format.md | Cole Nussbaumer Knaflic, Microsoft Power BI guidelines, PBIP format reference |
| **data-visualization** | 2 standards (accessibility, design) | WCAG for charts, data-ink ratio, chart selection |
| **frontend** | (existing) | React, TypeScript, component patterns |
| **backend** | (existing) | Node.js, API design, database patterns |
| **security** | (existing) | OWASP, authentication, cryptography |

**Quality Checklists**: `skills/polish/checklists/` and `skills/client-work/powerbi/` contain 7 YAML checklists for design compliance (web, Fluent, Material, data viz, Power BI).

Each domain includes:
- **Pattern YAML files**: Structured rules, checklists, scoring criteria
- **REFERENCES.md**: Curated external resources with GitHub star counts and rationale

**Usage**: Skills automatically reference domain knowledge when relevant (e.g., `polish` uses web-design.yml, `client-work` uses Power BI patterns).

---

## Enforcement Status

What fires automatically vs what requires a manual command:

| Standard | Enforced | Mechanism |
|---|---|---|
| Context budget + handoff | **Auto** | `on-context-threshold` — blocks at 82%, writes handoff at 75% |
| Project health check | **Auto** | `on-pulse` — every prompt |
| Session token logging | **Auto** | `on-token-log` — every Stop |
| Security pattern scan | **Auto** | `on-security-scan` — every Edit/Write |
| CHANGELOG reminder | **Auto** | `on-changelog-nudge` — every Stop when source changed |
| Hardening nudge | **Auto** | `on-tool-activity` — once per project on first Edit/Write |
| Code format | **Auto** | Pre-commit black hook |
| Code lint | **Auto** | Pre-commit flake8 hook |
| Test coverage ≥ 70% | **Auto** | CI on every push/PR |
| Full security review | **Manual** | `/secure` — OWASP + STRIDE |
| Folder structure audit | **Manual** | `/structure-audit` |
| Documentation quality | **Manual** | `/harden` item 19 + template scaffold |
| Workflow gating | **Manual** | `/workflow run <name>` |

> Run `/harden audit` to get a scored gap report for any project. Items marked Manual require intentional invocation — they are not wired to hooks to avoid excessive interruption during development.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming conventions, commit format, and the PR checklist.

```bash
make test        # run 167 tests with coverage (threshold: 70%)
make lint        # flake8
make fmt         # black --check
make security    # pip-audit for known vulnerabilities
```

Bugs and security issues: see [SECURITY.md](SECURITY.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

> Built by [SeayInsights](https://github.com/SeayInsights).
