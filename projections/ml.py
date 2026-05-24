"""
ML Intelligence - Enterprise Feature

Advanced ML-powered recommendations, forecasting, and pattern detection
are available in dream-studio-enterprise.

Features:
- Automated recommendations based on project context
- ARIMA forecasting for token usage and trends
- Behavior clustering and segmentation
- Pattern detection across sessions
- Benchmarking and model evaluation

Learn more: https://dreamstudio.dev/enterprise
"""


class MLNotAvailableError(Exception):
    """Raised when ML features are accessed without enterprise license."""

    pass


def check_ml_available():
    """Check if ML features are available."""
    try:
        import dream_studio_enterprise.ml

        return True
    except ImportError:
        return False


def generate_recommendations(*args, **kwargs):
    """
    Get ML-powered recommendations - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_ml_available():
        raise MLNotAvailableError(
            "ML recommendations require dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise"
        )
    from dream_studio_enterprise.ml import recommendations

    return recommendations.generate_recommendations(*args, **kwargs)


def forecast_token_usage(*args, **kwargs):
    """
    Forecast token usage using ARIMA - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_ml_available():
        raise MLNotAvailableError(
            "Token usage forecasting requires dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise"
        )
    from dream_studio_enterprise.ml import forecasting

    return forecasting.forecast_token_usage(*args, **kwargs)


def detect_patterns(*args, **kwargs):
    """
    Detect patterns across sessions - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_ml_available():
        raise MLNotAvailableError(
            "Pattern detection requires dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise"
        )
    from dream_studio_enterprise.ml import patterns

    return patterns.detect_patterns(*args, **kwargs)


def cluster_behaviors(*args, **kwargs):
    """
    Cluster user behaviors - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_ml_available():
        raise MLNotAvailableError(
            "Behavior clustering requires dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise"
        )
    from dream_studio_enterprise.ml import clustering

    return clustering.cluster_behaviors(*args, **kwargs)


# Export stubs
__all__ = [
    "MLNotAvailableError",
    "check_ml_available",
    "generate_recommendations",
    "forecast_token_usage",
    "detect_patterns",
    "cluster_behaviors",
]
