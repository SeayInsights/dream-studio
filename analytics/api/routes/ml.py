"""ML/Advanced Analytics API routes"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional, Literal
from datetime import datetime
import os

from analytics.ml import (
    PatternDetector,
    BehaviorClusterer,
    BenchmarkEngine,
)
from analytics.ml.forecasting import TimeSeriesForecaster
from analytics.ml.recommendations import RecommendationEngine
from analytics.core.collectors import (
    SessionCollector,
    SkillCollector,
    TokenCollector,
)

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class ForecastPoint(BaseModel):
    """Single forecast data point"""
    date: str
    value: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None


class ForecastResponse(BaseModel):
    """Forecast response"""
    metric: str
    method: str
    forecast: List[ForecastPoint]
    historical_mean: float
    forecast_mean: float
    days: int
    generated_at: str


class Pattern(BaseModel):
    """Detected pattern"""
    pattern_type: str
    pattern: str
    support: int
    confidence: Optional[float] = None
    lift: Optional[float] = None
    examples: Optional[List[str]] = None


class PatternsResponse(BaseModel):
    """Patterns detection response"""
    patterns: List[Pattern]
    pattern_type: Optional[str] = None
    total_count: int
    min_support: int
    generated_at: str


class MLRecommendation(BaseModel):
    """ML-generated recommendation"""
    category: str
    title: str
    description: str
    impact_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Dict[str, Any]
    suggested_action: str


class RecommendationsResponse(BaseModel):
    """ML recommendations response"""
    recommendations: List[MLRecommendation]
    category: Optional[str] = None
    total_count: int
    min_impact: int
    generated_at: str


class BenchmarkResult(BaseModel):
    """Single benchmark result"""
    metric: str
    current_value: float
    baseline: float
    percentile: float
    trend: Literal["improving", "stable", "declining"]
    status: Literal["above_baseline", "at_baseline", "below_baseline"]


class BenchmarksResponse(BaseModel):
    """Benchmarks response"""
    benchmarks: List[BenchmarkResult]
    metric: Optional[str] = None
    period: str
    generated_at: str


class TrainRequest(BaseModel):
    """Model training request"""
    model_type: Literal["forecaster", "pattern_detector", "clusterer", "recommendation_engine", "benchmark_engine"]
    params: Optional[Dict[str, Any]] = None


class TrainResponse(BaseModel):
    """Model training response"""
    model_type: str
    status: Literal["success", "failed"]
    message: str
    model_id: Optional[str] = None
    training_samples: Optional[int] = None
    trained_at: str


# ============================================================================
# Helper Functions
# ============================================================================

def get_db_path() -> str:
    """Get database path"""
    return os.path.expanduser("~/.dream-studio/state/studio.db")


def collect_time_series_data(metric: str, days: int = 30):
    """Collect time series data for a specific metric"""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pandas is required for time series operations. Install with: pip install pandas"
        )

    db_path = get_db_path()

    if metric == "sessions":
        collector = SessionCollector(db_path)
        data = collector.collect(days=days)
        if "timeline" in data:
            # Convert to time series format
            timeline = data["timeline"]
            df = pd.DataFrame(timeline)
            if not df.empty and "date" in df.columns and "count" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                return df[["count"]].rename(columns={"count": "value"})

    elif metric == "tokens":
        collector = TokenCollector(db_path)
        data = collector.collect(days=days)
        if "timeline" in data:
            timeline = data["timeline"]
            df = pd.DataFrame(timeline)
            if not df.empty and "date" in df.columns and "total" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                return df[["total"]].rename(columns={"total": "value"})

    elif metric == "skills":
        collector = SkillCollector(db_path)
        data = collector.collect(days=days)
        if "timeline" in data:
            timeline = data["timeline"]
            df = pd.DataFrame(timeline)
            if not df.empty and "date" in df.columns and "count" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                return df[["count"]].rename(columns={"count": "value"})

    return None


def collect_skill_telemetry(days: int = 30):
    """Collect skill telemetry data for pattern detection"""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pandas is required for pattern detection. Install with: pip install pandas"
        )

    db_path = get_db_path()
    collector = SkillCollector(db_path)
    data = collector.collect(days=days)

    # Convert to telemetry format expected by PatternDetector
    # Expected columns: session_id, skill_name, invoked_at
    if "invocations" in data and len(data["invocations"]) > 0:
        df = pd.DataFrame(data["invocations"])
        if "session_id" in df.columns and "skill_name" in df.columns and "invoked_at" in df.columns:
            return df[["session_id", "skill_name", "invoked_at"]]

    return pd.DataFrame(columns=["session_id", "skill_name", "invoked_at"])


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/forecasts", response_model=ForecastResponse)
async def get_forecasts(
    metric: str = Query(default="sessions", description="Metric to forecast: sessions, tokens, or skills"),
    days: int = Query(default=7, ge=1, le=30, description="Number of days to forecast ahead")
):
    """
    Get time series forecasts for a specific metric.

    Uses ARIMA/exponential smoothing when statsmodels is available,
    with simple moving average fallback.
    """
    try:
        # Collect historical data
        data = collect_time_series_data(metric, days=90)  # Use 90 days history for forecasting

        if data is None or len(data) < 14:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient historical data for metric '{metric}'. Need at least 14 days of history."
            )

        # Train forecaster
        forecaster = TimeSeriesForecaster(method='auto')
        forecaster.fit(data)

        # Generate forecast
        forecast_result = forecaster.forecast(steps=days)

        # Format response
        forecast_points = []
        for item in forecast_result["forecast"]:
            forecast_points.append(ForecastPoint(
                date=item["date"],
                value=item["value"],
                lower_bound=item.get("lower_bound"),
                upper_bound=item.get("upper_bound")
            ))

        return ForecastResponse(
            metric=metric,
            method=forecast_result["method"],
            forecast=forecast_points,
            historical_mean=float(data["value"].mean()),
            forecast_mean=forecast_result["mean"],
            days=days,
            generated_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating forecast: {str(e)}")


@router.get("/patterns", response_model=PatternsResponse)
async def get_patterns(
    pattern_type: Optional[str] = Query(default=None, description="Pattern type filter: sequence, temporal_hour, temporal_day"),
    min_support: int = Query(default=3, ge=1, description="Minimum number of occurrences")
):
    """
    Get detected patterns in skill usage and workflows.

    Detects sequence patterns, temporal patterns, and workflow patterns.
    """
    try:
        # Collect skill telemetry
        telemetry = collect_skill_telemetry(days=90)

        if len(telemetry) < min_support:
            return PatternsResponse(
                patterns=[],
                pattern_type=pattern_type,
                total_count=0,
                min_support=min_support,
                generated_at=datetime.now().isoformat()
            )

        # Train pattern detector
        detector = PatternDetector(min_support=min_support)
        detector.fit(telemetry)

        # Get patterns
        patterns_data = detector.get_patterns(pattern_type=pattern_type)

        # Format response
        patterns = []
        for p in patterns_data:
            patterns.append(Pattern(
                pattern_type=p["pattern_type"],
                pattern=p["pattern"],
                support=p["support"],
                confidence=p.get("confidence"),
                lift=p.get("lift"),
                examples=p.get("examples")
            ))

        return PatternsResponse(
            patterns=patterns,
            pattern_type=pattern_type,
            total_count=len(patterns),
            min_support=min_support,
            generated_at=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting patterns: {str(e)}")


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    category: Optional[str] = Query(default=None, description="Category filter: skill_optimization, workflow_improvement, inefficiency_detection, performance_booster"),
    min_impact: int = Query(default=0, ge=0, le=100, description="Minimum impact score (0-100)")
):
    """
    Get ML-generated recommendations for workflow optimization.

    Analyzes patterns and behaviors to suggest actionable improvements.
    """
    try:
        import pandas as pd

        # Collect data
        telemetry = collect_skill_telemetry(days=90)

        # Collect session data
        db_path = get_db_path()
        session_collector = SessionCollector(db_path)
        session_data_raw = session_collector.collect(days=90)

        # Convert to format expected by RecommendationEngine
        # Expected columns: session_id, duration, tokens, outcome (optional: skills_used, time_of_day, day_of_week)
        if "sessions" in session_data_raw and len(session_data_raw["sessions"]) > 0:
            session_data = pd.DataFrame(session_data_raw["sessions"])
            # Ensure required columns exist
            if "session_id" not in session_data.columns:
                session_data["session_id"] = range(len(session_data))
            if "duration" not in session_data.columns:
                session_data["duration"] = 0
            if "tokens" not in session_data.columns:
                session_data["tokens"] = 0
            if "outcome" not in session_data.columns:
                session_data["outcome"] = "success"
        else:
            session_data = pd.DataFrame(columns=["session_id", "duration", "tokens", "outcome"])

        if len(telemetry) < 20 or len(session_data) < 20:
            return RecommendationsResponse(
                recommendations=[],
                category=category,
                total_count=0,
                min_impact=min_impact,
                generated_at=datetime.now().isoformat()
            )

        # Train recommendation engine
        engine = RecommendationEngine(min_support=3)
        engine.fit(telemetry, session_data)

        # Get recommendations
        recs_data = engine.get_recommendations(category=category, min_impact=min_impact)

        # Format response
        recommendations = []
        for rec in recs_data:
            recommendations.append(MLRecommendation(
                category=rec["category"],
                title=rec["title"],
                description=rec["description"],
                impact_score=rec["impact_score"],
                confidence=rec["confidence"],
                evidence=rec["evidence"],
                suggested_action=rec["suggested_action"]
            ))

        return RecommendationsResponse(
            recommendations=recommendations,
            category=category,
            total_count=len(recommendations),
            min_impact=min_impact,
            generated_at=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@router.get("/benchmarks", response_model=BenchmarksResponse)
async def get_benchmarks(
    metric: Optional[str] = Query(default=None, description="Metric to benchmark: sessions, skills, tokens"),
    period: str = Query(default="30d", description="Period for current metrics (e.g., 7d, 30d)")
):
    """
    Get comparative benchmarks comparing current vs historical performance.

    Returns percentile rankings, trend analysis, and baseline comparisons.
    """
    try:
        import pandas as pd

        # Parse period (e.g., "30d" -> 30 days)
        period_days = int(period.rstrip("d"))
        if period_days < 1 or period_days > 90:
            raise HTTPException(status_code=400, detail="Period must be between 1d and 90d")

        # Collect historical data (last 180 days for baseline)
        historical_data = {}
        metrics_to_benchmark = [metric] if metric else ["sessions", "skills", "tokens"]

        for m in metrics_to_benchmark:
            ts_data = collect_time_series_data(m, days=180)
            if ts_data is not None and len(ts_data) >= 14:
                historical_data[m] = ts_data

        if not historical_data:
            raise HTTPException(
                status_code=400,
                detail="Insufficient historical data for benchmarking. Need at least 14 days of history."
            )

        # Combine metrics into single DataFrame
        combined_df = pd.DataFrame()
        for m, df in historical_data.items():
            combined_df[m] = df["value"]

        # Train benchmark engine
        engine = BenchmarkEngine()
        engine.fit(combined_df)

        # Calculate current values (average over the period)
        benchmarks = []
        for m in historical_data.keys():
            ts_data = collect_time_series_data(m, days=period_days)
            if ts_data is not None and len(ts_data) > 0:
                current_value = float(ts_data["value"].mean())

                # Get benchmark
                benchmark = engine.benchmark_metric(m, current_value)

                benchmarks.append(BenchmarkResult(
                    metric=m,
                    current_value=current_value,
                    baseline=benchmark["baseline"],
                    percentile=benchmark["percentile"],
                    trend=benchmark["trend"],
                    status=benchmark["status"]
                ))

        return BenchmarksResponse(
            benchmarks=benchmarks,
            metric=metric,
            period=period,
            generated_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating benchmarks: {str(e)}")


@router.post("/train", response_model=TrainResponse)
async def train_model(request: TrainRequest):
    """
    Trigger model training for a specific ML model type.

    Trains the model on historical data and saves it for future use.
    """
    try:
        import pandas as pd
        from analytics.ml.storage import save_model

        model_type = request.model_type
        params = request.params or {}

        training_samples = 0
        model_id = None

        if model_type == "forecaster":
            # Train time series forecaster
            metric = params.get("metric", "sessions")
            method = params.get("method", "auto")

            data = collect_time_series_data(metric, days=90)
            if data is None or len(data) < 14:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient data for training forecaster on '{metric}'. Need at least 14 days."
                )

            model = TimeSeriesForecaster(method=method)
            model.fit(data)
            training_samples = len(data)

            # Save model
            model_id = save_model(model, f"forecaster_{metric}")

        elif model_type == "pattern_detector":
            # Train pattern detector
            min_support = params.get("min_support", 3)

            telemetry = collect_skill_telemetry(days=90)
            if len(telemetry) < min_support:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient data for training pattern detector. Need at least {min_support} samples."
                )

            model = PatternDetector(min_support=min_support)
            model.fit(telemetry)
            training_samples = len(telemetry)

            # Save model
            model_id = save_model(model, "pattern_detector")

        elif model_type == "recommendation_engine":
            # Train recommendation engine
            min_support = params.get("min_support", 3)

            telemetry = collect_skill_telemetry(days=90)
            db_path = get_db_path()
            session_collector = SessionCollector(db_path)
            session_data_raw = session_collector.collect(days=90)

            if "sessions" in session_data_raw and len(session_data_raw["sessions"]) > 0:
                session_data = pd.DataFrame(session_data_raw["sessions"])
                if "session_id" not in session_data.columns:
                    session_data["session_id"] = range(len(session_data))
                if "duration" not in session_data.columns:
                    session_data["duration"] = 0
                if "tokens" not in session_data.columns:
                    session_data["tokens"] = 0
                if "outcome" not in session_data.columns:
                    session_data["outcome"] = "success"
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No session data available for training recommendation engine."
                )

            if len(telemetry) < 20 or len(session_data) < 20:
                raise HTTPException(
                    status_code=400,
                    detail="Need at least 20 sessions for training recommendation engine."
                )

            model = RecommendationEngine(min_support=min_support)
            model.fit(telemetry, session_data)
            training_samples = len(session_data)

            # Save model
            model_id = save_model(model, "recommendation_engine")

        elif model_type == "benchmark_engine":
            # Train benchmark engine
            baselines = params.get("baselines", {})

            historical_data = {}
            for m in ["sessions", "skills", "tokens"]:
                ts_data = collect_time_series_data(m, days=180)
                if ts_data is not None and len(ts_data) >= 14:
                    historical_data[m] = ts_data

            if not historical_data:
                raise HTTPException(
                    status_code=400,
                    detail="Insufficient data for training benchmark engine."
                )

            combined_df = pd.DataFrame()
            for m, df in historical_data.items():
                combined_df[m] = df["value"]

            model = BenchmarkEngine(baselines=baselines)
            model.fit(combined_df)
            training_samples = len(combined_df)

            # Save model
            model_id = save_model(model, "benchmark_engine")

        elif model_type == "clusterer":
            # Train behavior clusterer
            n_clusters = params.get("n_clusters", 3)

            db_path = get_db_path()
            session_collector = SessionCollector(db_path)
            session_data_raw = session_collector.collect(days=90)

            if "sessions" in session_data_raw and len(session_data_raw["sessions"]) > 0:
                session_data = pd.DataFrame(session_data_raw["sessions"])
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No session data available for training clusterer."
                )

            if len(session_data) < 20:
                raise HTTPException(
                    status_code=400,
                    detail="Need at least 20 sessions for training behavior clusterer."
                )

            model = BehaviorClusterer(n_clusters=n_clusters)
            model.fit(session_data)
            training_samples = len(session_data)

            # Save model
            model_id = save_model(model, "behavior_clusterer")

        else:
            raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

        return TrainResponse(
            model_type=model_type,
            status="success",
            message=f"Successfully trained {model_type}",
            model_id=model_id,
            training_samples=training_samples,
            trained_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        return TrainResponse(
            model_type=request.model_type,
            status="failed",
            message=f"Training failed: {str(e)}",
            trained_at=datetime.now().isoformat()
        )
