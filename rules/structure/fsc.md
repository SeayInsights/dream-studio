# Folder Structure Conventions (FSC)

> Based on https://github.com/kriasoft/Folder-Structure-Conventions
> Applied to projects built and analyzed by dream-studio.

## Standard Top-Level Layout

```
project/
├── src/          # Source files (or lib/ for libraries, hooks/ for plugins)
├── tests/        # Automated tests
│   ├── unit/     # Pure function tests — no filesystem I/O, fast
│   └── integration/  # Full handler/service tests — filesystem, slower
├── docs/         # Documentation and reference material
├── build/        # Compiled output (gitignored)
├── LICENSE
└── README.md
```

## Rules

### Naming
- All top-level directories must use short, lowercase names
- No camelCase or PascalCase directory names at the top level
- Exception: `LICENSE`, `README.md` are uppercase by convention

### Source code
- Application source goes in `src/` or `lib/`
- Plugin hooks go in `hooks/` (plugin-specific variant of `src/`)
- Do not scatter source files at the root level

### Tests
- All automated tests live in `tests/` (preferred) or `test/`
- Split into `tests/unit/` and `tests/integration/` once the suite exceeds ~20 tests
- **Unit**: test pure functions in isolation — no filesystem, no network, no spawned processes
- **Integration**: test full handlers or services — may use filesystem via `tmp_path`
- CI should support `pytest tests/unit/` for fast pre-commit checks

### Documentation
- User-facing documentation goes in `docs/`
- Reference material (API specs, engine references) goes in `docs/reference/`
- Internal planning artifacts (`.planning/`, `.sessions/`) are gitignored — not docs

### Generated and runtime files
- Compiled output: gitignored under `build/` or `dist/`
- Session handoffs (`.sessions/`): gitignored — contain conversation history
- Runtime state (`.dream-studio/`): gitignored — user-specific
- `__pycache__/`, `*.pyc`, `.coverage`: gitignored

## dream-studio Self-Compliance

This plugin follows FSC with domain-specific adaptations:

| FSC Concept | dream-studio Implementation |
|---|---|
| `src/` / `lib/` | `hooks/` (plugin hooks = source) + `hooks/lib/` (shared library) |
| `tests/` | `tests/unit/` and `tests/integration/` |
| `docs/` | `docs/engine-ref/` (Godot4 reference) |
| `rules/` | Plugin-specific: coding standards for agents |
| `skills/` | Plugin-specific: reusable agent skill definitions |
| `agents/` | Plugin-specific: agent role definitions |
| `workflows/` | Plugin-specific: DAG workflow templates |

## Validation Checklist

When analyzing or scaffolding a new project, verify:

- [ ] No source files at the repository root (except `README.md`, `LICENSE`, config files)
- [ ] Test directory named `tests/` or `test/` (not `spec/` unless JS ecosystem)
- [ ] Tests split into `unit/` and `integration/` subdirectories if suite > 20 tests
- [ ] `docs/` present if the project has any non-trivial setup or API surface
- [ ] Generated/compiled files are gitignored
- [ ] All top-level directory names are lowercase
- [ ] No orphaned files outside any logical directory (e.g., stray `.py` files at root)

## Violations to Flag

Flag these when reviewing a project:

| Pattern | Severity | Fix |
|---|---|---|
| Source files at root level | High | Move to `src/` or appropriate dir |
| Tests mixed with source | High | Move to `tests/` |
| No `.gitignore` | High | Add one; exclude build artifacts + runtime state |
| All tests in a flat `tests/` beyond 20 tests | Medium | Split into `unit/` + `integration/` |
| No `docs/` with complex setup | Medium | Add basic usage documentation |
| Uppercase directory names (non-convention) | Low | Rename to lowercase |
| `build/` or `dist/` committed to git | High | Add to `.gitignore` |
