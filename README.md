# dream-studio

[![CI](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.11.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen.svg)](pyproject.toml)

An opinionated Claude Code plugin that gives you a structured build pipeline, automated quality gates, and a local analytics dashboard — portable across every project.

Ships with **8 skill packs (42 modes)** covering the full lifecycle from thinking through shipping, plus domain-specific skills for game dev, SaaS, Power Platform, security, and career ops. Hooks run automatically on every session to track health, enforce CI gates, and surface lessons learned.

---

## Table of Contents

- [What it does](#what-it-does)
- [Token Overhead](#token-overhead)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Setup](#setup)
- [Quick Start](#quick-start)
- [Skills](#skills)
- [Hooks](#hooks)
- [Analytics](#analytics)
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

## Pattern Enhancements

dream-studio implements 9 foundational patterns for optimized LLM consumption:

**Progressive Disclosure** — Core SKILL.md files route to focused reference files, reducing token overhead by 40%
- Example: `quality/debug` refactored from 217 lines → 65 lines with 6 reference files
- On-demand content loading: simple tasks load less, complex tasks load more

**Design System Library** — 5 curated design systems (3,500+ lines) with I-Lang discovery protocol
- tech-minimal (Stripe/Linear) • editorial-modern (Notion/Substack) • brutalist-bold (Wired)
- playful-rounded (Airbnb/Duolingo) • executive-clean (IBM/Salesforce)
- Reduces design iteration rounds from 3-5 → 1-2 (60% reduction)

**Version Guards** — Automatic feature gating based on detected tool versions
- Python/Node/Power BI version detection
- Prevents compatibility bugs (target: 70% reduction)
- Fallback strategies for older versions

**Decision Tables** — First-class routing with symptom → solution mapping
- Debug mode: 8 symptom patterns → trace strategies
- Client-work: 6 request patterns → submodes
- Design: 5 design systems → user intent matching

**Response Contracts** — Standardized output sections for quality modes
- Security reviews: Threat Model + Findings + Remediation + Verification
- Client deliverables: Scope + Data Lineage + Validation + Handoff
- Ship gate: Quality Checks + Limitations + Rollback + Monitoring

See [`.github/SKILL_STANDARDS.md`](.github/SKILL_STANDARDS.md) for full pattern documentation.

---

## Token Overhead

dream-studio injects context each session (routing table, memories, skills, hooks). The [`docs/token-overhead.md`](docs/token-overhead.md) report breaks down the per-category cost.

To measure overhead for your sessions:

```bash
py scripts/benchmark_tokens.py --run-label <your-session-label> --publish
```

---

## Architecture

**See [ARCHITECTURE.md](ARCHITECTURE.md) for a visual overview of the system.**

dream-studio follows a two-layer architecture: a Python hook runtime that responds to Claude Code lifecycle events, and a markdown-based skill system that guides Claude's behavior. All state is persisted to a local SQLite database in WAL mode, serving as the single source of truth for telemetry, sessions, workflows, and project intelligence.

The system is designed for local-first operation with no external dependencies (GitHub API is optional for health checks). Hooks batch into dispatchers to minimize overhead, all database writes use retry logic for graceful concurrent access, and skills are stateless markdown files that can be version-controlled with your project.

### Documentation

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — System overview, component diagram, and architectural decisions (why SQLite, why batched hooks, why markdown skills, etc.)
- **[DATABASE.md](docs/DATABASE.md)** — Complete SQLite schema with ERD, table definitions, indexes, migrations, and query patterns
- **[WORKFLOWS.md](docs/WORKFLOWS.md)** — Sequence diagrams and state machines for the five major workflows (session lifecycle, skill invocation, YAML workflows, analytics, health monitoring)

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

```bash
claude plugin install github:SeayInsights/dream-studio
```

> **Note:** dream-studio is a community plugin — not affiliated with or endorsed by Anthropic.

That's it. Open any Claude Code session after installing — the `on-first-run` hook fires automatically and walks you through the onboarding workflow (`Director profile`, `projects root`, `memory path`).

**First-time setup** (run once to merge hooks into your global settings and create your memory directory):

```bash
make setup          # any OS
# or: bash install.sh       # Mac/Linux
# or: .\install.ps1         # Windows
```

**For contributors:**

```bash
make install-dev
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

## Setup

dream-studio works out of the box with zero external tools installed. Optional tools unlock additional capabilities. Choose the profile that matches your needs.

> **Interactive setup:** Run `dream-studio:setup wizard` to auto-detect installed tools and walk through each install step.  
> **Check current state:** Run `dream-studio:setup status` to see which tools are installed and what each unlocks.

### Workspace Structure

**First-time setup automatically creates:**

```
~/
├── builds/          # All project repos
├── claude_mcp/      # MCP server installations
└── shared/          # Shared utilities
```

Each folder includes a README explaining its purpose. This prevents drive clutter and ensures consistent project organization across all dream-studio users.

---

### Minimal Profile — Zero Install

No external tools required. Skills fall back to built-in Claude Code capabilities (WebSearch, WebFetch). Best for trying dream-studio or working in restricted environments.

**What works:**
- All `dream-studio:core` modes (think, plan, build, review, verify, ship, handoff, recap, explain)
- All `dream-studio:quality` modes (debug, polish, harden, secure, structure-audit, learn, coach)
- All `dream-studio:analyze` modes
- `dream-studio:domains` — all modes except browser automation steps
- `dream-studio:career` — all modes

**What requires additional tools:**
- GitHub workflows (`gh` CLI) — see Standard profile
- Web scraping and DAST scanning (Firecrawl, Playwright) — see Full profile

No install steps needed. Just install dream-studio and start using it.

---

### Standard Profile — GitHub + Runtime Tools

Adds the GitHub CLI, Node.js, npm, and Python. Unlocks the full Issue → PR workflow, Node and Python script execution, and GitHub-integrated workflows.

**What this unlocks:**
- `gh` CLI: GitHub Issues, PRs, branch management, CI status checks
- `node` / `npm`: Node.js script execution in `saas-build` and `mcp-build` modes
- `python` / `py`: Python script execution, local hook development, `make test`

#### Install `gh` (GitHub CLI)

| Platform | Command |
|---|---|
| **Windows** | `winget install GitHub.cli` or download from [cli.github.com](https://cli.github.com) |
| **macOS** | `brew install gh` |
| **Linux (apt)** | `sudo apt install gh` (Ubuntu 22.04+) or see [cli.github.com/manual/installation](https://cli.github.com/manual/installation) |

After install, authenticate:
```bash
gh auth login
```

#### Install Node.js + npm

| Platform | Command |
|---|---|
| **Windows** | `winget install OpenJS.NodeJS.LTS` or download from [nodejs.org](https://nodejs.org) |
| **macOS** | `brew install node` |
| **Linux** | `sudo apt install nodejs npm` or use [nvm](https://github.com/nvm-sh/nvm): `nvm install --lts` |

Verify:
```bash
node --version    # v20+ recommended
npm --version
```

#### Install Python

| Platform | Command |
|---|---|
| **Windows** | `winget install Python.Python.3.12` or download from [python.org](https://python.org) |
| **macOS** | `brew install python@3.12` |
| **Linux** | `sudo apt install python3.12 python3-pip` |

> Python 3.12 recommended. Python 3.14+ is not supported — use 3.10, 3.11, or 3.12.

Verify:
```bash
python --version    # or: py --version (Windows)
```

---

### Full Profile — Everything

Adds Firecrawl and Playwright on top of the Standard profile. Unlocks web scraping, browser automation, DAST scanning, and the full `dream-studio:security` dast mode.

**What this unlocks:**
- **Firecrawl MCP Server**: Web scraping, search, and extraction in `dream-studio:career scan` (job portal scraping), `dream-studio:security dast` (site crawling), and `dream-studio:domains saas-build` (competitive research)
- **Playwright**: Browser automation in `dream-studio:core verify` (screenshot evidence), `dream-studio:security dast` (dynamic testing), and `dream-studio:domains game-dev` (automated QA)

#### Install Firecrawl (MCP Server)

Firecrawl runs as an MCP server inside Claude Code. It requires an API key from [firecrawl.dev](https://firecrawl.dev).

**Quick setup** (uses npx, no global install):

```bash
claude mcp add --scope user firecrawl-mcp -e FIRECRAWL_API_KEY="fc-your-key-here" -- npx -y firecrawl-mcp
```

**Global install** (if you prefer):

```bash
npm install -g firecrawl-mcp
claude mcp add --scope user firecrawl-mcp -e FIRECRAWL_API_KEY="fc-your-key-here" -- node "$(npm root -g)/firecrawl-mcp/dist/index.js"
```

**Windows (global install, PowerShell):**

```powershell
npm install -g firecrawl-mcp
claude mcp add --scope user firecrawl-mcp -e FIRECRAWL_API_KEY="fc-your-key-here" -- node "$($env:APPDATA)\npm\node_modules\firecrawl-mcp\dist\index.js"
```

Verify:

```bash
claude mcp list
# Should show: firecrawl-mcp: connected
```

#### Install Playwright

| Platform | Command |
|---|---|
| **Windows / macOS / Linux** | `npm install -g playwright` then `playwright install` |

Playwright downloads browser binaries (~300 MB). To install only Chromium:
```bash
playwright install chromium
```

Verify:
```bash
playwright --version
```

#### Full profile verification

```bash
gh --version
node --version
python --version    # or: py --version (Windows)
playwright --version
claude mcp list     # Should show firecrawl-mcp: connected
```

All commands should return version numbers. `claude mcp list` should show `firecrawl-mcp` as connected. Run `dream-studio:setup status` to see dream-studio's view of your installed tools.

---

## Quick Start

Once installed, dream-studio activates automatically in every Claude Code session.

**First time? Run the onboarding walkthrough:**

```
workflow: run studio-onboard
```

This audits your setup, customises dream-studio to your project, and walks you through the Director profile (name, domain, primary use). Run it once after install — subsequent sessions skip it automatically once your profile is set.

```
/dream-studio:core think     Shape a feature idea into a spec
/dream-studio:core plan      Break the approved spec into ordered tasks
/dream-studio:core build     Execute the plan with subagent-per-task
/dream-studio:core review    Two-stage quality check
/dream-studio:core verify    Evidence-based proof it works
/dream-studio:core ship      Pre-deploy gate — blocks on any FAIL
```

Or just use natural language — the router infers the mode from keywords like `think:`, `plan:`, `debug:`, etc.

**Harden a project** (run once to scaffold missing standards files):

```
/dream-studio:quality harden
```

**Run the test suite:**

```bash
make test
```

---

## Skills

Skills are organized into **7 packs**. Each pack is a single discoverable skill with multiple modes. Invoke via `/dream-studio:<pack> <mode>` or natural language — the router infers the mode from keywords.

### `dream-studio:core` — Build Lifecycle

| Mode | Keywords | What it does |
|---|---|---|
| `think` | `think:`, `spec:`, `research:` | Clarify + spec an idea; get explicit approval before any code |
| `plan` | `plan:` | Break an approved spec into atomic, dependency-ordered tasks |
| `build` | `build:`, `execute plan:` | Execute plan with a fresh subagent per task, parallel wave execution |
| `review` | `review:`, `review code:` | Two-stage check: spec compliance first, then code quality |
| `verify` | `verify:`, `prove it:` | Evidence-based verification with screenshots + Playwright results |
| `ship` | `ship:`, `pre-deploy:`, `deploy:` | Pre-deploy gate: a11y, perf, error states, regression — any FAIL blocks |
| `handoff` | `handoff:` | Structured state capture for session continuity |
| `recap` | `recap:` | Build memory snapshot — decisions, risks, stack, remaining work |
| `explain` | `explain:`, `how does X work` | Trace entry point through layers to output; depth adapts to the question |

### `dream-studio:quality` — Code Quality & Learning

| Mode | Keywords | What it does |
|---|---|---|
| `debug` | `debug:`, `diagnose:` | Reproduce → hypothesize → test one variable at a time → fix |
| `polish` | `polish ui:`, `critique design:` | Critique 7 UI dimensions (layout, typography, color...), scored 1-5 |
| `harden` | `harden:` | 20-item project audit + gap-fill from templates |
| `secure` | `secure:`, `security review:` | OWASP Top 10 checklist + STRIDE threat model |
| `structure-audit` | `structure-audit:` | Folder structure audit scored against FSC + architecture conventions |
| `learn` | `learn:`, `capture lesson:` | Draft → Director review → promote to memory / skill / agent updates |
| `coach` | `coach:` | Workflow coaching; `route-classify` mode maps unmatched intents |

### `dream-studio:security` — Enterprise Security Analysis

| Mode | Keywords | What it does |
|---|---|---|
| `scan` | `scan:`, `scan org:` | SAST scanning — Semgrep rule generation, scan execution, SARIF ingestion |
| `dast` | `dast:`, `web scan:` | DAST scanning — ZAP + Nuclei setup, run, ingest for web app targets |
| `binary-scan` | `binary-scan:`, `scan binary:` | Binary analysis — checksec + YARA + strings against compiled artifacts |
| `mitigate` | `mitigate:`, `how to fix:` | Generate fix snippets + effort estimates for every finding |
| `comply` | `comply:`, `SOC 2:`, `NIST:` | Map findings → SOC 2, NIST CSF, OWASP ASVS controls; identify gaps |
| `netcompat` | `netcompat:`, `Zscaler check:` | Detect cert pinning, custom TLS, non-standard ports that break proxies |
| `dashboard` | `security dashboard:` | ETL pipeline → Power BI-ready CSVs (findings, mitigations, compliance) |

### `dream-studio:domains` — Stack-Specific Builders

| Mode | Keywords | What it does |
|---|---|---|
| `game-dev` | `game:`, `game build:` | Godot 4: controllers, scenes, CSG blockouts, Blender→GLB pipeline |
| `saas-build` | `build feature:`, `build api:` | React 19 + React Router 7 + Cloudflare Workers + D1/Kysely |
| `mcp-build` | `build mcp:`, `new mcp:` | 4-phase MCP server dev: research → implement → test → evaluate |
| `dashboard-dev` | `dashboard:`, `feed contract:` | Tauri + React desktop dashboards, feed contract pattern |
| `client-work` | `intake:`, `build powerbi:` | Power BI, Power Apps, Power Automate — DAX/M-query + delegation rules |
| `design` | `design art:`, `canvas:`, `brand:` | Brand tokens, p5.js generative art, theme application, ad creative |

### `dream-studio:career` — Career Pipeline

| Mode | Keywords | What it does |
|---|---|---|
| `ops` | `career:`, `job search:` | Career pipeline management hub |
| `scan` | `scan jobs:`, `find jobs:` | Scrape job portals, deduplicate against history, add to pipeline |
| `evaluate` | `evaluate offer:`, `evaluate gig:` | Score offers, freelance gigs, proposals |
| `apply` | `apply:`, `cover letter:` | Form fill + answer generation (single or parallel batch) |
| `track` | `track:`, `pipeline:` | Pipeline management + follow-up cadence |
| `pdf` | `resume:`, `generate pdf:` | ATS-optimized CV generation + LinkedIn outreach messages |

### `dream-studio:analyze` — Analysis Engine

| Mode | Keywords | What it does |
|---|---|---|
| `multi` | `analyze:`, `/analyze` | Parallel multi-perspective analyst subagents → synthesized decision memo |
| `domain-re` | `domain-re:`, `real estate:` | Real estate domain-specific evaluation |

### `dream-studio:workflow` — Workflow Orchestration

Standalone skill (no modes). Invoke with `workflow:`, `workflow status`, `workflow resume`, `workflow abort`.

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

When `dream-studio:quality debug` is invoked for a bug:

1. Run systematic debug process (reproduce, hypothesize, test, narrow)
2. Once root cause is identified, **create GitHub issue** with full debug log
3. Follow Issue → PR workflow above to implement the fix
4. Include debug log summary in PR description for traceability

**Never debug without creating an issue** — bugs need tracking even if the fix is trivial.

### When to use `dream-studio:ship`

Regular PRs do NOT need the full ship gate. Use `/dream-studio:core ship` (comprehensive quality gate) only when:

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
            "command": "echo 'BLOCKED: Use dream-studio:core with arg plan instead of built-in plan mode.' >&2; exit 2"
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

dream-studio organizes skills into **packs** — each pack is a single discoverable skill with a router that dispatches to modes. This keeps the total skill description budget under 900 chars (Claude Code has a character budget for skill descriptions shared across all plugins).

### Packs

| Pack | Skill | Modes | Hooks | Other |
|---|---|---|---|---|
| **core** | `dream-studio:core` | think, plan, build, review, verify, ship, handoff, recap, explain | milestone-start/end, workflow-progress, changelog-nudge, stop-handoff | Agents: director, engineering, chief-of-staff |
| **quality** | `dream-studio:quality` | debug, polish, harden, secure, structure-audit, learn, coach | security-scan, quality-score, structure-check, agent-correction | Rules: FSC, architecture |
| **career** | `dream-studio:career` | ops, scan, evaluate, apply, track, pdf | — | — |
| **analyze** | `dream-studio:analyze` | multi, domain-re | — | 27 analyst personas |
| **domains** | `dream-studio:domains` | game-dev, saas-build, mcp-build, dashboard-dev, client-work, design | game-validate | Agents: game, client. Rules: game/* |
| **security** | `dream-studio:security` | scan, dast, binary-scan, mitigate, comply, netcompat, dashboard | — | ETL pipeline, compliance mappings |
| **meta** | `dream-studio:workflow` | (standalone) | pulse, meta-review, context-threshold, token-log, tool-activity, skill-load | Shared hook lib |

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
├── skills/                          # 7 pack skills (each with modes/ subdirectory containing full skill definitions)
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

As of **v0.11.0**, skills are organized into 7 pack-level routers. Each pack's `modes/` directory contains the full skill definitions with evolution tracking, quality metrics, and auto-generated documentation.

### Standardized Skill Structure

Every mode has:
- **metadata.yml** — Evolution tracking, quality metrics (success rate, token usage), dependencies
- **gotchas.yml** — Structured lessons learned (avoid patterns, best practices, edge cases)
- **config.yml** — Skill metadata (name, model_tier, description, triggers, chain_suggests)
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
2. Create `config.yml` with skill metadata (name, model_tier, description, triggers, chain_suggests)
3. Create `SKILL.md` with orchestration logic (pure instructions, no frontmatter)
4. Edit `metadata.yml` with evolution tracking info
5. Add `changelog.md` entry
6. Regenerate catalog: `py generate-catalog.py`

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

## Analytics

dream-studio includes a built-in analytics pipeline that harvests operational data, computes trends, and renders a standalone HTML dashboard.

### Quick start

```bash
./launch-dashboard          # Windows (.cmd) or Unix — bootstrap DB + launch server + open browser
make dashboard              # alternative if you have make installed
```

This is the recommended way to use analytics. On first run it automatically:
1. Creates the SQLite database (`~/.dream-studio/state/studio.db`) and runs all migrations
2. Harvests existing data from token logs, pulse reports, git repos, and lessons
3. Starts the FastAPI analytics server at `http://localhost:8000`
4. Opens the real-time dashboard at `http://localhost:8000/dashboard` in your browser

On subsequent runs, if the server is already running it just opens the browser. Stop the server with `Ctrl+C`.

### Interactive setup

For a guided walkthrough with health checks and gates at each step:

```
workflow: studio-analytics          # interactive — pauses at each phase for confirmation
workflow: studio-analytics auto     # non-interactive — runs everything end-to-end
```

The workflow shows you what data sources exist, how many rows were harvested, and lets you review before launching.

### What you get

Once the server is running:

| URL | What |
|-----|------|
| `http://localhost:8000/dashboard` | Real-time dashboard with WebSocket streaming |
| `http://localhost:8000/api/docs` | Interactive API documentation (Swagger) |
| `ws://localhost:8000/api/v1/stream/metrics` | WebSocket real-time metric stream |
| `http://localhost:8000/api/v1/` | REST API for metrics, reports, exports |

### First-time setup

Analytics is automatically bootstrapped when you run `make setup` — the database is created and any existing data (token logs, pulse reports, lessons) is harvested. You don't need to do anything extra before running `make dashboard`.

### What it tracks

- **Pulse health trend** — health score over time with linear regression
- **Skill velocity** — invocation counts and success rates per skill per week
- **Spec conversion rate** — how many planning specs result in actual build commits
- **Orphan detection** — specs with no build commit within 14 days
- **Commit velocity** — commits per week over the last 12 weeks
- **Operational snapshots** — CI status, open PRs, stale branches per project
- **ML insights** — anomaly detection, pattern recognition
- **Alerts & SLA** — threshold monitoring with real-time notifications

### Data sources

The analytics pipeline harvests from these sources (all optional — works with whatever exists):

| Source | Location | What it provides |
|--------|----------|-----------------|
| Token log | `~/.dream-studio/meta/token-log.md` | Session durations, model usage, cost estimates |
| Pulse reports | `~/.dream-studio/meta/pulse-*.md` | Health scores, CI status, stale branches |
| Lessons | `~/.dream-studio/meta/lessons/*.md` | Lesson counts and themes |
| Handoffs | `.sessions/*/handoff-*.json` | Session handoff history |
| Git repos | `~/builds/*/.git` | Commit velocity, branch counts |

---

## IDE & Editor Support

dream-studio's 38 skills and domain knowledge are portable to other AI coding platforms via auto-generated adapter files.

```bash
make adapters                    # build all adapters
make adapters PLATFORM=cursor    # build one platform only
```

| Platform | Output | Format | Domains |
|----------|--------|--------|---------|
| Cursor | `dist/adapters/cursor/.cursorrules` | XML `<rule>` blocks | No |
| Copilot | `dist/adapters/copilot/.github/copilot-instructions.md` | Flat markdown | Yes |
| Windsurf | `dist/adapters/windsurf/.windsurfrules` | Markdown with YAML frontmatter | Yes |
| Generic | `dist/adapters/system-prompt/system-prompt.md` | Dense markdown (<8K tokens) | Yes |

**Adding a new platform:** Create one `.j2` template in `scripts/adapter_templates/` and add one entry to `scripts/adapters_config.yml`. No script edits needed. See `scripts/adapter_templates/README.md`.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming conventions, commit format, and the PR checklist.

```bash
make test        # run tests with coverage (threshold: 70%)
make lint        # flake8
make fmt         # black --check
make security    # pip-audit for known vulnerabilities
make analytics   # harvest data + render analytics dashboard
make dashboard   # bootstrap + render + open dashboard in browser
make adapters    # generate IDE adapter files
make setup       # first-time project setup (includes analytics bootstrap)
```

Bugs and security issues: see [SECURITY.md](SECURITY.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

> Built by [SeayInsights](https://github.com/SeayInsights).
