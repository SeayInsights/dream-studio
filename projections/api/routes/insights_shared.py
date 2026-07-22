"""Cross-cutting helpers used by 3+ insights route groups.

WO-GF-API-ROUTES: split out of insights.py.
"""

from __future__ import annotations

from projections.core.analyzers import (
    PerformanceAnalyzer,
    TrendAnalyzer,
    AnomalyDetector,
    Predictor,
)
from projections.core.collectors import (
    SessionCollector,
    SkillCollector,
    TokenCollector,
    ModelCollector,
    LessonCollector,
    WorkflowCollector,
)


def get_db_path() -> str:
    """Get database path"""
    from core.config.database import get_db_path as _canonical

    return str(_canonical())


def collect_metrics(days: int = 30):
    """Collect all metrics"""
    db_path = get_db_path()

    collectors = {
        "sessions": SessionCollector(db_path),
        "skills": SkillCollector(db_path),
        "tokens": TokenCollector(db_path),
        "models": ModelCollector(db_path),
        "lessons": LessonCollector(db_path),
        "workflows": WorkflowCollector(db_path),
    }

    metrics = {key: collector.collect(days=days) for key, collector in collectors.items()}

    return metrics


def analyze_metrics(metrics: dict):
    """Run all analyzers on metrics"""
    perf_analyzer = PerformanceAnalyzer()
    trend_analyzer = TrendAnalyzer()
    anomaly_detector = AnomalyDetector()
    predictor = Predictor()

    analysis = {}

    # Performance analysis
    if "skills" in metrics:
        analysis["performance"] = perf_analyzer.analyze_skill_performance(metrics["skills"])

    # Trend analysis
    if "sessions" in metrics and "timeline" in metrics["sessions"]:
        analysis["trends"] = {
            "sessions": trend_analyzer.analyze_timeline(metrics["sessions"]["timeline"])
        }

    # Anomaly detection
    if "sessions" in metrics and "timeline" in metrics["sessions"]:
        anomaly_results = anomaly_detector.comprehensive_anomaly_scan(
            metrics["sessions"]["timeline"]
        )
        analysis["anomalies"] = anomaly_results

    # Forecasting
    if "sessions" in metrics and "timeline" in metrics["sessions"]:
        forecast = predictor.forecast_linear(metrics["sessions"]["timeline"], steps_ahead=7)
        analysis["forecast"] = forecast

    return analysis
