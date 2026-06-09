# Gate System — Two-Tier Model (AD-3)

**Canonical reference for the Dream Studio gate system.**  
Implementation: `core/gates/pre_push.py`, `canonical/workflows/pre-push.yaml`, `core/work_orders/close.py`

---

## Two Tiers

Gates are classified into two tiers based on what they protect:

| Tier | Effect on push | Classification rule |
|------|---------------|---------------------|
| **Blocking** | Failure halts `git push` (exit 1). First failing blocking gate stops the run. | Correctness, safety, authority-integrity |
| **Advisory** | Failure surfaces a `[WARN]` line. Push proceeds. Overall result stays PASS. | Hygiene, drift, informational signals |

---

## Pre-Push Gate Registry

Defined in `canonical/workflows/pre-push.yaml`. Each gate declares its `tier`.

| Gate | Tier | What it checks |
|------|------|---------------|
| `format-check` | blocking | `black --check` — zero would-reformat files |
| `lint-check` | blocking | flake8 baseline — no new findings vs pinned baseline |
| `skill-sync` | blocking | A4/A5 enforcement block has no CLI subprocess regression |
| `test-suite` | blocking | `tests/evals/` must pass |
| `atlas-leak` | blocking | Contract atlas lifecycle — no PRD/contract leakage |
| `docs-drift` | advisory | Doc/code reference drift — hygiene signal only (Item 28) |
| `migration-risk` | blocking | SQL/migration changes require explicit matrix-watch confirmation |

---

## Work-Order Close Gates

Per-WO gates are evaluated in `core/work_orders/close.py`. These are always blocking — a failing close gate halts the close and returns the first failing step with a remediation instruction.

| Gate name | Trigger | Required artifact |
|-----------|---------|------------------|
| `security_scan` | all infrastructure WOs | `.planning/work-orders/<id>/security-scan.md` (no BLOCKED) |
| `api_contract_exists` | api_endpoint WOs | `.planning/work-orders/<id>/api-contract.md` |
| `api_contract_and_security_review` | api_endpoint + security | both files above |
| `spec_approved` | spec-gated WOs | `.planning/work-orders/<id>/spec.md` |
| `all_tests_pass` | test-gated WOs | `.planning/work-orders/<id>/test-results.md` with PASSED |
| `design_critique` | design WOs | `.planning/work-orders/<id>/design-critique.md` with Score: N/M ≥ 3 |
| `design_brief_locked` | brief-gated WOs | design brief in locked state |

---

## Merge Authorization

Merge requires all three CI matrix platforms green (ubuntu-latest, macos-latest, windows-latest).

```
gh pr ready <N>
gh pr checks <N> --watch   # wait for all 3 platforms
gh pr merge <N> --squash --delete-branch
```

The pre-push gate is a necessary but not sufficient merge prerequisite. The merge matrix runs `gate tests + format/lint` (not the full test suite). See `docs/operations/lightweight-github-ci-strategy.md`.

---

## Advisory Gate Behavior

An advisory gate failure:
- Prints `[WARN] <gate-id>` with the `advisory:` message
- Does NOT set overall result to FAIL
- Does NOT emit a `gate.pre_push.failed` event
- Does NOT stop subsequent blocking gates from running

Use advisory gates for hygiene signals where the cost of false positives (blocking valid pushes on stamps/drift) exceeds the value of enforcement. The operator sees the warning and can address it in a follow-up PR.

---

## Adding or Reclassifying a Gate

1. Add/update the entry in `canonical/workflows/pre-push.yaml` with `tier: blocking|advisory`.
2. If adding a WO-close gate: add a branch in `core/work_orders/close.py:run_gate_check()`.
3. Update this file.
4. Verify with a test run: a blocking gate halts on failure; an advisory gate emits `[WARN]` but overall passes.
