# External Project Validation Pipeline

Lifecycle status: runtime_validated

**2026-06-12 (WO b1961e3e):** No external validation pipeline changes. ci.yml smoke suite updated to include resurrection guard tests.

**2026-06-10 (WO-CONSTITUTION-GATES):** No external validation pipeline changes. ci.yml smoke suite updated to include dependency rule gate tests.

Dream Studio can track external projects, but external targets are paused by
default. The pipeline is reusable and target-scoped: it plans intake,
validation, evidence, dashboard visibility, and commit boundaries without
opening, scanning, mutating, staging, committing, pushing, or deploying a target
repo.

## Default Registry

The default external target registry contains DreamySuite, Bill Stack, TORII,
and future projects as paused external targets. A target is not readable just
because it exists in the registry. Read-only intake requires an explicit current
operator selection for that target and scope.

Default policy:

- external targets start paused
- read access requires explicit current target selection
- mutation requires scoped approval
- commit requires validation evidence and a commit policy
- push and deploy require separate approval
- no stale external route may auto-resume from old state

## Pipeline Steps

The non-executing pipeline records the intended Work Order sequence:

1. capture target boundary
2. verify current target selection
3. classify dirty state
4. detect PRD and project status
5. discover stack/dependency evidence
6. classify security/readiness scope
7. select validation profile
8. verify approval scope
9. run read-only validation
10. record target repo mutation eval
11. record validation evidence
12. route next decision

These steps are planning authority only. The pipeline reports
`external_repo_inspected=false`, `external_repo_mutated=false`, and
`execution_allowed=false` until a later scoped Work Order authorizes real target
access.

<!-- 18.1.14b review 2026-05-25: enterprise bring-back (core/org_intelligence/, projections/ml/) does not affect the external project validation pipeline. The enterprise source repo (dream-studio-enterprise/) was accessed READ-ONLY during bring-back; no external target read access was used. External targets remain paused. -->

## Evidence Separation

Private Dream Studio planning artifacts remain in Dream Studio SQLite or
operator-local `meta/` evidence. Target repos must not receive `.planning`,
Work Orders, handoffs, local evidence, backup dumps, SQLite databases, generated
runtime state, secrets, or private dogfood traces unless a later publication
policy explicitly approves a sanitized artifact.

Release-gate or pilot evidence for external-project workflows must use isolated
Dream Studio runtime state and sanitized summaries. It must not include raw
target paths, local runtime paths, private route decisions, or target-specific
evidence unless the current operator decision approves that exact disclosure.

## Dashboard Behavior

All Projects and Project Details may show a derived external target card with
paused status, dirty-state evidence, validation profile, risks, approval
requirements, and next action. The dashboard remains derived. It does not become
authority for resume, mutation, commit, push, or deploy approval.

## Validation

Static validation checks that:

- external projects default to paused
- read-only intake is gated by current target selection
- mutation, cleanup, push, and deploy are forbidden in the plan
- private target artifacts are excluded from target Git tracking
- Work Order evidence includes a target repo mutation evaluation
- dashboard cards are derived and non-authoritative

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. README.md health-checks section added. fresh-install-validation.md updated to require both commands. No policy or runtime behavior change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.17: PR Smoke CI expanded to multi-OS matrix (ubuntu-latest, macos-latest, windows-latest). pip-audit dependency vulnerability scan added to PR Smoke. Full CI workflow now also triggers on push to main (not just manual dispatch) and adds pytest-cov coverage gate (fail_under=8%). No policy or publication boundary change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.18: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true added to all 4 CI workflows ahead of 2026-06-02 mandatory Node.js 24 transition. INSTALL.md added as standalone installation reference. CHANGELOG updated with Phase 18.1.16-18.1.17 notes. No policy or publication boundary change in this doc. -->

<!-- Last reviewed 2026-05-27 — fix/ci-gate-db-path-collision: ci_gate.py _isolated_test_env() now uses separate mkdtemp calls for HOME and DREAM_STUDIO_DB_PATH so conftest.guard_real_homedir's _db_redirected check returns True and the CI abort guard does not fire on test DB writes. No release gate policy change; this is a CI isolation bug fix only. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: no external project validation pipeline change in this PR. Reviewed for compliance with release_publication_gate required_doc_refs. No policy change. -->

<!-- Last reviewed 2026-05-29 — Phase 18.4.6 migration-risk gate: flake8-baseline.txt stale-entry cleanup + pre-push migration-risk gate added. No external project validation pipeline change. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-05: Wave 2 reviewed — validate-skills.yml CI workflow fixed to exclude deleted SKILL.md files (--diff-filter=d). No release-gate or publication policy change; no semantic change required in this doc. -->

<!-- 2026-06-06: WO-D dead discovery route removal — flake8-baseline.txt stale-entry cleanup. No external project validation pipeline change; deleted routes were internal only. -->
<!-- Last reviewed 2026-06-07 — WO-H hygiene & gate bookkeeping: flake8-baseline regenerated. No change to external project validation pipeline behavior or validation rules. -->

<!-- Last reviewed 2026-06-07 — WO-N behavioral eval harness (18.8.3): full-ci.yml updated to add eval harness unit tests step. Step runs tests/evals/behavioral/test_eval_harness.py excluding TestLiveJudge (skipped in CI — requires functional claude -p subprocess). No change to publication boundary, release gate policy, Docker profiles, or privacy classification. CI-only, post-merge, ubuntu-latest. -->

<!-- Last reviewed 2026-06-07 — WO-N2 (fix/wo-n2-deterministic-evals): removed eval harness step from full-ci.yml. No change to publication boundary, release gate policy, Docker profiles, or privacy classification. CI eval step removal is internal-only. -->
<!-- Last reviewed 2026-06-09 — WO-F2 dead-code cleanup: removed 18 stale entries from flake8-baseline.txt for check_old_dbs.py and shared/mcp-integrations/ (already deleted in prior waves). Removed broken agent-browser.md link from verify/SKILL.md. No change to publication boundary, release gate policy, Docker profiles, or privacy classification. Release gate baseline pruned — only removing entries for files that no longer exist. -->

<!-- Last reviewed 2026-06-10 — WO-DEBT-H (chore/wo-debt-h-hygiene): regenerated flake8-baseline.txt from 707 (stale, 126+ entries for deleted files) down to 509 clean entries. No change to baseline policy, publication boundary, privacy classification, Docker profiles, or release gate enforcement logic. Baseline content change only — dead-file violations removed. -->

<!-- Last reviewed 2026-06-11 — WO-FULLCI-RED ci_gate.py truncation fix: ci_gate.py updated to emit failures to stderr before JSON truncation. External project validation pipeline logic is unchanged. -->

<!-- Last reviewed 2026-06-12 — WO f0e8f2c0 ci_gate.py failing_tests field: ci_gate JSON verdict adds failing_tests list. External project validation pipeline is unchanged — failing_tests is an internal diagnostic field only. -->

<!-- Last reviewed 2026-06-13 — fix/full-ci-duplicate-test-run: removed duplicate pytest+coverage step from full-ci.yml; ci_gate.py already runs the full test suite internally. Bumped timeout-minutes from 45 to 60 as headroom. No change to publication boundary, privacy classification, or gate enforcement policy. -->

<!-- Last reviewed 2026-06-15 — WO-BLAST-RADIUS-GATE: new pr-smoke blast-radius gate is internal to this repo's merge flow. External project validation pipeline is unchanged. -->


<!-- Last reviewed 2026-06-19 — WO-LIVE-DATA-GATE: .github/workflows/ci.yml pr-smoke gains a "Dashboard truth gate" step (`ds doctor dashboard-truth`) — a read-only live-authority invariant check that vacuously passes on the fresh CI DB, so unrelated PRs are unaffected. No release/publication boundary, packaging, or module-profile change. -->


<!-- Last reviewed 2026-06-20 — WO-P20-AGENTS-GEN: interfaces/cli/ci_gate.py adds an "agents-md-fresh" pre-push check (py -m integrations.compiler.agents_md --check) so a stale generated AGENTS.md is flagged. Read-only drift check; no release/publication boundary, packaging, or module-profile change. -->

<!-- Last reviewed 2026-06-24 — chore/docstore-move-files-db (three-store architecture fix): flake8-baseline.txt gains 3 E402 entries for interfaces/cli/migrate_docstore_to_files_db.py (lines 24-26: module-level imports after sys.path.insert — unavoidable pattern for standalone CLI migration scripts, consistent with migrate_files_to_sqlite.py and other migration utilities). No change to lint policy, publication boundary, packaging, docker module profiles, or privacy classification. The three new baseline entries represent known unavoidable debt (path manipulation before imports is standard practice for CLI scripts that cannot be imported as packages). -->
