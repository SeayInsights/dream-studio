"""Optional Sentry error tracking stub. Copy to hooks/lib/telemetry.py."""

from __future__ import annotations

import os


def init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        import sentry_sdk  # type: ignore[import]

        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1)


def capture_exception(exc: BaseException) -> None:
    if os.environ.get("SENTRY_DSN"):
        try:
            import sentry_sdk  # type: ignore[import]

            sentry_sdk.capture_exception(exc)
        except Exception:
            pass
