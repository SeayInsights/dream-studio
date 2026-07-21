"""Shared constants and helpers for the installed-productization facade.

WO-GF-INSTALLED-PROD: leaf module of the ``installed_productization`` split.
Holds the constants and small helpers used across more than one of the split
sibling modules. No logic changes — extracted verbatim from the original
``core/installed_productization.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.module_profiles import module_profile_map

DEFAULT_INSTALL_PROFILES: tuple[str, ...] = ("core", "analytics_only", "adapter_router_only")
PRODUCTIZATION_VERSION = "dream_studio.installed_productization.v1"
DEFAULT_GLOBAL_COMMAND_DIR = Path.home() / ".local" / "bin"


def _normalize_profiles(profiles: list[str] | tuple[str, ...]) -> list[str]:
    profile_map = module_profile_map()
    normalized = list(dict.fromkeys(str(profile) for profile in profiles))
    unknown = sorted(profile for profile in normalized if profile not in profile_map)
    if unknown:
        raise ValueError(f"unknown module profile(s): {', '.join(unknown)}")
    return normalized


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _timestamp_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
