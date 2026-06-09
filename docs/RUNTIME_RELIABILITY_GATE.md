# Runtime Reliability Gate

Phase 5.7A — a repeatable gate that verifies core runtime contracts stabilized in Phase 5.

## How to run

```bash
# Via Makefile
make runtime-check

# Via pytest marker
py -3.12 -m pytest -m runtime_reliability -q

# Via explicit file list
py -3.12 -m pytest \
  tests/unit/test_studio_db.py \
  tests/unit/test_database_governance.py \
  tests/unit/test_event_emission_reliability.py \
  tests/unit/test_event_type_advisory.py \
  tests/unit/test_dashboard_safety.py \
  tests/unit/test_entry_point_reliability.py \
  tests/unit/test_hook_runtime_reliability.py \
  tests/unit/test_workflow_runtime_reliability.py \
  -q
```

## What it covers

### DB / Migration Authority
- Explicit `db_path` creates isolated DB
- `db_path=None` uses canonical path
- Projection routes do not use direct `sqlite3.connect`
- `core/security` does not use direct `sqlite3.connect`
- Migration authority doc exists
- Migration numbering is sequential
- Schema version managed exclusively by `studio_db`

### Event Emission
- `emit_event()` with default args succeeds
- `emit_event()` validates severity correctly (info, low, medium, high, critical)
- `emit_security_event()` routes through canonical event path
- Advisory `EventType` validation remains non-blocking
- Taxonomy-derived type registry loads correctly

### Dashboard Safety
- Default host is `127.0.0.1`
- CORS does not use wildcard
- Activity log filtering excludes private types
- Decision log exposure is aggregate-only
- Dashboard `--check` is read-only

### Entry Points
- Setup help/check commands work
- Dashboard help/check commands work
- Compatibility shims delegate correctly
- Install wrappers validate Python version and repo root
- Makefile check targets exist

### Hooks
- `hooks.json` references valid handlers
- `run.sh` / `run.cmd` path roots are aligned
- PYTHONPATH includes plugin root
- All registered handlers resolve to existing files
- Dispatcher sub-handlers resolve correctly

### Workflows
- Workflow YAML files parse
- Representative workflows validate
- State lock/read/write behavior uses documented locking
- Retry/timeout gaps are documented (not silently assumed)
- Dashboard-dependent workflow risks are identified
- Gate/pause/resume behavior works

## Test files

| File | Area | Tests |
|------|------|-------|
| `test_studio_db.py` | DB isolation, schema, graceful degradation | 8 |
| `test_database_governance.py` | Migration authority, SSOT, canonical imports | 29 |
| `test_event_emission_reliability.py` | Severity validation, canonical routing | 23 |
| `test_event_type_advisory.py` | Advisory validation, taxonomy, non-blocking | 32 |
| `test_dashboard_safety.py` | Host binding, CORS, data filtering | 25 |
| `test_entry_point_reliability.py` | Setup/dashboard CLI, install wrappers | 26 |
| `test_hook_runtime_reliability.py` | hooks.json, handler resolution, dispatch | 50+ |
| `test_workflow_runtime_reliability.py` | YAML parsing, state locking, gates | 41 |

**Total: 273 tests**

## Documented gaps (Phase 6+ scope)

- Retry enforcement: workflows declare `retry.max` but the engine does not re-queue failed steps
- Timeout enforcement: workflows declare `timeout_seconds` but neither engine nor state enforces deadlines
- Model portability: workflow model names are Claude-specific (Phase 7 scope)
