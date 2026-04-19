# hooks/handlers/

Event handler scripts invoked by Claude Code hooks at defined lifecycle events.

## What this directory provides

One Python script per hook event. Each script reads a JSON payload from stdin, performs its specific action, and exits. Handlers are thin entry points — business logic lives in `hooks/lib/`.

## Entry point

`hooks/hooks.json` is the registry. It maps each event to the handler file path and any filter conditions. Read that file to see which handler fires for which event.

## Public interfaces

Handlers are not imported — they are executed as subprocesses by the Claude Code runtime. There is no importable API surface.

## What should never be imported directly

Internal helper functions (e.g., `_is_suppressed`, `_parse_godot_version`). These are implementation details that may change. Tests load the handler module via `importlib` to access named functions.

## Key invariants

- Every handler reads its payload from `sys.stdin` and never from argv
- Handlers exit 0 on success, 2 on blocking error (stops the tool), non-zero on unexpected failure
- Handlers must complete in under 2 seconds on typical input — no blocking network calls
- Handlers import shared logic from `hooks/lib/` only — never from other handlers
- Adding a new handler requires a corresponding entry in `hooks/hooks.json`
