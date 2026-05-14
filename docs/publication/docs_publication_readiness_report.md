# Docs Publication Readiness Report

Generated: 2026-05-14T22:18:08.566955+00:00

## Verdict

`CURRENT_TREE_CLEAN_HISTORY_REWRITE_OR_RISK_ACCEPTANCE_REQUIRED_BEFORE_PUBLICATION`

The current tracked tree is publication-safe after sanitizing operator-specific path fixtures and making the release-gate profile portable. The strict publication certificate remains blocked because Git history still contains private/local artifact paths.

## Current Tree

- Tracked files audited: 1545
- Private/local artifacts currently tracked: 0
- Untracked non-ignored files: 0
- Operator-specific absolute path findings in current tree: 0
- Apache-2.0 license consistency: pass
- README product framing: pass
- PRD product framing: pass

Repo-level `.claude/` files are classified as public adapter surfaces, not local user config. Generated/local Claude or Codex state remains private by boundary and is not tracked.

## Ignored And Local Boundary

`.gitignore` excludes runtime state, database files, backups, raw telemetry, local meta/work-order outputs, `.tmp`, `test_output`, logs, caches, and virtual environments. The ignored-file audit found ignored local/cache files only and no untracked publication-risk files.

## Clean Clone

A clean local clone was validated with HOME and USERPROFILE redirected to an empty temp home. Focused bootstrap, drift-gate, maturity ledger, and release-gate profile tests passed without using live `.dream-studio` state.

## Git History Privacy

Secret-pattern scan result: no findings.

Publication-blocking private artifacts remain in history:

- `.dream-studio/team/conventions.md` (runtime_state_path)
- `.dream-studio/team/gotchas.yml` (runtime_state_path)
- `.dream-studio/team/pack-overrides.yml` (runtime_state_path)
- `backups/analytics.db.2026-05-06-135343.bak` (backup_file)
- `backups/checksums.txt` (backup_file)
- `backups/studio-state.db.2026-05-06-135343.bak` (backup_file)
- `backups/studio.db.2026-05-06-135343.bak` (backup_file)
- `test_output/multiple/tokens.csv` (secret_or_auth_path)

These require an explicit operator decision before any history rewrite. No history rewrite, force-push, tag, push, deploy, cleanup, or live-state mutation was performed.

## Files

- `docs/publication/repo_publication_cleanliness_certificate.yaml`
- `docs/publication/tracked_file_audit.yaml`
- `docs/publication/ignored_file_audit.yaml`
- `docs/publication/git_history_privacy_audit.yaml`
- `docs/publication/clean_clone_validation_evidence.yaml`
