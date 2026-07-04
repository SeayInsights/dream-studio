"""Unit tests for analytics collectors"""

import json
import pytest
import sqlite3
from datetime import datetime, timedelta
from projections.core.collectors.session_collector import SessionCollector
from projections.core.collectors.skill_collector import SkillCollector
from projections.core.collectors.token_collector import TokenCollector
from projections.core.collectors.model_collector import ModelCollector
from projections.core.collectors.lesson_collector import LessonCollector
from projections.core.collectors.workflow_collector import WorkflowCollector


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary test database with sample data"""
    db_path = tmp_path / "test_studio.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create raw_sessions table
    cursor.execute("""
        CREATE TABLE raw_sessions (
            session_id TEXT PRIMARY KEY,
            project_id TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            outcome TEXT,
            exit_reason TEXT
        )
    """)

    # Insert sample data
    now = datetime.now()
    test_data = [
        (
            "session-1",
            "project-a",
            (now - timedelta(days=1)).isoformat(),
            (now - timedelta(days=1, hours=-1)).isoformat(),
            "success",
            None,
        ),
        (
            "session-2",
            "project-a",
            (now - timedelta(days=2)).isoformat(),
            (now - timedelta(days=2, hours=-2)).isoformat(),
            "success",
            None,
        ),
        (
            "session-3",
            "project-b",
            (now - timedelta(days=3)).isoformat(),
            (now - timedelta(days=3, hours=-1)).isoformat(),
            "failed",
            None,
        ),
        (
            "session-4",
            "project-a",
            (now - timedelta(days=5)).isoformat(),
            (now - timedelta(days=5, hours=-1.5)).isoformat(),
            "success",
            None,
        ),
        (
            "session-5",
            "project-c",
            (now - timedelta(days=100)).isoformat(),
            (now - timedelta(days=100, hours=-1)).isoformat(),
            "success",
            None,
        ),  # Outside 90-day window
    ]

    cursor.executemany(
        """
        INSERT INTO raw_sessions (session_id, project_id, started_at, ended_at, outcome, exit_reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        test_data,
    )

    conn.commit()
    conn.close()

    return db_path


def test_session_collector_initialization():
    """Test SessionCollector can be initialized"""
    collector = SessionCollector()
    assert collector.db_path is not None


def test_session_collector_custom_db(test_db):
    """Test SessionCollector with custom database path"""
    collector = SessionCollector(db_path=str(test_db))
    assert collector.db_path == str(test_db)


def test_collect_total_sessions(test_db):
    """Test total sessions count"""
    collector = SessionCollector(db_path=str(test_db))
    metrics = collector.collect(days=90)

    assert "total_sessions" in metrics
    assert metrics["total_sessions"] == 4  # 5 total, but 1 is > 90 days old


def test_collect_by_project(test_db):
    """Test sessions grouped by project"""
    collector = SessionCollector(db_path=str(test_db))
    metrics = collector.collect(days=90)

    assert "by_project" in metrics
    assert metrics["by_project"]["project-a"] == 3
    assert metrics["by_project"]["project-b"] == 1
    assert "project-c" not in metrics["by_project"]  # Too old


def test_collect_timeline(test_db):
    """Test timeline contains daily counts"""
    collector = SessionCollector(db_path=str(test_db))
    metrics = collector.collect(days=90)

    assert "timeline" in metrics
    assert isinstance(metrics["timeline"], list)
    assert len(metrics["timeline"]) > 0
    assert "date" in metrics["timeline"][0]
    assert "count" in metrics["timeline"][0]


def test_collect_day_of_week(test_db):
    """Test day of week aggregation"""
    collector = SessionCollector(db_path=str(test_db))
    metrics = collector.collect(days=90)

    assert "day_of_week" in metrics
    assert isinstance(metrics["day_of_week"], dict)
    # Should have weekday names as keys
    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day in metrics["day_of_week"].keys():
        assert day in weekday_names


def test_collect_outcomes(test_db):
    """Test outcome aggregation"""
    collector = SessionCollector(db_path=str(test_db))
    metrics = collector.collect(days=90)

    assert "outcomes" in metrics
    assert metrics["outcomes"]["success"] == 3
    assert metrics["outcomes"]["failed"] == 1


def test_collect_avg_duration(test_db):
    """Test average duration calculation"""
    collector = SessionCollector(db_path=str(test_db))
    metrics = collector.collect(days=90)

    assert "avg_duration_minutes" in metrics
    assert isinstance(metrics["avg_duration_minutes"], float)
    assert metrics["avg_duration_minutes"] > 0


def test_get_recent_sessions(test_db):
    """Test retrieving recent sessions"""
    collector = SessionCollector(db_path=str(test_db))
    recent = collector.get_recent_sessions(limit=3)

    assert len(recent) == 3
    assert "session_id" in recent[0]
    assert "project_id" in recent[0]
    assert "started_at" in recent[0]


def test_collect_with_custom_days(test_db):
    """Test collecting with custom day range"""
    collector = SessionCollector(db_path=str(test_db))

    # Collect only last 2 days
    metrics_2d = collector.collect(days=2)
    assert metrics_2d["total_sessions"] == 2  # Only session-1 and session-2

    # Collect last 7 days
    metrics_7d = collector.collect(days=7)
    assert metrics_7d["total_sessions"] == 4  # All except session-5


# SkillCollector tests


@pytest.fixture
def test_skill_db(tmp_path):
    """Create a temporary test database with skill telemetry data"""
    db_path = tmp_path / "test_studio_skills.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Seed execution_events — the current skill-telemetry authority. SkillCollector
    # reads skill_usage_sql(), which projects event_type='skill.invoked' rows and
    # derives execution_time_s by pairing execution.started/completed events that
    # share the same process_run_id. (Model/token dimensions are not carried here.)
    cursor.execute("""
        CREATE TABLE execution_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            skill_id TEXT,
            outcome_status TEXT,
            process_run_id TEXT,
            project_id TEXT,
            created_at TEXT NOT NULL
        )
    """)

    now = datetime.now()

    def _ts(days_ago, secs=0):
        return (now - timedelta(days=days_ago) + timedelta(seconds=secs)).isoformat()

    # 5 in-window skill.invoked rows + 1 older than 90 days.
    # (event_id, skill_id, outcome_status, process_run_id, project_id, days_ago)
    invocations = [
        ("inv-1", "ds-core", "completed", "run-1", "proj-a", 1),
        ("inv-2", "ds-core", "completed", "run-2", "proj-a", 2),
        ("inv-3", "ds-core", "completed", "run-3", "proj-a", 4),
        ("inv-4", "ds-quality", "failed", "run-4", "proj-b", 3),
        ("inv-5", "ds-security", "completed", "run-5", "proj-c", 5),
        ("inv-old", "ds-quality", "completed", "run-old", "proj-b", 100),  # too old
    ]
    rows = [
        (eid, "skill.invoked", skill, outcome, run, proj, _ts(ago))
        for eid, skill, outcome, run, proj, ago in invocations
    ]
    # Timing pairs for the first two ds-core runs (durations ~12s and ~15s); run-3
    # is intentionally unpaired (NULL duration, excluded from AVG, never fabricated).
    rows += [
        ("es-1", "execution.started", None, None, "run-1", "proj-a", _ts(1, 0)),
        ("ec-1", "execution.completed", None, None, "run-1", "proj-a", _ts(1, 12)),
        ("es-2", "execution.started", None, None, "run-2", "proj-a", _ts(2, 0)),
        ("ec-2", "execution.completed", None, None, "run-2", "proj-a", _ts(2, 15)),
    ]

    cursor.executemany(
        """
        INSERT INTO execution_events
        (event_id, event_type, skill_id, outcome_status, process_run_id, project_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        rows,
    )

    conn.commit()
    conn.close()

    return db_path


def test_skill_collector_initialization():
    """Test SkillCollector can be initialized"""
    collector = SkillCollector()
    assert collector.db_path is not None


def test_skill_collect_total(test_skill_db):
    """Test total invocations count"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "total_invocations" in metrics
    assert metrics["total_invocations"] == 5  # 6 total, but 1 is > 90 days old


def test_skill_collect_by_skill(test_skill_db):
    """Test metrics grouped by skill"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "by_skill" in metrics
    assert "ds-core" in metrics["by_skill"]
    assert metrics["by_skill"]["ds-core"]["count"] == 3


def test_skill_success_rates(test_skill_db):
    """Test success rate calculation"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    # ds-core: 3/3 success = 100%
    assert metrics["by_skill"]["ds-core"]["success_rate"] == 100.0

    # ds-quality: 0/1 success = 0%
    assert metrics["by_skill"]["ds-quality"]["success_rate"] == 0.0


def test_skill_overall_success_rate(test_skill_db):
    """Test overall success rate"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "overall_success_rate" in metrics
    # 4 successes out of 5 total = 80%
    assert metrics["overall_success_rate"] == 80.0


def test_skill_failures(test_skill_db):
    """Test failure tracking"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "failures" in metrics
    assert len(metrics["failures"]) == 1  # Only 1 failure in test data
    assert metrics["failures"][0]["skill_name"] == "ds-quality"


def test_skill_top_skills(test_skill_db):
    """Test top skills list"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "top_skills" in metrics
    assert len(metrics["top_skills"]) > 0
    # Most used should be ds-core with 3 invocations (entries are dicts).
    assert metrics["top_skills"][0]["skill_name"] == "ds-core"
    assert metrics["top_skills"][0]["count"] == 3


def test_skill_performance_metrics(test_skill_db):
    """Test performance metrics (execution time, tokens)"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    core_metrics = metrics["by_skill"]["ds-core"]
    assert "avg_exec_time_s" in core_metrics
    # Two of three ds-core runs have execution.started/completed pairs → positive avg.
    assert core_metrics["avg_exec_time_s"] > 0
    # Token dimensions are not carried by skill telemetry in the current authority.
    assert "avg_input_tokens" in core_metrics
    assert core_metrics["avg_input_tokens"] == 0


def test_skill_timeline(test_skill_db):
    """Test skill timeline retrieval"""
    collector = SkillCollector(db_path=str(test_skill_db))
    timeline = collector.get_skill_timeline("ds-core", days=30)

    assert isinstance(timeline, list)
    assert len(timeline) == 3  # 3 days with core skill usage
    assert "date" in timeline[0]
    assert "count" in timeline[0]
    assert "success_rate" in timeline[0]


# TokenCollector tests
#
# WO-DBA-DROP (migration 137): token_usage_records is retired from SQLite.
# TokenCollector reads authority_sources.token_usage_sql(), which now falls
# through to the DuckDB aggregate_metrics.db token_usage_records view when
# the SQLite connection has no such table. These fixtures seed that view via
# events_fact (the test_session_collector_duckdb.py pattern) instead of
# building the dropped table directly — model ids are real Claude models
# (claude-sonnet-4-6/claude-haiku-4-5/claude-opus-4-8) so the view's
# token_model_pricing join produces real, non-zero estimated_cost, same as
# production. The sqlite db_path returned is a bare, empty database — the
# collector still needs one to open, but it carries no token data.

_SONNET = "claude-sonnet-4-6"
_HAIKU = "claude-haiku-4-5"
_OPUS = "claude-opus-4-8"


def _seed_token_events_fact(analytics_db, rows: list[tuple]) -> None:
    """Seed token.consumed events into an isolated DuckDB analytics store.

    Each row: (event_id, project_id, skill_id, model_id, input_tokens,
    output_tokens, event_timestamp).
    """
    from core.analytics import duckdb_store

    conn = duckdb_store.connect_analytics(analytics_db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        for event_id, project_id, skill_id, model_id, inp, out, ts in rows:
            conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp, project_id,"
                " skill_id, model_id, input_tokens, output_tokens)"
                " VALUES (?, 'token.consumed', ?, ?, ?, ?, ?, ?)",
                [event_id, ts, project_id, skill_id, model_id, inp, out],
            )
    finally:
        conn.close()


@pytest.fixture
def test_token_db(tmp_path, monkeypatch):
    """Create an isolated DuckDB analytics store with token.consumed events,
    plus a bare SQLite db_path for the collector to open."""
    from core.analytics import duckdb_store

    db_path = tmp_path / "test_studio_tokens.db"
    sqlite3.connect(str(db_path)).close()

    analytics_db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: analytics_db)

    now = datetime.now()
    rows = [
        ("token-1", "proj-a", "ds-core", _SONNET, 1000, 500, (now - timedelta(days=1)).isoformat()),
        ("token-2", "proj-a", "ds-core", _SONNET, 1200, 600, (now - timedelta(days=2)).isoformat()),
        (
            "token-3",
            "proj-b",
            "ds-quality",
            _HAIKU,
            500,
            200,
            (now - timedelta(days=3)).isoformat(),
        ),
        ("token-4", "proj-a", "ds-core", _OPUS, 2000, 1000, (now - timedelta(days=4)).isoformat()),
        (
            "token-5",
            "proj-c",
            "ds-security",
            _SONNET,
            800,
            400,
            (now - timedelta(days=5)).isoformat(),
        ),
        # Too old — excluded by the 90-day window.
        (
            "token-6",
            "proj-a",
            "ds-core",
            _SONNET,
            1000,
            500,
            (now - timedelta(days=100)).isoformat(),
        ),
    ]
    _seed_token_events_fact(analytics_db, rows)

    return db_path


def test_token_collector_initialization():
    """Test TokenCollector can be initialized"""
    collector = TokenCollector()
    assert collector.db_path is not None


def test_token_collect_totals(test_token_db):
    """Test total token counts"""
    collector = TokenCollector(db_path=str(test_token_db))
    metrics = collector.collect(days=90)

    assert "total_input_tokens" in metrics
    assert "total_output_tokens" in metrics
    assert "total_tokens" in metrics

    # 5 records within 90 days: (1000+1200+500+2000+800) input, (500+600+200+1000+400) output
    assert metrics["total_input_tokens"] == 5500
    assert metrics["total_output_tokens"] == 2700
    assert metrics["total_tokens"] == 8200


def test_token_cost_calculation(test_token_db):
    """Test cost calculation"""
    collector = TokenCollector(db_path=str(test_token_db))
    metrics = collector.collect(days=90)

    assert "total_cost_usd" in metrics
    assert metrics["total_cost_usd"] > 0  # Should have calculated cost


def test_token_by_model(test_token_db):
    """Test tokens grouped by model"""
    collector = TokenCollector(db_path=str(test_token_db))
    metrics = collector.collect(days=90)

    assert "by_model" in metrics
    assert _SONNET in metrics["by_model"]
    assert _HAIKU in metrics["by_model"]
    assert _OPUS in metrics["by_model"]

    # Sonnet: 3 records within 90 days
    sonnet = metrics["by_model"][_SONNET]
    assert sonnet["input_tokens"] == (1000 + 1200 + 800)
    assert sonnet["output_tokens"] == (500 + 600 + 400)


def test_token_by_project(test_token_db):
    """Test tokens grouped by project"""
    collector = TokenCollector(db_path=str(test_token_db))
    metrics = collector.collect(days=90)

    assert "by_project" in metrics
    assert "proj-a" in metrics["by_project"]

    proj_a = metrics["by_project"]["proj-a"]
    assert proj_a["total_tokens"] > 0
    assert "cost_usd" in proj_a


def test_token_by_skill(test_token_db):
    """Test tokens grouped by skill"""
    collector = TokenCollector(db_path=str(test_token_db))
    metrics = collector.collect(days=90)

    assert "by_skill" in metrics
    assert "ds-core" in metrics["by_skill"]

    core = metrics["by_skill"]["ds-core"]
    assert core["total_tokens"] > 0
    assert "cost_usd" in core


def test_token_daily_average(test_token_db):
    """Test daily average calculation"""
    collector = TokenCollector(db_path=str(test_token_db))
    metrics = collector.collect(days=90)

    assert "daily_average" in metrics
    assert metrics["daily_average"] > 0


def test_token_timeline(test_token_db):
    """Test token usage timeline"""
    collector = TokenCollector(db_path=str(test_token_db))
    timeline = collector.get_timeline(days=30)

    assert isinstance(timeline, list)
    assert len(timeline) == 5  # 5 days with token usage
    assert "date" in timeline[0]
    assert "tokens" in timeline[0]
    assert "cost_usd" in timeline[0]


def test_token_percentage(test_token_db):
    """Test model percentage calculation"""
    collector = TokenCollector(db_path=str(test_token_db))
    metrics = collector.collect(days=90)

    # All models should have percentage
    for model_data in metrics["by_model"].values():
        assert "percentage" in model_data
        assert 0 <= model_data["percentage"] <= 100

    # Sum of all percentages should be ~100
    total_percentage = sum(m["percentage"] for m in metrics["by_model"].values())
    assert 99 <= total_percentage <= 101  # Allow small rounding errors


# ModelCollector tests
#
# WO-DBA-DROP (migration 137): same DuckDB-events_fact seeding as the
# TokenCollector fixture above (token_usage_records is retired from SQLite).
# ModelCollector reads token_usage_sql() for per-model invocation counts and
# token volume; skill telemetry no longer carries the model dimension, so
# success/timing are not attributed per model.


@pytest.fixture
def test_model_db(tmp_path, monkeypatch):
    """Create an isolated DuckDB analytics store with token.consumed events,
    plus a bare SQLite db_path for the collector to open."""
    from core.analytics import duckdb_store

    db_path = tmp_path / "test_studio_models.db"
    sqlite3.connect(str(db_path)).close()

    analytics_db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: analytics_db)

    now = datetime.now()

    def _ts(days_ago):
        return (now - timedelta(days=days_ago)).isoformat()

    # 5 in-window records: sonnet x3 (days 1,2,5), haiku x1 (day 3), opus x1 (day 4),
    # plus one older-than-90-days record that must be excluded.
    # (id, model_id, input, output, project, skill, days_ago)
    token_data = [
        ("tok-1", _SONNET, 1000, 500, "proj-a", "ds-core", 1),
        ("tok-2", _SONNET, 1200, 600, "proj-a", "ds-core", 2),
        ("tok-3", _HAIKU, 500, 200, "proj-b", "ds-quality", 3),
        ("tok-4", _OPUS, 2000, 1000, "proj-a", "ds-core", 4),
        ("tok-5", _SONNET, 800, 400, "proj-c", "ds-security", 5),
        ("tok-old", _HAIKU, 450, 180, "proj-b", "ds-quality", 100),  # too old
    ]
    rows = [
        (tid, proj, skill, model, inp, out, _ts(ago))
        for tid, model, inp, out, proj, skill, ago in token_data
    ]
    _seed_token_events_fact(analytics_db, rows)

    return db_path


def test_model_collector_initialization():
    """Test ModelCollector can be initialized"""
    collector = ModelCollector()
    assert collector.db_path is not None


def test_model_collect_by_model(test_model_db):
    """Test metrics grouped by model"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    assert "by_model" in metrics
    assert _SONNET in metrics["by_model"]
    assert _HAIKU in metrics["by_model"]
    assert _OPUS in metrics["by_model"]

    # Sonnet: 3 invocations
    assert metrics["by_model"][_SONNET]["invocations"] == 3


def test_model_success_rates(test_model_db):
    """Success rates are surfaced per model. The current authority does not
    attribute skill outcomes to a model (skill telemetry carries no model
    dimension), so token-sourced models report 0.0 — honest, not fabricated."""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    assert "success_rates" in metrics
    assert _SONNET in metrics["success_rates"]
    assert metrics["by_model"][_SONNET]["success_rate"] == 0.0
    assert metrics["by_model"][_OPUS]["success_rate"] == 0.0


def test_model_distribution(test_model_db):
    """Test model usage distribution"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    assert "distribution_pct" in metrics
    assert _SONNET in metrics["distribution_pct"]

    # 5 in-window invocations, sonnet has 3 = 60%
    assert metrics["distribution_pct"][_SONNET] == 60.0

    # Sum should be ~100%
    total = sum(metrics["distribution_pct"].values())
    assert 99 <= total <= 101


def test_model_performance_rank(test_model_db):
    """Test model performance ranking"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    assert "performance_rank" in metrics
    assert isinstance(metrics["performance_rank"], list)
    # Ranking is a list of model names ordered by a speed-weighted score. It only
    # includes models with attributed timing; the current authority has none per
    # model, so the list is empty (but well-formed) until timing is attributed.
    assert all(isinstance(m, str) for m in metrics["performance_rank"])


def test_model_token_totals(test_model_db):
    """Per-model token volume is aggregated from token_usage_records."""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    # sonnet: (1000+500) + (1200+600) + (800+400) = 4500 tokens across 3 records.
    assert metrics["by_model"][_SONNET]["total_tokens"] == 4500
    assert metrics["by_model"][_HAIKU]["total_tokens"] == 700


def test_model_timeline(test_model_db):
    """Test model timeline retrieval"""
    collector = ModelCollector(db_path=str(test_model_db))
    timeline = collector.get_model_timeline(_SONNET, days=30)

    assert isinstance(timeline, list)
    assert len(timeline) == 3  # 3 days with sonnet usage
    assert "date" in timeline[0]
    assert "invocations" in timeline[0]
    assert "success_rate" in timeline[0]
    assert "avg_exec_time_s" in timeline[0]


def test_model_performance_metrics(test_model_db):
    """Test performance metrics (execution time, tokens)"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    sonnet_metrics = metrics["by_model"][_SONNET]
    # Timing is not attributed per model in the current authority.
    assert "avg_exec_time_s" in sonnet_metrics
    assert sonnet_metrics["avg_exec_time_s"] == 0.0
    # Token volume IS attributed (from the DuckDB token_usage_records view).
    assert sonnet_metrics["avg_tokens_per_run"] > 0
    assert sonnet_metrics["total_tokens"] > 0


# LessonCollector tests


@pytest.fixture
def test_lesson_db(tmp_path):
    """Create a temporary test database with lesson data"""
    db_path = tmp_path / "test_studio_lessons.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE raw_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            confidence TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'draft',
            title TEXT NOT NULL,
            what_happened TEXT,
            lesson TEXT,
            evidence TEXT,
            promoted_to TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        )
    """)

    now = datetime.now()
    test_data = [
        (
            "lesson-1",
            "on-skill-complete",
            "high",
            "final",
            "Auth bug fixed",
            "Bug desc",
            "Lesson text",
            "Evidence",
            "gotchas.yml",
            (now - timedelta(days=1)).isoformat(),
            None,
        ),
        (
            "lesson-2",
            "on-context-threshold",
            "medium",
            "draft",
            "Context overflow",
            "Desc",
            "Lesson",
            "Evidence",
            None,
            (now - timedelta(days=2)).isoformat(),
            None,
        ),
        (
            "lesson-3",
            "on-skill-complete",
            "high",
            "final",
            "Perf improvement",
            "Desc",
            "Lesson",
            "Evidence",
            "best_practices.md",
            (now - timedelta(days=3)).isoformat(),
            (now - timedelta(days=2)).isoformat(),
        ),
        (
            "lesson-4",
            "manual",
            "low",
            "draft",
            "Minor issue",
            "Desc",
            "Lesson",
            "Evidence",
            None,
            (now - timedelta(days=5)).isoformat(),
            None,
        ),
        (
            "lesson-5",
            "on-skill-complete",
            "medium",
            "draft",
            "Old lesson",
            "Desc",
            "Lesson",
            "Evidence",
            None,
            (now - timedelta(days=100)).isoformat(),
            None,
        ),  # Too old
    ]

    cursor.executemany(
        """
        INSERT INTO raw_lessons
        (lesson_id, source, confidence, status, title, what_happened, lesson, evidence, promoted_to, created_at, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        test_data,
    )

    conn.commit()
    conn.close()

    return db_path


def test_lesson_collector_initialization():
    """Test LessonCollector can be initialized"""
    collector = LessonCollector()
    assert collector.db_path is not None


def test_lesson_collect_total(test_lesson_db):
    """Test total lessons count"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    metrics = collector.collect(days=90)

    assert "total_lessons" in metrics
    assert metrics["total_lessons"] == 4  # 5 total, but 1 is > 90 days old


def test_lesson_by_source(test_lesson_db):
    """Test lessons grouped by source"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    metrics = collector.collect(days=90)

    assert "by_source" in metrics
    assert "on-skill-complete" in metrics["by_source"]
    assert metrics["by_source"]["on-skill-complete"] == 2


def test_lesson_by_status(test_lesson_db):
    """Test lessons grouped by status"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    metrics = collector.collect(days=90)

    assert "by_status" in metrics
    assert "draft" in metrics["by_status"]
    assert "final" in metrics["by_status"]


def test_lesson_by_confidence(test_lesson_db):
    """Test lessons grouped by confidence"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    metrics = collector.collect(days=90)

    assert "by_confidence" in metrics
    assert "high" in metrics["by_confidence"]
    assert "medium" in metrics["by_confidence"]
    assert "low" in metrics["by_confidence"]


def test_lesson_capture_rate(test_lesson_db):
    """Test lesson capture rate calculation"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    metrics = collector.collect(days=90)

    assert "capture_rate" in metrics
    assert metrics["capture_rate"] > 0  # 4 lessons / 90 days


def test_lesson_promoted_count(test_lesson_db):
    """Test promoted lessons count"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    metrics = collector.collect(days=90)

    assert "promoted_count" in metrics
    assert metrics["promoted_count"] == 2  # lesson-1 and lesson-3 are promoted


def test_lesson_recent_lessons(test_lesson_db):
    """Test recent lessons retrieval"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    metrics = collector.collect(days=90)

    assert "recent_lessons" in metrics
    assert len(metrics["recent_lessons"]) == 4  # 4 within 90 days
    assert "lesson_id" in metrics["recent_lessons"][0]
    assert "title" in metrics["recent_lessons"][0]


def test_lesson_timeline(test_lesson_db):
    """Test lesson timeline"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    timeline = collector.get_timeline(days=30)

    assert isinstance(timeline, list)
    assert len(timeline) > 0


def test_lesson_source_quality(test_lesson_db):
    """Test source quality analysis"""
    collector = LessonCollector(db_path=str(test_lesson_db))
    quality = collector.get_source_quality()

    assert isinstance(quality, list)
    assert len(quality) > 0
    assert "source" in quality[0]
    assert "count" in quality[0]
    assert "promoted_rate" in quality[0]
    assert "avg_confidence_score" in quality[0]


# WorkflowCollector tests


def _workflow_completed_payload(
    run_key: str,
    workflow: str,
    yaml_path: str,
    status: str,
    started,
    finished,
    node_count,
    nodes_done,
) -> dict:
    duration_ms = int((finished - started).total_seconds() * 1000)
    return {
        "run_key": run_key,
        "workflow": workflow,
        "yaml_path": yaml_path,
        "status": status,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": duration_ms,
        "node_count": node_count,
        "nodes_done": nodes_done,
    }


def _workflow_node_completed_payload(
    run_key: str, workflow: str, node_id: str, status: str, started, finished, output: str
) -> dict:
    duration_ms = int((finished - started).total_seconds() * 1000) if finished and started else None
    return {
        "run_key": run_key,
        "node_id": node_id,
        "workflow": workflow,
        "status": status,
        "output": output,
        "duration_ms": duration_ms,
    }


def _insert_ai_canonical_event(
    cursor, event_id: str, event_type: str, event_timestamp: str, payload: dict, workflow_id: str
) -> None:
    cursor.execute(
        """
        INSERT INTO ai_canonical_events
        (event_id, event_type, event_timestamp, trace, payload, workflow_id)
        VALUES (?, ?, ?, '{}', ?, ?)
        """,
        (event_id, event_type, event_timestamp, json.dumps(payload), workflow_id),
    )


@pytest.fixture
def test_workflow_db(tmp_path):
    """Create a temporary test database seeded with workflow.completed /
    workflow.node.completed canonical events (ai_canonical_events).

    WO 9f47a1a0: raw_workflow_runs/raw_workflow_nodes (dropped migration 141)
    replaced as WorkflowCollector's data source by these canonical events —
    see core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql.
    """
    from core.config.sqlite_bootstrap import run_migrations

    db_path = tmp_path / "test_studio_workflows.db"
    conn = sqlite3.connect(str(db_path))
    run_migrations(conn, apply_unreleased=True)
    cursor = conn.cursor()

    now = datetime.now()
    workflow_data = [
        (
            "run-1",
            "build-pipeline",
            "/workflows/build.yml",
            "completed",
            now - timedelta(days=1),
            now - timedelta(days=1, hours=-1),
            3,
            3,
        ),
        (
            "run-2",
            "test-suite",
            "/workflows/test.yml",
            "completed",
            now - timedelta(days=2),
            now - timedelta(days=2, hours=-0.5),
            2,
            2,
        ),
        (
            "run-3",
            "build-pipeline",
            "/workflows/build.yml",
            "failed",
            now - timedelta(days=3),
            now - timedelta(days=3, hours=-0.8),
            3,
            2,
        ),
        (
            "run-4",
            "deploy",
            "/workflows/deploy.yml",
            "completed",
            now - timedelta(days=5),
            now - timedelta(days=5, hours=-2),
            4,
            4,
        ),
        (
            "run-5",
            "test-suite",
            "/workflows/test.yml",
            "completed",
            now - timedelta(days=100),
            now - timedelta(days=100, hours=-0.5),
            2,
            2,
        ),  # Too old
    ]

    for i, (
        run_key,
        workflow,
        yaml_path,
        status,
        started,
        finished,
        node_count,
        nodes_done,
    ) in enumerate(workflow_data):
        payload = _workflow_completed_payload(
            run_key, workflow, yaml_path, status, started, finished, node_count, nodes_done
        )
        _insert_ai_canonical_event(
            cursor,
            f"evt-run-{i}",
            "workflow.completed",
            finished.isoformat(),
            payload,
            workflow,
        )

    # Add some nodes
    node_data = [
        (
            "run-1",
            "build-pipeline",
            "compile",
            "completed",
            now - timedelta(days=1),
            now - timedelta(days=1, hours=-0.3),
            "output1",
        ),
        (
            "run-1",
            "build-pipeline",
            "test",
            "completed",
            now - timedelta(days=1),
            now - timedelta(days=1, hours=-0.5),
            "output2",
        ),
        (
            "run-2",
            "test-suite",
            "test",
            "completed",
            now - timedelta(days=2),
            now - timedelta(days=2, hours=-0.5),
            "output3",
        ),
        (
            "run-3",
            "build-pipeline",
            "compile",
            "completed",
            now - timedelta(days=3),
            now - timedelta(days=3, hours=-0.3),
            "output4",
        ),
        (
            "run-3",
            "build-pipeline",
            "test",
            "failed",
            now - timedelta(days=3),
            now - timedelta(days=3, hours=-0.5),
            "output5",
        ),
    ]

    for i, (run_key, workflow, node_id, status, started, finished, output) in enumerate(node_data):
        payload = _workflow_node_completed_payload(
            run_key, workflow, node_id, status, started, finished, output
        )
        _insert_ai_canonical_event(
            cursor,
            f"evt-node-{i}",
            "workflow.node.completed",
            finished.isoformat(),
            payload,
            workflow,
        )

    conn.commit()
    conn.close()

    return db_path


def test_workflow_collector_initialization():
    """Test WorkflowCollector can be initialized"""
    collector = WorkflowCollector()
    assert collector.db_path is not None


def test_workflow_collect_total(test_workflow_db):
    """Test total workflow runs count"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    metrics = collector.collect(days=90)

    assert "total_runs" in metrics
    assert metrics["total_runs"] == 4  # 5 total, but 1 is > 90 days old


def test_workflow_by_workflow(test_workflow_db):
    """Test workflows grouped by name"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    metrics = collector.collect(days=90)

    assert "by_workflow" in metrics
    assert "build-pipeline" in metrics["by_workflow"]
    assert metrics["by_workflow"]["build-pipeline"]["count"] == 2


def test_workflow_success_rate(test_workflow_db):
    """Test workflow success rate"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    metrics = collector.collect(days=90)

    assert "success_rate" in metrics
    # 3 completed out of 4 total = 75%
    assert metrics["success_rate"] == 75.0


def test_workflow_by_status(test_workflow_db):
    """Test workflows grouped by status"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    metrics = collector.collect(days=90)

    assert "by_status" in metrics
    assert "completed" in metrics["by_status"]
    assert "failed" in metrics["by_status"]


def test_workflow_avg_completion_time(test_workflow_db):
    """Test average completion time"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    metrics = collector.collect(days=90)

    assert "avg_completion_time_minutes" in metrics
    assert metrics["avg_completion_time_minutes"] > 0


def test_workflow_total_nodes(test_workflow_db):
    """Test total nodes executed"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    metrics = collector.collect(days=90)

    assert "total_nodes_executed" in metrics
    assert metrics["total_nodes_executed"] == 5  # 5 nodes in recent workflows


def test_workflow_timeline(test_workflow_db):
    """Test workflow timeline"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    timeline = collector.get_timeline(days=30)

    assert isinstance(timeline, list)
    assert len(timeline) > 0
    assert "date" in timeline[0]
    assert "runs" in timeline[0]


def test_workflow_node_performance(test_workflow_db):
    """Test node performance analysis"""
    collector = WorkflowCollector(db_path=str(test_workflow_db))
    performance = collector.get_node_performance()

    assert isinstance(performance, list)
    assert len(performance) > 0
    assert "node_id" in performance[0]
    assert "executions" in performance[0]
    assert "avg_duration_s" in performance[0]
    assert "failure_rate" in performance[0]
