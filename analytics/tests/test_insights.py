"""Unit tests for analytics insights"""
import pytest
from analytics.core.insights.insight_engine import InsightEngine
from analytics.core.insights.root_cause import RootCauseAnalyzer
from analytics.core.insights.recommendations import RecommendationEngine


# InsightEngine tests

def test_insight_engine_initialization():
    """Test InsightEngine can be initialized"""
    engine = InsightEngine()
    assert engine is not None
    assert len(engine.insight_categories) == 4


def test_generate_insights():
    """Test comprehensive insight generation"""
    engine = InsightEngine()

    # Mock metrics and analysis
    metrics = {
        "sessions": {
            "total_sessions": 100,
            "outcomes": {"success": 85, "failed": 15}
        },
        "tokens": {
            "total_tokens": 50000,
            "total_cost_usd": 2.50
        },
        "models": {
            "by_model": {
                "sonnet": {"invocations": 80, "success_rate": 90.0},
                "haiku": {"invocations": 20, "success_rate": 95.0}
            }
        }
    }

    analysis = {
        "performance": {
            "high_performers": ["skill-a", "skill-b"],
            "underperformers": ["skill-c"],
            "improvement_opportunities": [
                {"skill": "skill-c", "success_rate": 60, "count": 10, "recommendation": "Review skill-c"}
            ]
        },
        "trends": {
            "sessions": {
                "trend": "increasing",
                "slope": 2.5,
                "volatility": 10.0
            }
        }
    }

    result = engine.generate_insights(metrics, analysis)

    assert "strengths" in result
    assert "issues" in result
    assert "opportunities" in result
    assert "risks" in result
    assert "summary" in result
    assert "confidence_score" in result

    assert isinstance(result["strengths"], list)
    assert isinstance(result["issues"], list)
    assert 0 <= result["confidence_score"] <= 1


def test_identify_strengths():
    """Test strength identification"""
    engine = InsightEngine()

    metrics = {
        "sessions": {
            "total_sessions": 100,
            "outcomes": {"success": 90, "failed": 10}
        }
    }

    analysis = {
        "performance": {
            "high_performers": ["skill-a", "skill-b", "skill-c"]
        }
    }

    result = engine.generate_insights(metrics, analysis)
    strengths = result["strengths"]

    assert len(strengths) > 0
    # Should identify high performers as a strength
    assert any("high-performing" in s["title"].lower() for s in strengths)


def test_identify_issues():
    """Test issue identification"""
    engine = InsightEngine()

    metrics = {
        "sessions": {
            "total_sessions": 100,
            "outcomes": {"success": 50, "failed": 50}  # Low success rate
        }
    }

    analysis = {
        "performance": {
            "underperformers": ["skill-x", "skill-y"]
        }
    }

    result = engine.generate_insights(metrics, analysis)
    issues = result["issues"]

    assert len(issues) > 0
    # Should identify low success rate
    assert any("success rate" in i["title"].lower() for i in issues)


def test_get_insights_by_category():
    """Test filtering insights by category"""
    engine = InsightEngine()

    metrics = {"sessions": {"total_sessions": 10, "outcomes": {"success": 8, "failed": 2}}}
    analysis = {"performance": {"high_performers": ["skill-a"]}}

    insights = engine.generate_insights(metrics, analysis)

    strengths = engine.get_insights_by_category(insights, "strengths")
    assert isinstance(strengths, list)

    invalid = engine.get_insights_by_category(insights, "invalid")
    assert invalid == []


def test_get_high_priority_insights():
    """Test high priority insight filtering"""
    engine = InsightEngine()

    metrics = {
        "sessions": {
            "total_sessions": 100,
            "outcomes": {"success": 40, "failed": 60}  # Critical quality issue
        }
    }

    analysis = {
        "performance": {
            "high_performers": ["skill-a"],
            "underperformers": ["skill-b", "skill-c"]
        },
        "anomalies": {
            "overall_health": "critical",
            "anomaly_count": 10
        }
    }

    insights = engine.generate_insights(metrics, analysis)
    high_priority = engine.get_high_priority_insights(insights)

    assert len(high_priority) > 0
    # Should include critical issues
    assert any(item.get("severity") in ["critical", "high"] for item in high_priority if item.get("type") == "issue")


# RootCauseAnalyzer tests

def test_root_cause_analyzer_initialization():
    """Test RootCauseAnalyzer can be initialized"""
    analyzer = RootCauseAnalyzer()
    assert analyzer is not None
    assert len(analyzer.patterns) > 0


def test_analyze_skill_performance_issue():
    """Test root cause analysis for skill performance issues"""
    analyzer = RootCauseAnalyzer()

    issue = {
        "category": "skill_performance",
        "title": "Underperforming skills",
        "severity": "high",
        "evidence": {"skills": ["skill-a"]}
    }

    metrics = {
        "models": {
            "by_model": {
                "sonnet": {"invocations": 10, "success_rate": 70.0}
            }
        }
    }

    analysis = {}

    result = analyzer.analyze_issue(issue, metrics, analysis)

    assert "probable_causes" in result
    assert "confidence" in result
    assert "recommendations" in result

    assert len(result["probable_causes"]) > 0
    assert 0 <= result["confidence"] <= 1


def test_analyze_quality_issue():
    """Test root cause analysis for quality issues"""
    analyzer = RootCauseAnalyzer()

    issue = {
        "category": "quality",
        "title": "Low success rate",
        "severity": "critical",
        "evidence": {"success_rate": 40.0, "outcomes": {"success": 40, "failed": 60}}
    }

    metrics = {
        "sessions": {"total_sessions": 100},
        "tokens": {"total_tokens": 1000000}  # Very high
    }

    analysis = {
        "trends": {
            "sessions": {"trend": "decreasing", "slope": -5.0}
        }
    }

    result = analyzer.analyze_issue(issue, metrics, analysis)

    assert len(result["probable_causes"]) > 0
    # Should detect critical failure
    assert any("critical" in c["cause"].lower() or "regression" in c["cause"].lower()
               for c in result["probable_causes"])


def test_analyze_anomaly_issue():
    """Test root cause analysis for anomaly issues"""
    analyzer = RootCauseAnalyzer()

    issue = {
        "category": "anomalies",
        "title": "Anomalies detected",
        "severity": "medium",
        "evidence": {
            "outliers": [
                {"date": "2026-04-03", "value": 100, "direction": "high"}
            ],
            "trend_breaks": [
                {"date": "2026-04-05", "break_type": "reversal"}
            ]
        }
    }

    metrics = {}
    analysis = {}

    result = analyzer.analyze_issue(issue, metrics, analysis)

    assert len(result["probable_causes"]) > 0


# RecommendationEngine tests

def test_recommendation_engine_initialization():
    """Test RecommendationEngine can be initialized"""
    engine = RecommendationEngine()
    assert engine is not None
    assert len(engine.priority_levels) == 4


def test_generate_recommendations():
    """Test recommendation generation"""
    engine = RecommendationEngine()

    insights = {
        "issues": [
            {
                "category": "quality",
                "severity": "high",
                "description": "Low success rate",
                "recommended_action": "Improve error handling"
            }
        ],
        "opportunities": [
            {
                "title": "Optimize skill-a",
                "description": "Can improve performance",
                "potential_impact": "medium"
            }
        ],
        "risks": [
            {
                "category": "cost",
                "risk_level": "medium",
                "mitigation": "Monitor token usage",
                "description": "Cost increasing"
            }
        ]
    }

    result = engine.generate_recommendations(insights)

    assert isinstance(result, list)
    assert len(result) > 0

    # Check recommendation structure
    for rec in result:
        assert "title" in rec
        assert "priority" in rec
        assert "category" in rec


def test_get_quick_wins():
    """Test quick win filtering"""
    engine = RecommendationEngine()

    recommendations = [
        {
            "title": "Quick fix",
            "category": "optimize",
            "priority": "medium",
            "impact": "Potential high impact improvement",
            "effort": "low"
        },
        {
            "title": "Long project",
            "category": "fix",
            "priority": "high",
            "impact": "Resolves critical severity issue",
            "effort": "high"
        }
    ]

    quick_wins = engine.get_quick_wins(recommendations)

    assert len(quick_wins) > 0
    # All should be low effort
    assert all(qw["effort"] == "low" for qw in quick_wins)


def test_format_for_executive():
    """Test executive summary formatting"""
    engine = RecommendationEngine()

    recommendations = [
        {
            "title": "Fix critical bug",
            "category": "fix",
            "priority": "critical",
            "impact": "Resolves critical severity issue",
            "effort": "medium",
            "details": "System failing"
        }
    ]

    result = engine.format_for_executive(recommendations, limit=5)

    assert isinstance(result, str)
    assert "CRITICAL" in result
    assert "Fix critical bug" in result


def test_group_by_category():
    """Test grouping recommendations by category"""
    engine = RecommendationEngine()

    recommendations = [
        {"title": "Fix A", "category": "fix"},
        {"title": "Optimize B", "category": "optimize"},
        {"title": "Fix C", "category": "fix"}
    ]

    grouped = engine.group_by_category(recommendations)

    assert "fix" in grouped
    assert "optimize" in grouped
    assert len(grouped["fix"]) == 2
    assert len(grouped["optimize"]) == 1


def test_recommendation_prioritization():
    """Test that recommendations are prioritized correctly"""
    engine = RecommendationEngine()

    insights = {
        "issues": [
            {
                "category": "quality",
                "severity": "critical",
                "recommended_action": "Critical fix"
            },
            {
                "category": "quality",
                "severity": "low",
                "recommended_action": "Minor improvement"
            }
        ],
        "opportunities": [],
        "risks": []
    }

    result = engine.generate_recommendations(insights)

    # Critical should come first
    assert result[0]["priority"] == "critical"
