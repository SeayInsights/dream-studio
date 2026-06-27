"""Built-in projection consumers — RETIRED in WO-READMODELS-DUCKDB.

The five SQLite projection tables these consumers maintained
(proj_workflow_runs, proj_skill_stats, proj_sessions,
proj_decision_patterns, proj_security_summary) had no live readers and
were dropped in migration 129.  The equivalent data is now derived
on-demand from events_fact in DuckDB (aggregate_metrics.db).

The consumer classes and get_default_engine() are removed.  The module
is retained as a stub so any static-import of the module path does not
break until import-site cleanup is done.
"""
