"""ML/Advanced Analytics API routes"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional, Literal
from datetime import datetime
from pathlib import Path
import sqlite3

from projections.ml import (
    PatternDetector,
    BehaviorClusterer,
    BenchmarkEngine,
)
from projections.ml.forecasting import TimeSeriesForecaster
from projections.ml.recommendations import RecommendationEngine
from projections.ml.storage import save_model

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
    actionable: bool
    data: Dict[str, Any]


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

    model_type: Literal[
        "forecaster", "pattern_detector", "clusterer", "recommendation_engine", "benchmark_engine"
    ]
    input_path: Optional[str] = Field(
        default=None,
        description="Explicit operator-selected aggregate/redacted SQLite input path",
    )
    input_package_path: Optional[str] = Field(
        default=None,
        description="Explicit operator-selected aggregate/redacted package path",
    )
    output_dir: str = Field(
        ...,
        description="Explicit directory for derived model artifacts",
    )
    params: Optional[Dict[str, Any]] = None


class TrainResponse(BaseModel):
    """Model training response"""

    model_type: str
    status: Literal["success", "failed"]
    message: str
    model_path: Optional[str] = None
    training_samples: Optional[int] = None
    trained_at: str


# ============================================================================
# Helper Functions
# ============================================================================


def resolve_operator_input(
    input_path: Optional[str] = None,
    input_package_path: Optional[str] = None,
) -> str:
    """Resolve an explicit operator input path; never auto-discover local state."""
    selected = input_path or input_package_path
    if not selected:
        raise HTTPException(
            status_code=400,
            detail=(
                "ML analytics requires an explicit operator-selected aggregate "
                "or redacted input path. Live Dream Studio runtime state is not "
                "auto-discovered."
            ),
        )

    path = Path(selected).expanduser()
    if not path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Input path does not exist: {path}",
        )

    return str(path)


def _read_sql(db_path: str, query: str):
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pandas is required for analytics. Install with: pip install pandas",
        )

    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def collect_time_series_data(metric: str, days: int = 30, input_path: Optional[str] = None):
    """Collect time series data for a specific metric"""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pandas is required for time series operations. Install with: pip install pandas",
        )

    db_path = resolve_operator_input(input_path)

    if metric == "sessions":
        df = _read_sql(
            db_path,
            """
            SELECT DATE(start_time) as date, COUNT(*) as value
            FROM sessions
            WHERE start_time IS NOT NULL
            GROUP BY DATE(start_time)
            ORDER BY date
        """,
        )

    elif metric == "tokens":
        df = _read_sql(
            db_path,
            """
            SELECT DATE(timestamp) as date, SUM(tokens) as value
            FROM token_usage
            WHERE timestamp IS NOT NULL
            GROUP BY DATE(timestamp)
            ORDER BY date
        """,
        )

    elif metric == "skills":
        df = _read_sql(
            db_path,
            """
            SELECT DATE(invoked_at) as date, COUNT(*) as value
            FROM raw_skill_telemetry
            WHERE invoked_at IS NOT NULL
            GROUP BY DATE(invoked_at)
            ORDER BY date
        """,
        )
    else:
        return None

    if not df.empty and "date" in df.columns and "value" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df[["value"]]

    return None


def collect_skill_telemetry(days: int = 30, input_path: Optional[str] = None):
    """Collect skill telemetry data for pattern detection"""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pandas is required for pattern detection. Install with: pip install pandas",
        )

    db_path = resolve_operator_input(input_path)
    df = _read_sql(
        db_path,
        """
        SELECT session_id, skill_name, invoked_at
        FROM raw_skill_telemetry
        WHERE session_id IS NOT NULL
        ORDER BY invoked_at
    """,
    )
    if not df.empty and all(
        col in df.columns for col in ["session_id", "skill_name", "invoked_at"]
    ):
        return df[["session_id", "skill_name", "invoked_at"]]

    return pd.DataFrame(columns=["session_id", "skill_name", "invoked_at"])


def collect_session_data(input_path: Optional[str] = None):
    """Collect session data from an explicit aggregate/redacted input."""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pandas is required for session analytics. Install with: pip install pandas",
        )

    db_path = resolve_operator_input(input_path)
    try:
        df = _read_sql(
            db_path,
            """
            SELECT
                session_id,
                duration,
                total_tokens as tokens,
                outcome,
                skills_used
            FROM agg_sessions
            WHERE session_id IS NOT NULL
        """,
        )
    except Exception:
        df = pd.DataFrame(columns=["session_id", "duration", "tokens", "outcome", "skills_used"])

    return df


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/forecasts", response_model=ForecastResponse)
async def get_forecasts(
    metric: str = Query(
        default="sessions", description="Metric to forecast: sessions, tokens, or skills"
    ),
    days: int = Query(default=7, ge=1, le=30, description="Number of days to forecast ahead"),
    input_path: str = Query(..., description="Explicit aggregate/redacted input path"),
):
    """
    Get time series forecasts for a specific metric.

    Uses ARIMA/exponential smoothing when statsmodels is available,
    with simple moving average fallback.
    """
    try:
        data = collect_time_series_data(metric, days=90, input_path=input_path)

        if data is None or len(data) < 14:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient historical data for metric '{metric}'. Need at least 14 days of history.",
            )

        forecaster = TimeSeriesForecaster(method="auto")
        forecaster.fit(data)
        forecast_result = forecaster.forecast(periods=days)

        predictions = forecast_result["predictions"]
        dates = forecast_result["dates"]
        lower_bounds = forecast_result.get("lower_95", [None] * len(predictions))
        upper_bounds = forecast_result.get("upper_95", [None] * len(predictions))

        forecast_points = []
        for i, date in enumerate(dates):
            forecast_points.append(
                ForecastPoint(
                    date=date,
                    value=predictions[i],
                    lower_bound=lower_bounds[i] if i < len(lower_bounds) else None,
                    upper_bound=upper_bounds[i] if i < len(upper_bounds) else None,
                )
            )

        forecast_mean = sum(predictions) / len(predictions) if predictions else 0.0

        return ForecastResponse(
            metric=metric,
            method=forecaster.method,
            forecast=forecast_points,
            historical_mean=float(data["value"].mean()),
            forecast_mean=forecast_mean,
            days=days,
            generated_at=datetime.now().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating forecast: {str(e)}")


@router.get("/patterns", response_model=PatternsResponse)
async def get_patterns(
    pattern_type: Optional[str] = Query(
        default=None, description="Pattern type filter: sequence, temporal_hour, temporal_day"
    ),
    min_support: int = Query(default=3, ge=1, description="Minimum number of occurrences"),
    input_path: str = Query(..., description="Explicit aggregate/redacted input path"),
):
    """
    Get detected patterns in skill usage and workflows.
    """
    try:
        telemetry = collect_skill_telemetry(days=90, input_path=input_path)

        if len(telemetry) < min_support:
            return PatternsResponse(
                patterns=[],
                pattern_type=pattern_type,
                total_count=0,
                min_support=min_support,
                generated_at=datetime.now().isoformat(),
            )

        detector = PatternDetector(min_support=min_support)
        detector.fit(telemetry)
        patterns_data = detector.get_patterns(pattern_type=pattern_type)

        patterns = []
        for p in patterns_data:
            patterns.append(
                Pattern(
                    pattern_type=p["pattern_type"],
                    pattern=p["pattern"],
                    support=p["support"],
                    confidence=p.get("confidence"),
                    lift=p.get("lift"),
                    examples=p.get("examples"),
                )
            )

        return PatternsResponse(
            patterns=patterns,
            pattern_type=pattern_type,
            total_count=len(patterns),
            min_support=min_support,
            generated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting patterns: {str(e)}")


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    category: Optional[str] = Query(default=None, description="Category filter"),
    min_impact: int = Query(default=0, ge=0, le=100, description="Minimum impact score (0-100)"),
    input_path: str = Query(..., description="Explicit aggregate/redacted input path"),
):
    """
    Get ML-generated recommendations for workflow optimization.
    """
    try:
        telemetry = collect_skill_telemetry(days=90, input_path=input_path)
        session_data = collect_session_data(input_path=input_path)

        if "session_id" not in session_data.columns:
            session_data["session_id"] = range(len(session_data))
        if "duration" not in session_data.columns:
            session_data["duration"] = 0
        if "tokens" not in session_data.columns:
            session_data["tokens"] = 0
        if "outcome" not in session_data.columns:
            session_data["outcome"] = "success"

        if len(telemetry) < 20 or len(session_data) < 20:
            return RecommendationsResponse(
                recommendations=[],
                category=category,
                total_count=0,
                min_impact=min_impact,
                generated_at=datetime.now().isoformat(),
            )

        engine = RecommendationEngine(min_support=3)
        engine.fit(telemetry, session_data)
        recs_data = engine.get_recommendations(category=category, min_impact=min_impact)

        recommendations = []
        for rec in recs_data:
            recommendations.append(
                MLRecommendation(
                    category=rec["category"],
                    title=rec["title"],
                    description=rec["description"],
                    impact_score=rec["impact_score"],
                    actionable=rec.get("actionable", True),
                    data=rec.get("data", {}),
                )
            )

        return RecommendationsResponse(
            recommendations=recommendations,
            category=category,
            total_count=len(recommendations),
            min_impact=min_impact,
            generated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@router.get("/benchmarks", response_model=BenchmarksResponse)
async def get_benchmarks(
    metric: Optional[str] = Query(
        default=None, description="Metric to benchmark: sessions, skills, tokens"
    ),
    period: str = Query(default="30d", description="Period for current metrics (e.g., 7d, 30d)"),
    input_path: str = Query(..., description="Explicit aggregate/redacted input path"),
):
    """
    Get comparative benchmarks comparing current vs historical performance.
    """
    try:
        import pandas as pd

        period_days = int(period.rstrip("d"))
        if period_days < 1 or period_days > 90:
            raise HTTPException(status_code=400, detail="Period must be between 1d and 90d")

        historical_data = {}
        metrics_to_benchmark = [metric] if metric else ["sessions", "skills", "tokens"]

        for m in metrics_to_benchmark:
            ts_data = collect_time_series_data(m, days=180, input_path=input_path)
            if ts_data is not None and len(ts_data) >= 14:
                historical_data[m] = ts_data

        if not historical_data:
            raise HTTPException(
                status_code=400,
                detail="Insufficient historical data for benchmarking. Need at least 14 days of history.",
            )

        combined_df = pd.DataFrame()
        for m, df in historical_data.items():
            combined_df[m] = df["value"]

        engine = BenchmarkEngine()
        engine.fit(combined_df)

        benchmarks = []
        for m in historical_data.keys():
            ts_data = collect_time_series_data(m, days=period_days, input_path=input_path)
            if ts_data is not None and len(ts_data) > 0:
                current_value = float(ts_data["value"].mean())
                benchmark = engine.benchmark_metric(m, current_value)

                benchmarks.append(
                    BenchmarkResult(
                        metric=m,
                        current_value=current_value,
                        baseline=benchmark["baseline"],
                        percentile=benchmark["percentile"],
                        trend=benchmark["trend"],
                        status=benchmark["status"],
                    )
                )

        return BenchmarksResponse(
            benchmarks=benchmarks,
            metric=metric,
            period=period,
            generated_at=datetime.now().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating benchmarks: {str(e)}")


@router.post("/train", response_model=TrainResponse)
async def train_model(request: TrainRequest):
    """
    Trigger model training for a specific ML model type.
    """
    try:
        import pandas as pd

        model_type = request.model_type
        params = request.params or {}
        input_path = resolve_operator_input(request.input_path, request.input_package_path)
        output_dir = Path(request.output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        training_samples = 0
        model_path = None

        if model_type == "forecaster":
            metric = params.get("metric", "sessions")
            method = params.get("method", "auto")

            data = collect_time_series_data(metric, days=90, input_path=input_path)
            if data is None or len(data) < 14:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient data for training forecaster on '{metric}'. Need at least 14 days.",
                )

            model = TimeSeriesForecaster(method=method)
            model.fit(data)
            training_samples = len(data)
            model_path = str(output_dir / f"forecaster_{metric}")
            save_model(model, model_path)

        elif model_type == "pattern_detector":
            min_support = params.get("min_support", 3)

            telemetry = collect_skill_telemetry(days=90, input_path=input_path)
            if len(telemetry) < min_support:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient data for training pattern detector. Need at least {min_support} samples.",
                )

            model = PatternDetector(min_support=min_support)
            model.fit(telemetry)
            training_samples = len(telemetry)
            model_path = str(output_dir / "pattern_detector")
            save_model(model, model_path)

        elif model_type == "recommendation_engine":
            min_support = params.get("min_support", 3)

            telemetry = collect_skill_telemetry(days=90, input_path=input_path)
            session_data = collect_session_data(input_path=input_path)

            if session_data.empty:
                raise HTTPException(
                    status_code=400,
                    detail="No session data available for training recommendation engine.",
                )
            if "session_id" not in session_data.columns:
                session_data["session_id"] = range(len(session_data))
            if "duration" not in session_data.columns:
                session_data["duration"] = 0
            if "tokens" not in session_data.columns:
                session_data["tokens"] = 0
            if "outcome" not in session_data.columns:
                session_data["outcome"] = "success"

            if len(telemetry) < 20 or len(session_data) < 20:
                raise HTTPException(
                    status_code=400,
                    detail="Need at least 20 sessions for training recommendation engine.",
                )

            model = RecommendationEngine(min_support=min_support)
            model.fit(telemetry, session_data)
            training_samples = len(session_data)
            model_path = str(output_dir / "recommendation_engine")
            save_model(model, model_path)

        elif model_type == "benchmark_engine":
            baselines = params.get("baselines", {})

            historical_data = {}
            for m in ["sessions", "skills", "tokens"]:
                ts_data = collect_time_series_data(m, days=180, input_path=input_path)
                if ts_data is not None and len(ts_data) >= 14:
                    historical_data[m] = ts_data

            if not historical_data:
                raise HTTPException(
                    status_code=400, detail="Insufficient data for training benchmark engine."
                )

            combined_df = pd.DataFrame()
            for m, df in historical_data.items():
                combined_df[m] = df["value"]

            model = BenchmarkEngine(baselines=baselines)
            model.fit(combined_df)
            training_samples = len(combined_df)
            model_path = str(output_dir / "benchmark_engine")
            save_model(model, model_path)

        elif model_type == "clusterer":
            n_clusters = params.get("n_clusters", 3)

            session_data = collect_session_data(input_path=input_path)

            if session_data.empty:
                raise HTTPException(
                    status_code=400, detail="No session data available for training clusterer."
                )

            if len(session_data) < 20:
                raise HTTPException(
                    status_code=400,
                    detail="Need at least 20 sessions for training behavior clusterer.",
                )

            model = BehaviorClusterer(n_clusters=n_clusters)
            model.fit(session_data)
            training_samples = len(session_data)
            model_path = str(output_dir / "behavior_clusterer")
            save_model(model, model_path)

        else:
            raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

        return TrainResponse(
            model_type=model_type,
            status="success",
            message=f"Successfully trained {model_type}",
            model_path=model_path,
            training_samples=training_samples,
            trained_at=datetime.now().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        return TrainResponse(
            model_type=request.model_type,
            status="failed",
            message=f"Training failed: {str(e)}",
            trained_at=datetime.now().isoformat(),
        )
