from __future__ import annotations

from datetime import datetime, UTC


def utcnow() -> datetime:
    return datetime.now(UTC)
