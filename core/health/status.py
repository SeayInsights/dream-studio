"""Runtime status — installed paths, schema version, module profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def get_runtime_status(
    *,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Return the installed runtime model dict.

    Thin wrapper around `installed_runtime_model` for symmetry with the
    other `core.health.*` entry points; skills may import either. Lazy
    imports keep test patches on `interfaces.cli.ds.installed_runtime_model`
    effective.
    """

    from interfaces.cli.ds import installed_runtime_model

    return installed_runtime_model(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
