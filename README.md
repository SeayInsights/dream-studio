# dream-studio

[![CI](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.6.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-73%25-green.svg)](pyproject.toml)

An opinionated Claude Code plugin that adds a **Build Pipeline**, **28 skills**, automated hooks, agent personas, and a context-aware status bar — portable across every project.

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

**Install dev dependencies (for contributing):**

```bash
make install-dev
# or: pip install -r requirements-dev.txt
```

---

## Quick Start

Once installed, dream-studio activates automatically in every Claude Code session.

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
| `polish` | `/polish`, `polish ui:`, `critique design:` | Critique 7 UI dimensions (layout, typography, color…), scored 1–5 |
| `secure` | `/secure`, `secure:`, `check security` | OWASP Top 10 checklist + STRIDE threat model |
| `analyze` | `/analyze` | Parallel multi-perspective analyst subagents → synthesized decision memo |

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
| `on-game-validate` | PostToolUse | Validates Godot scene/script changes |
| `on-workflow-progress` | PostToolUse | Advances workflow DAG state |

---

## Status Bar

dream-studio installs a status bar (configured in `~/.claude/settings.json`) that renders on every prompt:

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

Session notes are written to `.sessions/<YYYY-MM-DD>/` inside each project.

---

## Project Structure

```
dream-studio/
├── .claude-plugin/
│   └── plugin.json                  # Plugin manifest (name, version, author, keywords)
├── .github/
│   └── workflows/
│       └── ci.yml                   # CI matrix: ubuntu/macos/windows × py3.10–3.12
├── agents/                          # Agent persona definitions
│   ├── context/                     # Context files injected at session start
│   │   ├── director-corrections.md
│   │   ├── director-preferences.md
│   │   ├── fullstack-standards.md
│   │   ├── session-context.md
│   │   └── session-primer.md
│   ├── chief-of-staff.md
│   ├── client.md
│   ├── director.md
│   ├── engineering.md
│   └── game.md
├── docs/
│   └── engine-ref/
│       └── godot4/                  # Godot 4 reference (best practices, deprecated APIs)
├── hooks/
│   ├── handlers/                    # 12 hook event handlers (Python scripts)
│   │   ├── on-context-threshold.py  # Context budget + handoff trigger
│   │   ├── on-pulse.py              # Project health check
│   │   ├── on-token-log.py          # Token usage logger
│   │   ├── on-milestone-start.py
│   │   ├── on-milestone-end.py
│   │   ├── on-meta-review.py
│   │   ├── on-agent-correction.py
│   │   ├── on-quality-score.py
│   │   ├── on-skill-load.py
│   │   ├── on-tool-activity.py      # Nudges /harden on first edit in unhardened projects
│   │   ├── on-game-validate.py
│   │   └── on-workflow-progress.py
│   ├── lib/                         # Shared Python library (imported by all handlers)
│   │   ├── audit.py                 # Append-only event log writer
│   │   ├── context_handoff.py       # Threshold constants + handoff/recap/lesson writers
│   │   ├── models.py                # Pydantic v2 payload models (UserPromptSubmit, etc.)
│   │   ├── paths.py                 # Cross-platform path resolution
│   │   ├── telemetry.py             # Optional Sentry integration (no-op without DSN)
│   │   ├── time_utils.py            # utcnow() — single UTC source of truth
│   │   ├── workflow_engine.py       # DAG execution engine
│   │   ├── workflow_state.py        # Workflow state persistence
│   │   └── workflow_validate.py     # YAML parser + DAG cycle/dependency validator
│   ├── hooks.json                   # Hook event → handler registrations
│   ├── run.cmd                      # Windows hook runner shim
│   └── run.sh                       # Unix hook runner shim
├── rules/
│   ├── game/                        # Godot 4 coding rules (AI, data, gameplay, networking, shaders, UI)
│   └── structure/                   # Project structure conventions (FSC, architecture)
├── scripts/
│   └── bom.py                       # Bill of materials: git SHA, packages, build date
├── skills/                          # 28 skill definitions — each folder contains SKILL.md
│   ├── analyze/
│   ├── build/
│   ├── career-apply/                # Sub-skill of career-ops
│   ├── career-evaluate/             # Sub-skill of career-ops
│   ├── career-ops/                  # Entry point — routes to sub-skills
│   ├── career-pdf/                  # Sub-skill of career-ops
│   ├── career-scan/                 # Sub-skill of career-ops
│   ├── career-track/                # Sub-skill of career-ops
│   ├── client-work/
│   ├── dashboard-dev/
│   ├── debug/
│   ├── design/
│   ├── game-dev/
│   ├── handoff/
│   ├── harden/
│   ├── learn/
│   ├── mcp-build/
│   ├── plan/
│   ├── polish/
│   ├── recap/
│   ├── review/
│   ├── saas-build/
│   ├── secure/
│   ├── ship/
│   ├── structure-audit/
│   ├── think/
│   ├── verify/
│   └── workflow/
├── templates/
│   └── project-standards/           # Scaffold files used by /harden to gap-fill projects
│       ├── Makefile
│       ├── CONTRIBUTING.md
│       ├── SECURITY.md
│       ├── README.md                # README template for new projects
│       ├── pyproject.toml
│       ├── requirements.txt
│       ├── requirements-dev.txt
│       ├── scripts/bom.py
│       └── hooks/lib/               # Copies of core lib files (audit, models, telemetry, time_utils)
├── tests/
│   ├── conftest.py
│   ├── factories.py                 # factory_boy payload factories
│   ├── integration/                 # Hook + workflow integration tests (16 test files)
│   └── unit/                        # Library unit tests (4 test files)
├── workflows/                       # YAML workflow DAG definitions
│   ├── comprehensive-review.yaml
│   ├── feature-research.yaml        # GitHub research pipeline for Claude integrations
│   ├── fix-issue.yaml
│   ├── game-feature.yaml
│   ├── hotfix.yaml
│   ├── idea-to-pr.yaml
│   ├── prototype.yaml
│   ├── safe-refactor.yaml
│   └── studio-onboard.yaml          # Onboarding audit for new dream-studio users
├── CHANGELOG.md                     # Version history
├── CONTRIBUTING.md                  # Branch naming, commit format, PR checklist
├── LICENSE                          # MIT
├── Makefile                         # Targets: test, lint, fmt, security, install-dev, status
├── README.md
├── SECURITY.md                      # Vulnerability reporting (30-day SLA)
├── pyproject.toml                   # Black, Flake8, pytest, coverage config (≥70% threshold)
├── requirements.txt                 # Runtime: pydantic>=2.0, sentry-sdk
└── requirements-dev.txt             # Dev: pytest-cov, freezegun, factory-boy, black, flake8, pip-audit
```

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
