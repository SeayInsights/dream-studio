"""
ML utilities for dream-studio analytics.

Provides base classes and utilities for machine learning operations
with graceful fallbacks for missing dependencies.
"""

from .base import (
    BaseModel,
    validate_dataframe,
    prepare_time_series,
    train_test_split_temporal,
)
from .clustering import BehaviorClusterer
from .patterns import (
    PatternDetector,
    detect_skill_patterns,
    detect_workflow_patterns,
)

__all__ = [
    "BaseModel",
    "validate_dataframe",
    "prepare_time_series",
    "train_test_split_temporal",
    "BehaviorClusterer",
    "PatternDetector",
    "detect_skill_patterns",
    "detect_workflow_patterns",
]
