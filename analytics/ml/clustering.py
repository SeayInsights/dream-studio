"""
User behavior clustering for dream-studio analytics.

Provides clustering for:
- Session behavior patterns (duration, skills, tokens, outcomes)
- User persona identification ("Power User", "Quick Task", "Exploratory")
- Behavior segmentation

Supports K-means clustering when sklearn is available,
with simple centroid-based fallback otherwise.
"""

from typing import Dict, List, Optional, Tuple
import warnings

from .base import BaseModel, PANDAS_AVAILABLE, NUMPY_AVAILABLE

# Try to import sklearn for advanced clustering
try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    warnings.warn(
        "scikit-learn not available. Clustering will use simple centroid-based fallback. "
        "Install with: pip install scikit-learn"
    )

if PANDAS_AVAILABLE:
    import pandas as pd

if NUMPY_AVAILABLE:
    import numpy as np


class BehaviorClusterer(BaseModel):
    """
    User behavior clustering model for dream-studio analytics.

    Clusters sessions by characteristics (duration, skills used, token usage, outcomes)
    to identify user personas and behavior patterns.

    Uses K-means when sklearn is available, simple centroid-based clustering otherwise.

    Attributes:
        fitted: Whether the model has been trained
        n_clusters: Number of clusters to create
        cluster_centers: Cluster centroids
        cluster_labels: Assigned cluster labels for each session
        feature_names: Names of features used for clustering
        scaler: Feature scaler (sklearn only)
        personas: Dict mapping cluster_id to persona labels
    """

    PERSONA_LABELS = {
        "high_duration_high_skills": "Power User",
        "low_duration_low_skills": "Quick Task",
        "high_skills_varied_duration": "Exploratory",
        "high_tokens_focused_skills": "Deep Work",
        "balanced": "Balanced User"
    }

    def __init__(self, n_clusters: Optional[int] = None, random_state: int = 42):
        """
        Initialize the behavior clusterer.

        Args:
            n_clusters: Number of clusters (None = auto-detect optimal, 2-5 range)
            random_state: Random seed for reproducibility
        """
        super().__init__()
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.cluster_centers = None
        self.cluster_labels = None
        self.feature_names = None
        self.scaler = None
        self.personas = {}

    def _extract_features(self, data: "pd.DataFrame") -> "pd.DataFrame":
        """
        Extract and engineer features from session data.

        Features include:
        - Session duration (normalized)
        - Skill diversity (unique skills / total skills)
        - Token efficiency (tokens per minute)
        - Success rate (proportion of successful outcomes)
        - Skills per session (average)

        Args:
            data: DataFrame with columns: duration, skills_used, tokens, outcome

        Returns:
            DataFrame with engineered features
        """
        features = pd.DataFrame()

        # Session duration in minutes (normalized)
        features['duration_minutes'] = data['duration'] / 60.0

        # Skill diversity: unique skills / total skills (0-1 scale)
        if 'skills_used' in data.columns:
            features['skill_diversity'] = data['skills_used'].apply(
                lambda x: len(set(x.split(','))) / len(x.split(',')) if isinstance(x, str) and x else 0
            )
            # Number of skills per session
            features['skills_count'] = data['skills_used'].apply(
                lambda x: len(x.split(',')) if isinstance(x, str) and x else 0
            )
        else:
            features['skill_diversity'] = 0
            features['skills_count'] = 0

        # Token efficiency: tokens per minute
        features['token_efficiency'] = data['tokens'] / (features['duration_minutes'] + 1e-6)

        # Success rate (binary outcome)
        if 'outcome' in data.columns:
            features['success'] = data['outcome'].apply(
                lambda x: 1 if x == 'success' else 0
            )
        else:
            features['success'] = 0

        # Time-of-day features (if available)
        if 'time_of_day' in data.columns:
            # Convert time_of_day to hour (0-23)
            features['hour'] = data['time_of_day'].apply(
                lambda x: x.hour if hasattr(x, 'hour') else 12
            )
            # Cyclical encoding for hour (sin/cos to preserve continuity)
            features['hour_sin'] = np.sin(2 * np.pi * features['hour'] / 24)
            features['hour_cos'] = np.cos(2 * np.pi * features['hour'] / 24)
            features = features.drop('hour', axis=1)

        # Day-of-week features (if available)
        if 'day_of_week' in data.columns:
            features['weekday'] = data['day_of_week'].apply(
                lambda x: x.weekday() if hasattr(x, 'weekday') else 0
            )
            # Cyclical encoding for weekday (0=Monday, 6=Sunday)
            features['weekday_sin'] = np.sin(2 * np.pi * features['weekday'] / 7)
            features['weekday_cos'] = np.cos(2 * np.pi * features['weekday'] / 7)
            features = features.drop('weekday', axis=1)

        self.feature_names = features.columns.tolist()
        return features

    def _determine_optimal_clusters(self, features: "np.ndarray", max_clusters: int = 5) -> int:
        """
        Determine optimal number of clusters using elbow method.

        Args:
            features: Feature matrix (n_samples, n_features)
            max_clusters: Maximum number of clusters to consider

        Returns:
            Optimal number of clusters (2-5 range)
        """
        if not SKLEARN_AVAILABLE or not NUMPY_AVAILABLE:
            # Default to 3 clusters if no sklearn
            return 3

        # Need at least 10 samples for meaningful clustering
        n_samples = features.shape[0]
        if n_samples < 10:
            return min(2, n_samples)

        # Try 2 to max_clusters and compute inertia
        inertias = []
        K_range = range(2, min(max_clusters + 1, n_samples))

        for k in K_range:
            kmeans = KMeans(n_clusters=k, random_state=self.random_state, n_init=10)
            kmeans.fit(features)
            inertias.append(kmeans.inertia_)

        # Find elbow using second derivative
        if len(inertias) < 3:
            return 2

        # Calculate rate of change
        deltas = np.diff(inertias)
        second_deltas = np.diff(deltas)

        # Find point where improvement slows down
        elbow_idx = np.argmax(second_deltas) + 2  # +2 because of two diff operations

        return min(max(elbow_idx, 2), max_clusters)

    def _assign_personas(self, cluster_info: List[Dict]) -> None:
        """
        Assign persona labels to clusters based on characteristics.

        Args:
            cluster_info: List of cluster characteristic dicts
        """
        for cluster in cluster_info:
            cid = cluster['cluster_id']
            chars = cluster['characteristics']

            # Extract key metrics
            duration = chars.get('avg_duration_minutes', 0)
            skills = chars.get('avg_skills_count', 0)
            token_eff = chars.get('avg_token_efficiency', 0)
            diversity = chars.get('avg_skill_diversity', 0)

            # Classify persona based on characteristics
            if duration > 30 and skills > 3:
                label = self.PERSONA_LABELS["high_duration_high_skills"]
            elif duration < 10 and skills < 2:
                label = self.PERSONA_LABELS["low_duration_low_skills"]
            elif diversity > 0.7 and skills > 2:
                label = self.PERSONA_LABELS["high_skills_varied_duration"]
            elif token_eff > 50 and skills <= 2:
                label = self.PERSONA_LABELS["high_tokens_focused_skills"]
            else:
                label = self.PERSONA_LABELS["balanced"]

            self.personas[cid] = label
            cluster['label'] = label

    def fit(self, data: "pd.DataFrame") -> None:
        """
        Train the clustering model on session data.

        Args:
            data: DataFrame with columns: duration, skills_used, tokens, outcome
                  Optional: time_of_day, day_of_week

        Raises:
            ValueError: If data has fewer than 10 sessions or missing required columns
        """
        if not PANDAS_AVAILABLE:
            raise ValueError("pandas is required for clustering")

        if len(data) < 10:
            raise ValueError(
                f"Insufficient data for clustering: {len(data)} sessions. "
                "Need at least 10 sessions."
            )

        # Check required columns
        required_cols = ['duration', 'tokens']
        missing = [col for col in required_cols if col not in data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Extract and engineer features
        features = self._extract_features(data)

        # Convert to numpy
        if NUMPY_AVAILABLE:
            feature_matrix = features.values
        else:
            feature_matrix = features.to_numpy()

        # Determine optimal cluster count if not specified
        if self.n_clusters is None:
            self.n_clusters = self._determine_optimal_clusters(feature_matrix)

        # Scale features
        if SKLEARN_AVAILABLE:
            self.scaler = StandardScaler()
            scaled_features = self.scaler.fit_transform(feature_matrix)
        else:
            # Simple min-max scaling fallback
            scaled_features = self._simple_scale(feature_matrix)

        # Fit clustering model
        if SKLEARN_AVAILABLE:
            kmeans = KMeans(
                n_clusters=self.n_clusters,
                random_state=self.random_state,
                n_init=10
            )
            self.cluster_labels = kmeans.fit_predict(scaled_features)
            self.cluster_centers = kmeans.cluster_centers_
        else:
            # Simple centroid-based clustering fallback
            self.cluster_labels, self.cluster_centers = self._simple_kmeans(
                scaled_features,
                self.n_clusters
            )

        self.fitted = True

    def predict(self, data: "pd.DataFrame") -> "np.ndarray":
        """
        Predict cluster assignments for new session data.

        Args:
            data: DataFrame with same columns as training data

        Returns:
            Array of cluster labels (integers)

        Raises:
            RuntimeError: If model has not been fitted
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before prediction")

        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            raise ValueError("pandas and numpy are required for prediction")

        # Extract features
        features = self._extract_features(data)
        feature_matrix = features.values

        # Scale features
        if SKLEARN_AVAILABLE and self.scaler:
            scaled_features = self.scaler.transform(feature_matrix)
        else:
            scaled_features = self._simple_scale(feature_matrix)

        # Assign to nearest cluster
        labels = self._assign_to_nearest(scaled_features, self.cluster_centers)

        return labels

    def evaluate(self, data: "pd.DataFrame", target: "np.ndarray" = None) -> Dict:
        """
        Evaluate clustering quality.

        Args:
            data: Input session data
            target: Optional true labels (not typically available for clustering)

        Returns:
            Dict with metrics: silhouette_score, cluster_sizes, cluster_info

        Raises:
            RuntimeError: If model has not been fitted
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before evaluation")

        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            raise ValueError("pandas and numpy are required for evaluation")

        # Get cluster assignments
        labels = self.predict(data)

        # Compute cluster sizes
        unique, counts = np.unique(labels, return_counts=True)
        cluster_sizes = dict(zip(unique.tolist(), counts.tolist()))

        # Compute cluster characteristics
        features = self._extract_features(data)
        cluster_info = []

        for cluster_id in unique:
            mask = labels == cluster_id
            cluster_features = features[mask]

            characteristics = {
                'avg_duration_minutes': float(cluster_features['duration_minutes'].mean()),
                'avg_skills_count': float(cluster_features['skills_count'].mean()),
                'avg_skill_diversity': float(cluster_features['skill_diversity'].mean()),
                'avg_token_efficiency': float(cluster_features['token_efficiency'].mean()),
                'avg_success_rate': float(cluster_features['success'].mean()),
            }

            cluster_info.append({
                'cluster_id': int(cluster_id),
                'size': int(cluster_sizes[cluster_id]),
                'characteristics': characteristics
            })

        # Assign persona labels
        self._assign_personas(cluster_info)

        # Compute silhouette score if sklearn available
        silhouette = None
        if SKLEARN_AVAILABLE:
            try:
                from sklearn.metrics import silhouette_score
                feature_matrix = features.values
                if len(unique) > 1 and len(feature_matrix) > 1:
                    scaled_features = self.scaler.transform(feature_matrix) if self.scaler else feature_matrix
                    silhouette = float(silhouette_score(scaled_features, labels))
            except Exception as e:
                warnings.warn(f"Could not compute silhouette score: {e}")

        return {
            'n_clusters': int(self.n_clusters),
            'cluster_sizes': cluster_sizes,
            'cluster_info': cluster_info,
            'silhouette_score': silhouette
        }

    def _simple_scale(self, features: "np.ndarray") -> "np.ndarray":
        """
        Simple min-max scaling fallback when sklearn unavailable.

        Args:
            features: Feature matrix (n_samples, n_features)

        Returns:
            Scaled feature matrix
        """
        if not NUMPY_AVAILABLE:
            return features

        scaled = features.copy()
        for i in range(features.shape[1]):
            col = features[:, i]
            min_val = col.min()
            max_val = col.max()
            if max_val - min_val > 1e-6:
                scaled[:, i] = (col - min_val) / (max_val - min_val)
            else:
                scaled[:, i] = 0
        return scaled

    def _simple_kmeans(
        self,
        features: "np.ndarray",
        n_clusters: int,
        max_iters: int = 100
    ) -> Tuple["np.ndarray", "np.ndarray"]:
        """
        Simple K-means clustering fallback when sklearn unavailable.

        Args:
            features: Feature matrix (n_samples, n_features)
            n_clusters: Number of clusters
            max_iters: Maximum iterations

        Returns:
            Tuple of (labels, centers)
        """
        if not NUMPY_AVAILABLE:
            raise ValueError("numpy is required for simple k-means")

        n_samples = features.shape[0]

        # Initialize centers randomly
        np.random.seed(self.random_state)
        center_indices = np.random.choice(n_samples, n_clusters, replace=False)
        centers = features[center_indices].copy()

        labels = np.zeros(n_samples, dtype=int)

        # Iterate until convergence or max_iters
        for _ in range(max_iters):
            # Assign to nearest center
            labels = self._assign_to_nearest(features, centers)

            # Update centers
            new_centers = np.zeros_like(centers)
            for i in range(n_clusters):
                mask = labels == i
                if mask.sum() > 0:
                    new_centers[i] = features[mask].mean(axis=0)
                else:
                    # If cluster is empty, reinitialize randomly
                    new_centers[i] = features[np.random.randint(n_samples)]

            # Check convergence
            if np.allclose(centers, new_centers):
                break

            centers = new_centers

        return labels, centers

    def _assign_to_nearest(
        self,
        features: "np.ndarray",
        centers: "np.ndarray"
    ) -> "np.ndarray":
        """
        Assign each sample to nearest cluster center.

        Args:
            features: Feature matrix (n_samples, n_features)
            centers: Cluster centers (n_clusters, n_features)

        Returns:
            Array of cluster labels
        """
        if not NUMPY_AVAILABLE:
            raise ValueError("numpy is required for cluster assignment")

        n_samples = features.shape[0]
        labels = np.zeros(n_samples, dtype=int)

        for i in range(n_samples):
            # Compute distance to each center
            distances = np.sum((centers - features[i]) ** 2, axis=1)
            # Assign to nearest
            labels[i] = np.argmin(distances)

        return labels

    def get_cluster_info(self) -> List[Dict]:
        """
        Get detailed information about each cluster.

        Returns:
            List of dicts with cluster_id, label, size, characteristics

        Raises:
            RuntimeError: If model has not been fitted
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before getting cluster info")

        # Note: This assumes evaluate() has been called to populate personas
        # In production, you'd want to store this during fit()
        return []  # Placeholder - populated via evaluate()
