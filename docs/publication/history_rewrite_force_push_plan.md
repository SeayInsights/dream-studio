# Git History Privacy Rewrite Force-Push Plan

Generated: 2026-05-14T22:46:00.642479+00:00

## Status

Rehearsal passed in a temp mirror clone. No real remote rewrite, force-push, tag, deploy, live DB mutation, or local installed-state mutation was performed.

Current branch mapping from rehearsal:

- Branch: `integration/shared-intelligence-remaining-milestones`
- Current local HEAD before rewrite: `fa51e3bd046a9f6d3f568fcd26dc125e864aa8b6`
- Rewritten rehearsal HEAD: `8ad0e0fe2ed1941f3263c8fe16fb8576f21bc9a3`

## Removed Classes

The rehearsal removed these classes from history:

- `.dream-studio/**`
- `backups/**`
- `test_output/**`

This covers the known private runtime/team files, historical DB backup artifacts, backup checksums, and generated test/report outputs.

## Validation Summary

- Private artifact history scan after rewrite: pass, 0 hits.
- Secret-pattern scan after rewrite: pass, 0 findings.
- Required source/docs/tests present: pass.
- Clean-home validation: pass, 26 tests passed, no clean-home `.dream-studio` created.
- Contract docs drift gate: pass.
- Full release gate in rewritten worktree: pass, 2285 passed, 9 skipped, 1 xfailed; format, lint baseline, and security passed.

## Remote Impact

Read-only remote inspection found 34 heads and 0 tags. Because private objects can remain reachable from any retained ref, a strict cleanup must update every retained branch/tag ref that contains the old objects, or intentionally delete/retire old refs under explicit operator approval.

## Final Execution Plan Requires Approval

After explicit operator approval only:

1. Freeze Dream Studio pushes and PR updates.
2. Create a timestamped mirror backup of the current remote:
   `git clone --mirror https://github.com/SeayInsights/dream-studio.git <backup-mirror>`
3. Create a fresh rewrite mirror:
   `git clone --mirror https://github.com/SeayInsights/dream-studio.git <rewrite-mirror>`
4. Run the same filter:
   `git -C <rewrite-mirror> filter-repo --force --path .dream-studio --path backups --path test_output --invert-paths`
5. Validate in the rewrite mirror/worktree:
   - private artifact history scan returns 0 hits;
   - secret scan returns 0 findings;
   - clean clone/bootstrap validation passes;
   - release gate passes or reports only explicitly accepted non-blocking CI limitations;
   - current branch maps to the expected rewritten head class.
6. Push rewritten refs with force-with-lease, not plain force:
   `git -C <rewrite-mirror> push --force-with-lease origin refs/heads/<branch>:refs/heads/<branch>` for each retained branch.
7. Push rewritten tags only if tags exist and are approved:
   `git -C <rewrite-mirror> push --force-with-lease origin refs/tags/<tag>:refs/tags/<tag>`
8. Delete/retire unneeded stale remote branches only if separately approved.
9. Re-clone from GitHub and rerun publication-cleanliness validation.
10. Tell collaborators to archive or delete old clones and re-clone, or run `git fetch --all --prune` followed by resetting local branches to the rewritten remote refs. Any old local clone can retain removed objects until garbage-collected.

## Risks

- All commit hashes on rewritten refs change.
- Open PRs and branch comparisons may need to be recreated or refreshed.
- Collaborators with old clones can accidentally reintroduce old objects if they push without recloning/resetting.
- GitHub forks/caches may retain old objects outside this repo's control.
- Branch deletion is a separate approval boundary.

## Recommendation

Approve final history rewrite execution only after deciding which remote branches to retain, rewrite, or delete. The rehearsal supports proceeding, but final remote mutation still requires explicit operator approval.
