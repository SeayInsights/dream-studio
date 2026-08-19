# Lightweight GitHub CI Strategy

Dream Studio uses local validation as the heavy release gate and GitHub Actions
as a lightweight remote confidence layer. GitHub workflows should protect PRs
without burning a full matrix on every push.

## Workflow Profiles

| Workflow | Trigger | Purpose | Cost posture |
| --- | --- | --- | --- |
| local pre-push hook (`canonical/workflows/pre-push.yaml`) | every `git push` | Blocking gates: format, lint baseline, skill-sync, `tests/evals/` suite, 10 hardcoded pin-test files, `tests/unit` collect-only smoke, **test-list-completeness** (every path named in the pin-tests and pr-smoke lists must exist; names impact-relevant unlisted tests for the change set — WO-CI-COMPLETENESS), atlas-leak, docs-drift, migration-risk, dependency rules, fixture-resurrection, rubric-immutability. Runs a SUBSET of tests — local-green ≠ CI-green. | Fast local gate (~8 min) |
| `.github/workflows/ci.yml` (pr-smoke) | pull request, manual | **3-platform matrix** (ubuntu-latest, macos-latest, windows-latest): docs drift, Contract Atlas lifecycle, blast-radius, dashboard truth, format, lint baseline, pip-audit, and 11 hardcoded focused test files (10 unit + 1 integration) — NOT the full suite. `fail-fast: false` — all platforms run to completion even if one fails. The matrix watch on these 3 jobs is the sole merge authorization. | Required remote confidence |
| `.github/workflows/full-ci.yml` | push to main, manual | Remote run of `python interfaces/cli/ci_gate.py`: the **full test suite** (`pytest tests/` — evals + unit + integration), format, lint, agents-md freshness, docs-drift, atlas, blast-radius, and pip-audit. **Ubuntu-only, post-merge only** — most unit/integration tests first execute here, after code is already on main; the test-list-completeness gate prints that gap's size at every push. `timeout-minutes: 60`. The former standalone coverage step was removed — it re-ran all tests a second time and caused 45m timeouts once ci_gate started passing. | Comprehensive ubuntu check |
| `.github/workflows/release-validation.yml` | manual or `v*` tag | Release-candidate evidence; runs the local release gate and release profile tests | Release-only evidence |
| `.github/workflows/validate-skills.yml` | PRs changing `skills/**/*.md` | Path-scoped skill standards validation | Optional/path-scoped |

The required branch-protection check is `pr-smoke` (3 platforms). Full CI and release
validation are not required on every PR by default.

**The 3-platform PR Smoke is the load-bearing gate.** It runs on `pull_request` against
main — meaning it runs only on the PR branch, not after merge. `full-ci.yml` (post-merge)
is ubuntu-only and provides no cross-platform confidence. If you merge before `pr-smoke`
completes on all 3 platforms, you have committed code that has never been tested on macOS
or Windows in this CI cycle.

## Local Gate Reality

The local gate runs a subset:

```text
pre-push hook (canonical/workflows/pre-push.yaml):
  - format-check    (black --check)
  - lint-check      (lint_baseline.py)
  - skill-sync      (enforcement block regression check)
  - test-suite      (tests/evals/ ONLY — subset to stay OOM-safe on Windows)
  - atlas-leak      (contract atlas lifecycle)
  - docs-drift      (contract docs drift)
  - migration-risk  (schema-authority file change escalation)
```

The full test suite (`tests/`) OOMs on Windows locally (exit 137). It runs only in CI.
`py interfaces/cli/ci_gate.py` is the single local entry point for comprehensive parity
evidence (runs `tests/` + format + lint + docs drift + atlas lifecycle + security), but
it is not safe to run locally on Windows for the same reason. Ubuntu is the practical
target for `ci_gate.py` locally.

**Local-green ≠ CI-green** — not because of subtle cross-platform SQLite quirks (though
those exist), but because the local gate executes a subset of the test suite. Merge
authorization must come from the remote 3-platform matrix, not from local gate results.

## Local Parity

The local heavy gate remains:

```powershell
python scripts/runtime_state_hash_guard.py --label local_release_gate -- python interfaces/cli/ci_gate.py
```

That gate runs the full test suite, format check, lint baseline, Contract Atlas
docs drift, Contract Atlas lifecycle, and dependency audit. It should be run
before release closure, publication, merge approval, or any operator decision
that needs full confidence.

## Branch And Merge Policy

- Work happens on a branch or PR, not direct-to-main.
- `main` is the default target branch.
- PR smoke must pass unless GitHub Actions is unavailable or disabled.
- A passing local heavy gate is required for release readiness.
- Full GitHub CI can be run manually when the operator wants remote parity
  evidence, but it is not burned on every push.
- Deployment, tag creation, publishing, and merge remain explicit
  operator-approved actions.

### The Universal Merge Sequence

Every PR, no exceptions:

```powershell
gh pr ready <N>
gh pr checks <N> --watch   # wait — do NOT skip this step
gh pr merge <N> --squash --delete-branch
```

Never chain `gh pr ready && gh pr merge`. The chained form skips `pr-smoke`'s
3-platform completion and is the documented cause of multiple post-merge hotfix
cycles in Phase 18.x (migrations 081, 082, and the 18.4.6 near-miss).

The `migration-risk` pre-push gate fires when schema-authority files change
(migrations, sqlite_bootstrap.py, event_store.py) and blocks the push with a
visible matrix-watch reminder. It is an escalation for the highest-risk change
class; the universal matrix-watch rule applies to all PRs regardless of whether
the migration-risk gate fired.

If GitHub Actions is disabled, unaffordable, unavailable, or blocked by account
limits, development is not blocked. The release gate should record the remote
confidence gap, rely on local release-gate evidence for continued development,
and require manual operator review before merge/release approval.

## Authority

The CI/CD profile is repo-backed in
`runtime/config/release-gates/dream-studio.json` and mirrored by
`core.release.github_pr_cicd_gate`. Contract Atlas exposes it as
`github_cicd_profile`. Dashboard/API views may show the profile as derived
evidence, but GitHub is not Dream Studio authority.

<!-- Reviewed 2026-08-19 — WO-CI-COMPLETENESS (04953426, Adversarial Verification Integrity): the runtime/subset gap is now self-checking and visible. New blocking pre-push gate `test-list-completeness` (core/gates/test_list_completeness.py) validates every test path named in the pin-tests manifest and the pr-smoke focused list EXISTS — a deleted/renamed listed file is a dead guard and blocks push — and prints how many tests/unit files run only post-merge (full-ci, ubuntu-only), so silent truncation is at least visible at every push. The all_tests_pass close gate's legacy Path B (test-results.md containing the string "PASSED" — hand-writable, never freshness-checked) is RETIRED: with no executable TEST-CHECKs the gate reports UNVERIFIED explicitly and names the remediation (register a TEST-CHECK AC or attest). Close output additionally surfaces every originating-symptom SQL-CHECK verbatim with its live result and a trivially_true flag for FROM-less SQL (symptom_checks in the close result). -->
