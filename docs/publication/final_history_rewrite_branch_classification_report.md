# Final History Rewrite Branch Classification

Generated: 2026-05-14T23:09:35.290965+00:00

Remote heads classified: 34
Remote tags classified: 0
Unknown/manual-review heads: 0

## Retain And Rewrite

- `integration/shared-intelligence-remaining-milestones` - current integration branch; Current branch. Local HEAD 8eaef80b5f6b6da42e93f52950c6bb2fe80dabd0 supersedes remote head f27e71c6413d55742f742dbc4a60de8a5e00f980.
- `main` - protected/default branch; Default branch reported by GitHub.

## Delete/Retire Remote Heads After Retained Refs Are Rewritten

- `chore/refresh-stale-commit-status` - stale delete/retire; #31 merged; Merged PR branch; no longer required as a remote head.
- `feat/analytics-realtime` - stale delete/retire; #90 merged; Merged PR branch; no longer required as a remote head.
- `feat/ds-analytics-p2-project` - stale delete/retire; #58 closed; No open PR remains; retained source of truth is main/current integration history.
- `feat/efficiency-analytics` - stale delete/retire; #72 merged; Merged PR branch; no longer required as a remote head.
- `feat/fullstack-skill` - stale delete/retire; #105 merged; Merged PR branch; no longer required as a remote head.
- `feat/gap-fixes-remaining` - stale delete/retire; #41 merged; Merged PR branch; no longer required as a remote head.
- `feat/github-release-check` - stale delete/retire; #30 merged; Merged PR branch; no longer required as a remote head.
- `feat/granular-skill-tracking` - stale delete/retire; #84 merged; Merged PR branch; no longer required as a remote head.
- `feat/pattern-enhancement` - stale delete/retire; no PR; Branch tip is already an ancestor of origin/main.
- `feat/project-intelligence-wave-2` - stale delete/retire; #107 merged; Merged PR branch; no longer required as a remote head.
- `feat/project-intelligence-wave-3` - stale delete/retire; #108 merged; Merged PR branch; no longer required as a remote head.
- `feat/schema-audit-phase-2` - stale delete/retire; #123 merged; Merged PR branch; no longer required as a remote head.
- `feat/schema-audit-phase-3` - stale delete/retire; #124 merged; Merged PR branch; no longer required as a remote head.
- `feat/skill-calibration` - stale delete/retire; #40 merged; Merged PR branch; no longer required as a remote head.
- `feat/sqlite-full-migration-pr4` - stale delete/retire; #71 merged; Merged PR branch; no longer required as a remote head.
- `feat/unified-discovery-phase-6` - stale delete/retire; #119 merged; Merged PR branch; no longer required as a remote head.
- `feat/unified-discovery-phase-7` - stale delete/retire; #120 merged; Merged PR branch; no longer required as a remote head.
- `feat/unified-discovery-phase-8` - stale delete/retire; #121 merged; Merged PR branch; no longer required as a remote head.
- `feat/unified-discovery-phases-1-5` - stale delete/retire; #118 merged; Merged PR branch; no longer required as a remote head.
- `feat/workflow-registry` - stale delete/retire; #39 merged; Merged PR branch; no longer required as a remote head.
- `fix/analytics-dashboard-charts` - stale delete/retire; #97 merged; Merged PR branch; no longer required as a remote head.
- `fix/analytics-db-path-and-format` - stale delete/retire; #95 closed; No open PR remains; retained source of truth is main/current integration history.
- `fix/analytics-empty-charts` - stale delete/retire; #98 merged; Merged PR branch; no longer required as a remote head.
- `integration/main-ci-analytics-dashboard-path` - stale delete/retire; #134 merged; Merged PR branch; no longer required as a remote head.
- `integration/main-ci-dashboard-check-timeout` - stale delete/retire; #135 merged; Merged PR branch; no longer required as a remote head.
- `integration/main-ci-graph-cache-isolation` - stale delete/retire; #133 merged; Merged PR branch; no longer required as a remote head.
- `integration/phase3-plus-phase1-phase2` - stale delete/retire; #132 merged; Merged PR branch; no longer required as a remote head.
- `integration/shared-intelligence-sqlite-foundation` - stale delete/retire; #137 merged, #136 merged; Merged PR branch; no longer required as a remote head.
- `refactor/phase1-runtime-consolidation` - stale delete/retire; #129 closed; Closed unmerged refactor branch superseded by merged integration/phase3-plus-phase1-phase2 line.
- `refactor/phase2a-event-authority` - stale delete/retire; #130 closed; Closed unmerged refactor branch superseded by merged integration/phase3-plus-phase1-phase2 line.
- `refactor/phase3-semantic-memory` - stale delete/retire; #131 closed; Closed unmerged refactor branch superseded by merged integration/phase3-plus-phase1-phase2 line.
- `refactor/track-a-data-plane` - stale delete/retire; #126 merged; Merged PR branch; no longer required as a remote head.

## Decision

No unknown/manual-review branches remain. The final rewrite may proceed against the retained refs only, followed by deletion of the retired remote heads.
