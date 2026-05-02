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
from .benchmarks import (
    BenchmarkEngine,
    run_benchmark_suite,
)
from .clustering import BehaviorClusterer
from .patterns import (
    PatternDetector,
    detect_skill_patterns,
    detect_workflow_patterns,
)
from .storage import (
    save_model,
    load_model,
    list_saved_models,
    delete_model,
    is_model_stale,
    get_model_metadata,
    cleanup_old_models,
)

__all__ = [
    "BaseModel",
    "validate_dataframe",
    "prepare_time_series",
    "train_test_split_temporal",
    "BenchmarkEngine",
    "run_benchmark_suite",
    "BehaviorClusterer",
    "PatternDetector",
    "detect_skill_patterns",
    "detect_workflow_patterns",
    "save_model",
    "load_model",
    "list_saved_models",
    "delete_model",
    "is_model_stale",
    "get_model_metadata",
    "cleanup_old_models",
]
