"""
Model evaluation metrics for dream-studio analytics.

Provides evaluation utilities for ML models:
- Forecast accuracy: MAE, RMSE, MAPE
- Pattern detection quality: Precision, Recall, F1-score
- Recommendation impact tracking: Acceptance rate, implementation rate, impact distribution

Example usage:
    >>> from analytics.ml.evaluation import evaluate_forecast_accuracy, export_evaluation_report
    >>> import numpy as np
    >>>
    >>> # Evaluate forecast accuracy
    >>> actual = np.array([100, 110, 105, 115, 120])
    >>> predicted = np.array([98, 112, 103, 118, 119])
    >>> metrics = evaluate_forecast_accuracy(actual, predicted)
    >>> print(f"MAE: {metrics['mae']:.2f}, RMSE: {metrics['rmse']:.2f}, MAPE: {metrics['mape']:.2%}")
    >>>
    >>> # Export to file
    >>> export_evaluation_report(metrics, 'forecast_eval.json')
"""

import json
import warnings
from pathlib import Path
from typing import Dict, List, Set, Union, Optional

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    warnings.warn("numpy not available. Evaluation functions will raise errors if called.")


def evaluate_forecast_accuracy(
    actual: "np.ndarray",
    predicted: "np.ndarray"
) -> Dict[str, float]:
    """
    Evaluate forecast accuracy using MAE, RMSE, and MAPE.

    Computes standard regression metrics for time series forecasting:
    - MAE (Mean Absolute Error): Average absolute difference between actual and predicted
    - RMSE (Root Mean Square Error): Square root of average squared differences
    - MAPE (Mean Absolute Percentage Error): Average absolute percentage error

    Args:
        actual: Array of actual values
        predicted: Array of predicted values (must have same length as actual)

    Returns:
        Dictionary with metrics:
            - 'mae': Mean Absolute Error
            - 'rmse': Root Mean Square Error
            - 'mape': Mean Absolute Percentage Error (as decimal, e.g., 0.15 = 15%)
            - 'n_samples': Number of samples evaluated

    Raises:
        ValueError: If arrays have different lengths, are empty, or numpy is not available
        RuntimeError: If MAPE cannot be computed (all actual values are zero)

    Example:
        >>> actual = np.array([100, 110, 105, 115, 120])
        >>> predicted = np.array([98, 112, 103, 118, 119])
        >>> metrics = evaluate_forecast_accuracy(actual, predicted)
        >>> print(f"MAE: {metrics['mae']:.2f}")
    """
    if not NUMPY_AVAILABLE:
        raise ValueError("numpy is required for forecast evaluation")

    # Convert to numpy arrays if needed
    actual = np.asarray(actual)
    predicted = np.asarray(predicted)

    # Validate inputs
    if len(actual) == 0 or len(predicted) == 0:
        raise ValueError("Actual and predicted arrays must not be empty")

    if len(actual) != len(predicted):
        raise ValueError(
            f"Actual and predicted arrays must have the same length. "
            f"Got {len(actual)} actual values and {len(predicted)} predicted values."
        )

    # Calculate errors
    errors = actual - predicted
    absolute_errors = np.abs(errors)

    # MAE: Mean Absolute Error
    mae = float(np.mean(absolute_errors))

    # RMSE: Root Mean Square Error
    rmse = float(np.sqrt(np.mean(errors ** 2)))

    # MAPE: Mean Absolute Percentage Error
    # Handle division by zero: only compute for non-zero actual values
    non_zero_mask = actual != 0
    if not np.any(non_zero_mask):
        # All actual values are zero - MAPE is undefined
        warnings.warn("Cannot compute MAPE: all actual values are zero")
        mape = float('inf')
    else:
        percentage_errors = np.abs(errors[non_zero_mask] / actual[non_zero_mask])
        mape = float(np.mean(percentage_errors))

    return {
        'mae': mae,
        'rmse': rmse,
        'mape': mape,
        'n_samples': int(len(actual))
    }


def evaluate_pattern_quality(
    detected_patterns: List[Dict],
    labeled_patterns: List[Dict]
) -> Dict[str, float]:
    """
    Evaluate pattern detection quality using precision, recall, and F1-score.

    Compares detected patterns against labeled ground truth patterns to compute
    classification metrics. Patterns are matched by their string representation.

    Args:
        detected_patterns: List of detected patterns, each with 'pattern' key
                          (e.g., from PatternDetector.get_patterns())
        labeled_patterns: List of ground truth patterns, each with 'pattern' key

    Returns:
        Dictionary with metrics:
            - 'precision': Proportion of detected patterns that are correct
            - 'recall': Proportion of ground truth patterns that were detected
            - 'f1_score': Harmonic mean of precision and recall
            - 'true_positives': Number of correctly detected patterns
            - 'false_positives': Number of incorrectly detected patterns
            - 'false_negatives': Number of missed ground truth patterns
            - 'n_detected': Total number of detected patterns
            - 'n_labeled': Total number of ground truth patterns

    Raises:
        ValueError: If input lists are malformed or required keys are missing

    Example:
        >>> detected = [
        ...     {'pattern': 'think → plan', 'support': 10},
        ...     {'pattern': 'plan → build', 'support': 15},
        ...     {'pattern': 'build → verify', 'support': 8}
        ... ]
        >>> labeled = [
        ...     {'pattern': 'think → plan'},
        ...     {'pattern': 'plan → build'},
        ...     {'pattern': 'build → review'}
        ... ]
        >>> metrics = evaluate_pattern_quality(detected, labeled)
        >>> print(f"Precision: {metrics['precision']:.2%}, Recall: {metrics['recall']:.2%}")
    """
    # Validate inputs
    if not isinstance(detected_patterns, list) or not isinstance(labeled_patterns, list):
        raise ValueError("Both detected_patterns and labeled_patterns must be lists")

    # Extract pattern strings
    try:
        detected_set: Set[str] = {p['pattern'] for p in detected_patterns if 'pattern' in p}
        labeled_set: Set[str] = {p['pattern'] for p in labeled_patterns if 'pattern' in p}
    except (TypeError, KeyError) as e:
        raise ValueError(f"Pattern lists must contain dictionaries with 'pattern' key: {e}")

    # Handle edge cases
    n_detected = len(detected_set)
    n_labeled = len(labeled_set)

    if n_detected == 0 and n_labeled == 0:
        # No patterns detected or labeled - perfect agreement
        return {
            'precision': 1.0,
            'recall': 1.0,
            'f1_score': 1.0,
            'true_positives': 0,
            'false_positives': 0,
            'false_negatives': 0,
            'n_detected': 0,
            'n_labeled': 0
        }

    # Calculate true positives, false positives, false negatives
    true_positives = len(detected_set & labeled_set)
    false_positives = len(detected_set - labeled_set)
    false_negatives = len(labeled_set - detected_set)

    # Calculate precision, recall, F1
    if n_detected == 0:
        precision = 0.0
    else:
        precision = true_positives / n_detected

    if n_labeled == 0:
        recall = 0.0
    else:
        recall = true_positives / n_labeled

    if precision + recall == 0:
        f1_score = 0.0
    else:
        f1_score = 2 * (precision * recall) / (precision + recall)

    return {
        'precision': float(precision),
        'recall': float(recall),
        'f1_score': float(f1_score),
        'true_positives': int(true_positives),
        'false_positives': int(false_positives),
        'false_negatives': int(false_negatives),
        'n_detected': int(n_detected),
        'n_labeled': int(n_labeled)
    }


def evaluate_recommendation_impact(
    recommendations: List[Dict],
    outcomes: List[Dict]
) -> Dict[str, Union[float, Dict[str, int]]]:
    """
    Evaluate recommendation impact by tracking acceptance and implementation rates.

    Analyzes how users interact with recommendations to measure effectiveness:
    - Acceptance rate: proportion of recommendations users agreed with
    - Implementation rate: proportion of accepted recommendations that were implemented
    - Impact score distribution: breakdown of recommendations by impact level

    Args:
        recommendations: List of recommendations, each with:
            - 'id' (str): Unique recommendation identifier
            - 'category' (str): Recommendation category
            - 'impact_score' (int): Impact score (0-100)
        outcomes: List of recommendation outcomes, each with:
            - 'recommendation_id' (str): ID matching recommendation
            - 'accepted' (bool): Whether user accepted the recommendation
            - 'implemented' (bool): Whether recommendation was implemented

    Returns:
        Dictionary with metrics:
            - 'acceptance_rate': Proportion of recommendations accepted (0.0-1.0)
            - 'implementation_rate': Proportion of accepted recs implemented (0.0-1.0)
            - 'overall_implementation_rate': Proportion of all recs implemented (0.0-1.0)
            - 'impact_distribution': Dict with counts by impact level:
                - 'low': 0-39 impact score
                - 'medium': 40-69 impact score
                - 'high': 70-100 impact score
            - 'n_recommendations': Total number of recommendations
            - 'n_accepted': Number of accepted recommendations
            - 'n_implemented': Number of implemented recommendations
            - 'avg_impact_accepted': Average impact score of accepted recommendations
            - 'avg_impact_implemented': Average impact score of implemented recommendations

    Raises:
        ValueError: If input lists are malformed or required keys are missing

    Example:
        >>> recommendations = [
        ...     {'id': 'rec1', 'category': 'skill_optimization', 'impact_score': 75},
        ...     {'id': 'rec2', 'category': 'workflow_improvement', 'impact_score': 60}
        ... ]
        >>> outcomes = [
        ...     {'recommendation_id': 'rec1', 'accepted': True, 'implemented': True},
        ...     {'recommendation_id': 'rec2', 'accepted': True, 'implemented': False}
        ... ]
        >>> metrics = evaluate_recommendation_impact(recommendations, outcomes)
        >>> print(f"Acceptance: {metrics['acceptance_rate']:.1%}")
    """
    if not NUMPY_AVAILABLE:
        raise ValueError("numpy is required for recommendation evaluation")

    # Validate inputs
    if not isinstance(recommendations, list) or not isinstance(outcomes, list):
        raise ValueError("Both recommendations and outcomes must be lists")

    # Build lookup from outcomes
    outcome_map = {}
    try:
        for outcome in outcomes:
            rec_id = outcome.get('recommendation_id')
            if rec_id is None:
                raise ValueError("Each outcome must have 'recommendation_id' key")
            outcome_map[rec_id] = {
                'accepted': bool(outcome.get('accepted', False)),
                'implemented': bool(outcome.get('implemented', False))
            }
    except (TypeError, AttributeError) as e:
        raise ValueError(f"Outcomes must be a list of dictionaries: {e}")

    # Track metrics
    n_total = len(recommendations)
    n_accepted = 0
    n_implemented = 0
    impact_distribution = {'low': 0, 'medium': 0, 'high': 0}
    accepted_impacts = []
    implemented_impacts = []

    # Process each recommendation
    try:
        for rec in recommendations:
            rec_id = rec.get('id')
            if rec_id is None:
                raise ValueError("Each recommendation must have 'id' key")

            impact_score = rec.get('impact_score', 0)

            # Categorize impact
            if impact_score < 40:
                impact_distribution['low'] += 1
            elif impact_score < 70:
                impact_distribution['medium'] += 1
            else:
                impact_distribution['high'] += 1

            # Check outcome
            outcome = outcome_map.get(rec_id)
            if outcome:
                if outcome['accepted']:
                    n_accepted += 1
                    accepted_impacts.append(impact_score)

                if outcome['implemented']:
                    n_implemented += 1
                    implemented_impacts.append(impact_score)

    except (TypeError, AttributeError) as e:
        raise ValueError(f"Recommendations must be a list of dictionaries: {e}")

    # Handle edge cases
    if n_total == 0:
        return {
            'acceptance_rate': 0.0,
            'implementation_rate': 0.0,
            'overall_implementation_rate': 0.0,
            'impact_distribution': impact_distribution,
            'n_recommendations': 0,
            'n_accepted': 0,
            'n_implemented': 0,
            'avg_impact_accepted': 0.0,
            'avg_impact_implemented': 0.0
        }

    # Calculate rates
    acceptance_rate = n_accepted / n_total
    implementation_rate = n_implemented / n_accepted if n_accepted > 0 else 0.0
    overall_implementation_rate = n_implemented / n_total

    # Calculate average impacts
    avg_impact_accepted = float(np.mean(accepted_impacts)) if accepted_impacts else 0.0
    avg_impact_implemented = float(np.mean(implemented_impacts)) if implemented_impacts else 0.0

    return {
        'acceptance_rate': float(acceptance_rate),
        'implementation_rate': float(implementation_rate),
        'overall_implementation_rate': float(overall_implementation_rate),
        'impact_distribution': impact_distribution,
        'n_recommendations': int(n_total),
        'n_accepted': int(n_accepted),
        'n_implemented': int(n_implemented),
        'avg_impact_accepted': avg_impact_accepted,
        'avg_impact_implemented': avg_impact_implemented
    }


def export_evaluation_report(
    metrics: Dict,
    filename: Union[str, Path]
) -> None:
    """
    Export evaluation metrics to a JSON file.

    Saves evaluation metrics in a human-readable JSON format with proper indentation.
    Creates parent directories if they don't exist.

    Args:
        metrics: Dictionary of evaluation metrics (from any evaluate_* function)
        filename: Path to output JSON file (relative or absolute)

    Raises:
        ValueError: If metrics is not a dictionary
        IOError: If file cannot be written

    Example:
        >>> metrics = evaluate_forecast_accuracy(actual, predicted)
        >>> export_evaluation_report(metrics, 'reports/forecast_eval.json')
        >>> # File saved to reports/forecast_eval.json
    """
    if not isinstance(metrics, dict):
        raise ValueError("Metrics must be a dictionary")

    # Convert to Path object
    output_path = Path(filename)

    # Create parent directories if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON file
    try:
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
    except (IOError, OSError) as e:
        raise IOError(f"Failed to write evaluation report to {output_path}: {e}")


# Convenience function for comprehensive model evaluation
def evaluate_model_suite(
    forecast_results: Optional[Dict[str, "np.ndarray"]] = None,
    pattern_results: Optional[Dict[str, List[Dict]]] = None,
    recommendation_results: Optional[Dict[str, List[Dict]]] = None
) -> Dict[str, Dict]:
    """
    Evaluate multiple models in one call and return comprehensive report.

    Convenience function that runs all evaluation functions and combines results
    into a single report. Useful for batch evaluation or automated testing.

    Args:
        forecast_results: Dict with 'actual' and 'predicted' arrays (optional)
        pattern_results: Dict with 'detected' and 'labeled' pattern lists (optional)
        recommendation_results: Dict with 'recommendations' and 'outcomes' lists (optional)

    Returns:
        Dictionary with evaluation results for each model type:
            {
                'forecast': {...},  # if forecast_results provided
                'patterns': {...},  # if pattern_results provided
                'recommendations': {...}  # if recommendation_results provided
            }

    Example:
        >>> results = evaluate_model_suite(
        ...     forecast_results={'actual': actual_vals, 'predicted': pred_vals},
        ...     pattern_results={'detected': detected_patterns, 'labeled': labeled_patterns}
        ... )
        >>> print(results['forecast']['mae'])
        >>> print(results['patterns']['f1_score'])
    """
    report = {}

    # Evaluate forecasting
    if forecast_results is not None:
        try:
            actual = forecast_results.get('actual')
            predicted = forecast_results.get('predicted')
            if actual is not None and predicted is not None:
                report['forecast'] = evaluate_forecast_accuracy(actual, predicted)
        except Exception as e:
            report['forecast'] = {'error': str(e)}

    # Evaluate pattern detection
    if pattern_results is not None:
        try:
            detected = pattern_results.get('detected')
            labeled = pattern_results.get('labeled')
            if detected is not None and labeled is not None:
                report['patterns'] = evaluate_pattern_quality(detected, labeled)
        except Exception as e:
            report['patterns'] = {'error': str(e)}

    # Evaluate recommendations
    if recommendation_results is not None:
        try:
            recommendations = recommendation_results.get('recommendations')
            outcomes = recommendation_results.get('outcomes')
            if recommendations is not None and outcomes is not None:
                report['recommendations'] = evaluate_recommendation_impact(recommendations, outcomes)
        except Exception as e:
            report['recommendations'] = {'error': str(e)}

    return report
