# Claude Code Hooks — Manual Installation

This document covers the manual hook installation for TA3 token attribution.
Auto-installation via `ds doctor` is a future workstream.

## Prerequisites

- Dream Studio installed and runtime bootstrapped (`ds doctor` shows green)
- Claude Code CLI installed

---

## Token Attribution Hook (TA3)

The `PostToolUse` hook emits a `token.consumed` canonical event for every Claude Code tool
invocation. This produces the first real attribution data — every tool call in an
instrumented session generates an event linked to the active SDLC task (or CWD project
if no task is set).

### 1. Register your project with a marker

Every project directory needs a `.dream-studio-project` marker file. Run this from
the project directory (or pass `--path` explicitly):

```powershell
cd C:\Users\<you>\builds\<your-project>
py -m interfaces.cli.ds project register --name "My Project" --path .
```

This writes a `.dream-studio-project` JSON marker to the directory and registers
the project in the Dream Studio SQLite authority.

### 2. Install the PostToolUse hook

Add the following to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "py C:\\Users\\<you>\\builds\\dream-studio-clean\\runtime\\hooks\\core\\on-post-tool-use.py"
          }
        ]
      }
    ]
  }
}
```

Replace `<you>` with your Windows username and adjust the path if your repo is in
a different location. On macOS/Linux, replace `py` with `python3` and use forward
slashes.

> **Note:** If you already have PostToolUse hooks configured, add the Dream Studio
> entry to the existing `hooks` array rather than replacing the whole block.

### 3. Verify the hook fires

Start a Claude Code session in your project directory, run any tool (e.g., ask
Claude to read a file), then check the diagnostic stream:

```powershell
py -m interfaces.cli.ds diagnostics list --source token-capture --limit 5
```

If attribution is working, you should see entries (or no entries if everything
is clean — anomalies only appear when something goes wrong).

To check that events are landing in canonical_events:

```powershell
py -m interfaces.cli.ds spool ingest
py -m interfaces.cli.ds dashboard
```

---

## Attribution Status

Every `token.consumed` event carries an `attribution_status` in its trace:

| Status | Meaning |
|--------|---------|
| `fully_attributed` | Active task was set via `ds task set-active <task_id>` — full SDLC chain in trace |
| `partial` | No active task, but CWD resolved to a project via `.dream-studio-project` marker |
| `orphan` | Neither active task nor CWD marker found — event is recorded but not attributed |

To get full attribution, set the active task before starting work:

```powershell
py -m interfaces.cli.ds task set-active <task_id>
```

---

## Diagnostics

The hook writes structured logs to `~/.dream-studio/state/diagnostics/`:

| File | Contents |
|------|---------|
| `token-capture.jsonl` | Anomalies, failures, and performance alerts from the token capture module |
| `cwd-resolver.jsonl` | Marker file parse errors and reconciliation anomalies |
| `hook-failures.jsonl` | Last-resort shim-level failures (module import failures, etc.) |

View recent diagnostics:

```powershell
py -m interfaces.cli.ds diagnostics list --limit 20
py -m interfaces.cli.ds diagnostics list --source token-capture --category anomaly
py -m interfaces.cli.ds diagnostics clear                   # truncate all logs
py -m interfaces.cli.ds diagnostics clear --source hook-failures
```

---

## Deferred work

- **Auto-install:** `ds doctor` and `ds integrate install` will auto-install this hook in a future workstream
- **Execution context:** Linking tool calls to parent skill/workflow/agent invocations (TA3b)
- **Session-level capture:** Aggregating token totals per session (future workstream)
- **Marker/DB reconciliation:** The auditor workstream will surface drift between marker files and `ds_projects`
