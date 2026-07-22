"""Tests for WO-A Dashboard Wiring Fix Pack.

Six fixes validated:
  Fix 1 - Skills:    skill_usage_sql reads canonical_events, not legacy skill_invocations
  Fix 2 - Security:  updateSecuritySummary reads findings_by_severity + findings_by_source
  Fix 3 - Memory:    loadMemorySurface included in navigate() for attribution tab too
  Fix 4 - Adaptation: /friction-signals/classifications defined before /{signal_id}
  Fix 5 - Invisible: tool_invocations, validation_failures, raw_claude_code_events surfaced
  Fix 6 - Token:     loadAttributionCoverage shows honest 0% with explanatory text
"""

from __future__ import annotations

from tests.dashboard_source import dashboard_source

import inspect
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections/frontend/dashboard.html"


# ── Fix 1: Skills reads canonical_events ─────────────────────────────────


class TestFix1SkillsCanonicalEvents:
    def test_skill_usage_sql_uses_canonical_events(self):
        """skill_usage_sql primary source is canonical_events, not skill_invocations."""
        from projections.core.collectors.authority_sources import skill_usage_sql

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE canonical_events "
            "(event_id TEXT, event_type TEXT, created_at TEXT, trace TEXT NOT NULL DEFAULT '{}')"
        )
        conn.execute(
            "INSERT INTO canonical_events (event_id, event_type, trace) "
            "VALUES ('e1', 'skill.invoked', '{\"skill_specifier\": \"core:plan\"}')"
        )
        conn.execute(
            "INSERT INTO canonical_events (event_id, event_type, trace) "
            "VALUES ('e2', 'skill.invoked', '{\"skill_specifier\": \"core:build\"}')"
        )
        conn.commit()

        sql = skill_usage_sql(conn)
        assert sql is not None
        assert (
            "canonical_events" in sql
        ), "skill_usage_sql must query canonical_events for real skill names"
        assert (
            "skill_invocations" not in sql
        ), "canonical_events fallback must not use legacy skill_invocations table"

        rows = conn.execute(
            f"SELECT skill_name, COUNT(*) cnt FROM ({sql}) GROUP BY skill_name ORDER BY cnt DESC"
        ).fetchall()
        names = [r["skill_name"] for r in rows]
        assert "core:plan" in names
        assert "core:build" in names
        assert (
            "unknown" not in names
        ), "skill_usage_sql must not return 'unknown' from canonical_events"
        conn.close()


# ── Fix 2: Security KPI reads correct fields ──────────────────────────────


class TestFix2SecurityKPI:
    def _get_dashboard_js_section(self, start_marker: str, end_marker: str) -> str:
        text = dashboard_source()
        start = text.find(start_marker)
        end = text.find(end_marker, start + len(start_marker))
        return text[start:end] if start >= 0 and end >= 0 else ""

    def test_update_security_summary_reads_findings_by_source(self):
        """updateSecuritySummary must read from findings_by_source, not total_sarif etc."""
        text = dashboard_source()
        fn_start = text.find("function updateSecuritySummary")
        fn_end = text.find("\n        function ", fn_start + 1)
        fn_body = text[fn_start:fn_end]

        assert "findings_by_source" in fn_body, (
            "Security KPI must read from findings_by_source (API field). "
            "Using total_sarif/total_cve produces 0 because those fields don't exist."
        )
        assert (
            "total_sarif" not in fn_body
        ), "Security KPI must not read total_sarif — this field doesn't exist in the API response"

    def test_update_security_summary_reads_findings_by_severity(self):
        """updateSecuritySummary must read from findings_by_severity."""
        text = dashboard_source()
        fn_start = text.find("function updateSecuritySummary")
        fn_end = text.find("\n        function ", fn_start + 1)
        fn_body = text[fn_start:fn_end]

        assert "findings_by_severity" in fn_body, (
            "Security KPI severity breakdown must read findings_by_severity. "
            "Using by_severity (which doesn't exist) produces 0 critical/high counts."
        )


# ── Fix 4: Route ordering — classifications before {signal_id} ───────────


class TestFix4RouteOrdering:
    def test_classifications_route_before_signal_id_route(self):
        """FastAPI route /friction-signals/classifications must be defined before /{signal_id}.

        Otherwise FastAPI matches GET /friction-signals/classifications as if
        signal_id='classifications', returning 404.
        """
        # WO-GF-API-ROUTES split: /friction-signals/classifications and
        # /friction-signals/{signal_id} now live in intelligence_friction.py.
        source = (REPO_ROOT / "projections/api/routes/intelligence_friction.py").read_text(
            encoding="utf-8"
        )
        lines = source.splitlines()

        classifications_line = next(
            (i for i, ln in enumerate(lines) if '"/friction-signals/classifications"' in ln), -1
        )
        signal_id_line = next(
            (i for i, ln in enumerate(lines) if '"/friction-signals/{signal_id}"' in ln), -1
        )

        assert classifications_line >= 0, "/friction-signals/classifications route not found"
        assert signal_id_line >= 0, "/friction-signals/{signal_id} route not found"
        assert classifications_line < signal_id_line, (
            f"Route ordering bug: /friction-signals/classifications (line {classifications_line+1}) "
            f"must come BEFORE /friction-signals/{{signal_id}} (line {signal_id_line+1}). "
            f"FastAPI matches in order — parameterized routes swallow specific ones if defined first."
        )


# ── Fix 5: Invisible tables surfaced ─────────────────────────────────────


class TestFix5InvisibleTables:
    def test_tool_activity_endpoint_exists(self):
        """GET /hooks/tool-activity endpoint must exist."""
        source = (REPO_ROOT / "projections/api/routes/hooks.py").read_text(encoding="utf-8")
        assert '"/hooks/tool-activity"' in source, "tool_activity endpoint missing from hooks.py"
        assert "execution_events" in source, "tool_activity must query execution_events table"

    def test_validation_failures_endpoint_exists(self):
        """GET /hooks/validation-failures endpoint must exist."""
        source = (REPO_ROOT / "projections/api/routes/hooks.py").read_text(encoding="utf-8")
        assert '"/hooks/validation-failures"' in source
        assert "validation_failures" in source

    def test_raw_events_endpoint_exists(self):
        """GET /hooks/raw-events endpoint must exist."""
        source = (REPO_ROOT / "projections/api/routes/hooks.py").read_text(encoding="utf-8")
        assert '"/hooks/raw-events"' in source
        assert "raw_claude_code_events" in source

    def test_frontend_has_invisible_tables_panel(self):
        """Frontend must have panel for previously-invisible tables."""
        text = dashboard_source()
        assert "tool-activity-list" in text, "Tool activity panel missing from dashboard"
        assert (
            "validation-failures-list" in text
        ), "Validation failures panel missing from dashboard"
        assert "raw-events-list" in text, "Raw events panel missing from dashboard"
        assert "loadInvisibleTables" in text, "loadInvisibleTables function missing from dashboard"

    def test_invisible_tables_load_on_developer_diagnostics_navigate(self):
        """navigate('developer-diagnostics') must trigger loadInvisibleTables().

        WO-DASH-DEVDIAG-CONSOLIDATE (#387) moved the previously-invisible tables
        out of the Hooks tab into the dedicated Developer Diagnostics tab, so the
        load now fires on that tab instead of hooks.
        """
        text = dashboard_source()
        assert (
            "tabName === 'developer-diagnostics'" in text and "loadInvisibleTables()" in text
        ), "loadInvisibleTables() must be called when navigating to the Developer Diagnostics tab"

    def test_tool_activity_endpoint_functional(self):
        """tool_activity endpoint returns correct structure from real or empty DB."""
        import asyncio

        async def run():
            from projections.api.routes.hooks import list_tool_activity
            from unittest.mock import patch
            import sqlite3

            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE execution_events "
                "(event_id TEXT, tool_id TEXT, outcome_status TEXT, project_id TEXT, "
                "created_at TEXT)"
            )
            for i in range(3):
                conn.execute(
                    "INSERT INTO execution_events VALUES (?,?,?,?,datetime('now'))",
                    (f"id-{i}", "Edit", "completed", "proj-1"),
                )
            conn.commit()

            with patch("projections.api.routes.hooks.get_connection", return_value=conn):
                result = await list_tool_activity(limit=50)
            conn.close()
            return result

        result = asyncio.run(run())
        assert "invocations" in result
        assert result["count"] == 3
        assert "top_tools" in result
        assert result["top_tools"].get("Edit") == 3


# ── Fix 6: Token Attribution honest empty state ───────────────────────────


class TestFix6TokenAttributionHonest:
    def test_attribution_coverage_no_infinite_loading(self):
        """loadAttributionCoverage must clear the 'loading...' state on any response."""
        text = dashboard_source()
        fn_start = text.find("async function loadAttributionCoverage")
        fn_end = text.find("\n    async function ", fn_start + 1)
        fn_body = text[fn_start:fn_end]

        # Must set attr-coverage-pct on success
        assert "attr-coverage-pct" in fn_body, "loadAttributionCoverage must update pct element"
        # Must set status on success (not leave as 'loading...')
        assert (
            "attr-coverage-status" in fn_body
        ), "loadAttributionCoverage must update status element"
        # Must handle 0% case with explanatory text
        assert "write-path" in fn_body.lower() or "under investigation" in fn_body.lower(), (
            "Token Attribution must show investigative note when fully=0 and total_events>0. "
            "Leaving 'loading...' is not an honest failure mode."
        )

    def test_attribution_coverage_error_path_clears_state(self):
        """On error, loadAttributionCoverage must not leave 'loading...' state."""
        text = dashboard_source()
        fn_start = text.find("async function loadAttributionCoverage")
        fn_end = text.find("\n    async function ", fn_start + 1)
        fn_body = text[fn_start:fn_end]

        # Error path must update coverage-pct (set to '--' or '0%')
        catch_block_start = fn_body.rfind("catch")
        catch_block = fn_body[catch_block_start:]
        assert (
            "attr-coverage-pct" in catch_block
        ), "Error path must update attr-coverage-pct to avoid leaving '--' with 'loading...' status"


# ── Cross-page: no regression ─────────────────────────────────────────────


class TestNoRegression:
    def test_existing_dashboard_sections_still_present(self):
        """Core dashboard sections must not be removed by the fix pack."""
        text = dashboard_source()
        required_ids = [
            "hooks",
            "security",
            "memory-surface",
            "adaptation",
            "attribution-coverage",
            "learning",
        ]
        for id_ in required_ids:
            assert f'id="{id_}"' in text, f"Dashboard section id={id_!r} was removed — regression"

    def test_security_chart_reads_findings_by_severity(self):
        """Security severity chart must use findings_by_severity field."""
        text = dashboard_source()
        fn_start = text.find("function initSecuritySeverityChart")
        fn_end = text.find("\n        function ", fn_start + 1)
        fn_body = text[fn_start:fn_end]
        assert (
            "findings_by_severity" in fn_body
        ), "Severity chart must use findings_by_severity — same fix as KPI"
