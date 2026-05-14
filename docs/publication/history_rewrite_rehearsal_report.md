# Git History Privacy Rewrite Rehearsal Report

Generated: 2026-05-14T22:46:00.642479+00:00

The rewrite rehearsal succeeded using `git-filter-repo` in a temp mirror clone. The real local repository and GitHub remote were not rewritten.

## Result

`HISTORY_REWRITE_REHEARSAL_VALIDATED_PENDING_OPERATOR_APPROVAL`

## Evidence

- `docs/publication/history_rewrite_rehearsal_evidence.yaml`
- `docs/publication/history_rewrite_force_push_plan.md`

## Removed In Rehearsal

- `.dream-studio/**`
- `backups/**`
- `test_output/**`

## Validation

- Removed paths no longer exist anywhere in rewritten history.
- Secret-pattern scan still reports zero findings.
- Clean-home validation passed.
- Full release gate passed in rewritten worktree.

## Next Boundary

Final history rewrite and force-push require explicit operator approval. Do not publish until the final remote rewrite is executed or the operator separately accepts publication risk.
