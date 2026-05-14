# Design: [FEATURE NAME]

**Date**: [DATE] | **Spec**: `.planning/specs/[topic]/spec.md`

> Use this template for complex features requiring architecture documentation. Output to `.planning/specs/[topic]/design.md`.

## System Overview

[1-2 paragraphs: what this system does, its boundaries, and how it fits into the larger project]

## Component Breakdown

| Component | Responsibility | Interface |
|-----------|---------------|-----------|
| [Name] | [What it owns] | [How others interact with it] |

## Key Decisions

### Decision 1: [Decision title]
- **Choice:** [What was decided]
- **Rationale:** [Why this choice]
- **Alternatives considered:** [What else was evaluated and why rejected]

### Decision 2: [Decision title]
- **Choice:**
- **Rationale:**
- **Alternatives considered:**

## Integration Points

| System/Service | How We Integrate | Data Exchanged |
|---------------|-----------------|----------------|
| [External system] | [REST/event/direct call] | [What goes in/out] |

## Data Flow

```
[Actor] → [Component] → [Storage/Service]
         ↓
    [Side effect or output]
```

## Known Constraints

- [Technical constraint or limitation]
- [Performance requirement]
- [Platform restriction]

## Open Questions

- [ ] [Question that needs answering before or during build]
