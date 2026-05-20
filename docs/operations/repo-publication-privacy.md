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

## Sanitized Contract Atlas Export

Use `ds contract-atlas-refresh --output-dir docs\publication --execute` only for
the public sanitized export. Do not use `--include-private` for repo-tracked
exports.

Final installed-platform closeout should remain private dogfood evidence until
the operator explicitly chooses public release. The public repo can state that
the closeout route exists and requires operator approval before publication.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->
