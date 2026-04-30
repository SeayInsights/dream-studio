# .planning/ — Project Planning Directory

## Purpose

This directory contains architectural planning documents, templates, and feature specifications for dream-studio. It serves as the source of truth for project decisions, implementation plans, and traceability.

## Structure

```
.planning/
├── README.md                    # This file
├── constitution.md              # Project principles and governance (optional)
├── templates/                   # Reusable templates for specs and plans
│   ├── spec-template.md
│   ├── plan-template.md
│   ├── tasks-template.md
│   └── constitution-template.md
├── specs/                       # Feature specifications (new structure)
│   └── <feature-name>/
│       ├── spec.md              # User stories, requirements (think output)
│       ├── plan.md              # Architecture, tech decisions (plan output)
│       ├── tasks.md             # Task breakdown (plan output)
│       ├── research.md          # Optional: research findings
│       ├── data-model.md        # Optional: data structures
│       └── contracts/           # Optional: API contracts
└── *.md                         # Legacy specs (backwards compatible)
```

## Workflow

### 1. Think → Spec
**Skill**: `dream-studio:think`  
**Template**: `templates/spec-template.md`  
**Output**: `specs/<feature-name>/spec.md`

Creates a feature specification with:
- User stories prioritized by value (P1 = MVP, P2, P3...)
- Functional requirements (FR-001, FR-002...)
- Success criteria (measurable outcomes)
- Edge cases and assumptions

### 2. Plan → Implementation Strategy
**Skill**: `dream-studio:plan`  
**Templates**: `templates/plan-template.md`, `templates/tasks-template.md`  
**Output**: `specs/<feature-name>/plan.md` and `tasks.md`

Creates an implementation plan with:
- Technical context (language, dependencies, storage)
- Project structure decisions
- Task breakdown organized by user story
- Dependencies and parallel opportunities ([P] markers)
- Traceability (optional, for complex features)

### 3. Build → Execute
**Skill**: `dream-studio:build`  
**Input**: `specs/<feature-name>/tasks.md`

Executes tasks in dependency order, with parallel execution where marked [P].

## When to Use Templates

### spec-template.md
Use when:
- Building a new feature
- Major refactor that needs design thinking
- Complex bug fix that needs multiple approaches evaluated
- User stories need to be independently testable

Skip when:
- Simple config change (1 paragraph summary sufficient)
- Trivial bug fix (problem statement + approach sufficient)

### plan-template.md + tasks-template.md
Use when:
- Spec is approved and ready for implementation
- Need to break work into atomic commits
- Multiple developers may work in parallel
- Traceability is needed (4+ tasks, distinct requirements)

Skip when:
- Prototype or exploratory work
- Single-file change with obvious approach

### constitution-template.md
Use when:
- Starting a new project with team
- Establishing principles and constraints
- Documenting governance and review processes

## Traceability

Traceability links requirements → tasks → implementation. Activate when:
- 4+ tasks with distinct requirements
- Audit trail needed for compliance
- User explicitly requests tracking

When active, create `traceability.yaml` with:
- Requirements (TR-001, TR-002...)
- Tasks tagged with implementing requirements
- Status tracking (planned → in_progress → completed)

See `core/traceability.md` for full structure.

## Backwards Compatibility

Existing `.planning/*.md` files remain valid. New work should use `specs/<feature-name>/` structure, but legacy files won't break workflows.

## Architectural Inspiration

This structure is validated by [spec-kit](https://github.com/github/spec-kit), GitHub's internal specification framework. We've adapted their templates for dream-studio's modular architecture and skill-based workflow.

## Credits

- **spec-kit** (GitHub) — Template structure and user story prioritization
- **dream-studio core team** — Skill integration and [P] parallel markers
