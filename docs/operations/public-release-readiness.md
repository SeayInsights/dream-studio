# Public Release Readiness

The release-blocker checklist gating a public Claude Code marketplace / plugin release of
Dream Studio. The **ship gate** (`ds-core:ship`) and the `WO-REL-SHIP-CLOSEOUT` work order
consult this checklist; a release is **NO-GO** until every blocker below is cleared and the
operator records an explicit go.

## Release-blocking checklist

1. **Green full-ci on main (sustained).** `full-ci.yml` (the full unit suite + `pip-audit`,
   ubuntu-only, post-merge) must be green across a sustained streak on `main` — not a single
   run. The 3-platform `pr-smoke` matrix is necessary but **not sufficient**: it runs a
   focused subset, so `pr-smoke`-green ≠ full-suite-green (the documented runtime/subset gap).
2. **Zero open release-blocking work orders.** No `created` / `in_progress` / `blocked` WO in
   a release-gating milestone.
3. **Publication boundary clean.** `build_repo_publication_readiness` reports the tracked tree
   publication-safe — no secrets, no operator-local paths, and no private state
   (`studio.db` / `files.db` / diagnostics / private evidence) tracked or shipped. See
   `docs/PUBLICATION_BOUNDARY.md`.
4. **Packaging finalized.** The plugin + marketplace manifests point at the public source and
   install cleanly (`WO-REL-PACKAGING`).
5. **Ship-closeout PASS + operator go/no-go.** `WO-REL-SHIP-CLOSEOUT` records a passing ship
   gate + installed-platform closeout and the operator's explicit **GO**.

## Full-CI baseline

- **Before 2026-08-06:** `main`'s `full-ci` was **red** — most recently on exactly two
  failures out of the full suite (5071 passing): a fragile dashboard-route test that touched
  `.path` on non-path route objects, and a stale outcome-eval test asserting a retired disk
  `ESC-*.md` escalation file (escalations moved to the authority store). Both fixed in
  `WO-REL-CI-BASELINE`.
- **Baseline start:** the sustained-green streak begins at the commit that lands those fixes.
  Record the consecutive-green run count here as it accrues; a release requires a sustained
  streak, not the first green run.

## How this is enforced

The ship gate reads this checklist; `WO-REL-SHIP-CLOSEOUT` is the executable close-out that
verifies each blocker and captures the operator go/no-go before any public publish.
