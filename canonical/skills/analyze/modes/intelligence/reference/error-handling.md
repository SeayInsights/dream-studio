# Error Handling - Project Intelligence

Common error scenarios and recovery steps.

## Path Errors

**Path not found:**
```
[ERROR] Path does not exist: {path}
Please provide a valid project directory.
```

**Not a directory:**
```
[ERROR] Path is not a directory: {path}
Please provide a directory path, not a file.
```

## Engine Errors

**Analysis engine not available:**
```
[ERROR] Project intelligence engine not installed
The intelligence mode requires Waves 0-4 of project-intelligence to be complete.
Missing module: control.analysis.engine

To install, run the project-intelligence build workflow.
```

**Analysis failed:**
```
[ERROR] Analysis failed: {error_message}

The error is re-raised to the caller.
```

What a failed run leaves behind is its events, nothing else: `analysis.started`, one
`analysis.*_completed` event for each phase that finished, and `analysis.failed` carrying
`run_id`, `project_id` and `error_message`. The engine writes them to the event spool
(`~/.dream-studio/events/spool/`); they reach the database when `ds spool ingest` runs.
Bugs are emitted as security findings (they reach `security_events` after `ds spool ingest`);
violations and improvements are not stored, and the PRD is written during synthesis, so a run
that failed in an earlier phase has none.

## Run type

`run_type` ("full", "targeted" or "incremental") is recorded in the `analysis.started` event.
The engine does not validate it, so a misspelt value is not an error; it is only recorded.

## Recovery Steps

1. Check path exists: `test -d <path>`
2. Verify engine installed: `py -c "from control.analysis.engine import analyze_project"`
3. Ingest the spool so the events reach the database: `ds spool ingest`
4. Find the failure: `sqlite3 ~/.dream-studio/state/studio.db "SELECT event_timestamp, payload FROM ai_canonical_events WHERE event_type = 'analysis.failed' ORDER BY event_timestamp DESC LIMIT 5"` (the payload is JSON with `run_id`, `project_id` and `error_message`; no error log file is written)
