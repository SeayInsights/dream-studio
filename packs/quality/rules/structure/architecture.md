# Large-Scale Project Architecture Conventions

> Companion to `fsc.md`. FSC defines *where* things go.
> This rule defines *how to structure things so the project communicates intent* —
> for both human readers and Claude.

## Core Principle

**The shape of the codebase must communicate what the project does.**
A developer (or Claude) should be able to read the top-level directory and
know what the application does, who it serves, and where to find any given thing
— without opening a single file.

---

## 1. Screaming Architecture

Top-level folder names describe **what the application does**, not how it is built.

```
# bad — describes implementation layer, says nothing about the domain
controllers/
models/
services/
utils/

# good — screams what the application is
orders/
payments/
inventory/
notifications/
```

For dream-studio, plugin-mandated names (`hooks/`, `skills/`, `rules/`) ARE the
domain — they are acceptable because they describe what the plugin provides.

**Violation**: Top-level dirs named `utils/`, `helpers/`, `misc/`, `common/`,
`shared/`, `stuff/` signal that structure decisions were deferred, not made.

---

## 2. Co-location Over Type-Grouping

Everything related to one feature lives together. If you delete a feature,
you delete one folder — not 8 files scattered across 8 directories.

```
# bad (type-grouped — deleting "checkout" requires hunting)
controllers/checkout.py
models/cart.py
validators/checkout_validator.py
tests/test_checkout.py
types/checkout_types.py

# good (co-located — delete checkout/ and it's gone)
checkout/
  controller.py
  model.py
  validator.py
  types.py
  test_checkout.py
```

**Exception**: Shared utilities used by 3+ features belong in `lib/` or `shared/`
with a clear contract, not duplicated per feature.

---

## 3. Depth Budget

**Maximum 4 directory levels from the project root.**

| Level | Example | Rule |
|---|---|---|
| 1 | `src/` | Domain or layer |
| 2 | `src/checkout/` | Feature or module |
| 3 | `src/checkout/components/` | Sub-grouping |
| 4 | `src/checkout/components/form.py` | File |

If you need level 5, the structure is wrong — the feature needs splitting or
the grouping is incorrect. Deep nesting creates navigation tax that compounds
across a team and across Claude context reads.

---

## 4. Directory Contracts

Every non-trivial directory (more than 3 files) must have a `README.md` or
equivalent contract document that answers:

1. **What does this directory provide?** (one sentence)
2. **What is the entry point?** (which file to read first)
3. **What are the public interfaces?** (what callers should import)
4. **What should never be imported directly?** (internal implementation)
5. **What are the key invariants?** (things that must always be true)

For dream-studio specifically: `SKILL.md` serves as the contract for skill
directories. Handler directories use `hooks.json` as their registry.

---

## 5. File Size Discipline

| Size | Status | Action |
|---|---|---|
| < 200 lines | Ideal | None |
| 200–400 lines | Acceptable | Monitor — may need splitting |
| 400–600 lines | Warning | Plan the split |
| > 600 lines | Violation | Split now |

**Why this matters for Claude**: Files over ~400 lines exceed what Claude can
read in a single context pass and reason about completely. Large files mean
Claude must make changes with incomplete context, increasing error rate.

Split strategies:
- Separate public API from implementation (`api.py` + `_impl.py`)
- Extract distinct concerns into sub-modules
- Move types/constants to a dedicated file

---

## 6. Consistent Naming Schema

Pick one naming convention per file category and enforce it everywhere.
Inconsistent names mean files can't be found by prediction — only by search.

| Category | Pattern | Example |
|---|---|---|
| Event handlers | `on-{event}.py` | `on-pulse.py`, `on-game-validate.py` |
| Test files | `test_{module}.py` | `test_workflow_state.py` |
| Skill definitions | `SKILL.md` (uppercase) | `skills/build/SKILL.md` |
| Config files | `{name}.json` or `{name}.yaml` | `hooks.json`, `workflows.yaml` |
| Library modules | `{noun}.py` (lowercase snake) | `workflow_state.py`, `paths.py` |

**Violation**: Mixed conventions in the same category (`onPulse.py` alongside
`on-game-validate.py`). One schema, zero exceptions.

---

## 7. Dependency Direction

Dependencies must flow in **one direction only**, enforced by directory layout.

```
core/       ← imported by everything, imports nothing from above
lib/        ← imported by features, imports only from core/
features/   ← imports from lib/ and core/, never from other features/
handlers/   ← imports from lib/, never from features/
tests/      ← imports everything, imported by nothing
```

**Rule**: If directory A imports from directory B, B must never import from A.
**Violation signal**: Circular imports, "god modules" that everything depends on.

For dream-studio: `hooks/lib/` imports nothing from `hooks/handlers/`. Handlers
import from `hooks/lib/`. This boundary must be maintained.

---

## 8. Single Source of Truth

Every concept, constant, or configuration value has exactly one home.
No config split across `.env` + `config.py` + `settings.json`.
No type definition duplicated in two modules.

**Test**: Can you change a value in one place and have it take effect everywhere?
If no — it's duplicated and one copy will eventually drift.

---

## 9. Claude-Specific Optimizations

These principles apply specifically to how Claude reads and reasons about code:

**9a. Entry point clarity**
Every directory should make its entry point obvious. Claude reads the most
recently-modified or most-referenced file first. If there's no clear entry,
Claude wastes context on the wrong file.

**9b. Avoid implicit magic**
No dynamic imports, no autoloading based on file names, no `__all__` abuse.
Claude cannot reason about code paths it cannot trace statically.

**9c. Co-locate tests with the code they test**
When a bug is found, the test that covers it should be in the same visual
neighborhood as the code. This reduces the number of files Claude must hold
in context simultaneously.

**9d. README per directory describes the WHY, not the WHAT**
Code describes what. README describes why the structure exists, what constraints
shaped it, and what is NOT here (and why).

**9e. Grep-friendly naming**
Use names that are unique enough to be found by grep. `utils.py` in every
directory makes grep useless. `workflow_validation_utils.py` is findable.

---

## 10. Generated and Runtime State

Generated files, runtime state, and build artifacts must be:
- Gitignored
- Located in a clearly-named `build/`, `dist/`, `.cache/`, or user-data directory
- Never mixed with source files

**Dream-studio specific**:
- `.sessions/` — gitignored, generated handoff files
- `.dream-studio/` — gitignored, user data
- `__pycache__/` — gitignored
- `.planning/` — gitignored if ephemeral session artifacts

---

## Validation Checklist (Large-Scale Projects)

Run this when starting a new project, reviewing a PR, or auditing an existing codebase:

### Structure
- [ ] Top-level dirs describe the domain (not implementation layers)
- [ ] Maximum 4 levels of nesting from root
- [ ] No directories named `utils/`, `helpers/`, `misc/`, `common/` at top level
- [ ] Related files co-located by feature, not by type

### Contracts
- [ ] Every directory with 3+ files has a README.md or equivalent contract
- [ ] Entry point per directory is unambiguous
- [ ] Public API is explicitly separated from internal implementation

### Files
- [ ] No file exceeds 400 lines (600 hard cap)
- [ ] Naming schema is consistent within each file category
- [ ] No file name collisions across directories (grep-friendly names)

### Dependencies
- [ ] Dependency direction flows one way
- [ ] No circular imports
- [ ] No god modules (imported everywhere, imports everywhere)

### State
- [ ] Generated/runtime files are gitignored
- [ ] Config has a single source of truth
- [ ] No duplicate type definitions or constants

### Claude readability
- [ ] Top-level structure communicates what the project does without opening files
- [ ] No dynamic imports or autoloading magic
- [ ] Each directory's purpose is clear from its name alone
