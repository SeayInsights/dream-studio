"""
Automated recommendation system for dream-studio analytics.

Analyzes patterns and behaviors to generate actionable recommendations:
- Skill optimization: Better skill usage patterns
- Workflow improvements: Workflow optimizations based on success
- Inefficiency detection: Identify and fix inefficient patterns
- Performance boosters: Actions to improve performance

Uses PatternDetector and BehaviorClusterer to derive insights.

Example usage:
    >>> from analytics.ml.recommendations import RecommendationEngine, generate_recommendations
    >>> import pandas as pd
    >>>
    >>> # Generate recommendations from database
    >>> recommendations = generate_recommendations('~/.dream-studio/state/studio.db')
    >>> for rec in recommendations[:5]:
    ...     print(f"[{rec['category']}] {rec['title']} (impact: {rec['impact_score']})")
    >>>
    >>> # Or use the engine directly
    >>> engine = RecommendationEngine(min_support=3)
    >>> engine.fit(skill_telemetry_df, session_df)
    >>> skill_recs = engine.get_recommendations(category='skill_optimization', min_impact=50)
"""

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple
import warnings

from .base import BaseModel, PANDAS_AVAILABLE, NUMPY_AVAILABLE
from .patterns import PatternDetector
from .clustering import BehaviorClusterer

if PANDAS_AVAILABLE:
    import pandas as pd

if NUMPY_AVAILABLE:
    import numpy as np


class RecommendationEngine(BaseModel):
    """
    Automated recommendation system for dream-studio analytics.

    Analyzes skill patterns, behavior clusters, and session outcomes to generate
    actionable recommendations for improving workflow efficiency and performance.

    Attributes:
        fitted: Whether the model has been trained
        min_support: Minimum pattern support for reliable recommendations
        pattern_detector: Pattern detection engine
        clusterer: Behavior clustering model
        recommendations: Generated recommendations after fitting
    """

    # Recommendation categories
    CATEGORIES = {
        'skill_optimization': 'Skill Optimization',
        'workflow_improvement': 'Workflow Improvement',
        'inefficiency_detection': 'Inefficiency Detection',
        'performance_booster': 'Performance Booster'
    }

    def __init__(self, min_support: int = 3):
        """
        Initialize the recommendation engine.

        Args:
            min_support: Minimum number of occurrences for reliable patterns (default: 3)
        """
        super().__init__()
        self.min_support = max(1, min_support)
        self.pattern_detector = PatternDetector(min_support=min_support)
        self.clusterer: Optional[BehaviorClusterer] = None
        self.recommendations: List[Dict] = []
        self._skill_telemetry: Optional["pd.DataFrame"] = None
        self._session_data: Optional["pd.DataFrame"] = None

    def fit(self, skill_telemetry: "pd.DataFrame", session_data: "pd.DataFrame") -> None:
        """
        Train the recommendation engine on skill and session data.

        Args:
            skill_telemetry: DataFrame with columns: session_id, skill_name, invoked_at
            session_data: DataFrame with columns: session_id, duration, tokens, outcome
                          Optional: skills_used, time_of_day, day_of_week

        Raises:
            ValueError: If data is insufficient (<20 sessions) or dependencies are missing
        """
        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            raise ValueError("pandas and numpy are required for recommendations")

        # Validate minimum data requirement
        n_sessions = len(session_data)
        if n_sessions < 20:
            warnings.warn(
                f"Insufficient data for good recommendations: {n_sessions} sessions. "
                "Need at least 20 sessions for reliable insights."
            )
            # Still fit but recommendations will be limited
            self.fitted = True
            self.recommendations = []
            return

        self._skill_telemetry = skill_telemetry.copy()
        self._session_data = session_data.copy()

        # Fit pattern detector
        try:
            self.pattern_detector.fit(skill_telemetry)
        except Exception as e:
            warnings.warn(f"Pattern detection failed: {e}")

        # Fit behavior clusterer (if sufficient data)
        try:
            self.clusterer = BehaviorClusterer()
            self.clusterer.fit(session_data)
        except Exception as e:
            warnings.warn(f"Clustering failed: {e}")
            self.clusterer = None

        # Generate all recommendations
        self.recommendations = []
        self.recommendations.extend(self._generate_skill_optimization())
        self.recommendations.extend(self._generate_workflow_improvements())
        self.recommendations.extend(self._generate_inefficiency_detection())
        self.recommendations.extend(self._generate_performance_boosters())

        # Sort by impact score
        self.recommendations = sorted(
            self.recommendations,
            key=lambda x: x['impact_score'],
            reverse=True
        )

        self.fitted = True

    def _generate_skill_optimization(self) -> List[Dict]:
        """
        Generate skill optimization recommendations.

        Suggests better skill usage patterns based on detected patterns.

        Returns:
            List of skill optimization recommendations
        """
        recommendations = []

        if not self.pattern_detector.fitted:
            return recommendations

        # Get high-confidence sequence patterns
        sequence_patterns = self.pattern_detector.get_patterns(
            pattern_type='sequence',
            min_confidence=0.6,
            min_lift=1.5
        )

        for pattern in sequence_patterns[:10]:  # Top 10 patterns
            # Extract skills from pattern
            pattern_str = pattern['pattern']
            confidence = pattern['confidence']
            lift = pattern['lift']
            support = pattern['support']

            # Calculate impact score (0-100)
            # Higher confidence, lift, and support = higher impact
            impact = min(100, int(
                (confidence * 30) +  # Max 30 points
                (min(lift / 5, 1) * 40) +  # Max 40 points (lift normalized to 5)
                (min(support / 20, 1) * 30)  # Max 30 points (support normalized to 20)
            ))

            # Only recommend if impact is meaningful
            if impact >= 40:
                recommendations.append({
                    'category': 'skill_optimization',
                    'title': f'Adopt pattern: {pattern_str}',
                    'description': (
                        f'This skill sequence occurs {support} times with {confidence:.1%} confidence. '
                        f'Sessions using this pattern show {lift:.1f}× higher success likelihood. '
                        f'Consider adopting this workflow when appropriate.'
                    ),
                    'impact_score': impact,
                    'actionable': True,
                    'data': {
                        'pattern': pattern_str,
                        'confidence': float(confidence),
                        'lift': float(lift),
                        'support': int(support)
                    }
                })

        # Look for co-occurrence patterns that suggest complementary skills
        cooccurrence_patterns = self.pattern_detector.get_patterns(
            pattern_type='cooccurrence',
            min_lift=1.8
        )

        for pattern in cooccurrence_patterns[:5]:  # Top 5
            pattern_str = pattern['pattern']
            confidence = pattern['confidence']
            lift = pattern['lift']
            support = pattern['support']

            impact = min(100, int((confidence * 25) + (min(lift / 4, 1) * 35) + (min(support / 15, 1) * 40)))

            if impact >= 45:
                skills = pattern_str.split(' + ')
                recommendations.append({
                    'category': 'skill_optimization',
                    'title': f'Combine skills: {skills[0]} with {skills[1]}',
                    'description': (
                        f'These skills appear together in {support} sessions ({confidence:.1%} of {skills[0]} uses). '
                        f'Using both together shows {lift:.1f}× higher value. '
                        f'Consider combining these skills in your workflow.'
                    ),
                    'impact_score': impact,
                    'actionable': True,
                    'data': {
                        'skills': skills,
                        'confidence': float(confidence),
                        'lift': float(lift),
                        'support': int(support)
                    }
                })

        return recommendations

    def _generate_workflow_improvements(self) -> List[Dict]:
        """
        Generate workflow improvement recommendations.

        Analyzes successful workflows and suggests improvements.

        Returns:
            List of workflow improvement recommendations
        """
        recommendations = []

        if self._session_data is None or self._skill_telemetry is None:
            return recommendations

        # Analyze success rate by skill usage
        if 'outcome' in self._session_data.columns and 'skills_used' in self._session_data.columns:
            success_sessions = self._session_data[self._session_data['outcome'] == 'success']
            total_success = len(success_sessions)

            if total_success >= 10:
                # Find skills that appear frequently in successful sessions
                skill_success_counts = Counter()

                for skills_str in success_sessions['skills_used'].dropna():
                    if isinstance(skills_str, str):
                        for skill in skills_str.split(','):
                            skill = skill.strip()
                            if skill:
                                skill_success_counts[skill] += 1

                # Calculate success rates
                total_skill_counts = Counter()
                for skills_str in self._session_data['skills_used'].dropna():
                    if isinstance(skills_str, str):
                        for skill in skills_str.split(','):
                            skill = skill.strip()
                            if skill:
                                total_skill_counts[skill] += 1

                for skill, success_count in skill_success_counts.most_common(10):
                    total_count = total_skill_counts[skill]
                    if total_count >= self.min_support:
                        success_rate = success_count / total_count
                        overall_success_rate = total_success / len(self._session_data)

                        # Recommend skills with above-average success rates
                        if success_rate > overall_success_rate * 1.3:  # 30% better than average
                            impact = min(100, int(
                                (success_rate * 50) +
                                (min(success_count / 20, 1) * 50)
                            ))

                            if impact >= 40:
                                recommendations.append({
                                    'category': 'workflow_improvement',
                                    'title': f'Increase usage of {skill}',
                                    'description': (
                                        f'{skill} appears in {success_count}/{total_count} uses with success, '
                                        f'achieving {success_rate:.1%} success rate (vs {overall_success_rate:.1%} overall). '
                                        f'Incorporate this skill more frequently in your workflow.'
                                    ),
                                    'impact_score': impact,
                                    'actionable': True,
                                    'data': {
                                        'skill': skill,
                                        'success_rate': float(success_rate),
                                        'success_count': int(success_count),
                                        'total_count': int(total_count)
                                    }
                                })

        # Analyze temporal patterns for optimal timing
        temporal_patterns = self.pattern_detector.get_patterns(
            pattern_type='temporal_hour',
            min_lift=1.5
        )

        for pattern in temporal_patterns[:3]:  # Top 3 temporal insights
            pattern_str = pattern['pattern']
            lift = pattern['lift']

            impact = min(100, int(40 + (min(lift / 3, 1) * 60)))

            if impact >= 50:
                recommendations.append({
                    'category': 'workflow_improvement',
                    'title': f'Optimize timing: {pattern_str}',
                    'description': (
                        f'This skill/time combination shows {lift:.1f}× higher usage than average. '
                        f'Schedule similar tasks during this window for better productivity.'
                    ),
                    'impact_score': impact,
                    'actionable': True,
                    'data': {
                        'pattern': pattern_str,
                        'lift': float(lift)
                    }
                })

        return recommendations

    def _generate_inefficiency_detection(self) -> List[Dict]:
        """
        Generate inefficiency detection recommendations.

        Identifies patterns with low success rates or high costs.

        Returns:
            List of inefficiency recommendations
        """
        recommendations = []

        if self._session_data is None or self._skill_telemetry is None:
            return recommendations

        # Detect skills with low success rates
        if 'outcome' in self._session_data.columns and 'skills_used' in self._session_data.columns:
            failed_sessions = self._session_data[self._session_data['outcome'] == 'failure']
            total_failed = len(failed_sessions)

            if total_failed >= 3:
                skill_failure_counts = Counter()

                for skills_str in failed_sessions['skills_used'].dropna():
                    if isinstance(skills_str, str):
                        for skill in skills_str.split(','):
                            skill = skill.strip()
                            if skill:
                                skill_failure_counts[skill] += 1

                # Calculate failure rates
                total_skill_counts = Counter()
                for skills_str in self._session_data['skills_used'].dropna():
                    if isinstance(skills_str, str):
                        for skill in skills_str.split(','):
                            skill = skill.strip()
                            if skill:
                                total_skill_counts[skill] += 1

                for skill, failure_count in skill_failure_counts.items():
                    total_count = total_skill_counts[skill]
                    if total_count >= self.min_support:
                        failure_rate = failure_count / total_count

                        # Flag skills with high failure rates (>40%)
                        if failure_rate > 0.4:
                            impact = min(100, int(
                                (failure_rate * 60) +
                                (min(failure_count / 10, 1) * 40)
                            ))

                            recommendations.append({
                                'category': 'inefficiency_detection',
                                'title': f'High failure rate: {skill}',
                                'description': (
                                    f'{skill} fails in {failure_count}/{total_count} uses ({failure_rate:.1%}). '
                                    f'Review skill usage context, consider alternatives, or investigate root causes.'
                                ),
                                'impact_score': impact,
                                'actionable': True,
                                'data': {
                                    'skill': skill,
                                    'failure_rate': float(failure_rate),
                                    'failure_count': int(failure_count),
                                    'total_count': int(total_count)
                                }
                            })

        # Detect long-duration sessions with low token output (inefficient sessions)
        if 'duration' in self._session_data.columns and 'tokens' in self._session_data.columns:
            # Calculate token efficiency (tokens per minute)
            session_efficiency = self._session_data.copy()
            session_efficiency['duration_minutes'] = session_efficiency['duration'] / 60.0
            session_efficiency['token_efficiency'] = (
                session_efficiency['tokens'] / (session_efficiency['duration_minutes'] + 1e-6)
            )

            # Find sessions with low efficiency (bottom 20%)
            efficiency_threshold = session_efficiency['token_efficiency'].quantile(0.2)
            inefficient = session_efficiency[
                (session_efficiency['token_efficiency'] < efficiency_threshold) &
                (session_efficiency['duration_minutes'] > 10)  # Only flag longer sessions
            ]

            if len(inefficient) >= 5:
                # Analyze common skills in inefficient sessions
                skill_inefficiency_counts = Counter()

                for idx, row in inefficient.iterrows():
                    if 'skills_used' in row and isinstance(row['skills_used'], str):
                        for skill in row['skills_used'].split(','):
                            skill = skill.strip()
                            if skill:
                                skill_inefficiency_counts[skill] += 1

                # Find skills frequently appearing in inefficient sessions
                for skill, count in skill_inefficiency_counts.most_common(5):
                    if count >= self.min_support:
                        proportion = count / len(inefficient)

                        if proportion > 0.3:  # Appears in >30% of inefficient sessions
                            impact = min(100, int(50 + (proportion * 50)))

                            recommendations.append({
                                'category': 'inefficiency_detection',
                                'title': f'Low efficiency pattern: {skill}',
                                'description': (
                                    f'{skill} appears in {count} low-efficiency sessions ({proportion:.1%}). '
                                    f'Sessions with this skill tend to have lower token output per time spent. '
                                    f'Review usage approach or workflow integration.'
                                ),
                                'impact_score': impact,
                                'actionable': True,
                                'data': {
                                    'skill': skill,
                                    'inefficient_count': int(count),
                                    'total_inefficient': len(inefficient)
                                }
                            })

        return recommendations

    def _generate_performance_boosters(self) -> List[Dict]:
        """
        Generate performance booster recommendations.

        Based on clustering and benchmarks, suggest actions to improve performance.

        Returns:
            List of performance booster recommendations
        """
        recommendations = []

        if self.clusterer is None or not self.clusterer.fitted:
            return recommendations

        # Get cluster information
        try:
            cluster_eval = self.clusterer.evaluate(self._session_data)
            cluster_info = cluster_eval.get('cluster_info', [])

            # Find the highest-performing cluster
            best_cluster = max(
                cluster_info,
                key=lambda c: c['characteristics']['avg_success_rate']
            ) if cluster_info else None

            if best_cluster:
                best_chars = best_cluster['characteristics']
                best_label = best_cluster.get('label', 'Unknown')

                # Recommend adopting characteristics of best cluster
                impact = min(100, int(60 + (best_chars['avg_success_rate'] * 40)))

                recommendations.append({
                    'category': 'performance_booster',
                    'title': f'Adopt {best_label} behavior pattern',
                    'description': (
                        f'The "{best_label}" cluster shows best performance with '
                        f'{best_chars["avg_success_rate"]:.1%} success rate. '
                        f'Key characteristics: '
                        f'{best_chars["avg_duration_minutes"]:.1f} min sessions, '
                        f'{best_chars["avg_skills_count"]:.1f} skills per session, '
                        f'{best_chars["avg_token_efficiency"]:.0f} tokens/min. '
                        f'Adjust your workflow to match these patterns.'
                    ),
                    'impact_score': impact,
                    'actionable': True,
                    'data': {
                        'cluster_label': best_label,
                        'characteristics': best_chars
                    }
                })

            # Compare user's current performance to benchmarks
            if 'outcome' in self._session_data.columns:
                overall_success = (
                    self._session_data['outcome'] == 'success'
                ).mean()

                # If overall success is below 70%, recommend improvement
                if overall_success < 0.7:
                    gap = 0.7 - overall_success
                    impact = min(100, int(50 + (gap * 100)))

                    recommendations.append({
                        'category': 'performance_booster',
                        'title': 'Improve overall success rate',
                        'description': (
                            f'Current success rate is {overall_success:.1%}, below the 70% benchmark. '
                            f'Review failed sessions to identify common issues, '
                            f'adopt successful patterns from high-performing clusters, '
                            f'and refine skill usage strategies.'
                        ),
                        'impact_score': impact,
                        'actionable': True,
                        'data': {
                            'current_success_rate': float(overall_success),
                            'target_success_rate': 0.7,
                            'gap': float(gap)
                        }
                    })

        except Exception as e:
            warnings.warn(f"Failed to generate cluster-based recommendations: {e}")

        # Recommend session length optimization if variance is high
        if 'duration' in self._session_data.columns:
            durations = self._session_data['duration'] / 60.0  # Convert to minutes
            mean_duration = durations.mean()
            std_duration = durations.std()

            if std_duration > mean_duration * 0.8:  # High variance
                impact = 60

                recommendations.append({
                    'category': 'performance_booster',
                    'title': 'Standardize session duration',
                    'description': (
                        f'Session durations vary widely (avg: {mean_duration:.1f} min, '
                        f'std: {std_duration:.1f} min). '
                        f'Consider breaking long sessions into focused chunks, '
                        f'or consolidating quick tasks for better efficiency.'
                    ),
                    'impact_score': impact,
                    'actionable': True,
                    'data': {
                        'mean_duration_minutes': float(mean_duration),
                        'std_duration_minutes': float(std_duration)
                    }
                })

        return recommendations

    def predict(self, data: "pd.DataFrame") -> "np.ndarray":
        """
        Make predictions (not applicable for recommendation systems).

        Args:
            data: Input data (not used)

        Returns:
            Empty array (recommendations are generated during fit)
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before prediction")

        if not NUMPY_AVAILABLE:
            return []

        return np.array([])

    def evaluate(self, data: "pd.DataFrame", target: "np.ndarray" = None) -> Dict:
        """
        Evaluate recommendation quality.

        Args:
            data: Input data (not used)
            target: True values (not applicable)

        Returns:
            Dictionary with recommendation statistics
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before evaluation")

        # Count recommendations by category
        category_counts = Counter([r['category'] for r in self.recommendations])

        # Calculate average impact by category
        category_impacts = defaultdict(list)
        for rec in self.recommendations:
            category_impacts[rec['category']].append(rec['impact_score'])

        avg_impacts = {
            cat: float(np.mean(impacts)) if impacts else 0.0
            for cat, impacts in category_impacts.items()
        }

        return {
            'total_recommendations': len(self.recommendations),
            'recommendations_by_category': dict(category_counts),
            'avg_impact_by_category': avg_impacts,
            'high_impact_count': sum(1 for r in self.recommendations if r['impact_score'] >= 70),
            'actionable_count': sum(1 for r in self.recommendations if r['actionable'])
        }

    def get_recommendations(
        self,
        category: Optional[str] = None,
        min_impact: Optional[int] = None,
        actionable_only: bool = False,
        top_n: Optional[int] = None
    ) -> List[Dict]:
        """
        Get recommendations with optional filtering.

        Args:
            category: Filter by category ('skill_optimization', 'workflow_improvement', etc.)
            min_impact: Minimum impact score (0-100)
            actionable_only: Only return actionable recommendations
            top_n: Return only top N recommendations (by impact)

        Returns:
            List of recommendations matching the criteria

        Raises:
            RuntimeError: If model has not been fitted
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before retrieving recommendations")

        filtered = self.recommendations

        # Apply filters
        if category is not None:
            filtered = [r for r in filtered if r['category'] == category]

        if min_impact is not None:
            filtered = [r for r in filtered if r['impact_score'] >= min_impact]

        if actionable_only:
            filtered = [r for r in filtered if r['actionable']]

        # Already sorted by impact during fit, just limit if needed
        if top_n is not None:
            filtered = filtered[:top_n]

        return filtered


def generate_recommendations(
    db_path: str,
    min_support: int = 3,
    min_impact: Optional[int] = None
) -> List[Dict]:
    """
    Generate recommendations from the dream-studio database.

    Args:
        db_path: Path to dream-studio SQLite database
        min_support: Minimum pattern support (default: 3)
        min_impact: Minimum impact score filter (optional)

    Returns:
        List of recommendations sorted by impact score

    Raises:
        ValueError: If insufficient data (<20 sessions) or dependencies missing
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for recommendations")

    import sqlite3

    # Load skill telemetry
    conn = sqlite3.connect(db_path)

    skill_query = """
        SELECT
            session_id,
            skill_name,
            invoked_at
        FROM raw_skill_telemetry
        WHERE session_id IS NOT NULL
        ORDER BY invoked_at
    """
    skill_df = pd.read_sql_query(skill_query, conn)

    # Load session data
    # Note: This is a simplified query - actual table structure may vary
    session_query = """
        SELECT
            session_id,
            duration,
            total_tokens as tokens,
            outcome,
            skills_used
        FROM agg_sessions
        WHERE duration IS NOT NULL AND total_tokens IS NOT NULL
    """
    try:
        session_df = pd.read_sql_query(session_query, conn)
    except Exception:
        # Fallback: construct session data from telemetry
        warnings.warn("Could not load session table, constructing from telemetry")
        session_df = _construct_session_data(skill_df)

    conn.close()

    # Fit engine and generate recommendations
    engine = RecommendationEngine(min_support=min_support)
    engine.fit(skill_df, session_df)

    # Get recommendations with optional impact filter
    return engine.get_recommendations(min_impact=min_impact)


def _construct_session_data(skill_df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Construct session data from skill telemetry when session table unavailable.

    Args:
        skill_df: Skill telemetry DataFrame

    Returns:
        Constructed session DataFrame with basic metrics
    """
    if skill_df.empty:
        return pd.DataFrame(columns=['session_id', 'duration', 'tokens', 'outcome', 'skills_used'])

    # Convert timestamps
    skill_df['invoked_at'] = pd.to_datetime(skill_df['invoked_at'])

    # Group by session
    sessions = []

    for session_id, group in skill_df.groupby('session_id'):
        start_time = group['invoked_at'].min()
        end_time = group['invoked_at'].max()
        duration = (end_time - start_time).total_seconds()

        skills_used = ','.join(group['skill_name'].unique())

        # Estimate tokens (rough heuristic: 50 tokens per skill invocation)
        tokens = len(group) * 50

        # Assume success (no outcome data available)
        outcome = 'success'

        sessions.append({
            'session_id': session_id,
            'duration': duration,
            'tokens': tokens,
            'outcome': outcome,
            'skills_used': skills_used
        })

    return pd.DataFrame(sessions)
