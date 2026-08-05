"""WO deb9ccb3 — the CLI/API tree must not open a read-write DuckDB connection.

The projection runner (core/projections/runner.py) is the SOLE read-write holder of the
derived DuckDB analytics store (aggregate_metrics.db is NEVER-AUTHORITY). The dashboard
serve/open path previously opened its own connect_analytics(read_only=False) to derive
events_fact — that derivation is already owned by the runner via sync_tick(). This locks
the boundary so a future edit cannot silently reintroduce a CLI-side write connection.
"""

from __future__ import annotations

from core.gates.authority_boundary_check import (
    REPO_ROOT,
    _uses_write_analytics_conn,
    check,
)


def test_dashboard_and_cli_open_no_write_analytics_conn():
    # The whole scanned tree (projections/api + interfaces/cli) is clean.
    assert (
        check() == 0
    ), "authority-boundary gate reports a read-write analytics conn outside runner.py"

    # And the dashboard command specifically opens no read-write analytics connection.
    dashboard = REPO_ROOT / "interfaces" / "cli" / "commands" / "system_dashboard.py"
    assert dashboard.is_file(), f"dashboard command file missing: {dashboard}"
    assert (
        _uses_write_analytics_conn(dashboard) == []
    ), "system_dashboard.py opens connect_analytics(read_only=False) — must route through the runner"
