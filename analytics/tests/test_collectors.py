"""Unit tests for analytics collectors"""
import pytest
import sqlite3
from datetime import datetime, timedelta
from analytics.core.collectors.session_collector import SessionCollector
from analytics.core.collectors.skill_collector import SkillCollector
from analytics.core.collectors.token_collector import TokenCollector


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
            project_slug TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            outcome TEXT,
            exit_reason TEXT
        )
    """)

    # Insert sample data
    now = datetime.now()
    test_data = [
        ("session-1", "project-a", (now - timedelta(days=1)).isoformat(), (now - timedelta(days=1, hours=-1)).isoformat(), "success", None),
        ("session-2", "project-a", (now - timedelta(days=2)).isoformat(), (now - timedelta(days=2, hours=-2)).isoformat(), "success", None),
        ("session-3", "project-b", (now - timedelta(days=3)).isoformat(), (now - timedelta(days=3, hours=-1)).isoformat(), "failed", None),
        ("session-4", "project-a", (now - timedelta(days=5)).isoformat(), (now - timedelta(days=5, hours=-1.5)).isoformat(), "success", None),
        ("session-5", "project-c", (now - timedelta(days=100)).isoformat(), (now - timedelta(days=100, hours=-1)).isoformat(), "success", None),  # Outside 90-day window
    ]

    cursor.executemany("""
        INSERT INTO raw_sessions (session_id, project_slug, started_at, ended_at, outcome, exit_reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """, test_data)

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
    assert "project_slug" in recent[0]
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

    # Create raw_skill_telemetry table
    cursor.execute("""
        CREATE TABLE raw_skill_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            invoked_at TEXT NOT NULL,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            success INTEGER NOT NULL,
            execution_time_s REAL,
            project_id TEXT,
            session_id TEXT
        )
    """)

    # Insert sample data
    now = datetime.now()
    test_data = [
        ("dream-studio:core", (now - timedelta(days=1)).isoformat(), "sonnet", 1000, 500, 1, 12.5, "proj-a", "sess-1"),
        ("dream-studio:core", (now - timedelta(days=2)).isoformat(), "sonnet", 1200, 600, 1, 15.2, "proj-a", "sess-2"),
        ("dream-studio:quality", (now - timedelta(days=3)).isoformat(), "haiku", 500, 200, 0, 5.1, "proj-b", "sess-3"),
        ("dream-studio:core", (now - timedelta(days=4)).isoformat(), "sonnet", 1100, 550, 1, 13.0, "proj-a", "sess-4"),
        ("dream-studio:security", (now - timedelta(days=5)).isoformat(), "opus", 2000, 1000, 1, 25.0, "proj-c", "sess-5"),
        ("dream-studio:quality", (now - timedelta(days=100)).isoformat(), "haiku", 450, 180, 1, 4.8, "proj-b", "sess-6"),  # Too old
    ]

    cursor.executemany("""
        INSERT INTO raw_skill_telemetry
        (skill_name, invoked_at, model, input_tokens, output_tokens, success, execution_time_s, project_id, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, test_data)

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
    assert "dream-studio:core" in metrics["by_skill"]
    assert metrics["by_skill"]["dream-studio:core"]["count"] == 3


def test_skill_success_rates(test_skill_db):
    """Test success rate calculation"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    # dream-studio:core: 3/3 success = 100%
    assert metrics["by_skill"]["dream-studio:core"]["success_rate"] == 100.0

    # dream-studio:quality: 0/1 success = 0%
    assert metrics["by_skill"]["dream-studio:quality"]["success_rate"] == 0.0


def test_skill_overall_success_rate(test_skill_db):
    """Test overall success rate"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "success_rate_overall" in metrics
    # 4 successes out of 5 total = 80%
    assert metrics["success_rate_overall"] == 80.0


def test_skill_failures(test_skill_db):
    """Test failure tracking"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "failures" in metrics
    assert len(metrics["failures"]) == 1  # Only 1 failure in test data
    assert metrics["failures"][0]["skill_name"] == "dream-studio:quality"


def test_skill_top_skills(test_skill_db):
    """Test top skills list"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    assert "top_skills" in metrics
    assert len(metrics["top_skills"]) > 0
    # Most used should be dream-studio:core with 3 invocations
    assert metrics["top_skills"][0] == ("dream-studio:core", 3)


def test_skill_performance_metrics(test_skill_db):
    """Test performance metrics (execution time, tokens)"""
    collector = SkillCollector(db_path=str(test_skill_db))
    metrics = collector.collect(days=90)

    core_metrics = metrics["by_skill"]["dream-studio:core"]
    assert "avg_exec_time_s" in core_metrics
    assert core_metrics["avg_exec_time_s"] > 0
    assert "avg_input_tokens" in core_metrics
    assert core_metrics["avg_input_tokens"] > 0


def test_skill_timeline(test_skill_db):
    """Test skill timeline retrieval"""
    collector = SkillCollector(db_path=str(test_skill_db))
    timeline = collector.get_skill_timeline("dream-studio:core", days=30)

    assert isinstance(timeline, list)
    assert len(timeline) == 3  # 3 days with core skill usage
    assert "date" in timeline[0]
    assert "count" in timeline[0]
    assert "success_rate" in timeline[0]


# TokenCollector tests

@pytest.fixture
def test_token_db(tmp_path):
    """Create a temporary test database with token usage data"""
    db_path = tmp_path / "test_studio_tokens.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create raw_token_usage table
    cursor.execute("""
        CREATE TABLE raw_token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            project_id TEXT,
            skill_name TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            model TEXT,
            recorded_at TEXT NOT NULL
        )
    """)

    # Insert sample data
    now = datetime.now()
    test_data = [
        ("sess-1", "proj-a", "dream-studio:core", 1000, 500, "sonnet", (now - timedelta(days=1)).isoformat()),
        ("sess-2", "proj-a", "dream-studio:core", 1200, 600, "sonnet", (now - timedelta(days=2)).isoformat()),
        ("sess-3", "proj-b", "dream-studio:quality", 500, 200, "haiku", (now - timedelta(days=3)).isoformat()),
        ("sess-4", "proj-a", "dream-studio:core", 2000, 1000, "opus", (now - timedelta(days=4)).isoformat()),
        ("sess-5", "proj-c", "dream-studio:security", 800, 400, "sonnet", (now - timedelta(days=5)).isoformat()),
        ("sess-6", "proj-a", "dream-studio:core", 1000, 500, "sonnet", (now - timedelta(days=100)).isoformat()),  # Too old
    ]

    cursor.executemany("""
        INSERT INTO raw_token_usage
        (session_id, project_id, skill_name, input_tokens, output_tokens, model, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, test_data)

    conn.commit()
    conn.close()

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
    assert "sonnet" in metrics["by_model"]
    assert "haiku" in metrics["by_model"]
    assert "opus" in metrics["by_model"]

    # Sonnet: 3 records within 90 days
    sonnet = metrics["by_model"]["sonnet"]
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
    assert "dream-studio:core" in metrics["by_skill"]

    core = metrics["by_skill"]["dream-studio:core"]
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
