"""Unit tests for analytics analyzers"""
import pytest
from datetime import datetime, timedelta
from analytics.core.analyzers.performance_analyzer import PerformanceAnalyzer
from analytics.core.analyzers.trend_analyzer import TrendAnalyzer


# PerformanceAnalyzer tests

def test_performance_analyzer_initialization():
    """Test PerformanceAnalyzer can be initialized"""
    analyzer = PerformanceAnalyzer()
    assert analyzer is not None


def test_analyze_skill_performance():
    """Test skill performance analysis"""
    analyzer = PerformanceAnalyzer()

    skill_metrics = {
        "by_skill": {
            "high-perf-skill": {"success_rate": 95.0, "count": 10, "avg_exec_time_s": 5.0},
            "low-perf-skill": {"success_rate": 60.0, "count": 8, "avg_exec_time_s": 10.0},
            "medium-skill": {"success_rate": 85.0, "count": 5, "avg_exec_time_s": 7.0}
        }
    }

    result = analyzer.analyze_skill_performance(skill_metrics)

    assert "high_performers" in result
    assert "underperformers" in result
    assert "efficiency_scores" in result
    assert "improvement_opportunities" in result

    assert "high-perf-skill" in result["high_performers"]
    assert "low-perf-skill" in result["underperformers"]
    assert len(result["improvement_opportunities"]) > 0


def test_analyze_model_efficiency():
    """Test model efficiency analysis"""
    analyzer = PerformanceAnalyzer()

    model_metrics = {
        "by_model": {
            "sonnet": {"invocations": 10, "success_rate": 90.0},
            "haiku": {"invocations": 5, "success_rate": 95.0}
        }
    }

    token_metrics = {
        "by_model": {
            "sonnet": {"cost_usd": 1.50, "total_tokens": 50000},
            "haiku": {"cost_usd": 0.40, "total_tokens": 25000}
        }
    }

    result = analyzer.analyze_model_efficiency(model_metrics, token_metrics)

    assert "cost_per_invocation" in result
    assert "tokens_per_dollar" in result
    assert "roi_scores" in result
    assert "recommendations" in result


def test_analyze_session_health():
    """Test session health analysis"""
    analyzer = PerformanceAnalyzer()

    session_metrics = {
        "total_sessions": 100,
        "outcomes": {"success": 80, "failed": 20},
        "avg_duration_minutes": 45.0,
        "by_project": {"project-a": 60, "project-b": 40}
    }

    result = analyzer.analyze_session_health(session_metrics)

    assert "productivity_score" in result
    assert "avg_sessions_per_day" in result
    assert "health_status" in result
    assert "recommendations" in result

    assert result["health_status"] in ["healthy", "warning", "critical"]
    assert 0 <= result["productivity_score"] <= 100


def test_compare_periods():
    """Test period comparison"""
    analyzer = PerformanceAnalyzer()

    current = {"total_sessions": 120, "total_invocations": 500}
    previous = {"total_sessions": 100, "total_invocations": 400}

    result = analyzer.compare_periods(current, previous)

    assert "total_sessions_change_pct" in result
    assert "total_invocations_change_pct" in result
    assert result["total_sessions_change_pct"] == 20.0  # 20% increase


# TrendAnalyzer tests

def test_trend_analyzer_initialization():
    """Test TrendAnalyzer can be initialized"""
    analyzer = TrendAnalyzer()
    assert analyzer is not None


def test_analyze_timeline_increasing():
    """Test timeline analysis with increasing trend"""
    analyzer = TrendAnalyzer()

    timeline = [
        {"date": "2026-04-01", "count": 10},
        {"date": "2026-04-02", "count": 12},
        {"date": "2026-04-03", "count": 15},
        {"date": "2026-04-04", "count": 18},
        {"date": "2026-04-05", "count": 20}
    ]

    result = analyzer.analyze_timeline(timeline)

    assert "trend" in result
    assert "slope" in result
    assert "volatility" in result
    assert "average" in result
    assert "peak_date" in result

    assert result["trend"] == "increasing"
    assert result["slope"] > 0


def test_analyze_timeline_decreasing():
    """Test timeline analysis with decreasing trend"""
    analyzer = TrendAnalyzer()

    timeline = [
        {"date": "2026-04-01", "count": 20},
        {"date": "2026-04-02", "count": 18},
        {"date": "2026-04-03", "count": 15},
        {"date": "2026-04-04", "count": 12},
        {"date": "2026-04-05", "count": 10}
    ]

    result = analyzer.analyze_timeline(timeline)

    assert result["trend"] == "decreasing"
    assert result["slope"] < 0


def test_analyze_timeline_stable():
    """Test timeline analysis with stable trend"""
    analyzer = TrendAnalyzer()

    timeline = [
        {"date": "2026-04-01", "count": 10},
        {"date": "2026-04-02", "count": 11},
        {"date": "2026-04-03", "count": 10},
        {"date": "2026-04-04", "count": 10},
        {"date": "2026-04-05", "count": 11}
    ]

    result = analyzer.analyze_timeline(timeline)

    assert result["trend"] == "stable"


def test_detect_seasonality():
    """Test seasonality detection"""
    analyzer = TrendAnalyzer()

    # Create data with weekly pattern (higher on weekdays)
    now = datetime(2026, 4, 7)  # Monday
    timeline = []

    for i in range(14):  # 2 weeks
        date = now + timedelta(days=i)
        # Weekdays (0-4) have higher values
        count = 20 if date.weekday() < 5 else 5

        timeline.append({
            "date": date.isoformat(),
            "count": count
        })

    result = analyzer.detect_seasonality(timeline)

    assert "has_weekly_pattern" in result
    assert "day_of_week_strength" in result
    assert "strongest_day" in result

    # Should detect pattern
    assert result["has_weekly_pattern"] is True


def test_identify_growth_rate():
    """Test growth rate identification"""
    analyzer = TrendAnalyzer()

    timeline = [
        {"date": f"2026-04-{str(i+1).zfill(2)}", "count": 10 + i * 2}
        for i in range(14)
    ]

    result = analyzer.identify_growth_rate(timeline, window_days=7)

    assert "growth_rate_pct" in result
    assert "acceleration" in result
    assert "forecast_next_period" in result

    assert result["growth_rate_pct"] > 0  # Should show growth


def test_detect_anomalies():
    """Test anomaly detection"""
    analyzer = TrendAnalyzer()

    timeline = [
        {"date": "2026-04-01", "count": 10},
        {"date": "2026-04-02", "count": 11},
        {"date": "2026-04-03", "count": 50},  # Anomaly - spike
        {"date": "2026-04-04", "count": 10},
        {"date": "2026-04-05", "count": 11},
        {"date": "2026-04-06", "count": 10}
    ]

    result = analyzer.detect_anomalies_simple(timeline)

    assert isinstance(result, list)
    assert len(result) >= 1  # Should find at least the spike
    assert result[0]["direction"] in ["high", "low"]
    assert result[0]["value"] == 50  # Spike should be first anomaly


def test_analyze_timeline_insufficient_data():
    """Test timeline analysis with insufficient data"""
    analyzer = TrendAnalyzer()

    timeline = [{"date": "2026-04-01", "count": 10}]

    result = analyzer.analyze_timeline(timeline)

    assert result["trend"] == "insufficient_data"


def test_detect_seasonality_insufficient_data():
    """Test seasonality with insufficient data"""
    analyzer = TrendAnalyzer()

    timeline = []

    result = analyzer.detect_seasonality(timeline)

    assert result["has_weekly_pattern"] is False
