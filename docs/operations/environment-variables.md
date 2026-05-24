# Dream Studio — Environment Variables

All env vars are **optional**. Dream Studio runs fully on their defaults;
none are required for basic operation. Variables that make external network
calls are marked **NETWORK** — they are always opt-in.

---

## Core path overrides

| Variable | Default | Purpose |
|---|---|---|
| `CLAUDE_PLUGIN_ROOT` | Resolved from `__file__` ancestors or `.plugin-root` sidecar | Path to the dream-studio repo root. Set when installed to a non-standard location. |
| `DREAM_STUDIO_HOME` | `~/.dream-studio` | Override the dream-studio runtime home directory (state, DB, handoffs). |
| `DS_DREAM_STUDIO_HOME` | Same as above | Alternate name accepted by `integrations/manifest.py`. |
| `DREAM_STUDIO_DB_PATH` | `$DREAM_STUDIO_HOME/state/studio.db` | Override the SQLite authority database path. Useful for CI isolation. |
| `DS_SPOOL_ROOT` | `$DREAM_STUDIO_HOME/spool` | Override the spool root directory. Used in tests to isolate writes. |
| `WORK_ORDER_ROOT` | `$DREAM_STUDIO_HOME/work-orders` | Override work order storage root. |
| `DREAM_STUDIO_CORRECTIONS_PATH` | `$DREAM_STUDIO_HOME/corrections.jsonl` | Override corrections log path. |
| `DS_DIAGNOSTICS_DIR` | `$DREAM_STUDIO_HOME/diagnostics` | Override diagnostics output directory. |
| `DS_CWD_RESOLVER_ROOT` | Working directory of the process | Anchor path for CWD resolver. Set in tests to constrain resolution. |
| `DS_PLATFORM_PROFILE_PATH` | `$DREAM_STUDIO_HOME/platform-profile.json` | Override platform detection cache. |
| `DS_ACTIVE_TASK_PATH` | `$DREAM_STUDIO_HOME/state/active-task.json` | Override active task state file. |
| `DS_MACHINE_ID_PATH` | `$DREAM_STUDIO_HOME/state/machine-id` | Override machine ID cache file. |

---

## Projection runner tuning

| Variable | Default | Purpose |
|---|---|---|
| `PROJECTION_POLL_INTERVAL` | `5` (seconds) | How often the projection daemon polls for new events. |
| `PROJECTION_EVENT_TRIGGER` | `10` (events) | Trigger an early projection run after this many new events. |

---

## Claude Code adapter (injected by Claude Code — not user-set)

These are injected into the hook process environment by the Claude Code
runtime. Do not set them manually in normal operation.

| Variable | Purpose |
|---|---|
| `CLAUDE_PLUGIN_ROOT` | Plugin root path (also used as an explicit override — see above). |
| `CLAUDE_FILE_PATH` | Absolute path of the file being edited (PostToolUse hooks). |
| `CLAUDE_SESSION_ID` | Active session ID. |
| `CLAUDE_USER_MESSAGE_TEXT` | Text of the user message that triggered the hook. |
| `CLAUDE_MODEL` | Model identifier for the active session. |
| `CLAUDE_CODE` | Set to `"1"` when running inside Claude Code. |

---

## Telemetry and debug

| Variable | Default | Purpose |
|---|---|---|
| `DREAM_STUDIO_MODEL` | `"unspecified"` | Model label written to telemetry records. Useful for multi-model setups. |
| `DREAM_STUDIO_DEBUG` | unset | Set to `1` or `true` to enable verbose debug logging. |
| `DREAM_STUDIO_TELEMETRY_DB` | Same as `DREAM_STUDIO_DB_PATH` | Override the telemetry write target (separate from authority DB). |

---

## External integrations (NETWORK — opt-in)

These variables enable optional integrations that make outbound network calls.
Dream Studio operates fully without them; set only if you need the feature.

### `ANTHROPIC_API_KEY`
- **Purpose:** Enables direct Anthropic API calls from the `ci_gate.py` check
  and any LLM-backed CLI commands.
- **Default when unset:** CI gate skips API validation; LLM features are
  disabled.
- **Network:** Calls `api.anthropic.com`. No data is sent except what you
  explicitly pass to the API command.
- **Privacy:** Do not commit this value. Use a `.env` file or OS keychain.

### `GITHUB_PERSONAL_ACCESS_TOKEN`
- **Purpose:** Used by `pulse_collector.py` to fetch GitHub activity (commits,
  PRs) for the proactive health pulse check.
- **Default when unset:** Pulse check skips GitHub data; only local data is
  collected.
- **Network:** Calls `api.github.com`. Accesses repositories visible to the
  token.
- **Privacy:** Scope the token to `repo:read` minimum.

### `JINA_API_KEY`
- **Purpose:** Enables Jina AI semantic search in `control/research/web.py`
  for the web research feature. When unset, the function returns an empty list
  and the metric `web_research.jina_skip` is emitted.
- **Default when unset:** Semantic search disabled; research falls back to
  local sources only.
- **Network:** Calls `api.jina.ai/v1/search`. Sends the search query string.
- **Privacy:** Query text is sent to Jina AI. Do not use for sensitive queries
  if privacy is a concern.

### `PULSE_COOLDOWN_SEC`
- **Purpose:** Minimum seconds between pulse check runs (default 60).
  Prevents hammering external APIs if hooks fire rapidly.
- **Network:** No direct network call — controls rate-limiting for the pulse
  check, which may itself call GitHub (see `GITHUB_PERSONAL_ACCESS_TOKEN`).

---

## Analytics API (projections/) — NETWORK, operator-configured

These are used by the analytics reporting subsystem in `projections/`.
They are never accessed by the Dream Studio core hooks or CLI.

| Variable | Purpose |
|---|---|
| `EMAIL_USERNAME` / `EMAIL_PASSWORD` | SMTP credentials for analytics report delivery. If unset, email delivery is skipped. |
| `ANALYTICS_SMTP_USER` / `ANALYTICS_SMTP_PASS` | Alternative SMTP credential names read by `projections/config/settings.py`. |

**Network:** Connects to the configured SMTP server to send reports to
recipients you specify. No data leaves the machine except the report content
you explicitly send.

---

## Removed variables

| Variable | Removed in | Reason |
|---|---|---|
| `SENTRY_DSN` | Phase 18.1.12 | Dream Studio does not phone home. Crashes surface to the local dashboard (18.8.10.1), never to external services. |
