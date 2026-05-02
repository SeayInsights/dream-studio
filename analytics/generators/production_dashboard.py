"""Production Dashboard Generator - Creates beautiful, interactive analytics dashboards"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from analytics.core.collectors import (
    SessionCollector,
    SkillCollector,
    TokenCollector,
    ModelCollector,
    LessonCollector,
    WorkflowCollector
)
from analytics.core.analyzers import (
    PerformanceAnalyzer,
    TrendAnalyzer,
    AnomalyDetector,
    Predictor
)
from analytics.core.insights import (
    InsightEngine,
    RecommendationEngine
)
from analytics.ml.forecasting import TimeSeriesForecaster
from analytics.ml.patterns import PatternDetector
from analytics.ml.recommendations import RecommendationEngine as MLRecommendationEngine
from analytics.ml.benchmarks import BenchmarkEngine


class ProductionDashboard:
    """Generates production-ready analytics dashboard"""

    def __init__(self, db_path: str | None = None):
        """
        Initialize dashboard generator

        Args:
            db_path: Path to studio.db (defaults to ~/.dream-studio/studio.db)
        """
        import os
        self.db_path = db_path or os.path.expanduser("~/.dream-studio/studio.db")

    def generate(self, days: int = 30, output_path: str = "analytics_dashboard.html") -> str:
        """
        Generate complete dashboard

        Args:
            days: Number of days to analyze
            output_path: Where to save the HTML file

        Returns:
            Path to generated dashboard
        """
        print(f"[Dashboard] Generating analytics dashboard for last {days} days...")

        # Collect all data
        print("  -> Collecting metrics...")
        metrics = self._collect_metrics(days)

        print("  -> Running analysis...")
        analysis = self._analyze_metrics(metrics)

        print("  -> Generating insights...")
        insights = self._generate_insights(metrics, analysis)

        print("  -> Running ML analysis...")
        ml_insights = self._generate_ml_insights(metrics, days)

        print("  -> Creating visualizations...")
        charts = self._generate_charts(metrics, analysis)

        print("  -> Creating ML visualizations...")
        ml_charts = self._generate_ml_charts(ml_insights)

        print("  -> Building dashboard...")
        html = self._build_html(metrics, analysis, insights, charts, ml_insights, ml_charts)

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"[SUCCESS] Dashboard generated: {output_path}")
        return output_path

    def _collect_metrics(self, days: int) -> Dict[str, Any]:
        """Collect all metrics"""
        collectors = {
            "sessions": SessionCollector(self.db_path),
            "skills": SkillCollector(self.db_path),
            "tokens": TokenCollector(self.db_path),
            "models": ModelCollector(self.db_path),
            "lessons": LessonCollector(self.db_path),
            "workflows": WorkflowCollector(self.db_path)
        }

        return {
            name: collector.collect(days=days)
            for name, collector in collectors.items()
        }

    def _analyze_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Run all analyzers"""
        perf = PerformanceAnalyzer()
        trend = TrendAnalyzer()
        anomaly = AnomalyDetector()
        predictor = Predictor()

        analysis = {}

        # Performance analysis
        if "skills" in metrics:
            analysis["skill_performance"] = perf.analyze_skill_performance(metrics["skills"])

        if "models" in metrics and "tokens" in metrics:
            analysis["model_efficiency"] = perf.analyze_model_efficiency(
                metrics["models"], metrics["tokens"]
            )

        if "sessions" in metrics:
            analysis["session_health"] = perf.analyze_session_health(metrics["sessions"])

        # Trend analysis
        if "sessions" in metrics and metrics["sessions"].get("timeline"):
            timeline = metrics["sessions"]["timeline"]
            analysis["session_trends"] = trend.analyze_timeline(timeline)
            analysis["session_forecast"] = predictor.forecast_linear(timeline, steps_ahead=7)

        # Anomaly detection
        if "sessions" in metrics and metrics["sessions"].get("timeline"):
            analysis["anomalies"] = anomaly.comprehensive_anomaly_scan(
                metrics["sessions"]["timeline"]
            )

        return analysis

    def _generate_insights(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate insights and recommendations"""
        engine = InsightEngine()
        insights = engine.generate_insights(metrics, analysis)

        rec_engine = RecommendationEngine()
        recommendations = rec_engine.generate_recommendations(insights)

        return {
            "insights": insights,
            "recommendations": recommendations
        }

    def _generate_ml_insights(self, metrics: Dict[str, Any], days: int) -> Dict[str, Any]:
        """
        Generate ML-powered insights

        Args:
            metrics: Collected metrics
            days: Number of days analyzed

        Returns:
            Dict containing ML insights (forecasts, patterns, recommendations, benchmarks)
        """
        ml_insights: Dict[str, Any] = {
            "forecasts": None,
            "patterns": None,
            "recommendations": None,
            "benchmarks": None
        }

        try:
            import pandas as pd
        except ImportError:
            print("  [WARNING] pandas not available, skipping ML insights")
            return ml_insights

        # Generate forecasts
        try:
            timeline = metrics.get("sessions", {}).get("timeline", [])
            if timeline and len(timeline) >= 14:
                df = pd.DataFrame(timeline)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")[["count"]].rename(columns={"count": "value"})

                forecaster = TimeSeriesForecaster(method='auto')
                forecaster.fit(df)
                forecast_result = forecaster.forecast(steps=7)
                ml_insights["forecasts"] = forecast_result
        except Exception as e:
            print(f"  [WARNING] Forecast generation failed: {e}")

        # Detect patterns
        try:
            skill_data = metrics.get("skills", {})
            if "invocations" in skill_data and len(skill_data["invocations"]) >= 3:
                telemetry = pd.DataFrame(skill_data["invocations"])
                if all(col in telemetry.columns for col in ["session_id", "skill_name", "invoked_at"]):
                    detector = PatternDetector(min_support=3)
                    detector.fit(telemetry[["session_id", "skill_name", "invoked_at"]])
                    patterns = detector.get_patterns()
                    ml_insights["patterns"] = patterns[:10]  # Top 10 patterns
        except Exception as e:
            print(f"  [WARNING] Pattern detection failed: {e}")

        # Generate ML recommendations
        try:
            skill_data = metrics.get("skills", {})
            session_data = metrics.get("sessions", {})

            if ("invocations" in skill_data and len(skill_data["invocations"]) >= 20 and
                "sessions" in session_data and len(session_data["sessions"]) >= 20):

                telemetry = pd.DataFrame(skill_data["invocations"])
                sessions = pd.DataFrame(session_data["sessions"])

                # Ensure required columns
                if "session_id" not in sessions.columns:
                    sessions["session_id"] = range(len(sessions))
                if "duration" not in sessions.columns:
                    sessions["duration"] = 0
                if "tokens" not in sessions.columns:
                    sessions["tokens"] = 0
                if "outcome" not in sessions.columns:
                    sessions["outcome"] = "success"

                engine = MLRecommendationEngine(min_support=3)
                engine.fit(telemetry, sessions)
                recs = engine.get_recommendations(min_impact=30)
                ml_insights["recommendations"] = recs[:5]  # Top 5 by impact
        except Exception as e:
            print(f"  [WARNING] ML recommendations failed: {e}")

        # Generate benchmarks
        try:
            timeline = metrics.get("sessions", {}).get("timeline", [])
            if timeline and len(timeline) >= 14:
                df = pd.DataFrame(timeline)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")[["count"]].rename(columns={"count": "sessions"})

                # Add other metrics if available
                token_timeline = metrics.get("tokens", {}).get("timeline", [])
                if token_timeline and len(token_timeline) >= 14:
                    token_df = pd.DataFrame(token_timeline)
                    token_df["date"] = pd.to_datetime(token_df["date"])
                    token_df = token_df.set_index("date")[["total"]].rename(columns={"total": "tokens"})
                    df = df.join(token_df, how="outer")

                engine = BenchmarkEngine()
                engine.fit(df)

                # Get current values (last 7 days average)
                current_sessions = df["sessions"].tail(7).mean() if "sessions" in df else 0
                benchmarks = []

                if current_sessions > 0:
                    benchmark = engine.benchmark_metric("sessions", current_sessions)
                    benchmarks.append(benchmark)

                if "tokens" in df:
                    current_tokens = df["tokens"].tail(7).mean()
                    if current_tokens > 0:
                        benchmark = engine.benchmark_metric("tokens", current_tokens)
                        benchmarks.append(benchmark)

                ml_insights["benchmarks"] = benchmarks
        except Exception as e:
            print(f"  [WARNING] Benchmark generation failed: {e}")

        return ml_insights

    def _generate_charts(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate chart data for JavaScript rendering"""
        charts = {}

        # Session timeline chart
        if "sessions" in metrics and metrics["sessions"].get("timeline"):
            timeline = metrics["sessions"]["timeline"]
            charts["session_timeline"] = {
                "type": "line",
                "title": "Session Activity Over Time",
                "data": {
                    "labels": [t["date"] for t in timeline],
                    "datasets": [{
                        "label": "Sessions",
                        "data": [t["count"] for t in timeline],
                        "borderColor": "rgb(59, 130, 246)",
                        "tension": 0.4
                    }]
                }
            }

        # Skills distribution
        if "skills" in metrics and metrics["skills"].get("by_skill"):
            skills = metrics["skills"]["by_skill"]
            top_skills = sorted(skills.items(), key=lambda x: x[1]["count"], reverse=True)[:10]

            charts["top_skills"] = {
                "type": "bar",
                "title": "Top 10 Skills by Usage",
                "data": {
                    "labels": [s[0] for s in top_skills],
                    "datasets": [{
                        "label": "Invocations",
                        "data": [s[1]["count"] for s in top_skills],
                        "backgroundColor": "rgba(59, 130, 246, 0.5)"
                    }]
                }
            }

        # Model distribution
        if "models" in metrics and metrics["models"].get("distribution_pct"):
            dist = metrics["models"]["distribution_pct"]
            charts["model_distribution"] = {
                "type": "doughnut",
                "title": "Model Usage Distribution",
                "data": {
                    "labels": list(dist.keys()),
                    "datasets": [{
                        "data": list(dist.values()),
                        "backgroundColor": [
                            "rgba(59, 130, 246, 0.8)",
                            "rgba(16, 185, 129, 0.8)",
                            "rgba(245, 158, 11, 0.8)"
                        ]
                    }]
                }
            }

        # Token cost over time
        if "tokens" in metrics and metrics["tokens"].get("timeline"):
            timeline = metrics["tokens"]["timeline"]
            charts["token_cost"] = {
                "type": "line",
                "title": "Token Cost Over Time",
                "data": {
                    "labels": [t["date"] for t in timeline],
                    "datasets": [{
                        "label": "Cost (USD)",
                        "data": [t.get("cost_usd", 0) for t in timeline],
                        "borderColor": "rgb(245, 158, 11)",
                        "tension": 0.4
                    }]
                }
            }

        return charts

    def _generate_ml_charts(self, ml_insights: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate ML-powered chart data for JavaScript rendering

        Args:
            ml_insights: ML insights from _generate_ml_insights()

        Returns:
            Dict of chart configurations for Chart.js
        """
        charts = {}

        # Forecast chart (predicted vs actual)
        if ml_insights.get("forecasts"):
            forecast_data = ml_insights["forecasts"]
            forecast_points = forecast_data.get("forecast", [])

            if forecast_points:
                charts["ml_forecast"] = {
                    "type": "line",
                    "title": "7-Day Forecast (ML Prediction)",
                    "data": {
                        "labels": [p["date"] for p in forecast_points],
                        "datasets": [
                            {
                                "label": "Predicted Sessions",
                                "data": [p["value"] for p in forecast_points],
                                "borderColor": "rgb(139, 92, 246)",
                                "backgroundColor": "rgba(139, 92, 246, 0.1)",
                                "tension": 0.4,
                                "fill": True
                            }
                        ]
                    },
                    "confidence": forecast_data.get("method", "unknown")
                }

                # Add confidence bands if available
                if all("lower_bound" in p and "upper_bound" in p for p in forecast_points):
                    charts["ml_forecast"]["data"]["datasets"].extend([
                        {
                            "label": "Upper Bound",
                            "data": [p.get("upper_bound") for p in forecast_points],
                            "borderColor": "rgba(139, 92, 246, 0.3)",
                            "borderDash": [5, 5],
                            "tension": 0.4,
                            "fill": False,
                            "pointRadius": 0
                        },
                        {
                            "label": "Lower Bound",
                            "data": [p.get("lower_bound") for p in forecast_points],
                            "borderColor": "rgba(139, 92, 246, 0.3)",
                            "borderDash": [5, 5],
                            "tension": 0.4,
                            "fill": False,
                            "pointRadius": 0
                        }
                    ])

        # Pattern visualization (top 10 patterns)
        if ml_insights.get("patterns"):
            patterns = ml_insights["patterns"][:10]
            if patterns:
                charts["ml_patterns"] = {
                    "type": "bar",
                    "title": "Top 10 Detected Patterns",
                    "data": {
                        "labels": [p.get("pattern", "Unknown")[:30] for p in patterns],
                        "datasets": [{
                            "label": "Support Count",
                            "data": [p.get("support", 0) for p in patterns],
                            "backgroundColor": "rgba(16, 185, 129, 0.6)",
                            "borderColor": "rgb(16, 185, 129)",
                            "borderWidth": 1
                        }]
                    }
                }

        # Benchmark comparisons (current vs historical)
        if ml_insights.get("benchmarks"):
            benchmarks = ml_insights["benchmarks"]
            if benchmarks:
                charts["ml_benchmarks"] = {
                    "type": "bar",
                    "title": "Performance vs Baseline",
                    "data": {
                        "labels": [b.get("metric", "Unknown").title() for b in benchmarks],
                        "datasets": [
                            {
                                "label": "Current Value",
                                "data": [b.get("current_value", 0) for b in benchmarks],
                                "backgroundColor": "rgba(59, 130, 246, 0.6)",
                                "borderColor": "rgb(59, 130, 246)",
                                "borderWidth": 1
                            },
                            {
                                "label": "Historical Baseline",
                                "data": [b.get("baseline", 0) for b in benchmarks],
                                "backgroundColor": "rgba(156, 163, 175, 0.6)",
                                "borderColor": "rgb(156, 163, 175)",
                                "borderWidth": 1
                            }
                        ]
                    }
                }

        return charts

    def _build_html(
        self,
        metrics: Dict[str, Any],
        analysis: Dict[str, Any],
        insights: Dict[str, Any],
        charts: Dict[str, Any],
        ml_insights: Dict[str, Any],
        ml_charts: Dict[str, Any]
    ) -> str:
        """
        Build complete HTML dashboard

        Args:
            metrics: Collected metrics
            analysis: Analysis results
            insights: Generated insights
            charts: Chart configurations
            ml_insights: ML-powered insights
            ml_charts: ML chart configurations

        Returns:
            Complete HTML dashboard as string
        """

        # Extract key metrics
        total_sessions = metrics.get("sessions", {}).get("total_sessions", 0)
        total_tokens = metrics.get("tokens", {}).get("total_tokens", 0)
        total_cost = metrics.get("tokens", {}).get("total_cost_usd", 0)
        success_rate = metrics.get("sessions", {}).get("outcomes", {}).get("success", 0)

        # Get insights
        all_insights = insights.get("insights", {})
        strengths = all_insights.get("strengths", [])
        issues = all_insights.get("issues", [])
        recommendations = insights.get("recommendations", [])

        # Get ML insights
        ml_recommendations = ml_insights.get("recommendations", [])
        ml_patterns = ml_insights.get("patterns", [])
        ml_benchmarks = ml_insights.get("benchmarks", [])
        has_ml_data = any([ml_insights.get("forecasts"), ml_patterns, ml_recommendations, ml_benchmarks])

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dream-Studio Analytics Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            background: white;
            border-radius: 1rem;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}

        h1 {{
            font-size: 2.5rem;
            color: #1a202c;
            margin-bottom: 0.5rem;
        }}

        .subtitle {{
            color: #718096;
            font-size: 1.1rem;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .metric-card {{
            background: white;
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}

        .metric-label {{
            color: #718096;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }}

        .metric-value {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #1a202c;
        }}

        .metric-change {{
            font-size: 0.875rem;
            color: #10b981;
            margin-top: 0.5rem;
        }}

        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 2rem;
            margin-bottom: 2rem;
        }}

        .chart-card {{
            background: white;
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}

        .chart-title {{
            font-size: 1.25rem;
            font-weight: 600;
            color: #1a202c;
            margin-bottom: 1rem;
        }}

        .insights-section {{
            background: white;
            border-radius: 1rem;
            padding: 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            margin-bottom: 2rem;
        }}

        .section-title {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #1a202c;
            margin-bottom: 1.5rem;
        }}

        .insight-item {{
            padding: 1rem;
            border-left: 4px solid #3b82f6;
            background: #f8fafc;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }}

        .insight-item.issue {{
            border-left-color: #ef4444;
        }}

        .insight-item.strength {{
            border-left-color: #10b981;
        }}

        .insight-title {{
            font-weight: 600;
            color: #1a202c;
            margin-bottom: 0.5rem;
        }}

        .insight-description {{
            color: #64748b;
            font-size: 0.9rem;
        }}

        .recommendations {{
            list-style: none;
        }}

        .recommendation {{
            padding: 1rem;
            background: #f8fafc;
            border-radius: 0.5rem;
            margin-bottom: 0.75rem;
            border-left: 4px solid #f59e0b;
        }}

        .priority-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .priority-critical {{
            background: #fee2e2;
            color: #991b1b;
        }}

        .priority-high {{
            background: #fef3c7;
            color: #92400e;
        }}

        .priority-medium {{
            background: #dbeafe;
            color: #1e40af;
        }}

        .confidence-indicator {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }}

        .confidence-bar {{
            height: 6px;
            width: 100px;
            background: #e5e7eb;
            border-radius: 3px;
            overflow: hidden;
        }}

        .confidence-fill {{
            height: 100%;
            background: linear-gradient(90deg, #f59e0b 0%, #10b981 100%);
            transition: width 0.3s ease;
        }}

        .ml-recommendation {{
            padding: 1rem;
            background: #f0f9ff;
            border-radius: 0.5rem;
            margin-bottom: 0.75rem;
            border-left: 4px solid #8b5cf6;
        }}

        .impact-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            background: #dbeafe;
            color: #1e40af;
        }}

        .pattern-item {{
            padding: 0.75rem;
            background: #f0fdf4;
            border-radius: 0.5rem;
            margin-bottom: 0.5rem;
            border-left: 3px solid #10b981;
        }}

        .benchmark-item {{
            padding: 1rem;
            background: #fefce8;
            border-radius: 0.5rem;
            margin-bottom: 0.75rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .trend-badge {{
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .trend-improving {{
            background: #d1fae5;
            color: #065f46;
        }}

        .trend-stable {{
            background: #e0e7ff;
            color: #3730a3;
        }}

        .trend-declining {{
            background: #fee2e2;
            color: #991b1b;
        }}

        .no-ml-data {{
            padding: 2rem;
            text-align: center;
            color: #64748b;
            font-style: italic;
        }}

        .export-buttons {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .export-buttons button {{
            padding: 10px 20px;
            font-size: 14px;
            border: none;
            border-radius: 4px;
            background: #3498db;
            color: white;
            cursor: pointer;
            transition: background 0.2s;
        }}

        .export-buttons button:hover {{
            background: #2980b9;
        }}

        .report-form {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}

        .report-form h3 {{
            margin-top: 0;
            margin-bottom: 15px;
            color: #1a202c;
        }}

        .report-form label {{
            display: block;
            margin-top: 10px;
            font-weight: bold;
            color: #4a5568;
        }}

        .report-form input, .report-form select {{
            width: 100%;
            padding: 8px;
            margin-top: 5px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-family: inherit;
        }}

        .report-form button {{
            margin-top: 15px;
            padding: 10px 20px;
            background: #10b981;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
        }}

        .report-form button:hover {{
            background: #059669;
        }}

        .schedule-section {{
            background: #f0f9ff;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}

        .schedule-section h3 {{
            margin-top: 0;
            margin-bottom: 15px;
            color: #1a202c;
        }}

        .schedule-section table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 4px;
            overflow: hidden;
        }}

        .schedule-section th {{
            background: #3b82f6;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}

        .schedule-section td {{
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }}

        .schedule-section tr:last-child td {{
            border-bottom: none;
        }}

        .schedule-section button {{
            padding: 6px 12px;
            margin-right: 5px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }}

        .schedule-section button:first-of-type {{
            background: #f59e0b;
            color: white;
        }}

        .schedule-section button:last-of-type {{
            background: #ef4444;
            color: white;
        }}

        .reports-list {{
            background: #fefce8;
            padding: 20px;
            border-radius: 8px;
        }}

        .reports-list h3 {{
            margin-top: 0;
            margin-bottom: 15px;
            color: #1a202c;
        }}

        .report-item {{
            background: white;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .report-item-info {{
            flex: 1;
        }}

        .report-item-info strong {{
            display: block;
            color: #1a202c;
            margin-bottom: 5px;
        }}

        .report-item-info small {{
            color: #64748b;
        }}

        .report-item button {{
            padding: 6px 12px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }}

        footer {{
            text-align: center;
            color: white;
            margin-top: 3rem;
            opacity: 0.9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 Dream-Studio Analytics</h1>
            <p class="subtitle">Enterprise AI Agent Performance Dashboard · Generated {datetime.now().strftime("%B %d, %Y at %I:%M %p")}</p>
        </header>

        <!-- Key Metrics -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Total Sessions</div>
                <div class="metric-value">{total_sessions:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Success Rate</div>
                <div class="metric-value">{success_rate}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Tokens</div>
                <div class="metric-value">{total_tokens:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Cost</div>
                <div class="metric-value">${total_cost:.2f}</div>
            </div>
        </div>

        <!-- Charts -->
        <div class="charts-grid">
"""

        # Add chart canvases
        for chart_id, chart in charts.items():
            html += f"""
            <div class="chart-card">
                <div class="chart-title">{chart['title']}</div>
                <canvas id="{chart_id}"></canvas>
            </div>
"""

        html += """
        </div>

        <!-- Insights -->
        <div class="insights-section">
            <h2 class="section-title">💡 Key Insights</h2>
"""

        # Add strengths
        if strengths:
            html += "<h3 style='color: #10b981; margin-bottom: 1rem;'>✅ Strengths</h3>"
            for strength in strengths[:3]:
                html += f"""
            <div class="insight-item strength">
                <div class="insight-title">{strength.get('title', 'Strength')}</div>
                <div class="insight-description">{strength.get('description', '')}</div>
            </div>
"""

        # Add issues
        if issues:
            html += "<h3 style='color: #ef4444; margin: 1.5rem 0 1rem;'>[WARNING] Issues</h3>"
            for issue in issues[:3]:
                html += f"""
            <div class="insight-item issue">
                <div class="insight-title">{issue.get('title', 'Issue')}</div>
                <div class="insight-description">{issue.get('description', '')}</div>
            </div>
"""

        html += """
        </div>

        <!-- Recommendations -->
        <div class="insights-section">
            <h2 class="section-title">📋 Top Recommendations</h2>
            <ul class="recommendations">
"""

        for rec in recommendations[:5]:
            priority = rec.get('priority', 'medium')
            html += f"""
                <li class="recommendation">
                    <span class="priority-badge priority-{priority}">{priority}</span>
                    <div style="margin-top: 0.5rem;">
                        <strong>{rec.get('title', 'Recommendation')}</strong><br>
                        <small style="color: #64748b;">{rec.get('impact', '')} · Effort: {rec.get('effort', 'medium')}</small>
                    </div>
                </li>
"""

        html += f"""
            </ul>
        </div>

        <!-- Export & Reports Section -->
        <div class="insights-section">
            <h2 class="section-title">📊 Export & Reports</h2>

            <!-- Quick Export Buttons -->
            <div class="export-buttons">
                <button onclick="exportReport('pdf')">📄 Export PDF</button>
                <button onclick="exportReport('excel')">📊 Export Excel</button>
                <button onclick="exportReport('pptx')">📽️ Export PowerPoint</button>
                <button onclick="exportReport('csv')">📑 Export CSV</button>
                <button onclick="exportReport('powerbi')">📈 Power BI Dataset</button>
            </div>

            <!-- Report Generation Form -->
            <div class="report-form">
                <h3>Generate Custom Report</h3>
                <label>Report Type:</label>
                <select id="reportType">
                    <option value="summary">Summary</option>
                    <option value="detailed">Detailed</option>
                    <option value="executive">Executive</option>
                </select>

                <label>Date Range:</label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <input type="date" id="startDate" placeholder="Start Date">
                    <input type="date" id="endDate" placeholder="End Date">
                </div>

                <label>Template:</label>
                <select id="template">
                    <option value="default">Default</option>
                    <option value="executive">Executive</option>
                    <option value="technical">Technical</option>
                </select>

                <label>Format:</label>
                <select id="exportFormat">
                    <option value="pdf">PDF</option>
                    <option value="excel">Excel</option>
                    <option value="pptx">PowerPoint</option>
                </select>

                <button onclick="generateCustomReport()">Generate Report</button>
            </div>

            <!-- Schedule Management -->
            <div class="schedule-section">
                <h3>Scheduled Reports</h3>
                <table id="schedulesTable">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Schedule</th>
                            <th>Next Run</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td colspan="5" style="text-align: center; color: #64748b; padding: 20px;">
                                No scheduled reports. Create one to get started!
                            </td>
                        </tr>
                    </tbody>
                </table>
                <button onclick="showScheduleForm()" style="margin-top: 10px; padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer;">+ New Schedule</button>
            </div>

            <!-- Generated Reports List -->
            <div class="reports-list">
                <h3>Recent Reports</h3>
                <div id="reportsList">
                    <p style="text-align: center; color: #64748b;">No reports generated yet. Use the buttons above to create one!</p>
                </div>
            </div>
        </div>
"""

        # Add ML Insights Section
        if has_ml_data:
            html += """
        <!-- ML Insights Section -->
        <div class="insights-section">
            <h2 class="section-title">🤖 ML-Powered Insights</h2>
"""

            # ML Charts
            if ml_charts:
                html += """
            <div class="charts-grid">
"""
                for chart_id, chart in ml_charts.items():
                    confidence_method = chart.get("confidence", "")
                    html += f"""
                <div class="chart-card">
                    <div class="chart-title">{chart['title']}</div>
                    <canvas id="{chart_id}"></canvas>
"""
                    if confidence_method:
                        html += f"""
                    <div class="confidence-indicator">
                        <span>Method: {confidence_method}</span>
                    </div>
"""
                    html += """
                </div>
"""
                html += """
            </div>
"""

            # ML Recommendations
            if ml_recommendations:
                html += """
            <h3 style='color: #8b5cf6; margin: 1.5rem 0 1rem;'>🎯 ML Recommendations (Top 5 by Impact)</h3>
"""
                for rec in ml_recommendations[:5]:
                    impact = rec.get("impact_score", 0)
                    confidence = rec.get("confidence", 0)
                    confidence_pct = int(confidence * 100)

                    html += f"""
            <div class="ml-recommendation">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                    <strong>{rec.get('title', 'ML Recommendation')}</strong>
                    <span class="impact-badge">Impact: {impact}/100</span>
                </div>
                <div style="color: #64748b; font-size: 0.9rem; margin-bottom: 0.5rem;">
                    {rec.get('description', '')}
                </div>
                <div style="color: #3730a3; font-size: 0.875rem; font-weight: 500;">
                    → {rec.get('suggested_action', '')}
                </div>
                <div class="confidence-indicator">
                    <span>Confidence:</span>
                    <div class="confidence-bar">
                        <div class="confidence-fill" style="width: {confidence_pct}%"></div>
                    </div>
                    <span>{confidence_pct}%</span>
                </div>
            </div>
"""

            # Pattern Insights
            if ml_patterns:
                html += """
            <h3 style='color: #10b981; margin: 1.5rem 0 1rem;'>🔍 Detected Patterns (Top 10)</h3>
"""
                for pattern in ml_patterns[:10]:
                    pattern_str = pattern.get("pattern", "Unknown")
                    support = pattern.get("support", 0)
                    pattern_type = pattern.get("pattern_type", "sequence")

                    html += f"""
            <div class="pattern-item">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 500;">{pattern_str}</span>
                    <span style="font-size: 0.875rem; color: #059669;">Support: {support}</span>
                </div>
                <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem;">
                    Type: {pattern_type}
                </div>
            </div>
"""

            # Benchmark Comparisons
            if ml_benchmarks:
                html += """
            <h3 style='color: #f59e0b; margin: 1.5rem 0 1rem;'>📊 Performance Benchmarks</h3>
"""
                for benchmark in ml_benchmarks:
                    metric = benchmark.get("metric", "Unknown").title()
                    current = benchmark.get("current_value", 0)
                    baseline = benchmark.get("baseline", 0)
                    percentile = benchmark.get("percentile", 50)
                    trend = benchmark.get("trend", "stable")
                    status = benchmark.get("status", "at_baseline")

                    # Status emoji
                    status_emoji = "✅" if status == "above_baseline" else "[WARNING]" if status == "below_baseline" else "➡️"

                    html += f"""
            <div class="benchmark-item">
                <div>
                    <div style="font-weight: 600; margin-bottom: 0.25rem;">{status_emoji} {metric}</div>
                    <div style="font-size: 0.875rem; color: #64748b;">
                        Current: {current:.1f} | Baseline: {baseline:.1f} | {percentile:.0f}th percentile
                    </div>
                </div>
                <span class="trend-badge trend-{trend}">{trend.replace('_', ' ').title()}</span>
            </div>
"""

            html += """
        </div>
"""
        else:
            # No ML data available
            html += """
        <!-- ML Insights Section -->
        <div class="insights-section">
            <h2 class="section-title">🤖 ML-Powered Insights</h2>
            <div class="no-ml-data">
                <p>ML insights require at least 14 days of historical data and pandas library.</p>
                <p style="margin-top: 0.5rem;">Continue using dream-studio to unlock advanced analytics!</p>
            </div>
        </div>
"""

        html += f"""
        <footer>
            <p>Dream-Studio Analytics Platform · Built with ❤️ by Twin Roots LLC</p>
        </footer>
    </div>

    <script>
        // Chart.js configuration
        const allCharts = {{...{json.dumps(charts, indent=8)}, ...{json.dumps(ml_charts, indent=8)}}};

        // Render all charts (standard + ML)
        Object.keys(allCharts).forEach(chartId => {{
            const config = allCharts[chartId];
            const ctx = document.getElementById(chartId);

            if (ctx) {{
                new Chart(ctx, {{
                    type: config.type,
                    data: config.data,
                    options: {{
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: {{
                            legend: {{
                                display: true,
                                position: 'bottom'
                            }}
                        }},
                        scales: config.type !== 'doughnut' ? {{
                            y: {{
                                beginAtZero: true
                            }}
                        }} : {{}}
                    }}
                }});
            }}
        }});

        // Export functionality
        async function exportReport(format) {{
            try {{
                const response = await fetch(`/api/v1/exports`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        report_id: 'dashboard-{datetime.now().strftime("%Y%m%d")}',
                        format: format,
                        include_charts: true,
                        include_raw_data: true
                    }})
                }});

                if (!response.ok) {{
                    throw new Error(`Export failed: ${{response.statusText}}`);
                }}

                const result = await response.json();
                const exportId = result.export_id;

                // Poll for completion
                await pollExportStatus(exportId, format);
            }} catch (error) {{
                console.error('Export error:', error);
                alert(`Export failed: ${{error.message}}`);
            }}
        }}

        async function pollExportStatus(exportId, format) {{
            const maxAttempts = 30;
            let attempts = 0;

            while (attempts < maxAttempts) {{
                const response = await fetch(`/api/v1/exports/${{exportId}}`);
                const status = await response.json();

                if (status.status === 'complete') {{
                    // Download the file
                    window.location.href = status.download_url;
                    addReportToList(exportId, format);
                    return;
                }} else if (status.status === 'failed') {{
                    throw new Error('Export generation failed');
                }}

                // Wait 2 seconds before next poll
                await new Promise(resolve => setTimeout(resolve, 2000));
                attempts++;
            }}

            throw new Error('Export timeout - please try again');
        }}

        async function generateCustomReport() {{
            const reportType = document.getElementById('reportType').value;
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value;
            const template = document.getElementById('template').value;
            const format = document.getElementById('exportFormat').value;

            if (!startDate || !endDate) {{
                alert('Please select both start and end dates');
                return;
            }}

            try {{
                // Create report configuration
                const reportResponse = await fetch('/api/v1/reports', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        name: `${{reportType}} Report`,
                        type: reportType,
                        description: `Custom report from ${{startDate}} to ${{endDate}}`,
                        days: 30,
                        filters: {{
                            start_date: startDate,
                            end_date: endDate,
                            template: template
                        }},
                        sections: ['metrics', 'insights', 'recommendations']
                    }})
                }});

                const report = await reportResponse.json();

                // Export the report
                const exportResponse = await fetch('/api/v1/exports', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        report_id: report.id,
                        format: format,
                        include_charts: true,
                        include_raw_data: true
                    }})
                }});

                const exportResult = await exportResponse.json();
                await pollExportStatus(exportResult.export_id, format);
            }} catch (error) {{
                console.error('Report generation error:', error);
                alert(`Report generation failed: ${{error.message}}`);
            }}
        }}

        function addReportToList(exportId, format) {{
            const reportsList = document.getElementById('reportsList');

            // Remove "no reports" message if present
            if (reportsList.querySelector('p')) {{
                reportsList.innerHTML = '';
            }}

            const reportItem = document.createElement('div');
            reportItem.className = 'report-item';
            reportItem.innerHTML = `
                <div class="report-item-info">
                    <strong>${{format.toUpperCase()}} Report</strong>
                    <small>Generated at ${{new Date().toLocaleString()}} · Export ID: ${{exportId}}</small>
                </div>
                <button onclick="window.location.href='/api/v1/exports/${{exportId}}/download'">Download</button>
            `;

            reportsList.insertBefore(reportItem, reportsList.firstChild);
        }}

        async function loadSchedules() {{
            try {{
                const response = await fetch('/api/v1/schedules');
                const data = await response.json();
                const tbody = document.getElementById('schedulesTable').querySelector('tbody');

                if (data.schedules && data.schedules.length > 0) {{
                    tbody.innerHTML = data.schedules.map(s => `
                        <tr>
                            <td>${{s.name}}</td>
                            <td>${{s.schedule}}</td>
                            <td>${{s.next_run || 'N/A'}}</td>
                            <td>${{s.enabled ? '✅ Active' : '⏸️ Paused'}}</td>
                            <td>
                                <button onclick="pauseSchedule('${{s.job_id}}')">Pause</button>
                                <button onclick="deleteSchedule('${{s.job_id}}')">Delete</button>
                            </td>
                        </tr>
                    `).join('');
                }}
            }} catch (error) {{
                console.log('Schedules not available:', error);
            }}
        }}

        function showScheduleForm() {{
            alert('Schedule form feature coming soon! This will allow you to set up automated report generation.');
        }}

        async function pauseSchedule(jobId) {{
            alert(`Pause schedule ${{jobId}} - Feature coming soon!`);
        }}

        async function deleteSchedule(jobId) {{
            if (confirm('Are you sure you want to delete this schedule?')) {{
                alert(`Delete schedule ${{jobId}} - Feature coming soon!`);
            }}
        }}

        // Load schedules on page load
        document.addEventListener('DOMContentLoaded', () => {{
            loadSchedules();
        }});
    </script>
</body>
</html>"""

        return html


# CLI function
def generate_dashboard(days: int = 30, output: str = "analytics_dashboard.html"):
    """CLI entry point for dashboard generation"""
    dashboard = ProductionDashboard()
    return dashboard.generate(days=days, output_path=output)


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    output = sys.argv[2] if len(sys.argv) > 2 else "analytics_dashboard.html"
    generate_dashboard(days=days, output=output)
