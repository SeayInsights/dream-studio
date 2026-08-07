# Testing Best Practices — Canonical Reference

**Source:** best-practices-master.md, LIST 4, Section G (+ Section I sleep cross-reference)
**Status:** Active reference for ds-quality:testing skill (18.5.1)
**Last updated:** 2026-05-29

## Boundary with sibling skills

This document covers testing quality — the quality of test code itself. It does NOT cover:

- **Code testability** — covered by ds-quality:code-quality (18.4.3). CQ cares whether code is structured to be testable (pure functions, CQS, no side effects from getters). Testing cares whether the tests that exist are good.
- **CI tooling & gate configuration** — deferred to ds-quality:ops (18.6.3). Testing verifies "tests run in CI" exists; ops owns the CI gate structure.
- **Coverage tooling setup** — testing checks coverage adequacy; ops owns the tooling configuration.
- **Type-checking** — ds-quality:code-quality (cq-M-partial).

**Cross-references to adjacent skills:**
- `tst-011` (no sleep() in test bodies) ↔ `cq-019` (no sleep() in production code): same symptom, different scope. CQ fires on production code; testing fires on test code. Reports note the sibling rule.
- `tst-009` (critical paths have integration tests) ↔ `cq-016` (trust boundaries validated): CQ identifies entry points; testing verifies they're covered. Different files, different angles.

When code-quality findings touch testability, they may cross-reference testing:
"Consider ds-quality:testing after refactoring to assess whether new tests are well-structured."

## Severity legend

- 🔴 Mandatory — tests don't actually work or aren't run; correctness and coverage failures
- 🟠 De facto standard — quality degrades visibly when skipped; real risk over time
- 🟢 Should have — best practice, judgment-dependent

---

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

---

## I. Concurrency (testing-relevant cross-reference)

- 🔴 No `sleep()` as sync primitive in tests

This item from Section I is assigned to ds-quality:testing because its manifestation is in test code. The production-code variant (no sleep() in production) is owned by ds-quality:code-quality (cq-019). Both rules may fire on the same commit; reports note the sibling.

---

## Testing patterns and anti-patterns

### What "test behavior, not implementation" means

**Test behavior (good):** Invoke the public API with a specific input, assert the observable output or side effect.
```python
def test_invoice_total_includes_tax():
    invoice = Invoice(items=[Item(price=100)], tax_rate=0.1)
    assert invoice.total() == 110
```

**Test implementation (bad):** Assert that specific internal methods were called, or inspect private state.
```python
def test_invoice_calculates_tax():
    invoice = Invoice(items=[Item(price=100)], tax_rate=0.1)
    invoice.calculate()
    assert invoice._tax_amount == 10  # private attribute
```

### What "mock at boundaries, not internals" means

**Boundary mock (good):** Mock at the edge of your system (external API, file system, database connection).
```python
def test_user_service_creates_user(mock_db):
    # mock_db patches the database adapter at the boundary
    service = UserService(db=mock_db)
    service.create(name="Alice")
    mock_db.insert.assert_called_once()
```

**Internal mock (bad):** Mock a private method or internal collaborator within the same module.
```python
def test_user_service_creates_user():
    service = UserService()
    service._validate_input = MagicMock(return_value=True)  # mocking internals
    service.create(name="Alice")
```

### What "one logical assertion" means

One *concept*, not one `assert` statement. A test that asserts three properties of a created record (id is not None, name matches, created_at is recent) is testing one concept (record was created correctly). A test that checks both creation AND deletion in the same body is testing two concepts.

### The AAA pattern

- **Arrange:** Set up the test data and context (fixtures, mocks, test objects)
- **Act:** Invoke the code under test (one invocation)
- **Assert:** Verify the observable result

Tests that lack a clear Act step, or that mix multiple Act-Assert cycles, are testing multiple behaviors and should be split.

### Fixture scope pitfalls

- **function-scoped fixtures** (default): fresh instance per test — safe, independent
- **module-scoped fixtures:** shared across all tests in a file — risky if any test mutates the fixture
- **session-scoped fixtures:** shared across the entire test run — use only for truly read-only expensive resources (e.g., a read-only database populated once)

Any session or module fixture that holds mutable state is a source of test-order dependence and flakiness.

### Dream Studio pattern: conftest.py early isolation

Dream Studio's `tests/conftest.py` redirects `DREAM_STUDIO_DB_PATH`, `DREAM_STUDIO_HOME`, and `DS_SPOOL_ROOT` at **module import time** (before pytest collection), not in a fixture. This is the correct pattern for preventing singleton contamination — if a production module caches a DB path singleton at import time, a fixture-level redirect is too late. The testing skill recognizes this as a positive pattern and does NOT flag it as a violation of any rule.
