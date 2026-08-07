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

- **Before 2026-08-06:** `main`'s `full-ci` was **red** on every run this session — a
  documented pr-smoke-vs-full-suite gap surfacing three failures in total (out of ~5073
  passing): a fragile dashboard-route test that touched `.path` on non-path route objects, a
  stale outcome-eval test asserting a retired disk `ESC-*.md` escalation file (escalations
  moved to the authority store), and a version-fragile prd-sow wiring assertion that scanned
  `app.routes` for a `.path` some FastAPI versions do not expose on wrapped included routers.
  All three fixed in `WO-REL-CI-BASELINE` (#589 fixed the first two; #590 fixed the wiring
  assertion via `app.openapi()`).
- **Baseline start — first green:** `full-ci` run `31110598731` at commit `9654946e`
  (2026-08-06) is the first green full-suite run on `main`. The sustained-green streak begins
  here (streak: 1). Record the consecutive-green run count as it accrues; a public release
  requires a sustained streak (a `WO-REL-SHIP-CLOSEOUT` concern), **not** the first green run.

## Versioning

Dream Studio versions with **semver** (`MAJOR.MINOR.PATCH`). The top-level `VERSION` file is
the single source of truth; `integrations/marketplace/plugin_manifest.py` reads it verbatim
into `.claude-plugin/plugin.json`, and the once-per-day marketplace update check parses it as a
version tuple. The release-readiness gate (`core/release/versioning.py`) rejects any version
that is not valid semver.

- **Pre-1.0 (current: `0.1.0`).** The public surface is real and installable but still evolving;
  a `0.MINOR.PATCH` line makes no stability guarantee across minor bumps. Breaking changes bump
  the minor while in `0.x`.
- **`1.0.0`** is reserved for the first release that commits to a stable skill/CLI/route surface.
- The plugin and marketplace manifests are **generated** (`build_plugin_manifest` /
  `build_marketplace_manifest`) and parity-checked in `tests/unit/test_plugin_manifest.py`, so
  the version and the public source never drift from the manifests on disk.
- **Releases are cut by the `release` workflow** (manual `workflow_dispatch` with a semver
  version). It runs `core/release/changelog.py --apply`, which bumps the `VERSION` file and
  `pyproject.toml`, prepends the CHANGELOG section from the conventional commits since the last
  release, and regenerates both manifests — then opens a release PR. There is no manual
  "regenerate the manifests" step; the version bump and manifest regen are one automated action.

> Historical note: `VERSION` was previously date-based CalVer (`2026-07-02`). `WO-REL-PACKAGING`
> switched it to semver — the release-readiness gate already required semver, and the update
> check's version-tuple parse silently degraded on the date form.

## How this is enforced

The ship gate reads this checklist; `WO-REL-SHIP-CLOSEOUT` is the executable close-out that
verifies each blocker and captures the operator go/no-go before any public publish.
