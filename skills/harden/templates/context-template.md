# Context — [Project Name]

> Copy this file to your project root as `CONTEXT.md`. Fill in the sections below.
> CONTEXT.md is the shared domain vocabulary for this project. It prevents AI verbosity
> and drift by defining what terms mean in THIS codebase specifically.

## Domain Terms

| Term | Definition | Example Usage |
|------|-----------|---------------|
| [term] | [what it means in this project] | [how it appears in code/docs] |
| session | [e.g., "A Power BI workspace, not a web session"] | `GET /sessions` returns workspaces |

## Abbreviations

| Abbrev | Stands For | Context |
|--------|-----------|---------|
| [abbr] | [full form] | [where used] |
| PLM | PLMarketing | Appears in org names, table prefixes |

## What Words Mean Here

Disambiguation for terms that mean something different in this project than in general usage:

- **[word]**: In this project, "[word]" means [project-specific meaning], NOT [common meaning].
- **report**: Refers to a Power BI report file (.pbix), not a generated text document.

## What This Is Not

Scope boundaries — what this project does NOT do, to prevent scope creep:

- This project does NOT [out-of-scope thing]
- [Feature] is handled by [other system], not here

## Naming Conventions

- Files: [convention, e.g., kebab-case]
- Variables: [convention, e.g., camelCase]
- Tables/columns: [convention, e.g., snake_case, PascalCase]
- Branch names: [convention, e.g., feat/topic, fix/issue-N]
