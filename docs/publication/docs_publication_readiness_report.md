# Docs Publication Readiness Report

Generated: 2026-05-15T15:56:46.463837+00:00

## Verdict

`CURRENT_TREE_AND_HISTORY_CLEAN_CLEAN_CLONE_VALIDATION_REQUIRED`

The current tracked tree is publication-safe when the checks below pass. Dream
Studio keeps product source, public docs, tests, templates, adapter projection
metadata, and sanitized generated exports in Git. Private operational history
belongs in operator-local runtime state and is not source authority.

## Current Tree

- Branch: `main`
- Head: `afe91411ce74072c0a7e7d16939fda74070a16d3`
- Tracked files audited: 1604
- Private/local artifacts currently tracked: 0
- Untracked publication-risk files: 0
- Secret-pattern findings: 0
- Apache-2.0 license consistency: pass
- README product framing: pass
- PRD product authority: pass

## Public/Private Boundary

Public repository content is limited to product source, public documentation,
schema migrations, tests, examples, templates, sanitized adapter projections,
sanitized demos, sanitized release notes, and sanitized Contract Atlas exports.

Private-by-default material remains out of Git: Work Orders, handoffs, local
evidence, operator decisions, raw telemetry, local SQLite databases, backups,
private dogfood traces, cutover or rollback details, private external-project
details, local absolute paths, secrets, and sensitive values.

## Clean Clone

Clean-clone validation status: `not_run`.

## Git History Privacy

Publication-blocking private artifacts in history:

- None

History rewrite, force-push, tag, push, deploy, cleanup, or live-state mutation
requires explicit operator approval and was not performed by this check.

## Evidence Files

- `docs/publication/repo_publication_cleanliness_certificate.yaml`
- `docs/publication/tracked_file_audit.yaml`
- `docs/publication/ignored_file_audit.yaml`
- `docs/publication/git_history_privacy_audit.yaml`
