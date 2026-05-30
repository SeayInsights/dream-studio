# Repo Publication Privacy

Dream Studio can be published only when the public repository contains product
source and sanitized public documentation without private operational history.

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
