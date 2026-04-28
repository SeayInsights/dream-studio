# dream-studio — Project Structure

**Version**: 2.0 (Repository Integration v2)  
**Last Updated**: 2026-04-27

## Overview

dream-studio is a modular agent framework built around a skill-based pipeline: **think → plan → build → review → verify → ship**. Each component has a specific responsibility and clear interfaces.

## Directory Organization

```
dream-studio/
├── .planning/                   # Project planning and architecture
│   ├── README.md
│   ├── templates/               # Reusable spec/plan templates
│   │   ├── spec-template.md
│   │   ├── plan-template.md
│   │   ├── tasks-template.md
│   │   └── constitution-template.md
│   ├── specs/                   # Feature specifications (v2 structure)
│   │   └── <feature-name>/
│   │       ├── spec.md          # User stories, requirements
│   │       ├── plan.md          # Architecture, tech decisions
│   │       ├── tasks.md         # Task breakdown
│   │       └── ...              # Optional: research, contracts
│   └── *.md                     # Legacy specs (backwards compatible)
│
├── skills/                      # Core capabilities
│   ├── think/                   # Spec generation, design thinking
│   │   ├── SKILL.md
│   │   ├── skill.ts
│   │   └── templates/
│   │       └── spec-template.md
│   ├── plan/                    # Implementation planning
│   │   ├── SKILL.md
│   │   ├── skill.ts
│   │   └── templates/
│   │       ├── plan-template.md
│   │       └── tasks-template.md
│   ├── build/                   # Task execution
│   ├── review/                  # Code review
│   ├── verify/                  # Testing and validation
│   ├── ship/                    # Pre-deploy quality gate
│   ├── debug/                   # Systematic debugging
│   ├── polish/                  # UI/UX refinement
│   │   └── checklists/
│   │       ├── web-design.yml
│   │       ├── fluent-design-compliance.yml
│   │       ├── material-design-compliance.yml
│   │       └── data-viz-accessibility.yml
│   ├── secure/                  # Security review
│   ├── design/                  # Visual design
│   ├── harden/                  # Project hardening
│   ├── client-work/             # Power Platform workflows
│   │   └── powerbi/
│   │       ├── storytelling-framework.yml
│   │       ├── accessibility-checklist.yml
│   │       └── design-hacks.yml
│   ├── saas-build/              # SaaS feature builder
│   ├── game-dev/                # Godot game development
│   ├── mcp-build/               # MCP server development
│   ├── dashboard-dev/           # Tauri dashboard builder
│   └── domains/                 # Domain knowledge library
│       ├── devops/
│       │   ├── github-actions-patterns.yml
│       │   └── REFERENCES.md
│       ├── testing/
│       │   ├── playwright-patterns.yml
│       │   └── REFERENCES.md
│       ├── documentation/
│       │   ├── technical-writing-standards.yml
│       │   └── REFERENCES.md
│       ├── design/
│       │   ├── fluent-design-system.yml
│       │   ├── material-design-system.yml
│       │   ├── typography-standards.yml
│       │   ├── color-standards.yml
│       │   ├── layout-standards.yml
│       │   └── REFERENCES.md
│       ├── powerbi/
│       │   ├── storytelling-patterns.yml
│       │   ├── accessibility-checklist.yml
│       │   ├── design-best-practices.yml
│       │   └── REFERENCES.md
│       ├── data-visualization/
│       │   ├── accessibility-standards.yml
│       │   ├── design-standards.yml
│       │   └── REFERENCES.md
│       ├── frontend/
│       ├── backend/
│       └── security/
│
├── core/                        # Shared building blocks
│   ├── git.md
│   ├── traceability.md
│   ├── format.md
│   └── ...
│
└── packs/                       # Skill collections
    ├── core/
    ├── security/
    ├── visual/
    ├── domain-builders/
    ├── power-platform/
    └── analysis/
```

## Skill Pipeline

### 1. think → Specification
**Skill**: `dream-studio:think`  
**Template**: `skills/think/templates/spec-template.md`  
**Output**: `.planning/specs/<feature>/spec.md`

Generates feature specification with:
- User stories prioritized by value (P1, P2, P3)
- Functional requirements (FR-001, FR-002...)
- Success criteria (SC-001, SC-002...)
- Edge cases and assumptions

**Trigger**: `think:`, `spec:`, `research:`

### 2. plan → Implementation Strategy
**Skill**: `dream-studio:plan`  
**Templates**: 
- `skills/plan/templates/plan-template.md`
- `skills/plan/templates/tasks-template.md`

**Output**: `.planning/specs/<feature>/plan.md` and `tasks.md`

Generates implementation plan with:
- Technical context (language, dependencies, platform)
- Task breakdown organized by user story
- Dependencies and [P] parallel markers
- Traceability matrix (optional, for 4+ task features)

**Trigger**: `plan:`, after `think` approval

### 3. build → Execution
**Skill**: `dream-studio:build`  
**Input**: `.planning/specs/<feature>/tasks.md`

Executes tasks in dependency order with parallel execution where marked [P].

### 4-6. review → verify → ship
Quality gates:
- **review**: Code quality, spec compliance
- **verify**: Test execution, proof of functionality
- **ship**: Pre-deploy audit (a11y, perf, e2e)

## Domain Knowledge Library

**Location**: `skills/domains/`

9 domain areas with curated patterns and references:

| Domain | Purpose | Key Files |
|--------|---------|-----------|
| **devops** | CI/CD, GitHub Actions, containerization | github-actions-patterns.yml |
| **testing** | E2E testing, Playwright, test patterns | playwright-patterns.yml |
| **documentation** | Technical writing, Diátaxis framework | technical-writing-standards.yml |
| **design** | Design systems (Fluent, Material), typography, color | 5 standards + fluent/material systems |
| **powerbi** | Power BI storytelling, accessibility, design | 3 patterns |
| **data-visualization** | Chart selection, accessibility, storytelling | 2 standards |
| **frontend** | React, TypeScript, component patterns | (existing) |
| **backend** | Node.js, API design, database patterns | (existing) |
| **security** | OWASP, authentication, cryptography | (existing) |

Each domain includes:
- **Pattern YML files**: Structured rules and checklists
- **REFERENCES.md**: Curated external resources (awesome-* repos, style guides)

## Template Usage

### When to Use spec-template.md
- Building a new feature
- Major refactor requiring design exploration
- Complex bug fix needing multiple approaches
- User stories must be independently testable

### When to Use plan-template.md + tasks-template.md
- Approved spec ready for implementation
- Need atomic task breakdown
- Multiple developers working in parallel
- Traceability required (4+ tasks, audit trail)

### When to Skip Templates
- Simple config change (summary sufficient)
- Trivial bug fix (problem statement + approach)
- Prototype/exploratory work

## Traceability

**File**: `.planning/traceability.yaml`

Activated when:
- 4+ tasks with distinct requirements
- Audit trail needed for compliance
- User explicitly requests tracking

Links requirements (TR-IDs) → tasks → implementation status.

See `core/traceability.md` for full spec.

## Packs

Skills are organized into packs for cohesion:

- **core**: think, plan, build, review, verify, ship
- **security**: secure, scan, mitigate, comply, netcompat, dast, binary-scan
- **visual**: design, polish, huashu-design
- **domain-builders**: saas-build, game-dev, mcp-build, dashboard-dev, client-work
- **power-platform**: client-work (Power BI, Power Apps, Power Automate)
- **analysis**: analyze, career-ops

## Architectural Validation

This structure is validated by [spec-kit](https://github.com/github/spec-kit), GitHub's internal specification framework. We've adapted their templates for dream-studio's modular architecture and added:

- **[P] parallel markers** for concurrent task execution
- **User story prioritization** (P1 MVP → P2 → P3 incremental)
- **dream-studio skill integration** (think → plan → build pipeline)
- **Domain knowledge library** (9 curated domains)

## Changelog

### v2.0 — Repository Integration (2026-04-27)

**Added**:
- `.planning/templates/` — spec, plan, tasks, constitution templates from spec-kit
- `skills/think/templates/spec-template.md` — User story prioritization (P1/P2/P3)
- `skills/plan/templates/` — plan-template.md, tasks-template.md with [P] markers
- **3 new domains**: devops, testing, documentation
- **Expanded domains**: design (+5 files), powerbi (+3 files), data-visualization (+2 files)
- `skills/polish/checklists/` — 4 design compliance checklists (web, fluent, material, data-viz)
- `skills/client-work/powerbi/` — 3 Power BI checklists (storytelling, accessibility, design)
- `.planning/README.md` — Workflow documentation
- This file (STRUCTURE.md)

**Updated**:
- `skills/think/SKILL.md` — References spec-template.md, example usage
- `skills/plan/SKILL.md` — References plan/tasks templates, [P] markers, user story organization

**Architectural validation**: Templates adapted from GitHub's spec-kit with dream-studio conventions

### v1.0 — Initial Structure

Core pipeline skills, domain library foundation, pack organization.

---

**Credits**: spec-kit (GitHub), dream-studio core team
