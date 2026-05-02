"""
Model persistence and versioning for dream-studio analytics ML models.

Provides storage, loading, versioning, and metadata tracking for trained models.
Handles graceful fallback when pickle/joblib is unavailable.
"""

import json
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import BaseModel

# Try to import serialization libraries with graceful fallbacks
try:
    import joblib
    JOBLIB_AVAILABLE = True
    SERIALIZER = "joblib"
except ImportError:
    JOBLIB_AVAILABLE = False
    try:
        import pickle
        PICKLE_AVAILABLE = True
        SERIALIZER = "pickle"
    except ImportError:
        PICKLE_AVAILABLE = False
        SERIALIZER = None
        warnings.warn(
            "Neither joblib nor pickle available. Model persistence disabled. "
            "Install with: pip install joblib (recommended) or use built-in pickle"
        )


def save_model(
    model: BaseModel,
    filepath: str,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Save a trained model to disk with metadata.

    Args:
        model: Trained BaseModel instance to save
        filepath: Path where model should be saved (will add timestamp and extension)
        metadata: Optional dictionary of additional metadata to store

    Returns:
        True if save succeeded, False otherwise

    Examples:
        >>> from analytics.ml.forecaster import TimeSeriesForecaster
        >>> model = TimeSeriesForecaster()
        >>> # ... train model ...
        >>> save_model(model, "models/forecaster", {"accuracy": 0.95})
        True

    Notes:
        - Automatically adds timestamp to filename (e.g., forecaster_2026-05-01_143022.pkl)
        - Uses joblib if available (better for scikit-learn models), falls back to pickle
        - Saves metadata separately as JSON file alongside model
        - Creates parent directory if it doesn't exist
    """
    if SERIALIZER is None:
        warnings.warn("Cannot save model: no serialization library available")
        return False

    if not isinstance(model, BaseModel):
        warnings.warn(f"Model is not a BaseModel instance: {type(model)}")
        return False

    try:
        # Add timestamp to filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = Path(filepath)
        base_name = path.stem
        parent_dir = path.parent

        # Create versioned filename
        extension = ".pkl" if SERIALIZER == "pickle" else ".joblib"
        versioned_name = f"{base_name}_{timestamp}{extension}"
        model_path = parent_dir / versioned_name
        metadata_path = parent_dir / f"{base_name}_{timestamp}_metadata.json"

        # Create directory if it doesn't exist
        parent_dir.mkdir(parents=True, exist_ok=True)

        # Prepare metadata
        model_metadata = {
            "saved_at": timestamp,
            "model_type": model.__class__.__name__,
            "model_module": model.__class__.__module__,
            "serializer": SERIALIZER,
            "fitted": getattr(model, "fitted", False),
        }

        # Add custom metadata if provided
        if metadata:
            model_metadata.update(metadata)

        # Save model
        if SERIALIZER == "joblib":
            joblib.dump(model, model_path, compress=3)
        else:  # pickle
            with open(model_path, "wb") as f:
                pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)

        # Save metadata
        with open(metadata_path, "w") as f:
            json.dump(model_metadata, f, indent=2)

        return True

    except Exception as e:
        warnings.warn(f"Failed to save model: {e}")
        return False


def load_model(filepath: str) -> Optional[BaseModel]:
    """
    Load a trained model from disk.

    Args:
        filepath: Path to the saved model file

    Returns:
        Loaded BaseModel instance, or None if loading failed

    Examples:
        >>> model = load_model("models/forecaster_2026-05-01_143022.pkl")
        >>> if model:
        ...     predictions = model.predict(new_data)

    Notes:
        - Automatically detects serialization format from file extension
        - Returns None if file doesn't exist or loading fails
        - Validates that loaded object is a BaseModel instance
    """
    if SERIALIZER is None:
        warnings.warn("Cannot load model: no serialization library available")
        return None

    path = Path(filepath)
    if not path.exists():
        warnings.warn(f"Model file not found: {filepath}")
        return None

    try:
        # Detect format from extension
        extension = path.suffix.lower()

        if extension == ".joblib" and JOBLIB_AVAILABLE:
            model = joblib.load(path)
        elif extension == ".pkl":
            with open(path, "rb") as f:
                model = pickle.load(f)
        else:
            warnings.warn(f"Unsupported model file format: {extension}")
            return None

        # Validate it's a BaseModel instance
        if not isinstance(model, BaseModel):
            warnings.warn(f"Loaded object is not a BaseModel: {type(model)}")
            return None

        return model

    except Exception as e:
        warnings.warn(f"Failed to load model: {e}")
        return None


def list_saved_models(directory: str) -> List[Dict[str, Any]]:
    """
    List all saved models in a directory with their metadata.

    Args:
        directory: Directory path to search for saved models

    Returns:
        List of dictionaries containing model information:
        - filepath: Full path to model file
        - filename: Model filename
        - metadata: Dictionary of metadata (if available)
        - size_bytes: File size in bytes
        - modified_at: Last modification timestamp
        - is_stale: Whether model is older than 7 days

    Examples:
        >>> models = list_saved_models("models/")
        >>> for model in models:
        ...     print(f"{model['filename']}: {model['metadata'].get('model_type')}")
        forecaster_2026-05-01_143022.pkl: TimeSeriesForecaster

    Notes:
        - Looks for .pkl and .joblib files
        - Attempts to load matching metadata JSON files
        - Returns empty list if directory doesn't exist
        - Models older than 7 days are marked as stale
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return []

    models = []

    # Find all model files
    for ext in ["*.pkl", "*.joblib"]:
        for model_file in dir_path.glob(ext):
            # Skip metadata files
            if model_file.stem.endswith("_metadata"):
                continue

            # Try to load metadata
            metadata_file = model_file.with_name(f"{model_file.stem}_metadata.json")
            metadata = {}
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r") as f:
                        metadata = json.load(f)
                except Exception as e:
                    warnings.warn(f"Failed to load metadata for {model_file.name}: {e}")

            # Get file stats
            stat = model_file.stat()
            modified_at = datetime.fromtimestamp(stat.st_mtime)
            is_stale = is_model_stale(str(model_file))

            models.append({
                "filepath": str(model_file.absolute()),
                "filename": model_file.name,
                "metadata": metadata,
                "size_bytes": stat.st_size,
                "modified_at": modified_at.isoformat(),
                "is_stale": is_stale,
            })

    # Sort by modification time (newest first)
    models.sort(key=lambda x: x["modified_at"], reverse=True)

    return models


def delete_model(filepath: str) -> bool:
    """
    Delete a saved model and its metadata file.

    Args:
        filepath: Path to the model file to delete

    Returns:
        True if deletion succeeded, False otherwise

    Examples:
        >>> delete_model("models/old_forecaster_2026-04-01_120000.pkl")
        True

    Notes:
        - Also deletes the associated metadata JSON file if it exists
        - Returns True even if metadata file doesn't exist
        - Returns False only if model file deletion fails
    """
    model_path = Path(filepath)

    if not model_path.exists():
        warnings.warn(f"Model file not found: {filepath}")
        return False

    try:
        # Delete model file
        model_path.unlink()

        # Try to delete metadata file
        metadata_file = model_path.with_name(f"{model_path.stem}_metadata.json")
        if metadata_file.exists():
            try:
                metadata_file.unlink()
            except Exception as e:
                warnings.warn(f"Failed to delete metadata file: {e}")

        return True

    except Exception as e:
        warnings.warn(f"Failed to delete model: {e}")
        return False


def is_model_stale(
    filepath: str,
    max_age_days: int = 7
) -> bool:
    """
    Check if a model is stale (older than specified age).

    Args:
        filepath: Path to the model file
        max_age_days: Maximum age in days before model is considered stale (default: 7)

    Returns:
        True if model is stale, False otherwise

    Examples:
        >>> is_model_stale("models/forecaster_2026-04-01_120000.pkl", max_age_days=7)
        True
        >>> is_model_stale("models/forecaster_2026-05-01_120000.pkl", max_age_days=1)
        False

    Notes:
        - Returns False if file doesn't exist
        - Based on file modification time, not metadata timestamp
        - Useful for auto-refresh detection in production systems
    """
    model_path = Path(filepath)

    if not model_path.exists():
        return False

    try:
        # Get file modification time
        stat = model_path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime)

        # Check age
        age = datetime.now() - modified_at
        return age > timedelta(days=max_age_days)

    except Exception as e:
        warnings.warn(f"Failed to check model staleness: {e}")
        return False


def get_model_metadata(filepath: str) -> Optional[Dict[str, Any]]:
    """
    Load metadata for a saved model without loading the model itself.

    Args:
        filepath: Path to the model file

    Returns:
        Dictionary of metadata, or None if not found

    Examples:
        >>> metadata = get_model_metadata("models/forecaster_2026-05-01_143022.pkl")
        >>> print(metadata["model_type"])
        TimeSeriesForecaster

    Notes:
        - Much faster than loading the full model
        - Returns None if metadata file doesn't exist
        - Useful for browsing available models
    """
    model_path = Path(filepath)
    metadata_file = model_path.with_name(f"{model_path.stem}_metadata.json")

    if not metadata_file.exists():
        return None

    try:
        with open(metadata_file, "r") as f:
            return json.load(f)
    except Exception as e:
        warnings.warn(f"Failed to load metadata: {e}")
        return None


def cleanup_old_models(
    directory: str,
    max_age_days: int = 30,
    keep_latest: int = 5
) -> int:
    """
    Clean up old model files from a directory.

    Args:
        directory: Directory to clean up
        max_age_days: Delete models older than this many days (default: 30)
        keep_latest: Always keep this many most recent models (default: 5)

    Returns:
        Number of models deleted

    Examples:
        >>> cleanup_old_models("models/", max_age_days=30, keep_latest=5)
        12

    Notes:
        - Sorts models by modification time and keeps the N most recent
        - Deletes both model and metadata files
        - Safe to run periodically as a maintenance task
    """
    models = list_saved_models(directory)
    deleted_count = 0

    # Keep the N most recent models regardless of age
    models_to_check = models[keep_latest:]

    for model in models_to_check:
        if is_model_stale(model["filepath"], max_age_days):
            if delete_model(model["filepath"]):
                deleted_count += 1

    return deleted_count
