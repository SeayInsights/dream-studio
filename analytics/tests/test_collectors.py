"""Unit tests for analytics collectors"""
import pytest
import sqlite3
from datetime import datetime, timedelta
from analytics.core.collectors.session_collector import SessionCollector
from analytics.core.collectors.skill_collector import SkillCollector
from analytics.core.collectors.token_collector import TokenCollector
from analytics.core.collectors.model_collector import ModelCollector
from analytics.core.collectors.lesson_collector import LessonCollector
from analytics.core.collectors.workflow_collector import WorkflowCollector


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


# ModelCollector tests

@pytest.fixture
def test_model_db(tmp_path):
    """Create a temporary test database with model performance data"""
    db_path = tmp_path / "test_studio_models.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create tables
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

    # Insert sample skill telemetry data
    now = datetime.now()
    skill_data = [
        ("dream-studio:core", (now - timedelta(days=1)).isoformat(), "sonnet", 1000, 500, 1, 10.0, "proj-a", "sess-1"),
        ("dream-studio:core", (now - timedelta(days=2)).isoformat(), "sonnet", 1200, 600, 1, 12.0, "proj-a", "sess-2"),
        ("dream-studio:quality", (now - timedelta(days=3)).isoformat(), "haiku", 500, 200, 1, 5.0, "proj-b", "sess-3"),
        ("dream-studio:core", (now - timedelta(days=4)).isoformat(), "opus", 2000, 1000, 0, 30.0, "proj-a", "sess-4"),
        ("dream-studio:security", (now - timedelta(days=5)).isoformat(), "sonnet", 800, 400, 1, 11.0, "proj-c", "sess-5"),
    ]

    cursor.executemany("""
        INSERT INTO raw_skill_telemetry
        (skill_name, invoked_at, model, input_tokens, output_tokens, success, execution_time_s, project_id, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, skill_data)

    # Insert token usage data
    token_data = [
        ("sess-1", "proj-a", "dream-studio:core", 1000, 500, "sonnet", (now - timedelta(days=1)).isoformat()),
        ("sess-2", "proj-a", "dream-studio:core", 1200, 600, "sonnet", (now - timedelta(days=2)).isoformat()),
        ("sess-3", "proj-b", "dream-studio:quality", 500, 200, "haiku", (now - timedelta(days=3)).isoformat()),
        ("sess-4", "proj-a", "dream-studio:core", 2000, 1000, "opus", (now - timedelta(days=4)).isoformat()),
        ("sess-5", "proj-c", "dream-studio:security", 800, 400, "sonnet", (now - timedelta(days=5)).isoformat()),
    ]

    cursor.executemany("""
        INSERT INTO raw_token_usage
        (session_id, project_id, skill_name, input_tokens, output_tokens, model, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, token_data)

    conn.commit()
    conn.close()

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
    assert "sonnet" in metrics["by_model"]
    assert "haiku" in metrics["by_model"]
    assert "opus" in metrics["by_model"]

    # Sonnet: 3 invocations
    assert metrics["by_model"]["sonnet"]["invocations"] == 3


def test_model_success_rates(test_model_db):
    """Test model success rate calculation"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    # Sonnet: 3/3 success = 100%
    assert metrics["by_model"]["sonnet"]["success_rate"] == 100.0

    # Opus: 0/1 success = 0%
    assert metrics["by_model"]["opus"]["success_rate"] == 0.0


def test_model_distribution(test_model_db):
    """Test model usage distribution"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    assert "distribution" in metrics
    assert "sonnet" in metrics["distribution"]

    # 5 total invocations, sonnet has 3 = 60%
    assert metrics["distribution"]["sonnet"] == 60.0

    # Sum should be 100%
    total = sum(metrics["distribution"].values())
    assert 99 <= total <= 101


def test_model_performance_rank(test_model_db):
    """Test model performance ranking"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    assert "performance_rank" in metrics
    assert isinstance(metrics["performance_rank"], list)
    assert len(metrics["performance_rank"]) > 0

    # Each entry should be (model, score) tuple
    assert isinstance(metrics["performance_rank"][0], tuple)
    assert len(metrics["performance_rank"][0]) == 2


def test_model_token_efficiency(test_model_db):
    """Test token efficiency calculation"""
    collector = ModelCollector(db_path=str(test_model_db))
    metrics = collector.collect(days=90)

    assert "token_efficiency" in metrics

    # Models with execution time should have efficiency score
    if "sonnet" in metrics["token_efficiency"]:
        assert metrics["token_efficiency"]["sonnet"] > 0


def test_model_timeline(test_model_db):
    """Test model timeline retrieval"""
    collector = ModelCollector(db_path=str(test_model_db))
    timeline = collector.get_model_timeline("sonnet", days=30)

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

    sonnet_metrics = metrics["by_model"]["sonnet"]
    assert "avg_exec_time_s" in sonnet_metrics
    assert sonnet_metrics["avg_exec_time_s"] > 0
    assert "avg_tokens_per_run" in sonnet_metrics
    assert sonnet_metrics["avg_tokens_per_run"] > 0
    assert "total_tokens" in sonnet_metrics
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
        ("lesson-1", "on-skill-complete", "high", "final", "Auth bug fixed", "Bug desc", "Lesson text", "Evidence", "gotchas.yml", (now - timedelta(days=1)).isoformat(), None),
        ("lesson-2", "on-context-threshold", "medium", "draft", "Context overflow", "Desc", "Lesson", "Evidence", None, (now - timedelta(days=2)).isoformat(), None),
        ("lesson-3", "on-skill-complete", "high", "final", "Perf improvement", "Desc", "Lesson", "Evidence", "best_practices.md", (now - timedelta(days=3)).isoformat(), (now - timedelta(days=2)).isoformat()),
        ("lesson-4", "manual", "low", "draft", "Minor issue", "Desc", "Lesson", "Evidence", None, (now - timedelta(days=5)).isoformat(), None),
        ("lesson-5", "on-skill-complete", "medium", "draft", "Old lesson", "Desc", "Lesson", "Evidence", None, (now - timedelta(days=100)).isoformat(), None),  # Too old
    ]

    cursor.executemany("""
        INSERT INTO raw_lessons
        (lesson_id, source, confidence, status, title, what_happened, lesson, evidence, promoted_to, created_at, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, test_data)

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

@pytest.fixture
def test_workflow_db(tmp_path):
    """Create a temporary test database with workflow data"""
    db_path = tmp_path / "test_studio_workflows.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE raw_workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT NOT NULL UNIQUE,
            workflow TEXT NOT NULL,
            yaml_path TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            node_count INTEGER,
            nodes_done INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE raw_workflow_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT NOT NULL REFERENCES raw_workflow_runs(run_key),
            node_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            duration_s REAL,
            output TEXT
        )
    """)

    now = datetime.now()
    workflow_data = [
        ("run-1", "build-pipeline", "/workflows/build.yml", "completed", (now - timedelta(days=1)).isoformat(), (now - timedelta(days=1, hours=-1)).isoformat(), 3, 3),
        ("run-2", "test-suite", "/workflows/test.yml", "completed", (now - timedelta(days=2)).isoformat(), (now - timedelta(days=2, hours=-0.5)).isoformat(), 2, 2),
        ("run-3", "build-pipeline", "/workflows/build.yml", "failed", (now - timedelta(days=3)).isoformat(), (now - timedelta(days=3, hours=-0.8)).isoformat(), 3, 2),
        ("run-4", "deploy", "/workflows/deploy.yml", "completed", (now - timedelta(days=5)).isoformat(), (now - timedelta(days=5, hours=-2)).isoformat(), 4, 4),
        ("run-5", "test-suite", "/workflows/test.yml", "completed", (now - timedelta(days=100)).isoformat(), (now - timedelta(days=100, hours=-0.5)).isoformat(), 2, 2),  # Too old
    ]

    cursor.executemany("""
        INSERT INTO raw_workflow_runs
        (run_key, workflow, yaml_path, status, started_at, finished_at, node_count, nodes_done)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, workflow_data)

    # Add some nodes
    node_data = [
        ("run-1", "compile", "completed", (now - timedelta(days=1)).isoformat(), (now - timedelta(days=1, hours=-0.3)).isoformat(), 18.5, "output1"),
        ("run-1", "test", "completed", (now - timedelta(days=1)).isoformat(), (now - timedelta(days=1, hours=-0.5)).isoformat(), 30.0, "output2"),
        ("run-2", "test", "completed", (now - timedelta(days=2)).isoformat(), (now - timedelta(days=2, hours=-0.5)).isoformat(), 28.0, "output3"),
        ("run-3", "compile", "completed", (now - timedelta(days=3)).isoformat(), (now - timedelta(days=3, hours=-0.3)).isoformat(), 20.0, "output4"),
        ("run-3", "test", "failed", (now - timedelta(days=3)).isoformat(), (now - timedelta(days=3, hours=-0.5)).isoformat(), 15.0, "output5"),
    ]

    cursor.executemany("""
        INSERT INTO raw_workflow_nodes
        (run_key, node_id, status, started_at, finished_at, duration_s, output)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, node_data)

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
