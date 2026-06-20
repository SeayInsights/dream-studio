# Repo Publication Privacy

Dream Studio can be published only when the public repository contains product
source and sanitized public documentation without private operational history.

**2026-06-12 (WO b1961e3e):** No privacy boundary changes. `tests/unit/test_gate_fixture_resurrection.py` added to ci.yml smoke suite — public test source, no private data.

**2026-06-10 (WO-CONSTITUTION-GATES):** No privacy boundary changes. `core/gates/dependency_rules.py` and related tests added — public source, no private data.

## Publication Readiness Command

Run the non-mutating check:

```powershell
python interfaces\cli\repo_publication_readiness.py --strict
```

Refresh public evidence artifacts intentionally:

```powershell
python interfaces\cli\repo_publication_readiness.py `
  --clean-clone-status pass `
  --execute `
  --output-dir docs\publication
```

The checker reads repository source and Git path metadata only. It does not open
operator-local runtime state, mutate SQLite, rewrite history, push, tag,
deploy, or print matched secret values.

Release-gate evidence included in publication or pilot materials must come from
isolated validation runs and sanitized summaries. Raw command output, local
runtime paths, active SQLite locations, private Work Orders, and operator-local
evidence remain private even when the underlying gate passes.

## Public Repo Allowlist

The public repo may contain product source, schema migrations, tests, public
docs, examples, templates, sanitized adapter projections, sanitized demos,
sanitized release notes, and sanitized Contract Atlas exports.

## Private By Default

Do not publish Work Orders, handoffs, local evidence, operator decisions, raw
telemetry, SQLite DBs, backups, private dogfood traces, cutover or rollback
details, private external-project details, local absolute paths, secrets, or
sensitive values.

External project pipeline docs may publish the generic paused-by-default policy,
but not target-specific intake evidence, dirty-state output, validation reports,
or private route decisions. Docker profile docs may publish optional profile
contracts, but not container runtime evidence, mounted paths, secrets, or local
scanner output.

## History Boundary

Current-tree cleanliness is not enough if Git history contains private runtime
artifacts. History rewrite, force-push, tag, push, deploy, cleanup, or
publication requires explicit operator approval and release-policy alignment.

**Phase 18.1.14b (2026-05-25):** Enterprise bring-back added `core/org_intelligence/` and `projections/ml/` to the public repo. Both packages contain no private content, no personal data, no operator-local paths, and no proprietary framing. They are clean OSS source under the main license. Phase 18.1.14c (Git history rewrite) is explicitly deferred and requires separate operator authorization before proceeding.

## Sanitized Contract Atlas Export

Use `ds contract-atlas-refresh --output-dir docs\publication --execute` only for
the public sanitized export. Do not use `--include-private` for repo-tracked
exports.

Final installed-platform closeout should remain private dogfood evidence until
the operator explicitly chooses public release. The public repo can state that
the closeout route exists and requires operator approval before publication.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. README.md health-checks section added. fresh-install-validation.md updated to require both commands. No policy or runtime behavior change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.17: PR Smoke CI expanded to multi-OS matrix (ubuntu-latest, macos-latest, windows-latest). pip-audit dependency vulnerability scan added to PR Smoke. Full CI workflow now also triggers on push to main (not just manual dispatch) and adds pytest-cov coverage gate (fail_under=8%). No policy or publication boundary change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.18: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true added to all 4 CI workflows ahead of 2026-06-02 mandatory Node.js 24 transition. INSTALL.md added as standalone installation reference. CHANGELOG updated with Phase 18.1.16-18.1.17 notes. No policy or publication boundary change in this doc. -->

<!-- Last reviewed 2026-05-27 — fix/ci-gate-db-path-collision: ci_gate.py _isolated_test_env() now uses separate mkdtemp calls for HOME and DREAM_STUDIO_DB_PATH so conftest.guard_real_homedir's _db_redirected check returns True and the CI abort guard does not fire on test DB writes. No release gate policy change; this is a CI isolation bug fix only. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: repo_publication_readiness.py extended with precision exclusions for contract_atlas.py (private content scan) and canonical/skills/quality/modes/security/ (secret scan). No privacy policy change. -->

<!-- Last reviewed 2026-05-29 — Phase 18.4.6 migration-risk gate: flake8-baseline.txt stale-entry cleanup + pre-push migration-risk gate added. No repo publication privacy change; the new gate operates at pre-push time and does not affect what is or is not tracked in Git. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-05: Wave 2 reviewed — validate-skills.yml CI workflow fixed to exclude deleted SKILL.md files (--diff-filter=d). No release-gate or publication policy change; no semantic change required in this doc. -->

<!-- 2026-06-06: WO-D dead discovery route removal — flake8-baseline.txt stale-entry cleanup. No repo publication privacy change; deleted routes had no public surface. -->

<!-- Last reviewed 2026-06-07 — WO-H hygiene & gate bookkeeping: flake8-baseline regenerated (171 dead entries removed). No change to publication privacy classification, sanitized export rules, or history path filtering. -->

<!-- Last reviewed 2026-06-07 — WO-N behavioral eval harness (18.8.3): full-ci.yml updated to add eval harness unit tests step. Step runs tests/evals/behavioral/test_eval_harness.py excluding TestLiveJudge (skipped in CI — requires functional claude -p subprocess). No change to publication boundary, release gate policy, Docker profiles, or privacy classification. CI-only, post-merge, ubuntu-latest. -->

<!-- Last reviewed 2026-06-07 — WO-N2 (fix/wo-n2-deterministic-evals): removed eval harness step from full-ci.yml. No change to publication boundary, release gate policy, Docker profiles, or privacy classification. CI eval step removal is internal-only. -->
<!-- Last reviewed 2026-06-09 — WO-F2 dead-code cleanup: removed 18 stale entries from flake8-baseline.txt for check_old_dbs.py and shared/mcp-integrations/ (already deleted in prior waves). Removed broken agent-browser.md link from verify/SKILL.md. No change to publication boundary, release gate policy, Docker profiles, or privacy classification. Release gate baseline pruned — only removing entries for files that no longer exist. -->

<!-- Last reviewed 2026-06-10 — WO-DEBT-H (chore/wo-debt-h-hygiene): regenerated flake8-baseline.txt from 707 (stale, 126+ entries for deleted files) down to 509 clean entries. No change to baseline policy, publication boundary, privacy classification, Docker profiles, or release gate enforcement logic. Baseline content change only — dead-file violations removed. -->

<!-- Last reviewed 2026-06-11 — WO-FULLCI-RED ci_gate.py truncation fix: ci_gate.py updated to print failures to stderr before truncating JSON output field. No private data is introduced or changed in publication scope. -->

<!-- Last reviewed 2026-06-11 — WO-EVAL-REGISTRY: migration 119 adds eval_registry and hook_eval_runs tables (no PII; eval run IDs, hook names, pass/fail, timestamps only). guardrails/evaluator.py write path unchanged in policy semantics — adds optional hook_id parameter for hook eval telemetry. ds eval registry list/show CLI added. All new schema is migration-authority-owned. No change to publication boundary, privacy classification, or Docker profile scope. -->

<!-- Last reviewed 2026-06-12 — WO f0e8f2c0 ci_gate.py failing_tests field: ci_gate JSON verdict adds failing_tests list (pytest node IDs, empty on pass). Diagnostic output only — no private data in test node IDs. No change to privacy classification or publication privacy policy. -->

<!-- Last reviewed 2026-06-13 — fix/full-ci-duplicate-test-run: removed duplicate pytest+coverage step from full-ci.yml; ci_gate.py already runs the full test suite internally. Bumped timeout-minutes from 45 to 60 as headroom. No change to publication boundary, privacy classification, or gate enforcement policy. -->

<!-- Last reviewed 2026-06-15 — WO-BLAST-RADIUS-GATE: new merge gate analyzes the diff for stale tests / broken callers / table-ownership conflicts. Reads repo source only; emits no private data. No change to privacy classification or publication privacy policy. -->


<!-- Last reviewed 2026-06-19 — WO-LIVE-DATA-GATE: .github/workflows/ci.yml pr-smoke gains a "Dashboard truth gate" step (`ds doctor dashboard-truth`) — a read-only live-authority invariant check that vacuously passes on the fresh CI DB, so unrelated PRs are unaffected. No release/publication boundary, packaging, or module-profile change. -->


<!-- Last reviewed 2026-06-20 — WO-P20-AGENTS-GEN: interfaces/cli/ci_gate.py adds an "agents-md-fresh" pre-push check (py -m integrations.compiler.agents_md --check) so a stale generated AGENTS.md is flagged. Read-only drift check; no release/publication boundary, packaging, or module-profile change. -->
