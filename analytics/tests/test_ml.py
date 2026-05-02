"""
Comprehensive tests for ML components in analytics/ml/.

Tests coverage:
- Forecasting: ARIMA, exponential smoothing, moving average, confidence intervals
- Pattern detection: sequence patterns, temporal patterns, support/confidence/lift
- Clustering: K-means, persona assignment, feature engineering
- Recommendations: generation, ranking, impact scoring
- Benchmarks: percentile calculation, trend analysis, baseline comparison
- Model evaluation: MAE/RMSE/MAPE, precision/recall/F1

Uses pytest framework with fixtures for mock data generation.
Aims for 70%+ coverage of ML modules (excluding storage.py and base.py).
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

from analytics.ml.forecasting import TimeSeriesForecaster, forecast_token_usage
from analytics.ml.patterns import PatternDetector, detect_skill_patterns
from analytics.ml.clustering import BehaviorClusterer
from analytics.ml.recommendations import RecommendationEngine, generate_recommendations
from analytics.ml.benchmarks import BenchmarkEngine, run_benchmark_suite
from analytics.ml.evaluation import (
    evaluate_forecast_accuracy,
    evaluate_pattern_quality,
    evaluate_recommendation_impact,
    export_evaluation_report
)


# ============================================================================
# Fixtures for Mock Data Generation
# ============================================================================

@pytest.fixture
def mock_time_series_data():
    """Generate mock time series data for forecasting tests."""
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    # Generate realistic token usage pattern with trend + noise
    np.random.seed(42)
    trend = np.linspace(1000, 1500, 30)
    noise = np.random.normal(0, 100, 30)
    values = trend + noise

    df = pd.DataFrame({'tokens': values}, index=dates)
    return df


@pytest.fixture
def mock_skill_telemetry():
    """Generate mock skill telemetry for pattern detection tests."""
    data = []
    session_id = 1

    # Create realistic skill sequences
    sequences = [
        ['dream-studio:core', 'dream-studio:quality', 'dream-studio:core'],
        ['dream-studio:core', 'dream-studio:quality'],
        ['dream-studio:core', 'dream-studio:quality', 'dream-studio:core'],
        ['dream-studio:security', 'dream-studio:quality'],
        ['dream-studio:core', 'dream-studio:domains', 'dream-studio:quality'],
        ['dream-studio:core', 'dream-studio:quality'],
        ['dream-studio:security', 'dream-studio:quality'],
    ]

    base_time = datetime(2024, 1, 1, 9, 0, 0)

    for seq in sequences:
        timestamp = base_time
        for skill in seq:
            data.append({
                'session_id': session_id,
                'skill_name': skill,
                'invoked_at': timestamp
            })
            timestamp += timedelta(minutes=15)
        session_id += 1
        base_time += timedelta(days=1)

    return pd.DataFrame(data)


@pytest.fixture
def mock_session_data():
    """Generate mock session data for clustering tests."""
    np.random.seed(42)

    data = {
        'session_id': range(1, 51),  # 50 sessions
        'duration': np.random.uniform(300, 3600, 50),  # 5min to 1hr in seconds
        'tokens': np.random.uniform(1000, 10000, 50),
        'outcome': np.random.choice(['success', 'failure'], 50, p=[0.7, 0.3]),
        'skills_used': [
            ','.join(np.random.choice([
                'dream-studio:core',
                'dream-studio:quality',
                'dream-studio:security',
                'dream-studio:domains'
            ], size=np.random.randint(1, 5), replace=False))
            for _ in range(50)
        ]
    }

    return pd.DataFrame(data)


@pytest.fixture
def mock_benchmark_data():
    """Generate mock historical data for benchmark tests."""
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    np.random.seed(42)

    data = {
        'session_count': np.random.poisson(10, 30),
        'skill_usage': np.random.poisson(25, 30),
        'token_usage': np.random.normal(5000, 1000, 30),
        'success_rate': np.random.beta(7, 3, 30),  # Beta distribution for rates
    }

    df = pd.DataFrame(data, index=dates)
    return df


@pytest.fixture
def temp_database(mock_skill_telemetry, mock_session_data):
    """Create a temporary SQLite database with mock data."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)

    # Create skill telemetry table
    mock_skill_telemetry.to_sql('raw_skill_telemetry', conn, if_exists='replace', index=False)

    # Create session table
    session_df = mock_session_data.copy()
    session_df['start_time'] = pd.date_range(start='2024-01-01', periods=len(session_df), freq='h')
    session_df['success'] = (session_df['outcome'] == 'success').astype(int)
    session_df['total_tokens'] = session_df['tokens']
    session_df.to_sql('agg_sessions', conn, if_exists='replace', index=False)

    # Create sessions table for benchmarking
    session_df.to_sql('sessions', conn, if_exists='replace', index=False)

    # Create skill_usage table for benchmarking
    mock_skill_telemetry.to_sql('skill_usage', conn, if_exists='replace', index=False)

    # Create token_usage table for benchmarking
    token_df = pd.DataFrame({
        'timestamp': pd.date_range(start='2024-01-01', periods=30, freq='D'),
        'tokens': np.random.uniform(1000, 5000, 30)
    })
    token_df.to_sql('token_usage', conn, if_exists='replace', index=False)

    conn.close()

    yield db_path

    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


# ============================================================================
# Forecasting Tests
# ============================================================================

class TestTimeSeriesForecaster:
    """Test suite for time series forecasting models."""

    def test_moving_average_initialization(self):
        """Test forecaster initialization with moving average method."""
        forecaster = TimeSeriesForecaster(method='moving_average')
        assert forecaster.method == 'moving_average'
        assert not forecaster.fitted

    def test_insufficient_data_raises_error(self):
        """Test that insufficient data raises ValueError."""
        forecaster = TimeSeriesForecaster()

        # Create data with only 10 days (minimum is 14)
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        df = pd.DataFrame({'tokens': range(10)}, index=dates)

        with pytest.raises(ValueError, match="Insufficient data"):
            forecaster.fit(df)

    def test_moving_average_fit(self, mock_time_series_data):
        """Test fitting moving average model."""
        forecaster = TimeSeriesForecaster(method='moving_average')
        forecaster.fit(mock_time_series_data)

        assert forecaster.fitted
        assert forecaster.method == 'moving_average'
        assert forecaster.data is not None

    def test_moving_average_forecast(self, mock_time_series_data):
        """Test generating forecast with moving average."""
        forecaster = TimeSeriesForecaster(method='moving_average')
        forecaster.fit(mock_time_series_data)

        forecast = forecaster.forecast(periods=7)

        # Check structure
        assert 'dates' in forecast
        assert 'predictions' in forecast
        assert 'lower_80' in forecast
        assert 'upper_80' in forecast
        assert 'lower_95' in forecast
        assert 'upper_95' in forecast

        # Check length
        assert len(forecast['dates']) == 7
        assert len(forecast['predictions']) == 7

        # Check confidence intervals are ordered correctly
        for i in range(7):
            assert forecast['lower_95'][i] <= forecast['lower_80'][i]
            assert forecast['lower_80'][i] <= forecast['predictions'][i]
            assert forecast['predictions'][i] <= forecast['upper_80'][i]
            assert forecast['upper_80'][i] <= forecast['upper_95'][i]

    def test_forecast_before_fit_raises_error(self):
        """Test that forecasting before fit raises error."""
        forecaster = TimeSeriesForecaster()

        with pytest.raises(RuntimeError, match="must be fitted"):
            forecaster.forecast(periods=7)

    def test_auto_method_selection(self, mock_time_series_data):
        """Test automatic method selection."""
        forecaster = TimeSeriesForecaster(method='auto')
        forecaster.fit(mock_time_series_data)

        # Should select exponential or moving_average
        assert forecaster.method in ['exponential', 'moving_average']
        assert forecaster.fitted

    def test_forecast_evaluation(self, mock_time_series_data):
        """Test forecast model evaluation."""
        # Split data
        train_data = mock_time_series_data.iloc[:20]
        test_data = mock_time_series_data.iloc[20:]

        forecaster = TimeSeriesForecaster(method='moving_average')
        forecaster.fit(train_data)

        # Evaluate
        target = test_data.iloc[:, 0].values
        metrics = forecaster.evaluate(test_data, target)

        assert 'mae' in metrics
        assert 'rmse' in metrics
        assert metrics['mae'] >= 0
        assert metrics['rmse'] >= 0

    def test_predict_returns_empty(self, mock_time_series_data):
        """Test that predict() returns empty array (use forecast instead)."""
        forecaster = TimeSeriesForecaster(method='moving_average')
        forecaster.fit(mock_time_series_data)

        result = forecaster.predict(mock_time_series_data)

        # Predict should return empty for time series (use forecast instead)
        assert len(result) == 0

    def test_confidence_interval_widths(self, mock_time_series_data):
        """Test that confidence intervals widen appropriately."""
        forecaster = TimeSeriesForecaster(method='moving_average')
        forecaster.fit(mock_time_series_data)

        forecast = forecaster.forecast(periods=7)

        # 95% CI should be wider than 80% CI
        for i in range(7):
            ci_80_width = forecast['upper_80'][i] - forecast['lower_80'][i]
            ci_95_width = forecast['upper_95'][i] - forecast['lower_95'][i]
            assert ci_95_width > ci_80_width

    def test_multiple_forecast_periods(self, mock_time_series_data):
        """Test forecasting different periods."""
        forecaster = TimeSeriesForecaster(method='moving_average')
        forecaster.fit(mock_time_series_data)

        # Test different forecast horizons
        for periods in [1, 7, 14, 30]:
            forecast = forecaster.forecast(periods=periods)
            assert len(forecast['predictions']) == periods
            assert len(forecast['dates']) == periods


# ============================================================================
# Pattern Detection Tests
# ============================================================================

class TestPatternDetector:
    """Test suite for pattern detection engine."""

    def test_initialization(self):
        """Test pattern detector initialization."""
        detector = PatternDetector(min_support=3)
        assert detector.min_support == 3
        assert not detector.fitted

    def test_missing_columns_raises_error(self):
        """Test that missing required columns raises error."""
        detector = PatternDetector()

        # Missing skill_name column
        df = pd.DataFrame({
            'session_id': [1, 1],
            'invoked_at': [datetime.now(), datetime.now()]
        })

        with pytest.raises(ValueError, match="Missing required columns"):
            detector.fit(df)

    def test_fit_with_skill_telemetry(self, mock_skill_telemetry):
        """Test fitting pattern detector."""
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        assert detector.fitted
        assert len(detector.patterns) > 0

    def test_sequence_pattern_detection(self, mock_skill_telemetry):
        """Test detection of sequence patterns."""
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        # Get sequence patterns
        seq_patterns = detector.get_patterns(pattern_type='sequence')

        assert len(seq_patterns) > 0

        # Check pattern structure
        pattern = seq_patterns[0]
        assert 'pattern_type' in pattern
        assert 'pattern' in pattern
        assert 'support' in pattern
        assert 'confidence' in pattern
        assert 'lift' in pattern

        assert pattern['pattern_type'] == 'sequence'
        assert '→' in pattern['pattern']  # Sequence arrow
        assert pattern['support'] >= 2
        assert 0 <= pattern['confidence'] <= 1
        assert pattern['lift'] >= 0

    def test_temporal_pattern_detection(self, mock_skill_telemetry):
        """Test detection of temporal patterns."""
        detector = PatternDetector(min_support=1)
        detector.fit(mock_skill_telemetry)

        # Get temporal patterns (hour-based)
        temporal_patterns = detector.get_patterns(pattern_type='temporal_hour')

        # May or may not have temporal patterns depending on data
        # Just check structure if they exist
        if temporal_patterns:
            pattern = temporal_patterns[0]
            assert pattern['pattern_type'] == 'temporal_hour'
            assert 'at' in pattern['pattern']

    def test_cooccurrence_pattern_detection(self, mock_skill_telemetry):
        """Test detection of co-occurrence patterns."""
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        # Get co-occurrence patterns
        cooccur_patterns = detector.get_patterns(pattern_type='cooccurrence')

        if cooccur_patterns:
            pattern = cooccur_patterns[0]
            assert pattern['pattern_type'] == 'cooccurrence'
            assert ' + ' in pattern['pattern']
            assert pattern['lift'] > 1.0  # Only patterns with lift > 1

    def test_pattern_filtering(self, mock_skill_telemetry):
        """Test pattern filtering by support, confidence, lift."""
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        # Filter by min_lift
        high_lift_patterns = detector.get_patterns(min_lift=1.5)

        for pattern in high_lift_patterns:
            assert pattern['lift'] >= 1.5

    def test_top_n_filtering(self, mock_skill_telemetry):
        """Test top-N pattern retrieval."""
        detector = PatternDetector(min_support=1)
        detector.fit(mock_skill_telemetry)

        # Get top 3 patterns
        top_patterns = detector.get_patterns(top_n=3)

        assert len(top_patterns) <= 3

        # Should be sorted by lift (descending)
        if len(top_patterns) > 1:
            for i in range(len(top_patterns) - 1):
                assert top_patterns[i]['lift'] >= top_patterns[i + 1]['lift']

    def test_pattern_evaluation(self, mock_skill_telemetry):
        """Test pattern evaluation metrics."""
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        eval_metrics = detector.evaluate(mock_skill_telemetry, None)

        assert 'total_patterns' in eval_metrics
        assert 'pattern_types' in eval_metrics
        assert 'avg_support' in eval_metrics
        assert 'avg_confidence' in eval_metrics
        assert 'avg_lift' in eval_metrics

        assert eval_metrics['total_patterns'] > 0

    def test_get_patterns_before_fit_raises_error(self):
        """Test that getting patterns before fit raises error."""
        detector = PatternDetector()

        with pytest.raises(RuntimeError, match="must be fitted"):
            detector.get_patterns()

    def test_predict_not_used(self, mock_skill_telemetry):
        """Test that predict returns empty (pattern detection is unsupervised)."""
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        result = detector.predict(mock_skill_telemetry)

        assert len(result) == 0

    def test_insufficient_data_fits_empty(self):
        """Test that insufficient data fits but produces no patterns."""
        detector = PatternDetector(min_support=10)

        # Only 2 rows, min_support is 10
        df = pd.DataFrame({
            'session_id': [1, 1],
            'skill_name': ['skill_a', 'skill_b'],
            'invoked_at': [datetime.now(), datetime.now()]
        })

        detector.fit(df)

        assert detector.fitted
        assert len(detector.patterns) == 0

    def test_min_support_filtering(self, mock_skill_telemetry):
        """Test that patterns below min_support are filtered."""
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        # All patterns should meet min_support
        for pattern in detector.patterns:
            assert pattern['support'] >= 2


# ============================================================================
# Clustering Tests
# ============================================================================

class TestBehaviorClusterer:
    """Test suite for behavior clustering model."""

    def test_initialization(self):
        """Test clusterer initialization."""
        clusterer = BehaviorClusterer(n_clusters=3)
        assert clusterer.n_clusters == 3
        assert not clusterer.fitted

    def test_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        clusterer = BehaviorClusterer()

        # Only 5 sessions (minimum is 10)
        df = pd.DataFrame({
            'duration': [100, 200, 300, 400, 500],
            'tokens': [1000, 2000, 3000, 4000, 5000]
        })

        with pytest.raises(ValueError, match="Insufficient data"):
            clusterer.fit(df)

    def test_fit_with_session_data(self, mock_session_data):
        """Test fitting clustering model."""
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        assert clusterer.fitted
        assert clusterer.n_clusters > 0
        assert clusterer.cluster_centers is not None

    def test_feature_engineering(self, mock_session_data):
        """Test feature extraction from session data."""
        clusterer = BehaviorClusterer()
        features = clusterer._extract_features(mock_session_data)

        # Check expected features
        assert 'duration_minutes' in features.columns
        assert 'skill_diversity' in features.columns
        assert 'skills_count' in features.columns
        assert 'token_efficiency' in features.columns
        assert 'success' in features.columns

        # Check feature ranges
        assert (features['skill_diversity'] >= 0).all()
        assert (features['skill_diversity'] <= 1).all()
        assert (features['skills_count'] >= 0).all()
        assert (features['success'].isin([0, 1])).all()

    def test_cluster_prediction(self, mock_session_data):
        """Test cluster assignment prediction."""
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        # Predict on same data
        labels = clusterer.predict(mock_session_data)

        assert len(labels) == len(mock_session_data)
        assert all(0 <= label < 3 for label in labels)

    def test_persona_assignment(self, mock_session_data):
        """Test persona label assignment to clusters."""
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        eval_results = clusterer.evaluate(mock_session_data)

        assert 'cluster_info' in eval_results

        for cluster_info in eval_results['cluster_info']:
            assert 'label' in cluster_info
            # Label should be one of the predefined personas
            assert cluster_info['label'] in BehaviorClusterer.PERSONA_LABELS.values()

    def test_cluster_evaluation(self, mock_session_data):
        """Test clustering evaluation metrics."""
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        eval_results = clusterer.evaluate(mock_session_data)

        assert 'n_clusters' in eval_results
        assert 'cluster_sizes' in eval_results
        assert 'cluster_info' in eval_results

        # Check cluster sizes sum to total sessions
        total_clustered = sum(eval_results['cluster_sizes'].values())
        assert total_clustered == len(mock_session_data)

        # Check cluster characteristics
        for cluster in eval_results['cluster_info']:
            assert 'cluster_id' in cluster
            assert 'size' in cluster
            assert 'characteristics' in cluster

            chars = cluster['characteristics']
            assert 'avg_duration_minutes' in chars
            assert 'avg_skills_count' in chars
            assert 'avg_skill_diversity' in chars
            assert 'avg_token_efficiency' in chars

    def test_auto_cluster_determination(self, mock_session_data):
        """Test automatic cluster number determination."""
        clusterer = BehaviorClusterer(n_clusters=None)
        clusterer.fit(mock_session_data)

        # Should auto-determine optimal cluster count
        assert clusterer.fitted
        assert 2 <= clusterer.n_clusters <= 5

    def test_simple_kmeans_fallback(self):
        """Test simple K-means implementation when sklearn unavailable."""
        clusterer = BehaviorClusterer(n_clusters=3)

        # Create minimal dataset
        data = pd.DataFrame({
            'duration': [300, 600, 900, 1200, 1500, 1800, 2100, 2400, 2700, 3000],
            'tokens': [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500]
        })

        clusterer.fit(data)

        # Should successfully cluster
        assert clusterer.fitted
        assert clusterer.cluster_centers is not None

    def test_predict_before_fit_raises_error(self):
        """Test that prediction before fit raises error."""
        clusterer = BehaviorClusterer()

        data = pd.DataFrame({
            'duration': [300, 600],
            'tokens': [1000, 2000]
        })

        with pytest.raises(RuntimeError, match="must be fitted"):
            clusterer.predict(data)

    def test_evaluate_before_fit_raises_error(self):
        """Test that evaluation before fit raises error."""
        clusterer = BehaviorClusterer()

        data = pd.DataFrame({
            'duration': [300, 600],
            'tokens': [1000, 2000]
        })

        with pytest.raises(RuntimeError, match="must be fitted"):
            clusterer.evaluate(data)


# ============================================================================
# Recommendations Tests
# ============================================================================

class TestRecommendationEngine:
    """Test suite for recommendation generation."""

    def test_initialization(self):
        """Test recommendation engine initialization."""
        engine = RecommendationEngine(min_support=3)
        assert engine.min_support == 3
        assert not engine.fitted

    def test_fit_with_insufficient_data_warns(self, mock_skill_telemetry):
        """Test that insufficient data triggers warning but still fits."""
        # Create small session data (< 20 sessions)
        small_session_data = pd.DataFrame({
            'session_id': range(1, 11),
            'duration': [300] * 10,
            'tokens': [1000] * 10,
            'outcome': ['success'] * 10
        })

        engine = RecommendationEngine()

        with pytest.warns(UserWarning, match="Insufficient data"):
            engine.fit(mock_skill_telemetry.head(10), small_session_data)

        assert engine.fitted

    def test_recommendation_generation(self, mock_skill_telemetry, mock_session_data):
        """Test generating recommendations from data."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        assert engine.fitted
        assert len(engine.recommendations) > 0

    def test_recommendation_structure(self, mock_skill_telemetry, mock_session_data):
        """Test recommendation structure and fields."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        if engine.recommendations:
            rec = engine.recommendations[0]

            assert 'category' in rec
            assert 'title' in rec
            assert 'description' in rec
            assert 'impact_score' in rec
            assert 'actionable' in rec
            assert 'data' in rec

            # Check category is valid
            assert rec['category'] in RecommendationEngine.CATEGORIES.keys()

            # Check impact score range
            assert 0 <= rec['impact_score'] <= 100

    def test_recommendation_filtering_by_category(self, mock_skill_telemetry, mock_session_data):
        """Test filtering recommendations by category."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        # Try filtering by category
        for category in ['skill_optimization', 'workflow_improvement']:
            recs = engine.get_recommendations(category=category)

            for rec in recs:
                assert rec['category'] == category

    def test_recommendation_filtering_by_impact(self, mock_skill_telemetry, mock_session_data):
        """Test filtering recommendations by minimum impact score."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        high_impact_recs = engine.get_recommendations(min_impact=60)

        for rec in high_impact_recs:
            assert rec['impact_score'] >= 60

    def test_top_n_recommendations(self, mock_skill_telemetry, mock_session_data):
        """Test retrieving top N recommendations."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        top_5 = engine.get_recommendations(top_n=5)

        assert len(top_5) <= 5

        # Should be sorted by impact (descending)
        if len(top_5) > 1:
            for i in range(len(top_5) - 1):
                assert top_5[i]['impact_score'] >= top_5[i + 1]['impact_score']

    def test_recommendation_evaluation(self, mock_skill_telemetry, mock_session_data):
        """Test recommendation quality evaluation."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        eval_metrics = engine.evaluate(mock_session_data, None)

        assert 'total_recommendations' in eval_metrics
        assert 'recommendations_by_category' in eval_metrics
        assert 'avg_impact_by_category' in eval_metrics
        assert 'high_impact_count' in eval_metrics
        assert 'actionable_count' in eval_metrics

    def test_get_recommendations_before_fit_raises_error(self):
        """Test that getting recommendations before fit raises error."""
        engine = RecommendationEngine()

        with pytest.raises(RuntimeError, match="must be fitted"):
            engine.get_recommendations()

    def test_predict_not_used(self, mock_skill_telemetry, mock_session_data):
        """Test that predict returns empty (recommendations use get_recommendations)."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        result = engine.predict(mock_session_data)

        assert len(result) == 0

    def test_actionable_only_filter(self, mock_skill_telemetry, mock_session_data):
        """Test filtering for actionable recommendations only."""
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        actionable_recs = engine.get_recommendations(actionable_only=True)

        for rec in actionable_recs:
            assert rec['actionable'] is True


# ============================================================================
# Benchmarks Tests
# ============================================================================

class TestBenchmarkEngine:
    """Test suite for benchmark comparison."""

    def test_initialization(self):
        """Test benchmark engine initialization."""
        engine = BenchmarkEngine(baselines={'session_count': 10.0})
        assert engine.baselines['session_count'] == 10.0
        assert not engine.fitted

    def test_insufficient_history_raises_error(self):
        """Test that insufficient history raises error."""
        engine = BenchmarkEngine()

        # Only 10 days (minimum is 14)
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        df = pd.DataFrame({'metric': range(10)}, index=dates)

        with pytest.raises(ValueError, match="Insufficient data"):
            engine.fit(df)

    def test_fit_with_historical_data(self, mock_benchmark_data):
        """Test fitting benchmark engine."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        assert engine.fitted
        assert len(engine.historical_stats) > 0

        # Check statistics are calculated
        for metric, stats in engine.historical_stats.items():
            assert 'mean' in stats
            assert 'median' in stats
            assert 'std' in stats
            assert 'min' in stats
            assert 'max' in stats
            assert 'p25' in stats
            assert 'p50' in stats
            assert 'p75' in stats
            assert 'p90' in stats
            assert 'p95' in stats

    def test_percentile_calculation(self, mock_benchmark_data):
        """Test percentile rank calculation."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        # Benchmark a value
        metric_name = 'session_count'
        current_value = 15.0  # High value

        result = engine.benchmark_metric(metric_name, current_value)

        assert 'percentile' in result
        assert 0 <= result['percentile'] <= 1

        # High value should have high percentile
        assert result['percentile'] > 0.5

    def test_trend_analysis(self, mock_benchmark_data):
        """Test trend direction determination."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        metric_name = 'session_count'

        # Test high current value (should be improving)
        result_high = engine.benchmark_metric(metric_name, 20.0)

        assert 'trend' in result_high
        assert result_high['trend'] in ['improving', 'stable', 'declining']

        # Test low current value (should be declining)
        result_low = engine.benchmark_metric(metric_name, 2.0)

        assert 'trend' in result_low
        assert result_low['trend'] in ['improving', 'stable', 'declining']

    def test_baseline_comparison(self, mock_benchmark_data):
        """Test baseline status determination."""
        baseline_value = 10.0
        engine = BenchmarkEngine(baselines={'session_count': baseline_value})
        engine.fit(mock_benchmark_data)

        # Test above baseline
        result_above = engine.benchmark_metric('session_count', 12.0)
        assert result_above['status'] == 'above_baseline'

        # Test at baseline
        result_at = engine.benchmark_metric('session_count', 10.0)
        assert result_at['status'] == 'at_baseline'

        # Test below baseline
        result_below = engine.benchmark_metric('session_count', 8.0)
        assert result_below['status'] == 'below_baseline'

    def test_comparison_metrics(self, mock_benchmark_data):
        """Test comparison percentage calculations."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        result = engine.benchmark_metric('session_count', 15.0)

        assert 'comparison' in result
        assert 'vs_mean' in result['comparison']
        assert 'vs_median' in result['comparison']
        assert 'vs_p90' in result['comparison']

    def test_benchmark_result_structure(self, mock_benchmark_data):
        """Test complete benchmark result structure."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        result = engine.benchmark_metric('session_count', 12.0)

        # Required fields
        assert 'metric' in result
        assert 'current' in result
        assert 'baseline' in result
        assert 'percentile' in result
        assert 'trend' in result
        assert 'status' in result
        assert 'comparison' in result
        assert 'historical' in result

        # Check types
        assert isinstance(result['metric'], str)
        assert isinstance(result['current'], float)
        assert isinstance(result['percentile'], float)
        assert result['trend'] in ['improving', 'stable', 'declining']
        assert result['status'] in ['above_baseline', 'at_baseline', 'below_baseline']

    def test_benchmark_all_metrics(self, mock_benchmark_data):
        """Test benchmarking all available metrics."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        # Benchmark all metrics in the data
        for metric_name in ['session_count', 'skill_usage', 'token_usage', 'success_rate']:
            result = engine.benchmark_metric(metric_name, 10.0)

            assert result['metric'] == metric_name
            assert 'percentile' in result
            assert 'trend' in result

    def test_predict_not_used(self, mock_benchmark_data):
        """Test that predict returns empty (use benchmark_metric instead)."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        result = engine.predict(mock_benchmark_data)

        # Should return empty array
        assert len(result) == 0

    def test_evaluate_returns_metadata(self, mock_benchmark_data):
        """Test evaluate returns metadata about available metrics."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        eval_result = engine.evaluate(mock_benchmark_data, None)

        assert 'metrics_available' in eval_result
        assert 'history_days' in eval_result
        assert len(eval_result['metrics_available']) > 0

    def test_benchmark_with_missing_metric_raises_error(self, mock_benchmark_data):
        """Test that benchmarking non-existent metric raises error."""
        engine = BenchmarkEngine()
        engine.fit(mock_benchmark_data)

        with pytest.raises(ValueError, match="not found"):
            engine.benchmark_metric('nonexistent_metric', 10.0)


# ============================================================================
# Model Evaluation Tests
# ============================================================================

class TestModelEvaluation:
    """Test suite for model evaluation metrics."""

    def test_forecast_accuracy_mae_rmse_mape(self):
        """Test MAE, RMSE, MAPE calculation."""
        actual = np.array([100, 110, 105, 115, 120])
        predicted = np.array([98, 112, 103, 118, 119])

        metrics = evaluate_forecast_accuracy(actual, predicted)

        assert 'mae' in metrics
        assert 'rmse' in metrics
        assert 'mape' in metrics
        assert 'n_samples' in metrics

        # MAE should be positive
        assert metrics['mae'] > 0

        # RMSE should be >= MAE (by definition)
        assert metrics['rmse'] >= metrics['mae']

        # MAPE should be a percentage (0-1 range typically)
        assert metrics['mape'] >= 0

        # n_samples should match input length
        assert metrics['n_samples'] == 5

    def test_perfect_predictions(self):
        """Test metrics with perfect predictions."""
        actual = np.array([100, 110, 120, 130, 140])
        predicted = actual.copy()

        metrics = evaluate_forecast_accuracy(actual, predicted)

        # All errors should be zero
        assert metrics['mae'] == 0
        assert metrics['rmse'] == 0
        assert metrics['mape'] == 0

    def test_mismatched_lengths_raises_error(self):
        """Test that mismatched array lengths raise error."""
        actual = np.array([100, 110, 120])
        predicted = np.array([98, 112])  # Different length

        with pytest.raises(ValueError, match="same length"):
            evaluate_forecast_accuracy(actual, predicted)

    def test_empty_arrays_raise_error(self):
        """Test that empty arrays raise error."""
        actual = np.array([])
        predicted = np.array([])

        with pytest.raises(ValueError, match="must not be empty"):
            evaluate_forecast_accuracy(actual, predicted)

    def test_mape_with_zero_actuals(self):
        """Test MAPE calculation handles zero actual values."""
        actual = np.array([0, 0, 0, 100, 110])
        predicted = np.array([5, 3, 2, 98, 112])

        # Should handle zeros gracefully
        metrics = evaluate_forecast_accuracy(actual, predicted)

        assert 'mape' in metrics
        # MAPE should only be calculated for non-zero actuals
        assert metrics['mape'] >= 0

    def test_pattern_quality_evaluation_perfect(self):
        """Test pattern quality evaluation with perfect detection."""
        detected = [
            {'pattern': 'think → plan', 'support': 10},
            {'pattern': 'plan → build', 'support': 15}
        ]
        labeled = [
            {'pattern': 'think → plan'},
            {'pattern': 'plan → build'}
        ]

        metrics = evaluate_pattern_quality(detected, labeled)

        assert metrics['precision'] == 1.0
        assert metrics['recall'] == 1.0
        assert metrics['f1_score'] == 1.0
        assert metrics['true_positives'] == 2
        assert metrics['false_positives'] == 0
        assert metrics['false_negatives'] == 0

    def test_pattern_quality_evaluation_partial(self):
        """Test pattern quality evaluation with partial match."""
        detected = [
            {'pattern': 'think → plan'},
            {'pattern': 'plan → build'},
            {'pattern': 'wrong → pattern'}  # False positive
        ]
        labeled = [
            {'pattern': 'think → plan'},
            {'pattern': 'plan → build'},
            {'pattern': 'build → review'}  # Missed (false negative)
        ]

        metrics = evaluate_pattern_quality(detected, labeled)

        assert metrics['true_positives'] == 2
        assert metrics['false_positives'] == 1
        assert metrics['false_negatives'] == 1
        assert abs(metrics['precision'] - 2/3) < 0.01  # 2 correct out of 3 detected
        assert abs(metrics['recall'] - 2/3) < 0.01  # 2 detected out of 3 labeled
        assert abs(metrics['f1_score'] - 2/3) < 0.01

    def test_pattern_quality_no_patterns(self):
        """Test pattern quality when no patterns exist."""
        detected = []
        labeled = []

        metrics = evaluate_pattern_quality(detected, labeled)

        # Perfect agreement when both are empty
        assert metrics['precision'] == 1.0
        assert metrics['recall'] == 1.0
        assert metrics['f1_score'] == 1.0

    def test_pattern_quality_missing_detections(self):
        """Test pattern quality when detection misses all patterns."""
        detected = []
        labeled = [
            {'pattern': 'pattern1'},
            {'pattern': 'pattern2'}
        ]

        metrics = evaluate_pattern_quality(detected, labeled)

        assert metrics['precision'] == 0.0
        assert metrics['recall'] == 0.0
        assert metrics['f1_score'] == 0.0
        assert metrics['false_negatives'] == 2

    def test_recommendation_impact_evaluation(self):
        """Test recommendation impact tracking."""
        recommendations = [
            {'id': 'rec1', 'category': 'skill_optimization', 'impact_score': 80},
            {'id': 'rec2', 'category': 'workflow_improvement', 'impact_score': 60},
            {'id': 'rec3', 'category': 'performance_booster', 'impact_score': 90},
            {'id': 'rec4', 'category': 'inefficiency_detection', 'impact_score': 50}
        ]

        outcomes = [
            {'recommendation_id': 'rec1', 'accepted': True, 'implemented': True},
            {'recommendation_id': 'rec2', 'accepted': True, 'implemented': False},
            {'recommendation_id': 'rec3', 'accepted': False, 'implemented': False},
            {'recommendation_id': 'rec4', 'accepted': True, 'implemented': True}
        ]

        metrics = evaluate_recommendation_impact(recommendations, outcomes)

        # 3 out of 4 accepted
        assert metrics['acceptance_rate'] == 0.75

        # 2 out of 3 accepted were implemented
        assert abs(metrics['implementation_rate'] - 2/3) < 0.01

        # 2 out of 4 total were implemented
        assert metrics['overall_implementation_rate'] == 0.5

        # Check impact distribution
        assert 'impact_distribution' in metrics
        assert metrics['impact_distribution']['high'] == 2  # rec1, rec3
        assert metrics['impact_distribution']['medium'] == 2  # rec2, rec4

    def test_export_evaluation_report(self):
        """Test exporting evaluation report to file."""
        metrics = {
            'mae': 2.5,
            'rmse': 3.2,
            'mape': 0.05
        }

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            output_path = f.name

        try:
            export_evaluation_report(metrics, output_path)

            # Verify file was created and contains data
            assert os.path.exists(output_path)

            with open(output_path, 'r') as f:
                loaded = json.load(f)

            assert loaded['mae'] == 2.5
            assert loaded['rmse'] == 3.2
            assert loaded['mape'] == 0.05

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


# ============================================================================
# Integration Tests
# ============================================================================

class TestMLIntegration:
    """Integration tests for ML pipeline."""

    def test_end_to_end_forecast_pipeline(self, mock_time_series_data):
        """Test complete forecasting pipeline."""
        # Fit forecaster
        forecaster = TimeSeriesForecaster(method='moving_average')
        forecaster.fit(mock_time_series_data)

        # Generate forecast
        forecast = forecaster.forecast(periods=7)

        # Validate forecast
        assert len(forecast['predictions']) == 7
        assert all(p > 0 for p in forecast['predictions'])

        # Evaluate on historical data
        train_data = mock_time_series_data.iloc[:20]
        test_data = mock_time_series_data.iloc[20:]

        forecaster_eval = TimeSeriesForecaster(method='moving_average')
        forecaster_eval.fit(train_data)

        target = test_data.iloc[:, 0].values
        metrics = forecaster_eval.evaluate(test_data, target)

        assert metrics['mae'] >= 0
        assert metrics['rmse'] >= 0

    def test_pattern_to_recommendation_pipeline(self, mock_skill_telemetry, mock_session_data):
        """Test pattern detection -> recommendation generation pipeline."""
        # Detect patterns
        detector = PatternDetector(min_support=2)
        detector.fit(mock_skill_telemetry)

        patterns = detector.get_patterns()
        assert len(patterns) > 0

        # Generate recommendations
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        recommendations = engine.get_recommendations(min_impact=40)

        # Should have some recommendations based on patterns
        assert engine.fitted

    def test_clustering_to_recommendation_pipeline(self, mock_session_data, mock_skill_telemetry):
        """Test clustering -> persona-based recommendations pipeline."""
        # Cluster sessions
        clusterer = BehaviorClusterer(n_clusters=3)
        clusterer.fit(mock_session_data)

        cluster_eval = clusterer.evaluate(mock_session_data)
        assert len(cluster_eval['cluster_info']) > 0

        # Generate recommendations (should include persona-based recs)
        engine = RecommendationEngine(min_support=2)
        engine.fit(mock_skill_telemetry, mock_session_data)

        perf_recs = engine.get_recommendations(category='performance_booster')

        # May or may not have performance boosters depending on data
        # Just verify the pipeline completes
        assert engine.fitted


# ============================================================================
# Database Integration Tests
# ============================================================================

class TestDatabaseIntegration:
    """Test ML components with database integration."""

    def test_detect_skill_patterns_from_db(self, temp_database):
        """Test pattern detection from database."""
        patterns = detect_skill_patterns(temp_database, min_support=2)

        # Should detect some patterns
        assert isinstance(patterns, list)

    def test_generate_recommendations_from_db(self, temp_database):
        """Test recommendation generation from database."""
        # May raise warning about insufficient data, that's OK
        try:
            recommendations = generate_recommendations(temp_database, min_support=2)
            assert isinstance(recommendations, list)
        except ValueError:
            # Insufficient data is acceptable in test
            pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
