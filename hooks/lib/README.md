# hooks/lib/

Shared library modules imported by handlers and tests. No handler logic lives here — only reusable utilities. Owned by the **meta** pack (`packs/meta/`) — stays at this path because all packs depend on it via PYTHONPATH.

## What this directory provides

| Module | Purpose |
|---|---|
| `paths.py` | Cross-platform path resolution (plugin root, user data dir, project root) |
| `state.py` | Reading and writing persistent hook state (JSON files in `~/.dream-studio/`) |
| `workflow_state.py` | Workflow lifecycle — loading, persisting, and querying workflow run state |
| `workflow_engine.py` | Pure evaluation engine — node execution, gate checks, DAG traversal (no I/O) |
| `workflow_validate.py` | YAML workflow schema validation |
| ~~`game_validate.py`~~ | Moved to `packs/domains/domain_lib/` — domain-specific, not shared infra |
| `context_handoff.py` | Session handoff writers — handoff.md, recap.md, draft lessons |
| `traceability.py` | File size cap guard and UTF-8 encoding check |
| `python_shim.py` | Cross-platform Python interpreter discovery |

## Entry point

`paths.py` is the foundational module — everything else depends on it. Start there when tracing path resolution issues.

## Public interfaces

Each module exports named functions. Callers should import only the documented public symbols (those without a leading underscore).

## What should never be imported directly

`_impl` helpers and underscore-prefixed functions (e.g., `_parse_godot_version`, `_is_suppressed`) are internal. Import the top-level validated functions instead.

## Key invariants

- Modules in `lib/` must never import from `hooks/handlers/`
- `workflow_engine.py` must remain pure (no filesystem I/O, no subprocess calls)
- `paths.py` must have no dependencies on other lib modules (it is the base layer)
- All modules must be importable without a running Claude Code session
