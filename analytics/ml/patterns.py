"""
Pattern detection engine for dream-studio analytics.

Detects recurring patterns in:
- Skill sequences (e.g., "skill A → skill B → skill C")
- Workflow patterns (task sequences, handoff patterns)
- Temporal patterns (time-of-day, day-of-week)

Uses association rule mining principles (support, confidence, lift).

Example usage:
    >>> from analytics.ml.patterns import PatternDetector, detect_skill_patterns
    >>> import pandas as pd
    >>>
    >>> # Detect patterns from database
    >>> patterns = detect_skill_patterns('~/.dream-studio/state/studio.db', min_support=3)
    >>> for p in patterns[:5]:
    ...     print(f"{p['pattern']}: support={p['support']}, lift={p['lift']:.2f}")
    >>>
    >>> # Or use the detector directly
    >>> detector = PatternDetector(min_support=3)
    >>> detector.fit(skill_telemetry_df)
    >>> sequence_patterns = detector.get_patterns(pattern_type='sequence', min_lift=1.5)
    >>> temporal_patterns = detector.get_patterns(pattern_type='temporal_hour', top_n=10)
"""

from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
import warnings

from .base import BaseModel, PANDAS_AVAILABLE, NUMPY_AVAILABLE

if PANDAS_AVAILABLE:
    import pandas as pd

if NUMPY_AVAILABLE:
    import numpy as np


class PatternDetector(BaseModel):
    """
    Pattern detection engine for dream-studio analytics.

    Detects recurring patterns in skill usage, workflows, and temporal data
    using association rule mining principles.

    Attributes:
        fitted: Whether the model has been trained
        min_support: Minimum number of occurrences for a pattern to be considered
        patterns: Detected patterns after fitting
        data: Training data
    """

    def __init__(self, min_support: int = 3):
        """
        Initialize the pattern detector.

        Args:
            min_support: Minimum number of occurrences for a pattern (default: 3)
        """
        super().__init__()
        self.min_support = max(1, min_support)
        self.patterns: List[Dict] = []
        self.data: Optional["pd.DataFrame"] = None
        self._sequence_db: List[List[str]] = []
        self._temporal_db: List[Tuple[str, datetime]] = []

    def fit(self, data: "pd.DataFrame") -> None:
        """
        Train the pattern detector on session/skill data.

        Expected DataFrame columns:
        - session_id: Session identifier
        - skill_name: Name of skill used
        - invoked_at: Timestamp of invocation (ISO format string or datetime)
        - (optional) pipeline_phase: Workflow phase

        Args:
            data: Training data as a pandas DataFrame

        Raises:
            ValueError: If required columns are missing or data is insufficient
        """
        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            raise ValueError("pandas and numpy are required for pattern detection")

        # Validate columns
        required_cols = ['session_id', 'skill_name', 'invoked_at']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        if len(data) < self.min_support:
            # Insufficient data - set fitted but leave patterns empty
            self.fitted = True
            self.patterns = []
            self.data = data.copy()
            return

        self.data = data.copy()

        # Convert invoked_at to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(self.data['invoked_at']):
            self.data['invoked_at'] = pd.to_datetime(self.data['invoked_at'])

        # Build sequence database (skill sequences per session)
        self._build_sequence_db()

        # Build temporal database (skill + timestamp pairs)
        self._build_temporal_db()

        # Detect all pattern types
        self.patterns = []
        self.patterns.extend(self._detect_sequence_patterns())
        self.patterns.extend(self._detect_temporal_patterns())
        self.patterns.extend(self._detect_cooccurrence_patterns())

        self.fitted = True

    def _build_sequence_db(self) -> None:
        """Build sequence database from skill telemetry data."""
        # Sort by session and time
        sorted_data = self.data.sort_values(['session_id', 'invoked_at'])

        # Group by session to get skill sequences
        self._sequence_db = []
        for session_id, group in sorted_data.groupby('session_id'):
            sequence = group['skill_name'].tolist()
            if len(sequence) >= 2:  # Only sequences with 2+ skills
                self._sequence_db.append(sequence)

    def _build_temporal_db(self) -> None:
        """Build temporal database (skill, timestamp) pairs."""
        self._temporal_db = [
            (row['skill_name'], row['invoked_at'])
            for _, row in self.data.iterrows()
        ]

    def _detect_sequence_patterns(self) -> List[Dict]:
        """
        Detect recurring skill sequences.

        Returns:
            List of sequence patterns with support, confidence, lift
        """
        if len(self._sequence_db) < self.min_support:
            return []

        patterns = []

        # Count 2-skill sequences (bigrams)
        bigram_counts = Counter()
        skill_counts = Counter()

        for sequence in self._sequence_db:
            # Count individual skills
            for skill in sequence:
                skill_counts[skill] += 1

            # Count skill pairs
            for i in range(len(sequence) - 1):
                pair = (sequence[i], sequence[i + 1])
                bigram_counts[pair] += 1

        # Count 3-skill sequences (trigrams)
        trigram_counts = Counter()
        for sequence in self._sequence_db:
            for i in range(len(sequence) - 2):
                triplet = (sequence[i], sequence[i + 1], sequence[i + 2])
                trigram_counts[triplet] += 1

        total_sessions = len(self._sequence_db)

        # Build patterns from bigrams
        for (skill_a, skill_b), count in bigram_counts.items():
            if count >= self.min_support:
                # Support: proportion of sessions containing this pattern
                support = count

                # Confidence: P(B|A) = count(A->B) / count(A)
                confidence = count / skill_counts[skill_a] if skill_counts[skill_a] > 0 else 0.0

                # Lift: confidence / P(B)
                prob_b = skill_counts[skill_b] / total_sessions if total_sessions > 0 else 0.0
                lift = confidence / prob_b if prob_b > 0 else 0.0

                patterns.append({
                    'pattern_type': 'sequence',
                    'pattern': f"{skill_a} → {skill_b}",
                    'support': int(support),
                    'confidence': float(confidence),
                    'lift': float(lift)
                })

        # Build patterns from trigrams
        for (skill_a, skill_b, skill_c), count in trigram_counts.items():
            if count >= self.min_support:
                support = count

                # Confidence: P(C|A,B) = count(A->B->C) / count(A->B)
                bigram_key = (skill_a, skill_b)
                confidence = count / bigram_counts[bigram_key] if bigram_counts[bigram_key] > 0 else 0.0

                # Lift: confidence / P(C)
                prob_c = skill_counts[skill_c] / total_sessions if total_sessions > 0 else 0.0
                lift = confidence / prob_c if prob_c > 0 else 0.0

                patterns.append({
                    'pattern_type': 'sequence',
                    'pattern': f"{skill_a} → {skill_b} → {skill_c}",
                    'support': int(support),
                    'confidence': float(confidence),
                    'lift': float(lift)
                })

        return patterns

    def _detect_temporal_patterns(self) -> List[Dict]:
        """
        Detect temporal patterns (time-of-day, day-of-week).

        Returns:
            List of temporal patterns with support, confidence, lift
        """
        if len(self._temporal_db) < self.min_support:
            return []

        patterns = []

        # Count skill usage by hour of day
        hour_skill_counts = defaultdict(Counter)
        skill_counts = Counter()

        for skill, timestamp in self._temporal_db:
            hour = timestamp.hour
            hour_skill_counts[hour][skill] += 1
            skill_counts[skill] += 1

        total_invocations = len(self._temporal_db)

        # Detect hour-of-day patterns
        for hour, skill_counter in hour_skill_counts.items():
            for skill, count in skill_counter.items():
                if count >= self.min_support:
                    # Support: raw count
                    support = count

                    # Confidence: P(skill | hour) = count(skill in hour) / count(all in hour)
                    total_in_hour = sum(hour_skill_counts[hour].values())
                    confidence = count / total_in_hour if total_in_hour > 0 else 0.0

                    # Lift: confidence / P(skill overall)
                    prob_skill = skill_counts[skill] / total_invocations if total_invocations > 0 else 0.0
                    lift = confidence / prob_skill if prob_skill > 0 else 0.0

                    # Only include if lift > 1 (skill is more common at this hour than average)
                    if lift > 1.2:
                        patterns.append({
                            'pattern_type': 'temporal_hour',
                            'pattern': f"{skill} at {hour:02d}:00-{hour:02d}:59",
                            'support': int(support),
                            'confidence': float(confidence),
                            'lift': float(lift)
                        })

        # Count skill usage by day of week
        dow_skill_counts = defaultdict(Counter)

        for skill, timestamp in self._temporal_db:
            dow = timestamp.strftime('%A')  # Monday, Tuesday, etc.
            dow_skill_counts[dow][skill] += 1

        # Detect day-of-week patterns
        for dow, skill_counter in dow_skill_counts.items():
            for skill, count in skill_counter.items():
                if count >= self.min_support:
                    support = count

                    total_on_dow = sum(dow_skill_counts[dow].values())
                    confidence = count / total_on_dow if total_on_dow > 0 else 0.0

                    prob_skill = skill_counts[skill] / total_invocations if total_invocations > 0 else 0.0
                    lift = confidence / prob_skill if prob_skill > 0 else 0.0

                    if lift > 1.2:
                        patterns.append({
                            'pattern_type': 'temporal_dow',
                            'pattern': f"{skill} on {dow}",
                            'support': int(support),
                            'confidence': float(confidence),
                            'lift': float(lift)
                        })

        return patterns

    def _detect_cooccurrence_patterns(self) -> List[Dict]:
        """
        Detect skills that frequently co-occur within the same session.

        Returns:
            List of co-occurrence patterns with support, confidence, lift
        """
        if len(self._sequence_db) < self.min_support:
            return []

        patterns = []

        # Count skill co-occurrences within sessions
        cooccurrence_counts = Counter()
        skill_session_counts = Counter()

        for sequence in self._sequence_db:
            # Get unique skills in this session
            unique_skills = list(set(sequence))

            # Count each skill
            for skill in unique_skills:
                skill_session_counts[skill] += 1

            # Count pairs of co-occurring skills
            for i in range(len(unique_skills)):
                for j in range(i + 1, len(unique_skills)):
                    pair = tuple(sorted([unique_skills[i], unique_skills[j]]))
                    cooccurrence_counts[pair] += 1

        total_sessions = len(self._sequence_db)

        # Build patterns
        for (skill_a, skill_b), count in cooccurrence_counts.items():
            if count >= self.min_support:
                support = count

                # Confidence: P(B in session | A in session)
                confidence = count / skill_session_counts[skill_a] if skill_session_counts[skill_a] > 0 else 0.0

                # Lift: confidence / P(B in any session)
                prob_b = skill_session_counts[skill_b] / total_sessions if total_sessions > 0 else 0.0
                lift = confidence / prob_b if prob_b > 0 else 0.0

                # Only include if lift > 1 (skills co-occur more than random)
                if lift > 1.0:
                    patterns.append({
                        'pattern_type': 'cooccurrence',
                        'pattern': f"{skill_a} + {skill_b}",
                        'support': int(support),
                        'confidence': float(confidence),
                        'lift': float(lift)
                    })

        return patterns

    def predict(self, data: "pd.DataFrame") -> "np.ndarray":
        """
        Make predictions (not applicable for pattern detection).

        Args:
            data: Input data (not used)

        Returns:
            Empty array (pattern detection is unsupervised)
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before prediction")

        if not NUMPY_AVAILABLE:
            return []

        return np.array([])

    def evaluate(self, data: "pd.DataFrame", target: "np.ndarray") -> dict:
        """
        Evaluate pattern detection (not applicable for unsupervised learning).

        Args:
            data: Input data (not used)
            target: True values (not applicable)

        Returns:
            Dictionary with pattern statistics
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before evaluation")

        # Return pattern statistics instead of predictive metrics
        pattern_types = Counter([p['pattern_type'] for p in self.patterns])

        return {
            'total_patterns': len(self.patterns),
            'pattern_types': dict(pattern_types),
            'avg_support': float(np.mean([p['support'] for p in self.patterns])) if self.patterns else 0.0,
            'avg_confidence': float(np.mean([p['confidence'] for p in self.patterns])) if self.patterns else 0.0,
            'avg_lift': float(np.mean([p['lift'] for p in self.patterns])) if self.patterns else 0.0
        }

    def get_patterns(
        self,
        pattern_type: Optional[str] = None,
        min_support: Optional[int] = None,
        min_confidence: Optional[float] = None,
        min_lift: Optional[float] = None,
        top_n: Optional[int] = None
    ) -> List[Dict]:
        """
        Get detected patterns with optional filtering and ranking.

        Args:
            pattern_type: Filter by pattern type ('sequence', 'temporal_hour', 'temporal_dow', 'cooccurrence')
            min_support: Minimum support threshold
            min_confidence: Minimum confidence threshold
            min_lift: Minimum lift threshold
            top_n: Return only top N patterns (ranked by lift)

        Returns:
            List of patterns matching the criteria

        Raises:
            RuntimeError: If model has not been fitted
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before retrieving patterns")

        filtered = self.patterns

        # Apply filters
        if pattern_type is not None:
            filtered = [p for p in filtered if p['pattern_type'] == pattern_type]

        if min_support is not None:
            filtered = [p for p in filtered if p['support'] >= min_support]

        if min_confidence is not None:
            filtered = [p for p in filtered if p['confidence'] >= min_confidence]

        if min_lift is not None:
            filtered = [p for p in filtered if p['lift'] >= min_lift]

        # Sort by lift (descending)
        filtered = sorted(filtered, key=lambda x: x['lift'], reverse=True)

        # Limit to top N
        if top_n is not None:
            filtered = filtered[:top_n]

        return filtered


def detect_skill_patterns(
    db_path: str,
    min_support: int = 3,
    pattern_type: Optional[str] = None
) -> List[Dict]:
    """
    Detect skill usage patterns from the dream-studio database.

    Args:
        db_path: Path to dream-studio SQLite database
        min_support: Minimum number of occurrences for a pattern (default: 3)
        pattern_type: Filter by pattern type (optional)

    Returns:
        List of detected patterns with support, confidence, lift

    Raises:
        ValueError: If insufficient data or pandas/numpy not available
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for pattern detection")

    import sqlite3

    # Load skill telemetry data
    conn = sqlite3.connect(db_path)
    query = """
        SELECT
            session_id,
            skill_name,
            invoked_at
        FROM raw_skill_telemetry
        WHERE session_id IS NOT NULL
        ORDER BY invoked_at
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty or len(df) < min_support:
        return []

    # Fit detector
    detector = PatternDetector(min_support=min_support)
    detector.fit(df)

    # Get patterns
    return detector.get_patterns(pattern_type=pattern_type)


def detect_workflow_patterns(
    db_path: str,
    min_support: int = 2
) -> List[Dict]:
    """
    Detect workflow patterns (handoff sequences, pipeline phase transitions).

    Args:
        db_path: Path to dream-studio SQLite database
        min_support: Minimum number of occurrences for a pattern (default: 2)

    Returns:
        List of detected workflow patterns

    Raises:
        ValueError: If insufficient data or pandas/numpy not available
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for pattern detection")

    import sqlite3

    # Load handoff data with pipeline phases
    conn = sqlite3.connect(db_path)
    query = """
        SELECT
            session_id,
            pipeline_phase as skill_name,
            created_at as invoked_at
        FROM raw_handoffs
        WHERE session_id IS NOT NULL AND pipeline_phase IS NOT NULL
        ORDER BY created_at
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty or len(df) < min_support:
        return []

    # Fit detector
    detector = PatternDetector(min_support=min_support)
    detector.fit(df)

    # Get only sequence patterns (workflow transitions)
    return detector.get_patterns(pattern_type='sequence')
