"""Phase 5.6A — Dashboard Runtime Safety tests.

Covers:
1. API default host is 127.0.0.1
2. Direct launch does not default to 0.0.0.0
3. CORS rejects non-localhost origins
4. CORS allows required localhost origins
5. Activity log filtering excludes private types
6. Decision log private reasoning not exposed by default
7. ds_dashboard.py --check is read-only
8. scripts/ds_dashboard.py --check delegates correctly
9. launch-dashboard and launch-dashboard.cmd point to same canonical module
10. Dashboard safety changes do not affect Phase 5.3A event tests
11. Pytest collection remains clean
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_CHECK_TIMEOUT_SECONDS = 90


# ── 1. API default host is 127.0.0.1 ────────────────────────────────────────


class TestDefaultHost:

    def test_start_api_default_host(self):
        """start_api() default host parameter is 127.0.0.1."""
        from projections.api.main import start_api

        sig = inspect.signature(start_api)
        assert sig.parameters["host"].default == "127.0.0.1"

    def test_safety_constant(self):
        """SAFE_DEFAULT_HOST is 127.0.0.1."""
        from projections.api.safety import SAFE_DEFAULT_HOST

        assert SAFE_DEFAULT_HOST == "127.0.0.1"


# ── 2. Direct launch does not default to 0.0.0.0 ────────────────────────────


class TestNoWildcardBind:

    def test_main_module_no_wildcard(self):
        """projections/api/main.py __main__ block uses SAFE_DEFAULT_HOST, not 0.0.0.0."""
        source = (REPO_ROOT / "projections" / "api" / "main.py").read_text(encoding="utf-8")
        main_block = source[source.index('if __name__ == "__main__"') :]
        assert "0.0.0.0" not in main_block

    def test_cli_dashboard_default_host(self):
        """interfaces/cli/ds_dashboard.py --host defaults to 127.0.0.1."""
        source = (REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py").read_text(encoding="utf-8")
        match = re.search(r'ap\.add_argument\(\s*"--host",[\s\S]*?default="([^"]+)"', source)
        assert match, "--host argument not found"
        assert match.group(1) == "127.0.0.1"

    def test_launch_server_default_host(self):
        """launch_server() default host is 127.0.0.1."""
        source = (REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py").read_text(encoding="utf-8")
        match = re.search(r'def launch_server\(.*host.*=\s*"([^"]+)"', source)
        assert match, "launch_server host default not found"
        assert match.group(1) == "127.0.0.1"

    def test_launch_server_reload_off_by_default(self):
        """launch_server() gained a `reload` param (WO-DASH-RESTART); hot-reload must
        be OFF by default — auto-reload is a dev convenience, not a default behavior."""
        import inspect

        from interfaces.cli import ds_dashboard

        params = inspect.signature(ds_dashboard.launch_server).parameters
        assert "reload" in params, "launch_server must accept a reload flag"
        assert params["reload"].default is False, "reload must default to False (off)"


# ── 3. CORS rejects non-localhost origins ────────────────────────────────────


class TestCORSRestriction:

    def test_no_wildcard_cors(self):
        """CORS allow_origins must not contain '*'."""
        source = (REPO_ROOT / "projections" / "api" / "main.py").read_text(encoding="utf-8")
        assert 'allow_origins=["*"]' not in source

    def test_cors_uses_localhost_origins(self):
        """CORS origins come from localhost_origins() helper."""
        source = (REPO_ROOT / "projections" / "api" / "main.py").read_text(encoding="utf-8")
        assert "localhost_origins()" in source


# ── 4. CORS allows required localhost origins ────────────────────────────────


class TestCORSAllowsLocalhost:

    def test_localhost_origins_default_port(self):
        from projections.api.safety import localhost_origins

        origins = localhost_origins()
        assert "http://127.0.0.1:8000" in origins
        assert "http://localhost:8000" in origins

    def test_localhost_origins_custom_port(self):
        from projections.api.safety import localhost_origins

        origins = localhost_origins(9000)
        assert "http://127.0.0.1:9000" in origins
        assert "http://localhost:9000" in origins

    def test_no_external_origins(self):
        from projections.api.safety import localhost_origins

        for origin in localhost_origins():
            assert "127.0.0.1" in origin or "localhost" in origin


# ── 5. Activity log filtering excludes private types ────────────────────────


class TestActivityLogFilter:

    def test_filter_clause_excludes_private_types(self):
        from projections.api.safety import activity_log_filter_clause, PRIVATE_ACTIVITY_TYPES

        clause = activity_log_filter_clause("al")
        for t in PRIVATE_ACTIVITY_TYPES:
            assert t in clause

    def test_filter_clause_excludes_private_prefixes(self):
        from projections.api.safety import activity_log_filter_clause, PRIVATE_ACTIVITY_PREFIXES

        clause = activity_log_filter_clause("al")
        for prefix in PRIVATE_ACTIVITY_PREFIXES:
            assert f"NOT LIKE '{prefix}%'" in clause

    def test_filter_clause_uses_alias(self):
        from projections.api.safety import activity_log_filter_clause

        clause = activity_log_filter_clause("ev")
        assert "ev.activity_type" in clause
        assert "al.activity_type" not in clause

    def test_intelligence_routes_use_filter(self):
        """intelligence.py routes include activity_log_filter_clause."""
        source = (REPO_ROOT / "projections" / "api" / "routes" / "intelligence.py").read_text(
            encoding="utf-8"
        )
        assert "activity_log_filter_clause" in source


# ── 6. Decision log private reasoning not exposed ────────────────────────────


class TestDecisionLogSafety:

    def test_decision_log_safe_columns_defined(self):
        from projections.api.safety import DECISION_LOG_SAFE_COLUMNS, DECISION_LOG_PRIVATE_COLUMNS

        assert "reasoning" in DECISION_LOG_PRIVATE_COLUMNS
        assert "context" in DECISION_LOG_PRIVATE_COLUMNS
        assert "reasoning" not in DECISION_LOG_SAFE_COLUMNS
        assert "context" not in DECISION_LOG_SAFE_COLUMNS

    def test_intelligence_decision_log_is_aggregate_only(self):
        """intelligence.py only uses COUNT(*) on decision_log, never exposes reasoning."""
        source = (REPO_ROOT / "projections" / "api" / "routes" / "intelligence.py").read_text(
            encoding="utf-8"
        )
        decision_queries = [line for line in source.splitlines() if "decision_log" in line.lower()]
        for line in decision_queries:
            assert (
                "reasoning" not in line.lower()
            ), f"decision_log reasoning exposed in: {line.strip()}"


# ── 7. Data classification constants ─────────────────────────────────────────


class TestDataClassification:

    def test_classification_levels_defined(self):
        from projections.api import safety

        assert safety.SAFE_LOCAL_SUMMARY == "safe_local_summary"
        assert safety.SENSITIVE_LOCAL_DETAIL == "sensitive_local_detail"
        assert safety.PRIVATE_INTERNAL == "private_internal"
        assert safety.UNSAFE_FOR_PILOT == "unsafe_for_pilot"


# ── 8. ds_dashboard.py --check is read-only ──────────────────────────────────


class TestDashboardCheck:

    def test_check_flag_accepted(self):
        """--check flag is accepted by the CLI."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=DASHBOARD_CHECK_TIMEOUT_SECONDS,
            cwd=str(REPO_ROOT),
        )
        assert "Preflight check" in result.stdout
        assert "projections.api.main importable" in result.stdout

    def test_check_does_not_start_server(self):
        """--check exits without starting a server or opening a browser."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=DASHBOARD_CHECK_TIMEOUT_SECONDS,
            cwd=str(REPO_ROOT),
        )
        assert "Starting analytics server" not in result.stdout
        assert "Opening" not in result.stdout


# ── 9. scripts/ds_dashboard.py --check delegates ─────────────────────────────


class TestDashboardSmokeCommand:

    def test_smoke_flag_runs_dashboard_smoke_harness(self, tmp_path: Path):
        """--smoke runs bounded dashboard smoke checks with a supplied temp DB."""
        db_path = tmp_path / "operator-command-smoke.db"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"),
                "--smoke",
                "--smoke-db-path",
                str(db_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
        )

        assert result.returncode == 0
        smoke = json.loads(result.stdout)
        assert smoke["result"] == "passed"
        assert smoke["db_path"] == str(db_path)
        assert smoke["uses_live_db"] is False
        assert all(item["status_code"] == 200 for item in smoke["endpoints"])

    def test_smoke_does_not_launch_server_or_browser(self, tmp_path: Path):
        """--smoke exits without launching uvicorn or opening a browser."""
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"),
                "--smoke",
                "--smoke-db-path",
                str(tmp_path / "operator-command-smoke.db"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
        )

        assert result.returncode == 0
        assert "Starting analytics server" not in result.stdout
        assert "Opening" not in result.stdout


class TestScriptShimCheck:

    def test_shim_check_delegates(self):
        """scripts/ds_dashboard.py --check delegates to canonical CLI."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "ds_dashboard.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=DASHBOARD_CHECK_TIMEOUT_SECONDS,
            cwd=str(REPO_ROOT),
        )
        assert "Preflight check" in result.stdout

    def test_shim_smoke_delegates(self, tmp_path: Path):
        """scripts/ds_dashboard.py --smoke delegates to canonical CLI."""
        db_path = tmp_path / "shim-smoke.db"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "ds_dashboard.py"),
                "--smoke",
                "--smoke-db-path",
                str(db_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
        )
        smoke = json.loads(result.stdout)
        assert result.returncode == 0
        assert smoke["result"] == "passed"
        assert smoke["db_path"] == str(db_path)


# ── 10. launch-dashboard and launch-dashboard.cmd point to same module ───────


class TestLaunchScripts:

    def test_bash_launcher_uses_canonical_bootstrap(self):
        """launch-dashboard delegates to canonical CLI bootstrap."""
        source = (REPO_ROOT / "launch-dashboard").read_text(encoding="utf-8")
        assert "interfaces/cli/ds_dashboard.py" in source

    def test_cmd_launcher_uses_canonical_bootstrap(self):
        """launch-dashboard.cmd delegates to canonical CLI bootstrap."""
        source = (REPO_ROOT / "launch-dashboard.cmd").read_text(encoding="utf-8")
        assert "interfaces\\cli\\ds_dashboard.py" in source

    def test_both_launchers_same_target(self):
        """Both launchers delegate to the same canonical CLI."""
        bash = (REPO_ROOT / "launch-dashboard").read_text(encoding="utf-8")
        cmd = (REPO_ROOT / "launch-dashboard.cmd").read_text(encoding="utf-8")
        assert "ds_dashboard" in bash
        assert "ds_dashboard" in cmd


# ── 11. Dashboard changes don't break Phase 5.3A event tests ────────────────


class TestNoRegressionPhase53A:

    def test_event_emission_tests_exist(self):
        """Phase 5.3A event emission test file still exists."""
        assert (REPO_ROOT / "tests" / "unit" / "test_event_emission_reliability.py").is_file()

    def test_safety_module_does_not_import_events(self):
        """Safety module doesn't touch event emission code."""
        source = (REPO_ROOT / "projections" / "api" / "safety.py").read_text(encoding="utf-8")
        assert "emit_event" not in source
        assert "event_emitter" not in source
        assert "EventStore" not in source


# ── 12. Wildcard bind warning ────────────────────────────────────────────────


class TestWildcardWarning:

    def test_start_api_warns_on_wildcard(self):
        """start_api() prints warning when host is 0.0.0.0."""
        source = (REPO_ROOT / "projections" / "api" / "main.py").read_text(encoding="utf-8")
        assert 'host == "0.0.0.0"' in source
        assert "WARNING" in source
