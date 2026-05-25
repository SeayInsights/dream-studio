"""Machine learning models for dream-studio analytics."""

from .base import BaseModel
from .benchmarks import BenchmarkEngine
from .clustering import BehaviorClusterer
from .forecasting import TimeSeriesForecaster
from .patterns import PatternDetector
from .recommendations import RecommendationEngine


def check_ml_available() -> bool:
    """Return True if core ML dependencies (pandas, numpy) are installed."""
    try:
        import pandas  # noqa: F401
        import numpy  # noqa: F401

        return True
    except ImportError:
        return False


__all__ = [
    "BaseModel",
    "BenchmarkEngine",
    "BehaviorClusterer",
    "TimeSeriesForecaster",
    "PatternDetector",
    "RecommendationEngine",
    "check_ml_available",
]
