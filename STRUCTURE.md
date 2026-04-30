# dream-studio — Project Structure

**Version**: 3.0 (Pack Consolidation)
**Last Updated**: 2026-04-30

## Overview

dream-studio is a modular Claude Code plugin built around a skill-based pipeline: **think → plan → build → review → verify → ship**. Skills are organized into 7 packs, each a single discoverable skill with multiple modes.

## Directory Organization

```
dream-studio/
├── .claude/                         # Claude Code project settings
│   └── settings.json
├── .claude-plugin/                  # Plugin manifest
│   ├── plugin.json
│   └── marketplace.json
├── .github/
│   ├── workflows/ci.yml             # CI: test matrix, ci-gate, audit
│   └── PULL_REQUEST_TEMPLATE.md
├── agents/                          # 9 bundled specialist agents
├── docs/                            # Reference documentation
│   ├── tool-reference.md            # Per-tool install guides
│   └── token-overhead.md            # Context cost analysis
├── hooks/                           # Hook infrastructure
│   └── lib/                         # Shared Python hook library
├── meta/                            # Lessons and observability
├── packs/                           # Pack-specific context and config
│   └── <pack>/
│       ├── hooks/                   # Pack-level hooks
│       ├── context/                 # Injected session context
│       └── agents/                  # Pack-level agent personas
├── scripts/                         # Utility scripts
├── skills/                          # Skill definitions (see below)
├── templates/                       # Shared templates
├── tests/                           # Test suite
├── workflows/                       # YAML DAG workflow definitions
├── ARCHITECTURE.md                  # Two-layer design doc
├── CHANGELOG.md
├── CLAUDE.md                        # Skill routing table
├── CONTEXT.md                       # Domain terminology
├── CONTRIBUTING.md
├── README.md
├── SECURITY.md
├── STRUCTURE.md                     # This file
├── packs.yaml                       # Pack registry
├── pyproject.toml                   # Python tooling config
├── requirements.txt
└── requirements-dev.txt
```

## Skills Directory

Skills are organized into **packs**. Each pack is a single discoverable skill with a router that dispatches to modes.

```
skills/
├── core/                            # dream-studio:core — Build Lifecycle
│   ├── SKILL.md                     # Pack router
│   ├── REGISTRY.md                  # Tool registry reference
│   ├── git.md                       # Shared: branch ops, commit format
│   ├── format.md                    # Shared: output formatting
│   ├── quality.md                   # Shared: build commands, test execution
│   ├── orchestration.md             # Shared: subagent spawning, model selection
│   ├── traceability.md              # Shared: TR-ID validation
│   ├── repo-map.md                  # Shared: repository structure mapping
│   ├── web.md                       # Shared: web access fallback chain
│   └── modes/
│       ├── think/SKILL.md           # Spec generation, design thinking
│       ├── plan/SKILL.md            # Implementation planning
│       ├── build/SKILL.md           # Task execution with subagents
│       ├── review/SKILL.md          # Two-stage code review
│       ├── verify/SKILL.md          # Evidence-based verification
│       ├── ship/SKILL.md            # Pre-deploy quality gate
│       ├── handoff/SKILL.md         # Session state capture
│       ├── recap/SKILL.md           # Session memory snapshot
│       └── explain/SKILL.md         # Code walkthrough
│
├── quality/                         # dream-studio:quality — Code Quality
│   ├── SKILL.md
│   └── modes/
│       ├── debug/SKILL.md           # Systematic debugging
│       ├── polish/SKILL.md          # UI critique and refinement
│       ├── harden/SKILL.md          # Project audit and scaffolding
│       ├── secure/SKILL.md          # OWASP + STRIDE security review
│       ├── structure-audit/SKILL.md # Folder structure scoring
│       ├── learn/SKILL.md           # Lesson capture and promotion
│       └── coach/SKILL.md           # Workflow coaching
│
├── security/                        # dream-studio:security — Enterprise Security
│   ├── SKILL.md
│   └── modes/
│       ├── scan/SKILL.md            # SAST scanning (Semgrep)
│       ├── dast/SKILL.md            # DAST scanning (ZAP + Nuclei)
│       ├── binary-scan/SKILL.md     # Binary analysis (checksec + YARA)
│       ├── mitigate/SKILL.md        # Fix generation + effort estimates
│       ├── comply/SKILL.md          # SOC 2, NIST CSF, OWASP ASVS mapping
│       ├── netcompat/SKILL.md       # Proxy/TLS compatibility checks
│       └── dashboard/SKILL.md       # Power BI dataset export
│
├── domains/                         # dream-studio:domains — Stack Builders
│   ├── SKILL.md
│   ├── modes/
│   │   ├── game-dev/SKILL.md        # Godot 4 development
│   │   ├── saas-build/SKILL.md      # React 19 + Cloudflare Workers
│   │   ├── mcp-build/SKILL.md       # MCP server development
│   │   ├── dashboard-dev/SKILL.md   # Tauri + React dashboards
│   │   ├── client-work/SKILL.md     # Power BI, Power Apps, Power Automate
│   │   └── design/SKILL.md          # Brand, generative art, ad creative
│   └── <domain>/                    # Domain knowledge library
│       ├── powerbi/                 # Power BI patterns + checklists
│       ├── design/                  # Design systems (Fluent, Material)
│       ├── devops/                  # CI/CD, GitHub Actions
│       ├── testing/                 # Playwright, test patterns
│       ├── documentation/           # Technical writing standards
│       ├── data-visualization/      # Chart selection, accessibility
│       └── ...                      # infra, mobile, research, etc.
│
├── career/                          # dream-studio:career — Career Pipeline
│   ├── SKILL.md
│   └── modes/
│       ├── ops/SKILL.md             # Pipeline management hub
│       ├── scan/SKILL.md            # Job portal scraping
│       ├── evaluate/SKILL.md        # Offer/gig scoring
│       ├── apply/SKILL.md           # Form fill + answer generation
│       ├── track/SKILL.md           # Pipeline + follow-up cadence
│       └── pdf/SKILL.md             # ATS-optimized resume generation
│
├── analyze/                         # dream-studio:analyze — Analysis Engine
│   ├── SKILL.md
│   ├── analysts/                    # 27 analyst personas
│   └── modes/
│       ├── multi/SKILL.md           # Multi-perspective analysis
│       └── domain-re/SKILL.md       # Real estate evaluation
│
├── setup/                           # dream-studio:setup — Onboarding
│   ├── SKILL.md
│   ├── tool-registry.yml            # Tool metadata (detect, install, verify)
│   └── modes/
│       ├── wizard/SKILL.md          # Interactive setup walkthrough
│       ├── status/SKILL.md          # Installed tool status report
│       └── jit/SKILL.md             # Just-in-time tool install prompts
│
├── workflow/                        # dream-studio:workflow — Orchestration
│   └── SKILL.md
│
└── templates/                       # Shared skill templates
```

## Pack Summary

| Pack | Skill | Modes | Purpose |
|---|---|---|---|
| core | `dream-studio:core` | 9 | Build lifecycle pipeline |
| quality | `dream-studio:quality` | 7 | Code quality and learning |
| security | `dream-studio:security` | 7 | Enterprise security analysis |
| domains | `dream-studio:domains` | 6 | Stack-specific builders |
| career | `dream-studio:career` | 6 | Career pipeline |
| analyze | `dream-studio:analyze` | 2 | Multi-perspective analysis |
| setup | `dream-studio:setup` | 3 | Onboarding and tool management |

**Total: 7 packs, 40 modes**

## Two-Layer Architecture

See `ARCHITECTURE.md` for full details.

- **Layer 1 — Python Hook Runtime** (`packs/`): Live hooks that execute on Claude Code events
- **Layer 2 — Claude Skill Guidance** (`skills/`): Markdown instructions Claude follows when a skill is invoked

## Skill Pipeline

```
think → plan → build → review → verify → ship → handoff
```

Each mode has:
- `SKILL.md` — Instructions Claude follows
- `gotchas.yml` — Known failure patterns (read before every invocation)
- `config.yml` — Mode-specific thresholds and defaults
- `templates/` — Reusable output templates

## Planning Structure

```
.planning/specs/<feature>/
├── spec.md              # User stories, requirements (think output)
├── plan.md              # Architecture, tech decisions (plan output)
├── tasks.md             # Task breakdown (plan output)
└── ...                  # Optional: research, contracts, design
```

Traceability (`.planning/traceability.yaml`) activates for 4+ task features.

## Domain Knowledge Library

**Location**: `skills/domains/<domain>/`

| Domain | Key Files |
|---|---|
| powerbi | storytelling, accessibility, design patterns |
| design | Fluent, Material, typography, color, layout |
| devops | GitHub Actions patterns |
| testing | Playwright patterns |
| documentation | Technical writing standards |
| data-visualization | Chart selection, accessibility |
| infra, mobile, research, quality | Specialist patterns |
