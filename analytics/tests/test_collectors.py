"""Unit tests for analytics collectors"""
import pytest
import sqlite3
from datetime import datetime, timedelta
from analytics.core.collectors.session_collector import SessionCollector


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
