"""Error telemetry — local-first, no external services.

Dream Studio does not phone home. Crashes and errors are surfaced to the
local dashboard only. Sentry (removed in Phase 18.1.12) is not used.

Future: 18.8.10.1 will add a local crash dashboard via the projection layer.
"""

from __future__ import annotations


def init_sentry() -> None:
    """No-op. Sentry was removed in Phase 18.1.12."""


def capture_exception(exc: BaseException) -> None:
    """No-op. Errors surface to local dashboard (18.8.10.1), not external services."""
