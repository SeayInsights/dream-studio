# Dream Studio Gates Reference

Two-tier gate system governing push authorization and work order closure.

**Pre-push workflow:** `canonical/workflows/pre-push.yaml`  
**Runner:** `core/gates/pre_push.py`  
**CI strategy:** `docs/operations/lightweight-github-ci-strategy.md`

---

## Two-Tier Model (AD-3)

| Tier | Failure behavior | Covers |
|------|-----------------|--------|
| **Blocking** | Exit 1 — halts `git push` | Correctness, safety, authority integrity |
| **Advisory** | Prints `[WARN]` — push proceeds | Hygiene, drift, informational |

---

## Pre-Push Gates

Run via `ds workflow run pre-push --non-interactive` (triggered by `hooks/git/pre-push`).  
Local invocation: `py -m core.gates.pre_push`.

| Gate | Tier | What it checks | Command |
|------|------|----------------|---------|
| `format-check` | blocking | `black --check .` — zero files would reformat | `py -m black --check .` |
| `lint-check` | blocking | flake8 — no new findings beyond pinned baseline | `py interfaces/cli/lint_baseline.py check` |
| `skill-sync` | blocking | `_ENFORCEMENT_BLOCK` constant has zero `py -m interfaces.cli.ds` refs | `py -m core.gates.skill_sync_source` |
| `test-suite` | blocking | `tests/evals/` eval suite passes | `py -m pytest tests/evals -q` |
| `atlas-leak` | blocking | Contract Atlas lifecycle — no unauthorized projection leakage | `py interfaces/cli/contract_atlas_lifecycle_gate.py` |
| `docs-drift` | advisory | WORKFLOW_RUNTIME.md + HOOK_RUNTIME.md review markers current | `py interfaces/cli/contract_docs_drift_gate.py` |
| `migration-risk` | blocking (escalation) | SQL/migration/schema-authority files changed — prints matrix-watch reminder | `py -m core.gates.migration_risk` |

**Stop-on-first-failure:** First blocking gate failure stops the run. Advisory gates never stop the run.

**Environment:** `DREAM_STUDIO_BASE_REF` defaults to `origin/main`. Override to compare against a different base.

---

## Migration-Risk Gate

**Applies to** changes in any of these paths on the current branch vs `origin/main`:

```
core/event_store/migrations/     ← SQL migration files
core/config/sqlite_bootstrap.py  ← migration runner + swallow handler
core/event_store/event_store.py  ← Python DDL for canonical_events
core/config/schema_coherence.py  ← aspirational-schema audit
```

**Behavior:**
1. Detects changed files matching risk patterns
2. If matches found AND not running in CI (`GITHUB_ACTIONS != true`):
   - Prints visible warning with matrix-watch instructions
   - Lists all 3 CI platforms: `ubuntu-latest`, `macos-latest`, `windows-latest`
   - Exits 1 (blocks push)

**Bypass:** `MIGRATION_RISK_ACKNOWLEDGED=1 git push`  
**CI:** Always returns 0 inside GitHub Actions to avoid false positives in the matrix.

**Why this exists:** Migration files historically pass local tests but fail on macOS/Windows in the remote matrix (Phase 18.x regressions: migrations 081, 082, near-miss 18.4.6).

---

## Work Order Close Gates

Applied by `ds work-order close <wo_id>`. Gate checked automatically — failure blocks closure.

| Gate | Requires | Work order types that trigger it |
|------|---------|----------------------------------|
| `design_brief_locked` | Locked design brief in project | `ui_component`, `ui_page`, `saas_feature` |
| `api_contract_exists` | `.planning/work-orders/<id>/api-contract.md` | `api_endpoint`, `saas_feature` |
| `api_contract_and_security_review` | Both files above | `authentication` |
| `security_scan` | `.planning/work-orders/<id>/security-scan.md` with no BLOCKED findings | `infrastructure` (and any WO with security-critical changes) |
| `all_tests_pass` | `.planning/work-orders/<id>/test-results.md` with PASSED | `deployment`, `data_pipeline`, `game_mechanic`, `authentication` |
| `design_critique` | `.planning/work-orders/<id>/design-critique.md` with `Score: N/M ≥ 3` | `ui_component`, `ui_page` |
| `spec_approved` | `.planning/work-orders/<id>/spec.md` | `game_mechanic` |

**Force-close:** `ds work-order close <id> --force` bypasses gates. Requires explicit operator approval. Emits `gate.bypassed` event.

---

## Merge Authorization — Two-Tier Rule

**Push authorization:** Pre-push gate green (all 7 gates pass or advisory-only failures).

**Merge authorization:** ALL THREE matrix platforms green on `pr-smoke`:
- `ubuntu-latest`
- `macos-latest`
- `windows-latest`

**Correct merge sequence — no exceptions:**

```powershell
gh pr ready <N>
gh pr checks <N> --watch   # wait for all 3 platforms — do NOT skip
gh pr merge <N> --squash --delete-branch
```

**Never chain** `gh pr ready && gh pr merge` — that skips the matrix watch and is the documented cause of Phase 18.4.x post-merge hotfixes.

---

## CI Workflows

| Workflow | Trigger | Platforms | Scope |
|----------|---------|-----------|-------|
| `ci.yml` (`pr-smoke`) | pull_request, manual | ubuntu + macos + windows | Docs drift, Contract Atlas, format, lint, focused gate tests. `fail-fast: false` |
| `full-ci.yml` | push to main, manual | ubuntu-only | Full test suite + coverage. Post-merge verification. |
| `release-validation.yml` | manual or `v*` tag | Release | Release-candidate evidence + release profile tests |
| `validate-skills.yml` | PRs changing `skills/**` | ubuntu | Skill standards validation |

**Required branch-protection check:** `pr-smoke` (all 3 platforms)

---

## Local vs CI Gate Scope

| Context | Test scope | Authorization level |
|---------|-----------|-------------------|
| Pre-push gate (local) | `tests/evals/` only | Necessary but not sufficient |
| `pr-smoke` (CI matrix) | Gate tests + format/lint | **Merge authorization** |
| `full-ci.yml` (CI, post-merge) | Full `tests/` suite | Post-merge verification |

**Why the gap exists:** Full `tests/` takes ~79 minutes on Windows (subprocess spawn overhead: 3–12s per call, 52 calls across 20 test files). OOM-safe (peak ~283MB). Local gate runs the evals subset to stay within development iteration speed.

---

## Gate Event Emission (B.4)

Each failed pre-push gate emits a `gate.pre_push.failed` event via `CanonicalEventEnvelope`. Session harvester routes patterns to `reg_gotchas`. Best-effort — spool-write failure logs to stderr but never aborts the gate run.

---

## Cross-references

- Pre-push workflow definition: `canonical/workflows/pre-push.yaml`
- Migration-risk gate source: `core/gates/migration_risk.py`
- Pre-push runner: `core/gates/pre_push.py`
- CI strategy rationale: `docs/operations/lightweight-github-ci-strategy.md`
- Events: [`docs/reference/events.md`](events.md) — `gate.pre_push.failed`, `gate.bypassed`
- Guardrails (separate from gates): [`docs/reference/guardrails.md`](guardrails.md)
