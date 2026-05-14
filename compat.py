"""Small compatibility shims for supported Python versions."""

from __future__ import annotations

from datetime import timezone

try:  # Python 3.11+
    from datetime import UTC as UTC
except ImportError:  # Python 3.10
    UTC = timezone.utc

try:  # Python 3.11+
    import tomllib as tomllib
except ModuleNotFoundError:  # Python 3.10 fallback, provided by requirements-dev.
    import tomli as tomllib
