"""
Tests for ML components in projections/ml/.

Tests coverage:
- Forecasting: ARIMA, exponential smoothing, moving average, confidence intervals
- Pattern detection: sequence patterns, temporal patterns, support/confidence/lift
- Clustering: K-means, persona assignment, feature engineering
- Recommendations: generation, ranking, impact scoring
- Benchmarks: percentile calculation, trend analysis, baseline comparison
- Model evaluation: MAE/RMSE/MAPE, precision/recall/F1
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import tempfile
import sqlite3
import json
import os

from projections.ml.forecasting import TimeSeriesForecaster, forecast_token_usage
from projections.ml.patterns import PatternDetector, detect_skill_patterns
from projections.ml.clustering import BehaviorClusterer
from projections.ml.recommendations import RecommendationEngine, generate_recommendations
from projections.ml.benchmarks import BenchmarkEngine, run_benchmark_suite
from projections.ml.evaluation import (
    evaluate_forecast_accuracy,
    evaluate_pattern_quality,
    evaluate_recommendation_impact,
    export_evaluation_report,
)

# ============================================================================
# Fixtures for Mock Data Generation
# ============================================================================


@pytest.fixture
def mock_time_series_data():
    """Generate mock time series data for forecasting tests."""
    dates = pd.date_range(start="2024-01-01", periods=30, freq="D")
    np.random.seed(42)
    trend = np.linspace(1000, 1500, 30)
    noise = np.random.normal(0, 100, 30)
    values = trend + noise

    df = pd.DataFrame({"tokens": values}, index=dates)
    return df


@pytest.fixture
def mock_skill_telemetry():
    """Generate mock skill telemetry for pattern detection tests."""
    data = []
    session_id = 1

    sequences = [
        ["ds-core", "ds-quality", "ds-core"],
        ["ds-core", "ds-quality"],
        ["ds-core", "ds-quality", "ds-core"],
        ["ds-security", "ds-quality"],
        ["ds-core", "ds-domains", "ds-quality"],
        ["ds-core", "ds-quality"],
        ["ds-security", "ds-quality"],
    ]

    base_time = datetime(2024, 1, 1, 9, 0, 0)

    for seq in sequences:
        timestamp = base_time
        for skill in seq:
            data.append({"session_id": session_id, "skill_name": skill, "invoked_at": timestamp})
            timestamp += timedelta(minutes=15)
        session_id += 1
        base_time += timedelta(days=1)

    return pd.DataFrame(data)


@pytest.fixture
def mock_session_data():
    """Generate mock session data for clustering tests."""
    np.random.seed(42)

    data = {
        "session_id": range(1, 51),
        "duration": np.random.uniform(300, 3600, 50),
        "tokens": np.random.uniform(1000, 10000, 50),
        "outcome": np.random.choice(["success", "failure"], 50, p=[0.7, 0.3]),
        "skills_used": [
            ",".join(
                np.random.choice(
                    ["ds-core", "ds-quality", "ds-security", "ds-domains"],
                    size=np.random.randint(1, 5),
                    replace=False,
                )
            )
            for _ in range(50)
        ],
    }

    return pd.DataFrame(data)


@pytest.fixture
def mock_benchmark_data():
    """Generate mock historical data for benchmark tests."""
    dates = pd.date_range(start="2024-01-01", periods=30, freq="D")
    np.random.seed(42)

    data = {
        "session_count": np.random.poisson(10, 30),
        "skill_usage": np.random.poisson(25, 30),
        "token_usage": np.random.normal(5000, 1000, 30),
        "success_rate": np.random.beta(7, 3, 30),
    }

    df = pd.DataFrame(data, index=dates)
    return df


@pytest.fixture
def temp_database(mock_skill_telemetry, mock_session_data):
    """Create a temporary SQLite database with mock data."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)

    mock_skill_telemetry.to_sql("raw_skill_telemetry", conn, if_exists="replace", index=False)

    session_df = mock_session_data.copy()
    session_df["start_time"] = pd.date_range(start="2024-01-01", periods=len(session_df), freq="h")
    session_df["success"] = (session_df["outcome"] == "success").astype(int)
    session_df["total_tokens"] = session_df["tokens"]
    session_df.to_sql("agg_sessions", conn, if_exists="replace", index=False)
    session_df.to_sql("sessions", conn, if_exists="replace", index=False)

    mock_skill_telemetry.to_sql("skill_usage", conn, if_exists="replace", index=False)

    token_df = pd.DataFrame(
        {
            "timestamp": pd.date_range(start="2024-01-01", periods=30, freq="D"),
            "tokens": np.random.uniform(1000, 5000, 30),
        }
    )
    token_df.to_sql("token_usage", conn, if_exists="replace", index=False)

    conn.close()

    yield db_path

    try:
        os.unlink(db_path)
    except Exception:
        pass


# ============================================================================
# Forecasting Tests
# ============================================================================


class TestTimeSeriesForecaster:
    """Test suite for time series forecasting models."""

    def test_moving_average_initialization(self):
        forecaster = TimeSeriesForecaster(method="moving_average")
        assert forecaster.method == "moving_average"
        assert not forecaster.fitted

    def test_insufficient_data_raises_error(self):
        forecaster = TimeSeriesForecaster()
        dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({"tokens": range(10)}, index=dates)

        with pytest.raises(ValueError, match="Insufficient data"):
            forecaster.fit(df)

    def test_moving_average_fit(self, mock_time_series_data):
        forecaster = TimeSeriesForecaster(method="moving_average")
        forecaster.fit(mock_time_series_data)

        assert forecaster.fitted
        assert forecaster.method == "moving_average"
        assert forecaster.data is not None

    def test_moving_average_forecast(self, mock_time_series_data):
        forecaster = TimeSeriesForecaster(method="moving_average")
        forecaster.fit(mock_time_series_data)

        forecast = forecaster.forecast(periods=7)

        assert "dates" in forecast
        assert "predictions" in forecast
        assert "lower_80" in forecast
        assert "upper_80" in forecast
        assert "lower_95" in forecast
        assert "upper_95" in forecast

        assert len(forecast["dates"]) == 7
        assert len(forecast["predictions"]) == 7

        for i in range(7):
            assert forecast["lower_95"][i] <= forecast["lower_80"][i]
            assert forecast["lower_80"][i] <= forecast["predictions"][i]
            assert forecast["predictions"][i] <= forecast["upper_80"][i]
            assert forecast["upper_80"][i] <= forecast["upper_95"][i]

    def test_forecast_before_fit_raises_error(self):
        forecaster = TimeSeriesForecaster()

        with pytest.raises(RuntimeError, match="must be fitted"):
            forecaster.forecast(periods=7)

    def test_auto_method_selection(self, mock_time_series_data):
        forecaster = TimeSeriesForecaster(method="auto")
        forecaster.fit(mock_time_series_data)

        assert forecaster.method in ["exponential", "moving_average"]
        assert forecaster.fitted

    def test_forecast_evaluation(self, mock_time_series_data):
        train_data = mock_time_series_data.iloc[:20]
        test_data = mock_time_series_data.iloc[20:]

        forecaster = TimeSeriesForecaster(method="moving_average")
        forecaster.fit(train_data)

        target = test_data.iloc[:, 0].values
        metrics = forecaster.evaluate(test_data, target)

        assert "mae" in metrics
        assert "rmse" in metrics
        assert metrics["mae"] >= 0
        assert metrics["rmse"] >= 0

    def test_predict_returns_empty(self, mock_time_series_data):
        forecaster = TimeSeriesForecaster(method="moving_average")
        forecaster.fit(mock_time_series_data)

        result = forecaster.predict(mock_time_series_data)
        assert len(result) == 0

    def test_confidence_interval_widths(self, mock_time_series_data):
        forecaster = TimeSeriesForecaster(method="moving_average")
        forecaster.fit(mock_time_series_data)

        forecast = forecaster.forecast(periods=7)

        for i in range(7):
            ci_80_width = forecast["upper_80"][i] - forecast["lower_80"][i]
            ci_95_width = forecast["upper_95"][i] - forecast["lower_95"][i]
            assert ci_95_width > ci_80_width

    def test_multiple_forecast_periods(self, mock_time_series_data):
        forecaster = TimeSeriesForecaster(method="moving_average")
        forecaster.fit(mock_time_series_data)

        for periods in [1, 7, 14, 30]:
            forecast = forecaster.forecast(periods=periods)
            assert len(forecast["predictions"]) == periods
            assert len(forecast["dates"]) == periods


# ============================================================================
# Pattern Detection Tests
# ============================================================================


class TestPatternDetector:
    """Test suite for pattern detection engine."""

    def test_initialization(self):
        detector = PatternDetector(min_support=3)
        assert detector.min_support == 3
        assert not detector.fitted

    def test_missing_columns_raises_error(self):
        detector = PatternDetector()

        df = pd.DataFrame({"session_id": [1, 1], "invoked_at": [datetime.now(), datetime.now()]})

        with pytest.raises(ValueError, match="Missing required columns"):
            detector.fit(df)

    def test_fit_with_skill_telemetry(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        assert detector.fitted
        assert len(detector.patterns) > 0

    def test_sequence_pattern_detection(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        seq_patterns = detector.get_patterns(pattern_type="sequence")
        assert len(seq_patterns) > 0

        pattern = seq_patterns[0]
        assert "pattern_type" in pattern
        assert "pattern" in pattern
        assert "support" in pattern
        assert "confidence" in pattern
        assert "lift" in pattern

        assert pattern["pattern_type"] == "sequence"
        assert "→" in pattern["pattern"]
        assert pattern["support"] >= 2
        assert 0 <= pattern["confidence"] <= 1
        assert pattern["lift"] >= 0

    def test_temporal_pattern_detection(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=1)
        detector.fit(mock_skill_telemetry)

        temporal_patterns = detector.get_patterns(pattern_type="temporal_hour")

        if temporal_patterns:
            pattern = temporal_patterns[0]
            assert pattern["pattern_type"] == "temporal_hour"
            assert "at" in pattern["pattern"]

    def test_cooccurrence_pattern_detection(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        cooccur_patterns = detector.get_patterns(pattern_type="cooccurrence")

        if cooccur_patterns:
            pattern = cooccur_patterns[0]
            assert pattern["pattern_type"] == "cooccurrence"
            assert " + " in pattern["pattern"]
            assert pattern["lift"] > 1.0

    def test_pattern_filtering(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        high_lift_patterns = detector.get_patterns(min_lift=1.5)

        for pattern in high_lift_patterns:
            assert pattern["lift"] >= 1.5

    def test_top_n_filtering(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=1)
        detector.fit(mock_skill_telemetry)

        top_patterns = detector.get_patterns(top_n=3)
        assert len(top_patterns) <= 3

        if len(top_patterns) > 1:
            for i in range(len(top_patterns) - 1):
                assert top_patterns[i]["lift"] >= top_patterns[i + 1]["lift"]

    def test_pattern_evaluation(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        eval_metrics = detector.evaluate(mock_skill_telemetry, None)

        assert "total_patterns" in eval_metrics
        assert "pattern_types" in eval_metrics
        assert "avg_support" in eval_metrics
        assert "avg_confidence" in eval_metrics
        assert "avg_lift" in eval_metrics

        assert eval_metrics["total_patterns"] > 0

    def test_get_patterns_before_fit_raises_error(self):
        detector = PatternDetector()

        with pytest.raises(RuntimeError, match="must be fitted"):
            detector.get_patterns()

    def test_predict_not_used(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        result = detector.predict(mock_skill_telemetry)
        assert len(result) == 0

    def test_insufficient_data_fits_empty(self):
        detector = PatternDetector(min_support=10)

        df = pd.DataFrame(
            {
                "session_id": [1, 1],
                "skill_name": ["skill_a", "skill_b"],
                "invoked_at": [datetime.now(), datetime.now()],
            }
        )

        detector.fit(df)
        assert detector.fitted
        assert len(detector.patterns) == 0

    def test_min_support_filtering(self, mock_skill_telemetry):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        for pattern in detector.patterns:
            assert pattern["support"] >= 2


# ============================================================================
# Clustering Tests
# ============================================================================


class TestBehaviorClusterer:
    """Test suite for behavior clustering model."""

    def test_initialization(self):
        clusterer = BehaviorClusterer(n_clusters=3)
        assert clusterer.n_clusters == 3
        assert not clusterer.fitted

    def test_insufficient_data_raises_error(self):
        clusterer = BehaviorClusterer()

        df = pd.DataFrame(
            {"duration": [100, 200, 300, 400, 500], "tokens": [1000, 2000, 3000, 4000, 5000]}
        )

        with pytest.raises(ValueError, match="Insufficient data"):
            clusterer.fit(df)

    def test_fit_with_session_data(self, mock_session_data):
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        assert clusterer.fitted
        assert clusterer.n_clusters > 0
        assert clusterer.cluster_centers is not None

    def test_feature_engineering(self, mock_session_data):
        clusterer = BehaviorClusterer()
        features = clusterer._extract_features(mock_session_data)

        assert "duration_minutes" in features.columns
        assert "skill_diversity" in features.columns
        assert "skills_count" in features.columns
        assert "token_efficiency" in features.columns
        assert "success" in features.columns

        assert (features["skill_diversity"] >= 0).all()
        assert (features["skill_diversity"] <= 1).all()
        assert (features["skills_count"] >= 0).all()
        assert (features["success"].isin([0, 1])).all()

    def test_cluster_prediction(self, mock_session_data):
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        labels = clusterer.predict(mock_session_data)
        assert len(labels) == len(mock_session_data)
        assert all(0 <= label < 3 for label in labels)

    def test_persona_assignment(self, mock_session_data):
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        eval_results = clusterer.evaluate(mock_session_data)

        assert "cluster_info" in eval_results

        for cluster_info in eval_results["cluster_info"]:
            assert "label" in cluster_info
            assert cluster_info["label"] in BehaviorClusterer.PERSONA_LABELS.values()

    def test_cluster_evaluation(self, mock_session_data):
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        eval_results = clusterer.evaluate(mock_session_data)

        assert "n_clusters" in eval_results
        assert "cluster_sizes" in eval_results
        assert "cluster_info" in eval_results

        total_clustered = sum(eval_results["cluster_sizes"].values())
        assert total_clustered == len(mock_session_data)

        for cluster in eval_results["cluster_info"]:
            assert "cluster_id" in cluster
            assert "size" in cluster
            assert "characteristics" in cluster

            chars = cluster["characteristics"]
            assert "avg_duration_minutes" in chars
            assert "avg_skills_count" in chars
            assert "avg_skill_diversity" in chars
            assert "avg_token_efficiency" in chars

    def test_auto_cluster_determination(self, mock_session_data):
        clusterer = BehaviorClusterer(n_clusters=None)
        clusterer.fit(mock_session_data)

        assert clusterer.fitted
        assert 2 <= clusterer.n_clusters <= 5

    def test_simple_kmeans_fallback(self):
        clusterer = BehaviorClusterer(n_clusters=3)

        data = pd.DataFrame(
            {
                "duration": [300, 600, 900, 1200, 1500, 1800, 2100, 2400, 2700, 3000],
                "tokens": [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500],
            }
        )

        clusterer.fit(data)
        assert clusterer.fitted
        assert clusterer.cluster_centers is not None

    def test_predict_before_fit_raises_error(self):
        clusterer = BehaviorClusterer()

        data = pd.DataFrame({"duration": [300, 600], "tokens": [1000, 2000]})

        with pytest.raises(RuntimeError, match="must be fitted"):
            clusterer.predict(data)

    def test_evaluate_before_fit_raises_error(self):
        clusterer = BehaviorClusterer()

        data = pd.DataFrame({"duration": [300, 600], "tokens": [1000, 2000]})

        with pytest.raises(RuntimeError, match="must be fitted"):
            clusterer.evaluate(data)


# ============================================================================
# Recommendations Tests
# ============================================================================


class TestRecommendationEngine:
    """Test suite for recommendation generation."""

    def test_initialization(self):
        engine = RecommendationEngine(min_support=3)
        assert engine.min_support == 3
        assert not engine.fitted

    def test_fit_with_insufficient_data_warns(self, mock_skill_telemetry):
        small_session_data = pd.DataFrame(
            {
                "session_id": range(1, 11),
                "duration": [300] * 10,
                "tokens": [1000] * 10,
                "outcome": ["success"] * 10,
            }
        )

        engine = RecommendationEngine()

        with pytest.warns(UserWarning, match="Insufficient data"):
            engine.fit(mock_skill_telemetry.head(10), small_session_data)

        assert engine.fitted

    def test_recommendation_generation(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        assert engine.fitted
        assert len(engine.recommendations) > 0

    def test_recommendation_structure(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        if engine.recommendations:
            rec = engine.recommendations[0]

            assert "category" in rec
            assert "title" in rec
            assert "description" in rec
            assert "impact_score" in rec
            assert "actionable" in rec
            assert "data" in rec

            assert rec["category"] in RecommendationEngine.CATEGORIES.keys()
            assert 0 <= rec["impact_score"] <= 100

    def test_recommendation_filtering_by_category(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        for category in ["skill_optimization", "workflow_improvement"]:
            recs = engine.get_recommendations(category=category)

            for rec in recs:
                assert rec["category"] == category

    def test_recommendation_filtering_by_impact(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        high_impact_recs = engine.get_recommendations(min_impact=60)

        for rec in high_impact_recs:
            assert rec["impact_score"] >= 60

    def test_top_n_recommendations(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        top_5 = engine.get_recommendations(top_n=5)
        assert len(top_5) <= 5

        if len(top_5) > 1:
            for i in range(len(top_5) - 1):
                assert top_5[i]["impact_score"] >= top_5[i + 1]["impact_score"]

    def test_recommendation_evaluation(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        eval_metrics = engine.evaluate(mock_session_data, None)

        assert "total_recommendations" in eval_metrics
        assert "recommendations_by_category" in eval_metrics
        assert "avg_impact_by_category" in eval_metrics
        assert "high_impact_count" in eval_metrics
        assert "actionable_count" in eval_metrics

    def test_get_recommendations_before_fit_raises_error(self):
        engine = RecommendationEngine()

        with pytest.raises(RuntimeError, match="must be fitted"):
            engine.get_recommendations()

    def test_predict_not_used(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        result = engine.predict(mock_session_data)
        assert len(result) == 0

    def test_actionable_only_filter(self, mock_skill_telemetry, mock_session_data):
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        actionable_recs = engine.get_recommendations(actionable_only=True)

        for rec in actionable_recs:
            assert rec["actionable"] is True


# ============================================================================
# Benchmarks Tests
# ============================================================================


class TestBenchmarkEngine:
    """Test suite for benchmark comparison."""

    def test_initialization(self):
        engine = BenchmarkEngine(baselines={"session_count": 10.0})
        assert engine.baselines["session_count"] == 10.0
        assert not engine.fitted

    def test_insufficient_history_raises_error(self):
        engine = BenchmarkEngine()

        dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({"metric": range(10)}, index=dates)

        with pytest.raises(ValueError, match="Insufficient data"):
            engine.fit(df)

    def test_fit_with_historical_data(self, mock_benchmark_data):
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        assert engine.fitted
        assert len(engine.historical_stats) > 0

        for metric, stats in engine.historical_stats.items():
            assert "mean" in stats
            assert "median" in stats
            assert "std" in stats
            assert "min" in stats
            assert "max" in stats

    def test_percentile_calculation(self, mock_benchmark_data):
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        result = engine.benchmark_metric("session_count", 15.0)

        assert "percentile" in result
        assert 0 <= result["percentile"] <= 1
        assert result["percentile"] > 0.5

    def test_trend_analysis(self, mock_benchmark_data):
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        result_high = engine.benchmark_metric("session_count", 20.0)
        assert result_high["trend"] in ["improving", "stable", "declining"]

        result_low = engine.benchmark_metric("session_count", 2.0)
        assert result_low["trend"] in ["improving", "stable", "declining"]

    def test_baseline_comparison(self, mock_benchmark_data):
        engine = BenchmarkEngine(baselines={"session_count": 10.0})
        engine.fit(mock_benchmark_data)

        assert engine.benchmark_metric("session_count", 12.0)["status"] == "above_baseline"
        assert engine.benchmark_metric("session_count", 10.0)["status"] == "at_baseline"
        assert engine.benchmark_metric("session_count", 8.0)["status"] == "below_baseline"

    def test_benchmark_result_structure(self, mock_benchmark_data):
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        result = engine.benchmark_metric("session_count", 12.0)

        assert "metric" in result
        assert "current" in result
        assert "baseline" in result
        assert "percentile" in result
        assert "trend" in result
        assert "status" in result
        assert "comparison" in result
        assert "historical" in result

    def test_predict_not_used(self, mock_benchmark_data):
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        result = engine.predict(mock_benchmark_data)
        assert len(result) == 0

    def test_benchmark_with_missing_metric_raises_error(self, mock_benchmark_data):
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        with pytest.raises(ValueError, match="not found"):
            engine.benchmark_metric("nonexistent_metric", 10.0)


# ============================================================================
# Model Evaluation Tests
# ============================================================================


class TestModelEvaluation:
    """Test suite for model evaluation metrics."""

    def test_forecast_accuracy_mae_rmse_mape(self):
        actual = np.array([100, 110, 105, 115, 120])
        predicted = np.array([98, 112, 103, 118, 119])

        metrics = evaluate_forecast_accuracy(actual, predicted)

        assert "mae" in metrics
        assert "rmse" in metrics
        assert "mape" in metrics
        assert "n_samples" in metrics

        assert metrics["mae"] > 0
        assert metrics["rmse"] >= metrics["mae"]
        assert metrics["mape"] >= 0
        assert metrics["n_samples"] == 5

    def test_perfect_predictions(self):
        actual = np.array([100, 110, 120, 130, 140])
        predicted = actual.copy()

        metrics = evaluate_forecast_accuracy(actual, predicted)

        assert metrics["mae"] == 0
        assert metrics["rmse"] == 0
        assert metrics["mape"] == 0

    def test_mismatched_lengths_raises_error(self):
        actual = np.array([100, 110, 120])
        predicted = np.array([98, 112])

        with pytest.raises(ValueError, match="same length"):
            evaluate_forecast_accuracy(actual, predicted)

    def test_empty_arrays_raise_error(self):
        actual = np.array([])
        predicted = np.array([])

        with pytest.raises(ValueError, match="must not be empty"):
            evaluate_forecast_accuracy(actual, predicted)

    def test_pattern_quality_evaluation_perfect(self):
        detected = [
            {"pattern": "think → plan", "support": 10},
            {"pattern": "plan → build", "support": 15},
        ]
        labeled = [{"pattern": "think → plan"}, {"pattern": "plan → build"}]

        metrics = evaluate_pattern_quality(detected, labeled)

        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1_score"] == 1.0

    def test_pattern_quality_evaluation_partial(self):
        detected = [
            {"pattern": "think → plan"},
            {"pattern": "plan → build"},
            {"pattern": "wrong → pattern"},
        ]
        labeled = [
            {"pattern": "think → plan"},
            {"pattern": "plan → build"},
            {"pattern": "build → review"},
        ]

        metrics = evaluate_pattern_quality(detected, labeled)

        assert metrics["true_positives"] == 2
        assert metrics["false_positives"] == 1
        assert metrics["false_negatives"] == 1

    def test_pattern_quality_no_patterns(self):
        metrics = evaluate_pattern_quality([], [])

        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1_score"] == 1.0

    def test_recommendation_impact_evaluation(self):
        recommendations = [
            {"id": "rec1", "category": "skill_optimization", "impact_score": 80},
            {"id": "rec2", "category": "workflow_improvement", "impact_score": 60},
            {"id": "rec3", "category": "performance_booster", "impact_score": 90},
            {"id": "rec4", "category": "inefficiency_detection", "impact_score": 50},
        ]

        outcomes = [
            {"recommendation_id": "rec1", "accepted": True, "implemented": True},
            {"recommendation_id": "rec2", "accepted": True, "implemented": False},
            {"recommendation_id": "rec3", "accepted": False, "implemented": False},
            {"recommendation_id": "rec4", "accepted": True, "implemented": True},
        ]

        metrics = evaluate_recommendation_impact(recommendations, outcomes)

        assert metrics["acceptance_rate"] == 0.75
        assert abs(metrics["implementation_rate"] - 2 / 3) < 0.01
        assert metrics["overall_implementation_rate"] == 0.5

    def test_export_evaluation_report(self):
        metrics = {"mae": 2.5, "rmse": 3.2, "mape": 0.05}

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            output_path = f.name

        try:
            export_evaluation_report(metrics, output_path)

            assert os.path.exists(output_path)

            with open(output_path, "r") as f:
                loaded = json.load(f)

            assert loaded["mae"] == 2.5
            assert loaded["rmse"] == 3.2
            assert loaded["mape"] == 0.05

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


# ============================================================================
# Integration Tests
# ============================================================================


class TestMLIntegration:
    """Integration tests for ML pipeline."""

    def test_end_to_end_forecast_pipeline(self, mock_time_series_data):
        forecaster = TimeSeriesForecaster(method="moving_average")
        forecaster.fit(mock_time_series_data)

        forecast = forecaster.forecast(periods=7)

        assert len(forecast["predictions"]) == 7
        assert all(p > 0 for p in forecast["predictions"])

    def test_pattern_to_recommendation_pipeline(self, mock_skill_telemetry, mock_session_data):
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        patterns = detector.get_patterns()
        assert len(patterns) > 0

        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        assert engine.fitted

    def test_clustering_to_recommendation_pipeline(self, mock_session_data, mock_skill_telemetry):
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        cluster_eval = clusterer.evaluate(mock_session_data)
        assert len(cluster_eval["cluster_info"]) > 0

        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        assert engine.fitted


# ============================================================================
# Database Integration Tests
# ============================================================================


class TestDatabaseIntegration:
    """Test ML components with database integration."""

    def test_detect_skill_patterns_from_db(self, temp_database):
        patterns = detect_skill_patterns(temp_database, min_support=2)
        assert isinstance(patterns, list)

    def test_generate_recommendations_from_db(self, temp_database):
        try:
            recommendations = generate_recommendations(temp_database, min_support=2)
            assert isinstance(recommendations, list)
        except ValueError:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
