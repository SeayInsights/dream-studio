# [PROJECT_NAME] Constitution
<!-- Example: dream-studio Constitution, [Client] Project Constitution, etc. -->

## Core Principles

### [PRINCIPLE_1_NAME]
<!-- Example: I. Modular Architecture -->
[PRINCIPLE_1_DESCRIPTION]
<!-- Example: Every component should have a single, well-defined responsibility; Clear interfaces between modules; No circular dependencies -->

### [PRINCIPLE_2_NAME]
<!-- Example: II. Quality Gates -->
[PRINCIPLE_2_DESCRIPTION]
<!-- Example: think → plan → build → review → verify → ship; Each stage has clear acceptance criteria; No skipping stages without justification -->

### [PRINCIPLE_3_NAME]
<!-- Example: III. Documentation-First -->
[PRINCIPLE_3_DESCRIPTION]
<!-- Example: Every skill has SKILL.md with purpose, inputs, outputs; Domain docs have REFERENCES.md; Plans reference specs; Code is self-documenting -->

### [PRINCIPLE_4_NAME]
<!-- Example: IV. Testing Requirements -->
[PRINCIPLE_4_DESCRIPTION]
<!-- Example: Integration tests for cross-component features; Unit tests optional unless complexity warrants; Manual verification required for UI changes -->

### [PRINCIPLE_5_NAME]
<!-- Example: V. Simplicity, VI. Performance, VII. Security -->
[PRINCIPLE_5_DESCRIPTION]
<!-- Example: Start simple, YAGNI principles; Premature optimization avoided; Security by default (no secrets in code, least privilege) -->

## [SECTION_2_NAME]
<!-- Example: Technology Standards, Deployment Policies, Git Workflow, etc. -->

[SECTION_2_CONTENT]
<!-- Example: 
- Never push directly to main
- Feature branch naming: feat/, fix/, chore/
- PRs under 120 lines
- CI handles deploys, never run wrangler deploy directly
-->

## [SECTION_3_NAME]
<!-- Example: Code Review Requirements, Quality Checklist, Performance Standards, etc. -->

[SECTION_3_CONTENT]
<!-- Example: 
- All PRs require review
- Security changes require dream-studio:secure
- UI changes require browser testing + screenshots
- Performance regressions blocked
-->

## Governance
<!-- Example: Constitution supersedes all other practices; Amendments require documentation, approval, migration plan -->

[GOVERNANCE_RULES]
<!-- Example: 
- All work must align with core principles
- Violations require explicit justification
- Constitution can be amended via RFC process
- CLAUDE.md and memory override defaults but not constitution
-->

**Version**: [CONSTITUTION_VERSION] | **Ratified**: [RATIFICATION_DATE] | **Last Amended**: [LAST_AMENDED_DATE]
<!-- Example: Version: 1.0.0 | Ratified: 2026-04-27 | Last Amended: 2026-04-27 -->

## dream-studio Integration

This constitution template is part of the dream-studio planning framework:
- Stored in `.planning/templates/constitution-template.md`
- Referenced by `dream-studio:think` and `dream-studio:plan` skills
- Project-specific constitutions should be placed in `.planning/constitution.md`
- Constitution gates are checked during plan phase before implementation
