"""Error telemetry stub — no-op. Copy to hooks/lib/telemetry.py.

Sentry integration was removed in Phase 18.1.12. Dream Studio does not phone
home. This stub preserves the API surface for callers.
"""

from __future__ import annotations


def init_sentry() -> None:
    """No-op stub. Sentry was removed in Phase 18.1.12."""


def capture_exception(exc: BaseException) -> None:
    """No-op stub. Errors surface to local dashboard (18.8.10.1), not external services."""
