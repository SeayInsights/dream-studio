# Implementation Plan: [FEATURE]

**Date**: [DATE] | **Spec**: `.planning/specs/[topic-name]/spec.md`  
**Input**: Feature specification from spec.md

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, TypeScript 5.3, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., React 19, FastAPI, Cloudflare Workers or NEEDS CLARIFICATION]  
**Storage**: [if applicable, e.g., D1, PostgreSQL, file system or N/A]  
**Testing**: [e.g., Playwright, pytest, Vitest or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Cloudflare Workers, browser, desktop or NEEDS CLARIFICATION]
**Project Type**: [e.g., skill/domain-doc/web-app/cli/dashboard or NEEDS CLARIFICATION]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, <200ms p95, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before implementation. Check against project constitution if exists.*

[Review against dream-studio principles and any project-specific constitution]

## Project Structure

### Documentation (this feature)

```text
.planning/specs/[topic-name]/
├── spec.md              # User stories, requirements (dream-studio:think output)
├── plan.md              # This file (dream-studio:plan output)
├── tasks.md             # Task breakdown (dream-studio:plan output)
├── research.md          # Optional: research findings
├── data-model.md        # Optional: data structures
└── contracts/           # Optional: API contracts
```

### Source Code

<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Adjust based on whether this is a skill, domain doc, or other.
-->

```text
# For dream-studio skills
skills/[skill-name]/
├── SKILL.md
├── skill.ts or skill.py
├── templates/
└── checklists/

# For domain documentation
skills/domains/[domain-name]/
├── REFERENCES.md
├── [topic]-patterns.yml
└── [topic]-standards.yml

# For features/tools
[appropriate location in project structure]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if there are complexity concerns that must be justified**

| Concern | Why Needed | Simpler Alternative Rejected Because |
|---------|------------|-------------------------------------|
| [e.g., Multi-agent coordination] | [current need] | [why single agent insufficient] |
| [e.g., New subdomain] | [specific problem] | [why existing domain insufficient] |

## Requirements Traceability

<!--
  Link implementation tasks to functional requirements from spec.md
-->

| Requirement ID | Description | Implemented By |
|---------------|-------------|----------------|
| FR-001 | [Brief description] | Tasks T001, T002 |
| FR-002 | [Brief description] | Task T003 |

## Dependencies

### External Dependencies
- [List any new npm packages, Python libraries, etc.]
- [Include version constraints if known]

### Internal Dependencies
- [List any dream-studio skills or domains this depends on]
- [Note any building blocks or shared patterns]

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| [Potential issue] | [High/Medium/Low] | [How to address] |

## Success Metrics

- [ ] All functional requirements from spec.md implemented
- [ ] All user stories testable independently
- [ ] Performance goals met (if specified)
- [ ] Integration with existing dream-studio patterns verified

## dream-studio Integration

**Skill Flow**: think → **plan** → build → review → verify → ship

**Output Location**: `.planning/specs/[topic-name]/plan.md` and `tasks.md`

**Next Steps**: 
1. Review this plan with user for approval
2. Run `dream-studio:build` with the tasks.md file
3. Execute tasks in dependency order
