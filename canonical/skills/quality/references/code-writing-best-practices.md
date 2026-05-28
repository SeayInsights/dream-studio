# Code-Writing Best Practices — Canonical Reference

**Source:** best-practices-master.md, LIST 4
**Status:** Active reference for ds-quality:code-quality skill (18.4.3)
**Last updated:** 2026-05-28

## Boundary with sibling skills

This document covers sections A, B, C, D, E, F, G, H, I, L, N of the master LIST 4. The following sections are deliberately excluded:

- **Section J (Security in code)** — covered by ds-quality:security (18.4.1). Code-quality rules cross-reference sec-* rules rather than duplicate.
- **Section K (Dependencies)** — deferred to ds-quality:types-dependencies (18.5.2).
- **Section M (Tooling & CI)** — mostly deferred to ds-quality:ops (18.6.3). Only "type checker automated" lands here as code-quality-adjacent.
- **Section O (Frontend-specific)** — covered by ds-quality:accessibility (18.4.2b) and ds-quality:frontend-ux (18.6.1, future).
- **Section P (Backend/API-specific)** — deferred to ds-quality:backend-api (18.5.3, future).

When code-quality rules touch concepts in deferred sections, they cross-reference the owning skill rather than re-implement.

## Severity legend

- 🔴 Mandatory — breaking issue, security-adjacent, or correctness violation
- 🟠 De facto standard — every serious project does this; skipping has real cost
- 🟢 Should have — best practice, judgment-dependent

---

## A. Foundational principles

- 🔴 Code is read 10× more than written — optimize for the reader
- 🔴 Make the easy thing right and the wrong thing hard
- 🔴 Explicit beats implicit
- 🔴 Single source of truth — every fact lives in one place
- 🟠 DRY, but not at the cost of coupling (AHA: Avoid Hasty Abstractions)
- 🟠 YAGNI
- 🟠 Composition over inheritance
- 🟠 Dependency inversion at module boundaries
- 🟠 Pure functions where possible
- 🟠 Immutability by default
- 🟢 Boy Scout rule (small doses)
- 🟢 Rule of three before extracting abstraction

## B. Functions

- 🔴 One job per function
- 🟠 Short — most 5-20 lines
- 🟠 Few parameters — 0-3 ideal, 4 smells, 5+ needs a struct
- 🔴 No boolean flag parameters that change behavior
- 🟠 One level of abstraction per function
- 🔴 Return early, fail fast — guard clauses, not nested if/else
- 🟠 No deep nesting (2-3 levels max)
- 🔴 No side effects from getters
- 🟠 Commands and queries separated (CQS)
- 🔴 No silent failures
- 🟠 Push non-determinism to the edges
- 🟢 Predictable signatures across similar functions

## C. Naming

- 🔴 Names reveal intent
- 🔴 Pronounceable
- 🔴 Searchable (named constants, not magic numbers)
- 🔴 No abbreviations except universal ones (url, id, db, http)
- 🟠 Length proportional to scope
- 🔴 Don't encode types in names
- 🔴 No noise words (data, info, manager, helper, util)
- 🔴 Functions are verbs (`calculateTotal`, `sendEmail`)
- 🔴 Booleans are predicates (`isActive`, `hasPermission`, `canEdit`)
- 🔴 Classes/types are nouns (`Invoice`, `UserRepository`)
- 🟠 Collections plural (`users`, not `userList`)
- 🔴 Symmetric pairs (`open`/`close`, not `open`/`stop`)
- 🟠 Consistent vocabulary (pick `fetch`/`get`/`retrieve`, stick with it)
- 🔴 Domain language matches the business
- 🟠 Avoid disinformation
- 🟢 Pronounce differences (no near-identical names)
- 🔴 Constants SCREAMING_SNAKE_CASE
- 🟠 Follow language conventions

### Case conventions by language

- **Python**: `snake_case` functions/vars, `PascalCase` classes, `SCREAMING_SNAKE` constants, `_leading_underscore` private
- **JS/TS**: `camelCase` vars/functions, `PascalCase` classes/types/components, `SCREAMING_SNAKE` constants
- **Rust**: `snake_case` functions/vars, `PascalCase` types, `SCREAMING_SNAKE` consts
- **Go**: `camelCase` unexported, `PascalCase` exported, short names preferred
- **SQL**: `snake_case` plural tables
- **CSS**: `kebab-case`, BEM if structured

## D. Files & module organization

- 🔴 One concept per file
- 🟠 File name matches primary export
- 🟠 Group by feature, not by type
- 🟠 Public API via index file
- 🔴 Consistent import order: std → third-party → internal → relative
- 🟠 No circular dependencies
- 🟢 Files under ~300 lines (soft target)

## E. Comments & documentation

- 🔴 Code says what, comments say why
- 🔴 No dead/commented-out code (git remembers)
- 🔴 No TODO without context (owner, date, condition)
- 🔴 Comments next to non-obvious decisions
- 🟠 Public API has docstrings
- 🟠 Docstrings describe behavior, not implementation
- 🔴 Update comments when code changes
- 🟢 Examples in docstrings for non-obvious usage
- 🟠 README in every project
- 🟢 ADRs for non-obvious decisions

### Docstring formats

- **Python**: Google style, NumPy, or reStructuredText — pick one
- **JS/TS**: JSDoc / TSDoc
- **Rust**: `///` with Markdown, `# Examples`, `# Errors`, `# Panics`, `# Safety`
- **Go**: sentence starting with function name; godoc renders directly

## F. Error handling

- 🔴 Errors are values, not surprises — Result/Either or deliberate throws
- 🔴 Catch what you can handle, propagate what you can't
- 🔴 Specific exceptions, not bare `except`
- 🟠 Errors carry context (user ID, request ID, operation)
- 🟠 No exceptions for control flow
- 🔴 Validate at boundaries — every external input is untrusted
- 🔴 Fail loudly in dev, gracefully in prod, always log
- 🟠 Idempotent retries with exponential backoff, max attempts, jitter
- 🟠 Circuit breakers for downstream failures
- 🟠 Errors at edges have stable codes/types
- 🟢 Distinguish expected vs unexpected errors in logging

**Cross-reference:** "Validate at boundaries" overlaps with security's sec-007 (input validation). Code-quality cares about errors propagating correctly; security cares about injection vectors. Both may fire on the same code, from different angles.

## G. Testing

- 🔴 Tests exist
- 🟠 Test behavior, not implementation
- 🟠 Test pyramid: many unit, fewer integration, fewer E2E
- 🔴 Tests are deterministic
- 🟠 Tests are independent
- 🟠 Arrange/Act/Assert (or Given/When/Then)
- 🟠 One logical assertion per test
- 🟠 Test names describe behavior
- 🟠 Mock at boundaries, not internals
- 🔴 Critical paths have integration tests
- 🟢 Property-based tests for invariants
- 🟢 Snapshot tests for UI/generated output
- 🟠 Coverage is a floor, not a ceiling
- 🔴 Tests run in CI before merge
- 🟠 Tests run fast locally

**Note:** Future ds-quality:testing skill (18.5.1) will be the dedicated home for testing rules. Code-quality covers basics until then. When 18.5.1 ships, these rules either migrate or are reduced to cross-references.

## H. Code structure & control flow

- 🔴 No magic numbers/strings
- 🟠 No nested ternaries
- 🟠 Switch/match for finite enums with exhaustiveness check
- 🟠 Loops over recursion in non-TCO languages
- 🟢 Map/filter/reduce when it reads more clearly
- 🟠 No mutable global state
- 🟠 Configuration from environment, not hardcoded
- 🔴 Constants at top of file/module
- 🟠 Group related code spatially
- 🟢 Public methods first, then private (or top-to-bottom story)

## I. Concurrency, async & state

- 🔴 Async functions are colored — design for it
- 🔴 No shared mutable state across threads/tasks without sync
- 🟠 Prefer message passing/queues over locks
- 🟠 Timeouts on everything that can hang
- 🟠 Cancellation propagates
- 🟢 Backpressure (bounded queues)
- 🔴 No `sleep()` as sync primitive in tests

## L. Version control

- 🔴 Atomic commits — one logical change
- 🔴 Meaningful commit messages
- 🟠 Conventional Commits format if team uses
- 🟠 Trunk-based or short-lived feature branches
- 🔴 Never force-push to shared branches
- 🟠 PR descriptions explain why
- 🟠 PRs small (<400 lines)
- 🟠 Squash messy commits before merge
- 🔴 `.gitignore` includes secrets, build artifacts, IDE/OS files

## M-partial. Type checking (only the code-quality-adjacent item from M)

- 🔴 Type checker automated (TS strict, mypy strict)

The rest of section M (formatter automation, linter automation, pre-commit hooks, CI gates, dependency scanning) is deferred to ds-quality:ops (18.6.3).

## N. Performance

- 🔴 Measure before optimizing
- 🔴 Algorithmic > micro
- 🟠 Cache deliberately, invalidate intentionally
- 🟠 Lazy load when sensible
- 🟠 Avoid premature abstraction that hides allocations or queries
- 🟢 Know your platform's hot spots
- 🟢 Performance budgets for critical paths

---

## Excluded sections (cross-reference to owning skills)

When a code-quality finding touches these areas, cross-reference rather than duplicate:

| Section | Topic | Owning Skill |
|---------|-------|--------------|
| J | Security in code | ds-quality:security (18.4.1) — sec-001 through sec-024 |
| K | Dependencies | ds-quality:types-dependencies (18.5.2, future) |
| M (most) | Tooling & CI | ds-quality:ops (18.6.3, future) |
| O | Frontend-specific | ds-quality:accessibility (18.4.2b) + ds-quality:frontend-ux (18.6.1, future) |
| P | Backend/API-specific | ds-quality:backend-api (18.5.3, future) |

When future skills ship, code-quality rules that cross-reference them are reviewed for whether they should remain as cross-references or migrate entirely.
