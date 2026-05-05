"""Pattern learning system for project-intelligence feature.

Tracks bug/violation detection patterns and adjusts confidence scores based on
validation outcomes (true positives vs false positives).
"""
from __future__ import annotations
from typing import Literal, Dict
from datetime import datetime, timezone

from .document_store import DocumentStore

_NOW = lambda: datetime.now(timezone.utc).isoformat()


def adjust_pattern_confidence(
    pattern_id: str, outcome: Literal['true_positive', 'false_positive']
) -> None:
    """
    Adjust pattern confidence based on validation outcome.

    - true_positive: increase confidence by 0.1 (max 1.0)
    - false_positive: decrease confidence by 0.2 (min 0.0)

    Store updated stats in ds_documents table (doc_type='pattern-stats').

    Args:
        pattern_id: Unique identifier for the pattern
        outcome: Validation outcome ('true_positive' or 'false_positive')

    Raises:
        ValueError: If outcome is not a valid literal
    """
    if outcome not in ('true_positive', 'false_positive'):
        raise ValueError(f"Invalid outcome: {outcome}. Must be 'true_positive' or 'false_positive'")

    # Get current stats or initialize new pattern
    stats = get_pattern_stats(pattern_id)

    # Update counters
    if outcome == 'true_positive':
        stats['true_positives'] += 1
        stats['confidence'] = min(1.0, stats['confidence'] + 0.1)
    else:  # false_positive
        stats['false_positives'] += 1
        stats['confidence'] = max(0.0, stats['confidence'] - 0.2)

    stats['total_detections'] = stats['true_positives'] + stats['false_positives']

    # Calculate accuracy rate
    if stats['total_detections'] > 0:
        stats['accuracy_rate'] = stats['true_positives'] / stats['total_detections']
    else:
        stats['accuracy_rate'] = 0.0

    # Persist to database
    store_pattern_stats(pattern_id, stats)


def get_pattern_stats(pattern_id: str) -> Dict[str, float | int | str]:
    """
    Get current stats for a pattern.

    If the pattern doesn't exist yet, returns initialized stats with 0.5 confidence.

    Args:
        pattern_id: Unique identifier for the pattern

    Returns:
        Dictionary containing:
        - pattern_id: str
        - confidence: float (0.0-1.0)
        - true_positives: int
        - false_positives: int
        - total_detections: int
        - accuracy_rate: float (0.0-1.0)
    """
    # Search for existing pattern stats
    # Use quoted query to handle hyphens in pattern_id
    results = DocumentStore.search(
        query=f'"{pattern_id}"',
        doc_type='pattern-stats',
        limit=1
    )

    # If found, extract from metadata with explicit type casting
    if results:
        doc = results[0]
        metadata = doc.get('metadata', {})
        return {
            'pattern_id': str(metadata.get('pattern_id', pattern_id)),
            'confidence': float(metadata.get('confidence', 0.5)),
            'true_positives': int(metadata.get('true_positives', 0)),
            'false_positives': int(metadata.get('false_positives', 0)),
            'total_detections': int(metadata.get('total_detections', 0)),
            'accuracy_rate': float(metadata.get('accuracy_rate', 0.0)),
        }

    # Initialize new pattern with default confidence of 0.5
    return {
        'pattern_id': pattern_id,
        'confidence': 0.5,
        'true_positives': 0,
        'false_positives': 0,
        'total_detections': 0,
        'accuracy_rate': 0.0,
    }


def store_pattern_stats(pattern_id: str, stats: Dict[str, float | int | str]) -> None:
    """
    Store updated pattern stats in ds_documents table.

    Creates a new document or updates existing one.

    Args:
        pattern_id: Unique identifier for the pattern
        stats: Dictionary containing all pattern statistics
    """
    # Check if pattern already exists
    # Use quoted query to handle hyphens in pattern_id
    results = DocumentStore.search(
        query=f'"{pattern_id}"',
        doc_type='pattern-stats',
        limit=1
    )

    # Build content summary for searchability
    content = (
        f"Pattern: {pattern_id}\n"
        f"Confidence: {stats['confidence']:.2f}\n"
        f"True Positives: {stats['true_positives']}\n"
        f"False Positives: {stats['false_positives']}\n"
        f"Total Detections: {stats['total_detections']}\n"
        f"Accuracy Rate: {stats['accuracy_rate']:.2%}"
    )

    # Add timestamp to metadata
    metadata = dict(stats)
    metadata['last_updated'] = _NOW()

    if results:
        # Update existing document
        doc_id = results[0]['doc_id']
        DocumentStore.update(
            doc_id,
            content=content,
            metadata=metadata
        )
    else:
        # Create new document
        DocumentStore.create(
            doc_type='pattern-stats',
            title=f"Pattern Stats: {pattern_id}",
            content=content,
            metadata=metadata,
            keywords=f"{pattern_id} pattern stats confidence accuracy"
        )
