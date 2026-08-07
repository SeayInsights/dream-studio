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
Missing module: analyze.engine

To install, run the project-intelligence build workflow.
```

**Analysis failed:**
```
[ERROR] Analysis failed: {error_message}

Partial results may be available in the database.
Check logs for details: cat ~/.dream-studio/logs/analysis-errors.log
```

## Database Errors

**Invalid run_type:**
```
CHECK constraint failed: chk_run_type
```
Valid values: 'full', 'targeted', 'incremental'

## Recovery Steps

1. Check path exists: `test -d <path>`
2. Verify engine installed: `py -c "from analyze.engine import analyze_project"`
3. Check database: `sqlite3 ~/.dream-studio/state/studio.db "SELECT * FROM pi_analysis_runs ORDER BY started_at DESC LIMIT 5"`
4. Review logs: `cat ~/.dream-studio/logs/analysis-errors.log`
