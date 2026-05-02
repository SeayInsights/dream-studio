"""
Base classes and utilities for ML operations in dream-studio analytics.

Provides:
- BaseModel abstract class for ML models
- Data validation and preparation utilities
- Graceful handling of missing dependencies
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
import warnings

# Try to import ML dependencies with graceful fallbacks
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    warnings.warn(
        "pandas not available. ML utilities will have limited functionality. "
        "Install with: pip install pandas>=2.0"
    )

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    warnings.warn(
        "numpy not available. ML utilities will have limited functionality. "
        "Install with: pip install numpy"
    )


class BaseModel(ABC):
    """
    Abstract base class for ML models in dream-studio analytics.

    All ML models should inherit from this class and implement
    the required abstract methods.

    Attributes:
        fitted: Whether the model has been trained
    """

    def __init__(self):
        """Initialize the base model."""
        self.fitted = False

    @abstractmethod
    def fit(self, data: "pd.DataFrame") -> None:
        """
        Train the model on the provided data.

        Args:
            data: Training data as a pandas DataFrame

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        pass

    @abstractmethod
    def predict(self, data: "pd.DataFrame") -> "np.ndarray":
        """
        Make predictions using the trained model.

        Args:
            data: Input data as a pandas DataFrame

        Returns:
            Predictions as a numpy array

        Raises:
            NotImplementedError: Must be implemented by subclass
            RuntimeError: If model has not been fitted
        """
        pass

    @abstractmethod
    def evaluate(self, data: "pd.DataFrame", target: "np.ndarray") -> dict:
        """
        Evaluate model performance on the provided data.

        Args:
            data: Input data as a pandas DataFrame
            target: True target values as a numpy array

        Returns:
            Dictionary of evaluation metrics (e.g., {"accuracy": 0.95, "mse": 0.05})

        Raises:
            NotImplementedError: Must be implemented by subclass
            RuntimeError: If model has not been fitted
        """
        pass


def validate_dataframe(
    df: "pd.DataFrame",
    required_columns: List[str]
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a DataFrame has the required columns.

    Args:
        df: DataFrame to validate
        required_columns: List of column names that must be present

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if all required columns are present
        - error_message: None if valid, error description otherwise

    Examples:
        >>> df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        >>> validate_dataframe(df, ["a", "b"])
        (True, None)
        >>> validate_dataframe(df, ["a", "c"])
        (False, "Missing required columns: ['c']")
    """
    if not PANDAS_AVAILABLE:
        return False, "pandas is not installed"

    if not isinstance(df, pd.DataFrame):
        return False, "Input is not a pandas DataFrame"

    if df.empty:
        return False, "DataFrame is empty"

    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        return False, f"Missing required columns: {missing_cols}"

    return True, None


def prepare_time_series(
    df: "pd.DataFrame",
    timestamp_col: str,
    value_col: str,
    sort: bool = True
) -> "pd.DataFrame":
    """
    Prepare time series data for analysis.

    Validates columns, ensures timestamp is datetime type, and optionally sorts.

    Args:
        df: Input DataFrame
        timestamp_col: Name of the timestamp column
        value_col: Name of the value column
        sort: Whether to sort by timestamp (default: True)

    Returns:
        Prepared DataFrame with datetime index

    Raises:
        ValueError: If required columns are missing or pandas is not available

    Examples:
        >>> df = pd.DataFrame({
        ...     "time": ["2024-01-01", "2024-01-02"],
        ...     "metric": [10, 20]
        ... })
        >>> prepared = prepare_time_series(df, "time", "metric")
        >>> prepared.index.name
        'time'
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for time series preparation")

    # Validate columns
    is_valid, error_msg = validate_dataframe(df, [timestamp_col, value_col])
    if not is_valid:
        raise ValueError(f"Invalid DataFrame: {error_msg}")

    # Create a copy to avoid modifying original
    result = df.copy()

    # Convert timestamp to datetime if needed
    if not pd.api.types.is_datetime64_any_dtype(result[timestamp_col]):
        result[timestamp_col] = pd.to_datetime(result[timestamp_col])

    # Sort by timestamp if requested
    if sort:
        result = result.sort_values(timestamp_col)

    # Set timestamp as index
    result = result.set_index(timestamp_col)

    return result


def train_test_split_temporal(
    df: "pd.DataFrame",
    test_size: float = 0.2,
    shuffle: bool = False
) -> Tuple["pd.DataFrame", "pd.DataFrame"]:
    """
    Split time series data into train and test sets while preserving temporal order.

    Unlike standard train_test_split, this function respects the temporal
    nature of the data and does not shuffle by default.

    Args:
        df: Input DataFrame (should be sorted by time)
        test_size: Proportion of data to use for testing (0.0 to 1.0)
        shuffle: Whether to shuffle before splitting (default: False, not recommended for time series)

    Returns:
        Tuple of (train_df, test_df)

    Raises:
        ValueError: If test_size is not between 0 and 1 or pandas is not available

    Examples:
        >>> df = pd.DataFrame({"value": range(100)})
        >>> train, test = train_test_split_temporal(df, test_size=0.2)
        >>> len(train), len(test)
        (80, 20)
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for train/test split")

    if not 0.0 < test_size < 1.0:
        raise ValueError(f"test_size must be between 0 and 1, got {test_size}")

    if df.empty:
        raise ValueError("Cannot split empty DataFrame")

    # Optionally shuffle (not recommended for time series)
    if shuffle:
        df = df.sample(frac=1.0, replace=False)

    # Calculate split point
    split_idx = int(len(df) * (1 - test_size))

    # Split while preserving order
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    return train_df, test_df
