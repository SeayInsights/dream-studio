# Cleanup Work Discipline

**Purpose:** This document codifies how to execute cleanup work — table drops, dead code
removal, schema consolidation — without creating new problems in the process. Read it
before starting any cleanup WO. Reference it whenever a gate failure or test failure
occurs during removal work.

"Cleanup" here means: removing tables, functions, modules, endpoints, or tests that no
longer serve a production purpose. It does not mean reformatting, renaming, or
restructuring live code.

---

## Core Principles

### 1. Production value or it goes

Code, tables, endpoints, and modules must justify themselves through operator-facing value
or actual production work. Justification requires answering three questions:

1. What does this code produce?
2. Who calls it outside of test code?
3. What does the operator gain from the output?

"Has callers" is not sufficient. The chain must end at something an operator uses. A
function called by a test called by a CI gate called by nothing the operator ever sees is
dead code.

*Example from Phase 18.6.2:* `context_packet_prd_authority()` was called from
`context_packets.py` which was served via an API endpoint. Audit confirmed: the endpoint
existed, the dashboard fetched it, the dashboard displayed metadata from it. That earned
its place. But the `prd_project_authority` key inside the packet — containing `stop_gates`
and `forbidden_context` — was never read by any enforcement code. The key was removed; the
function eventually was too.

---

### 2. Substrate is authority

The code is the substrate. Tests, docs, gates, and dashboards are consumers. When any
consumer disagrees with the code, the consumer adapts. The code does not preserve old
structure to keep a consumer valid.

Corollary: When a test fails during cleanup, the test is wrong about what exists. When a
doc references a dropped table, the doc is out of date. When a gate fires on removed code,
the gate found real drift. In each case, the consumer needs updating — not the removal.

*Example:* After removing `record_project_intake()`, the test
`test_new_project_intake_creates_adaptive_prd_authority` failed. The correct action was to
delete the test. The wrong action would have been to keep the function to make the test
pass.

---

### 3. No new tables, no new columns "for future use"

Cleanup work is net-negative in schema size. The schema is sufficient. If cleanup reveals a
gap — "we dropped this table but nothing fills its role" — that gap is documented and
deferred to a future WO. It is not filled speculatively during the cleanup WO.

Corollary: Cleanup work does not create new projections, new migrations, or new API
endpoints. It removes existing ones.

---

### 4. Test failures during cleanup are removal signal

A test failing during cleanup is not a blocker to fix. It is a signal that the removal is
working correctly — the test was coupled to the removed code.

**Classify each failing test:**
- Test exercises a function that was deleted → delete the test
- Test asserts on a contract that was intentionally changed → update the assertion to match
  the new contract
- Test fails because an import now fails → update or delete the import

Never re-add the deleted code to make the test pass. Never mark the test as expected-fail
to defer the decision.

*Example:* `test_project_details_separates_health_and_sqlite_readiness_authority` asserted
`repo_scan.classification == "confirmed"`. The popup performance fix earlier on the same
branch changed this to `"deferred"`. The test was asserting on the old contract. Correct
action: update the assertion to `"deferred"`. Wrong action: revert the popup fix to make
the test pass.

---

### 5. Doc drift during cleanup is update signal

When a docs gate fires because a code change doesn't have companion doc updates, the docs
need updating. The code does not roll back to keep the docs valid.

The docs-drift gate requires that when code changes hit a domain trigger (e.g., modifying
`prd_authority.py` hits the `project_prd_authority_lifecycle` domain), the required
companion docs for that domain must be touched in the same changeset.

**How to handle docs-drift failures:**
1. Run the docs-drift gate with `DREAM_STUDIO_BASE_REF=origin/main` to see the full list
   of blocking domains and missing companion docs
2. For docs that need real updates (schema changes, API surface changes): update the docs
   semantically
3. For docs that don't need semantic changes: add a review comment in the `<!-- ... -->`
   format at the end of the file acknowledging the change was reviewed

Always commit the doc updates before re-running the gate. The gate uses `git diff`, not
working-tree state — uncommitted docs are invisible to it.

---

### 6. Gate failures get understood, not bypassed

`--no-verify` is not a workflow. Every gate failure requires classification:

| Gate failure | Correct response |
|---|---|
| format-check | Run `py -m black <file>` and commit the formatting |
| lint-check | Fix the lint violation; do not raise the baseline |
| test-suite | Classify each failing test per Principle 4 above |
| atlas-leak | Find and fix the schema mismatch in the empty-state response |
| docs-drift | Update the required companion docs; commit before re-running |
| migration-risk | Use `MIGRATION_RISK_ACKNOWLEDGED=1 git push` (bash inline form), not `--no-verify` |

`--no-verify` bypasses all gates including quality gates that may have real findings. It is
acceptable only when: (a) all quality gates have been confirmed passing in a prior run, and
(b) only a process escalation gate (migration-risk) remains, and (c) the proper bypass
mechanism fails due to environment constraints (Windows PowerShell env var isolation).

When `--no-verify` is used, document it in the PR body with the reason.

---

### 7. Pre-flight first, act second

Cleanup work without investigation produces drift. Before removing anything:

1. Confirm the table/function/module has zero production callers (not just zero test callers)
2. Confirm there are no FK dependencies, view dependencies, or code paths that would
   OperationalError post-drop
3. Confirm the removal chain — what else becomes dead when this is removed?

Pre-flight findings are hypotheses to verify against the code, not facts to act on blindly.
The pre-flight report may be wrong (W6 in the Phase 18.6.2 pre-flight misattributed
`save_prd_health_scorecard()` to `prd_authority.py` when it doesn't exist there). Always
verify each finding against the actual file before deleting.

---

### 8. Failures during removal are usually incomplete removal signals

When a cascade failure occurs during cleanup — a gate fails, a test breaks, an import error
appears — the first question is:

*"Does this failure indicate something is still referencing the removed code?"*

If yes: the correct action is to find and remove the reference, not to put the removed code
back.

*Example:* After removing `context_packet_prd_authority()` from `prd_authority.py`, the
atlas-leak gate failed with `KeyError: 'lifecycle_counts'`. This was not a reason to
restore the function. It was a signal that `contract_atlas.py` was accessing a key that
no longer appeared in `_empty_summary()`. The correct action was to make `_empty_summary()`
schema-complete for its callers — not to restore the deleted function.

---

## Execution Workflows

Three concrete tooling patterns from the Phase 18.6.2 gate friction investigation
(`.planning/specs/pre-push-gate-cleanup-friction.md`). Each comes from a real failure.

### Pushing a cleanup PR with a migration

Use the Bash tool with the inline env var form:

```bash
MIGRATION_RISK_ACKNOWLEDGED=1 git push -u origin <branch>
```

Do NOT use PowerShell for this. PowerShell env var isolation means setting
`$env:MIGRATION_RISK_ACKNOWLEDGED = "1"` in one command and running `git push` as a
separate command does not propagate the var to the git hook subprocess. The gate blocks.
The shortcut becomes `--no-verify`, which bypasses every quality gate, not just the
migration-risk escalation.

General rule: use the Bash tool — not PowerShell — for any `git push` that depends on an
environment variable reaching the hook process.

### Committing docs alongside code

The docs-drift gate uses `git diff origin/main...HEAD`, not the working tree. Uncommitted
doc updates are invisible to it. Running the gate before committing docs produces false
failures; adding doc files to the working tree and re-running still produces false failures.

Before running the docs-drift gate: commit the doc updates. Verify the full blocking domain
list first with:

```powershell
$env:DREAM_STUDIO_BASE_REF = "origin/main"; py interfaces/cli/contract_docs_drift_gate.py
```

This shows every domain that needs a companion doc in the same changeset, so you can front-
load all the doc updates in one commit rather than iterating gate-fail → update → re-run.

### Formatting after bulk deletion

Bulk line-range deletions — PowerShell `Set-Content`, agent edits, any mechanical removal
of large contiguous blocks — frequently leave inconsistent blank lines that fail
`format-check`. Black's "Python 3.12 cannot parse code formatted for Python 3.14" warning
is a cosmetic side effect of missing `target-version` configuration; it does not cause
failures by itself.

Run `py -m black <file>` immediately after any bulk deletion, before committing. Do not
wait for the gate to catch it — the gate adds a full test-suite run (~7 min) between the
format failure and the re-run.

---

## Behaviors During Cleanup Work

### When a test fails after a deletion

1. Read the test. What function or behavior is it testing?
2. If the function was deleted: delete the test.
3. If the function was modified: update the assertion to match the new behavior.
4. If neither: the test is testing something still live and is a real regression — investigate.

Do not use `@pytest.mark.skip` to defer the decision. Skip is a temporary marker for tests
that should be re-enabled; it is not a parking lot for dead code.

Exception: `@pytest.mark.skip` is acceptable as an intermediate state only when the
following are all true: (1) the test's function is being removed in a specific later commit
on the same branch, (2) that later commit is already planned and scoped in the WO, and (3)
the test will be deleted — not unskipped — in that commit before the PR opens.

If you cannot point to the specific later commit where the test gets deleted, delete it now.
"I'll handle it later" without a concrete plan is a skip-as-parking-lot.

### When a gate fires

Read the full gate output before acting. The "stdout tail" shown by the pre-push runner
is not the full output. Run the gate standalone to see the complete manifest.

For docs-drift: run `py interfaces/cli/contract_docs_drift_gate.py` with
`$env:DREAM_STUDIO_BASE_REF = "origin/main"` to see the full blocking domain list.

### When the pre-flight was wrong

Pre-flights are read-only investigations, not guarantees. If the pre-flight says "function
X has no callers" and then removing X causes an import error from file Y, the pre-flight
missed a caller. This is expected — grep-based caller detection misses dynamic references.

Response: trace the import error to its source, classify the caller (test code? production?
dead?), and proceed accordingly. Do not restore X. Do not trust the pre-flight over the
running code.

### When removing a function reveals helper functions that should also go

Cascade removal is correct. When function A is deleted and helper `_h()` was used only by
A, `_h()` goes too. Trace the full cascade before committing any individual deletion.

The cascade should be committed in thematic groups (writers in one commit, helpers in
another) for reviewability, but it must be complete before the PR lands.

---

## Anti-Patterns Explicitly Forbidden

### Adding fields to satisfy callers without investigating whether the callers should exist

**Symptom:** A gate fails because a caller accesses key `X` which doesn't exist in the
empty-state response. The runner adds key `X` to the empty-state response to fix the gate.

**Why it's wrong:** Adding `X` is correct only if the caller should exist and the empty-state
response is genuinely missing a key it should have. If the caller is dead code or the
entire function chain is vestigial, the right answer is to remove the caller, not satisfy
it.

**Correct behavior:** Before adding the key, verify that the caller is live production code
that delivers operator value. If it is: add the key and document why it belongs. If it
isn't: remove the caller along with the rest of the cleanup.

*From Phase 18.6.2 — the key is the order, not the outcome:*

When atlas-leak failed with `KeyError: 'lifecycle_counts'`, the runner's first instinct
was to add the missing key to `_empty_summary()` and move on. That instinct is the
anti-pattern when taken alone.

What made the key addition correct was a verification step that came first: tracing the
caller chain for `contract_atlas.py`. That investigation confirmed the atlas is called by:
(1) the `atlas-leak` CI/CD gate on every PR, (2) `ds install --rehearsal` on every new
install, and (3) a live API endpoint served by the dashboard. The atlas covers ~46 sections
of which only 1 (`prd_authority_lifecycle`) touched the dropped tables. The other 45 read
from stable sources. The atlas earns its place.

If that investigation had found the atlas vestigial — called only by tests, never by CI or
the dashboard — then adding the key would have been exactly the mistake this anti-pattern
names. The correct action would have been to remove `contract_atlas.py`'s access to
`prd_authority` and let the section return empty, not to satisfy a vestigial caller.

The lesson is the order: verify the caller chain before adding any key to pass a gate. The
outcome (key added, caller removed) follows from that verification. Acting on instinct
without the verification step is the anti-pattern.

---

### Adding operational limits to expensive operations without questioning whether the operation should happen at all

**Symptom:** A performance problem is identified in an expensive operation. The runner adds
a cap (e.g., "only process 2,000 paths") to make the operation cheaper.

**Why it's wrong:** The cap treats the operation as load-bearing when it might not be.
Before optimizing an expensive operation, verify it is on a production-critical path and
delivers operator value. If it isn't, remove it.

*From Phase 18.2:* `_repo_stack_evidence()` was walking 110,000+ files on every popup
load. The runner was about to add a 2,000-path limit. The correct action was to remove the
call from the critical path entirely, preserving the function for future opt-in use.

---

### Using --no-verify without knowing what each gate was checking

**Symptom:** A gate fires. The runner uses `--no-verify` to get the push through.

**Why it's wrong:** `--no-verify` bypasses all hooks, not just the failing gate. If the
runner doesn't know what each gate was checking, it cannot know whether the bypass is safe.

**Correct behavior:** Before using `--no-verify`, run the pre-push gate manually and confirm
every quality gate shows `[PASS]`. Document which gates passed and what the specific
remaining failure was.

---

### Treating pre-flight findings as facts rather than hypotheses

**Symptom:** The pre-flight says "table X has 0 rows and no callers." The runner drops the
table without verifying the caller count against the actual codebase. A production caller
that was missed surfaces post-merge.

**Why it's wrong:** Pre-flights use grep and static analysis. They miss dynamic references,
indirect callers, and features added after the pre-flight was written.

**Correct behavior:** For every function or table listed as "no callers" in a pre-flight,
run a verification grep immediately before deletion. Quote the grep result in the commit
message or PR as proof.

---

### Preserving test fixtures that exercise dead code

**Symptom:** A function is deleted. The test that exercises it is marked `@pytest.mark.skip`
rather than deleted.

**Why it's wrong:** A skipped test that exercises dead code is a maintenance burden with
zero value. It trains the skip-as-parking-lot pattern. It misleads future reviewers into
thinking the functionality might come back.

**Correct behavior:** Delete the test. If the functionality comes back, new tests are
written at that time.

---

## How to Apply This to a Cleanup WO

Every cleanup WO prompt should include:

```
Cleanup discipline: docs/operations/cleanup-discipline.md applies to this WO.
- Test failures = signal to classify, not blockers to fix by reverting
- Gate failures = understood and addressed properly, not bypassed
- Pre-flight findings = hypotheses, verify each caller before deleting
- --no-verify only when all quality gates confirmed passing
```

The pre-flight spec for the WO goes in `.planning/specs/<wording>-preflight.md`. The
pre-flight is read-only and produces a classification table. The WO execution verifies
each classification against the live code before acting.

When a cascade removal is needed (removing A reveals B which reveals C), plan the full
cascade in one analysis step before committing any individual deletion. Use thematic
commits (writers / helpers / tests / docs) rather than function-by-function commits.

---

*Created Phase 18.6.2, 2026-06-05 — from principles developed during the project_* family
drop and prd_authority dead-code removal.*
