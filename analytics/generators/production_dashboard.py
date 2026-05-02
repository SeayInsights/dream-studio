"""Production Dashboard Generator - Creates beautiful, interactive analytics dashboards"""
from typing import Dict, Any, List
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
        print(f"📊 Generating analytics dashboard for last {days} days...")

        # Collect all data
        print("  → Collecting metrics...")
        metrics = self._collect_metrics(days)

        print("  → Running analysis...")
        analysis = self._analyze_metrics(metrics)

        print("  → Generating insights...")
        insights = self._generate_insights(metrics, analysis)

        print("  → Creating visualizations...")
        charts = self._generate_charts(metrics, analysis)

        print("  → Building dashboard...")
        html = self._build_html(metrics, analysis, insights, charts)

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"✅ Dashboard generated: {output_path}")
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

    def _build_html(
        self,
        metrics: Dict[str, Any],
        analysis: Dict[str, Any],
        insights: Dict[str, Any],
        charts: Dict[str, Any]
    ) -> str:
        """Build complete HTML dashboard"""

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
            html += "<h3 style='color: #ef4444; margin: 1.5rem 0 1rem;'>⚠️ Issues</h3>"
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

        <footer>
            <p>Dream-Studio Analytics Platform · Built with ❤️ by Twin Roots LLC</p>
        </footer>
    </div>

    <script>
        // Chart.js configuration
        const chartData = {json.dumps(charts, indent=8)};

        // Render all charts
        Object.keys(chartData).forEach(chartId => {{
            const config = chartData[chartId];
            const ctx = document.getElementById(chartId);

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
