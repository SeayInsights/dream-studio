---
name: harden
description: Project hardening audit and fix — checks 20 best-practice items (Makefile, pyproject.toml, UTC enforcement, Pydantic validation, SECURITY.md, CONTRIBUTING.md, test tooling, audit log, pre-commit, etc.) and fills gaps from templates. Trigger on `/harden`, `/harden audit`, `/harden fix tier1`, `/harden fix #N`.
---

# Harden — Project Standards Audit & Fix

## Trigger
`/harden` — runs full audit by default
`/harden audit` — audit only, no changes
`/harden fix tier1` — fix structural gaps (Makefile, pyproject.toml, SECURITY.md, CONTRIBUTING.md, requirements files)
`/harden fix #N` — fix a specific item by number

---

## Phase 1: Audit

Spawn an Explore subagent (model: haiku) with this task:

> Scan the current working directory for the 20 harden checklist items listed below. For each item, report: ✓ present / ✗ missing / ⚠ partial. Include a one-line reason for partial. Return as a markdown table. Also note any language (Python, TypeScript, etc.) and any existing CI files.

**The 20 checklist items:**

| # | Item | What to check |
|---|------|---------------|
| 1 | Makefile | File exists with `test`, `lint`, `fmt` targets |
| 2 | pyproject.toml | `[tool.black]` and `[tool.flake8]` sections present |
| 3 | Coverage config | `.coveragerc` or `[tool.coverage.*]` in pyproject.toml |
| 4 | UTC enforcement | No bare `datetime.now()` (without timezone) in source files |
| 5 | Input validation | Pydantic or schema validation at stdin/API entry points |
| 6 | SECURITY.md | File exists with contact and disclosure process |
| 7 | CONTRIBUTING.md | File exists with branch naming and commit format |
| 8 | freezegun | `freezegun` in dev requirements |
| 9 | factory_boy | `factory-boy` or `factory_boy` in dev requirements |
| 10 | Audit log | Append-only event log (`.jsonl`) written by handlers |
| 11 | .pre-commit-config.yaml | File exists with black and flake8 hooks |
| 12 | pip-audit | `pip-audit` in dev requirements or Makefile `security` target |
| 13 | Requirements split | Separate `requirements.txt` (runtime) and `requirements-dev.txt` |
| 14 | Error tracking | Sentry stub or equivalent in codebase |
| 15 | Bill of Materials | `scripts/bom.py` or equivalent BOM script |
| 16 | Integration tests | `tests/integration/` directory with test files |
| 17 | Health/status reporter | Handler or script for health check / pulse |
| 18 | CHANGELOG | CHANGELOG.md in Keep a Changelog format |
| 19 | README | README.md with setup instructions |
| 20 | Telemetry | Hook or handler usage telemetry (token log, audit.jsonl) |

After the Explore subagent returns:
1. Render the gap report as a scored table (✓/✗/⚠)
2. Count: X present, Y missing, Z partial
3. Ask: "Run `/harden fix tier1` to fill structural gaps, or `/harden fix #N` for a specific item?"

---

## Phase 2: Fix

### Tier 1 structural files (items 1, 2, 3, 6, 7, 11, 13)

For each missing structural file, copy from `templates/project-standards/` in the dream-studio repo:
- `Makefile` → project root (parameterize Python command if needed)
- `pyproject.toml` → project root
- `.coveragerc` → project root (or add to pyproject.toml)
- `SECURITY.md` → project root (replace `{{contact_email}}` and `{{project_name}}`)
- `CONTRIBUTING.md` → project root
- `.pre-commit-config.yaml` → project root
- `requirements.txt` → project root (stub)
- `requirements-dev.txt` → project root (stub, merge with existing)

**Never overwrite an existing file** — only fill gaps.

### Code stubs (items 4, 5, 8, 9, 10, 12, 14, 15)

For missing code-level items, create stub files with `# TODO: implement` comments:
- UTC enforcement: create `hooks/lib/time_utils.py` stub → replace bare `datetime.now()` manually
- Pydantic models: create `hooks/lib/models.py` stub
- Audit log: create `hooks/lib/audit.py` stub
- Sentry telemetry: create `hooks/lib/telemetry.py` stub
- BOM script: create `scripts/bom.py`

Copy from `templates/project-standards/hooks/lib/` where templates exist.

### Single-item fix (`/harden fix #N`)

Fix only the item with that number. Use templates where available, generate stubs otherwise.

---

## Rules

- Always confirm before overwriting any existing file
- Always run tests after making changes: `make test`
- Report what was changed and what still needs manual work
