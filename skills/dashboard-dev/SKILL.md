---
name: dashboard-dev
description: Tauri + React desktop dashboard patterns — feed contract (hooks write JSON, dashboard reads), multi-panel architecture, additive schema evolution. Trigger on `dashboard:`, `feed contract:`, or related dashboard-dev commands.
---

# Dashboard Dev — Patterns for Hook-Driven Desktop Dashboards

## Trigger
`dashboard:`, `feed contract:`, `build dashboard:`, `dashboard feature:`

## Architecture
- **Tauri** — Rust backend for system-level operations, React frontend for UI
- **Feed contract** — plugin hooks write structured JSON; the dashboard reads and renders. No coupling between the two.
- **Multi-panel** — dashboard, activity feed, session status, build history, health pulse

## Feed contract
Location: `%APPDATA%/Claude/<plugin-name>-feed.json` (Windows) · `~/.config/Claude/<plugin-name>-feed.json` (Linux) · `~/Library/Application Support/Claude/<plugin-name>-feed.json` (macOS)

```json
{
  "session": {
    "id": "string",
    "started": "ISO 8601",
    "context_pct": 0-100,
    "tokens_used": 0,
    "quality_score": 0-100
  },
  "activity": [
    {
      "ts": "ISO 8601",
      "type": "agent|hook|skill|build|alert",
      "summary": "string",
      "detail": "string (optional)"
    }
  ],
  "pulse": {
    "last_run": "ISO 8601",
    "stale_branches": 0,
    "open_prs": 0,
    "overdue_milestones": 0,
    "ci_status": "passing|failing|unknown"
  },
  "handoffs": [
    {
      "path": "string",
      "topic": "string",
      "created": "ISO 8601"
    }
  ]
}
```

## Data sources
| Data | Source hook | Feed field |
|---|---|---|
| Agent activity | on-tool-activity | activity[] |
| Context health | on-context-threshold | session.context_pct |
| Token usage | on-token-log | session.tokens_used |
| Quality score | on-quality-score | session.quality_score |
| Pulse report | on-pulse | pulse{} |
| Build recaps | recap skill | Read from `.sessions/` |
| Handoff state | handoff skill | handoffs[] |

## Contract rules
- **Additive only** — new fields OK; removing or renaming fields requires a migration
- **Graceful degradation** — the dashboard must handle stale, missing, or malformed feed data
- **Rust handles I/O** — file reads, system commands, process monitoring
- **React handles display** — rendering, layout, interactivity

## Tauri conventions
- Commands in `src-tauri/src/commands/` — one file per domain
- Frontend calls Tauri commands via `@tauri-apps/api/core` invoke
- Window management: single main window with panel routing, not multiple windows
- System tray: minimal — show/hide toggle + quit
- Auto-update: Tauri updater plugin for release builds
