# Work Order Authoring Guide

## Task Acceptance Criteria

Each task description should include a clear **Acceptance** clause: a statement of what the operator
observes or can verify when the task is done correctly.

Example:
```
Build POST /api/auth/login in src/routes/auth.py.
Acceptance: operator can curl the endpoint and receive a signed JWT on valid credentials, 401 on invalid.
```

---

## SQL-CHECK Convention

For tasks whose AC can be verified by querying the authority database, use the `SQL-CHECK:` inline
check. The completion grader executes these queries before analyzing the diff and treats the results
as ground truth — a failing SQL-CHECK overrides diff inference.

### Format

Add one or more lines to the task's `acceptance_criteria` field, each starting with `SQL-CHECK:`:

```
SQL-CHECK: <SELECT statement>
```

The check **passes** if the query returns at least one row with a truthy first-column value
(e.g. `COUNT(*) > 0`, `1`, a non-null string). It **fails** on zero, null, no rows, or any
query error.

### Examples

```
# Task was completed if a row now exists:
SQL-CHECK: SELECT COUNT(*) FROM business_work_orders WHERE title LIKE 'WO-FOO%'

# Task was completed if a column was added (check via PRAGMA):
SQL-CHECK: SELECT COUNT(*) FROM pragma_table_info('business_tasks') WHERE name='acceptance_criteria'

# Task was completed if status transitioned:
SQL-CHECK: SELECT COUNT(*) FROM business_work_orders WHERE work_order_id='<id>' AND status='done'
```

### When to use

Use SQL-CHECK when the task's outcome is a database state change that is:
- Not reliably visible in a git diff (e.g. a row inserted by a migration, a column added)
- A known stable query that will not break if schema evolves around it

Do **not** use SQL-CHECK for:
- Behavioral/UX checks (use Acceptance: clauses instead)
- Checks that require production data not present in a test DB
- Queries that are only valid in a specific environment

### How the grader uses SQL-CHECK results

When `verify_work_order` runs, it executes all SQL-CHECK lines read-only against the authority DB
before spawning the completion grader. The results are injected into the task list as:

```
SQL-CHECK RESULT: PASS (result=1)
SQL-CHECK RESULT: FAIL (result=0)
SQL-CHECK RESULT: FAIL (error: no such table: ...)
```

A `FAIL` result forces the grader to return verdict `"missing"` for that task regardless of the
diff. A `PASS` result is strong evidence of completion but does not prevent `"partial"` if other
evidence is thin.
