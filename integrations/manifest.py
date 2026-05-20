"""Integration manifest — read/write, hash tracking, drift detection."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "ds.integration.manifest.v1"


def get_ds_home(override: Path | None = None) -> Path:
    """Resolve dream-studio home. Tests redirect via DS_DREAM_STUDIO_HOME."""
    if override is not None:
        return override
    env = os.environ.get("DS_DREAM_STUDIO_HOME")
    if env:
        return Path(env)
    return Path.home() / ".dream-studio"


def get_manifest_path(tool_id: str, ds_home: Path | None = None) -> Path:
    return get_ds_home(ds_home) / "integrations" / tool_id / "manifest.json"


def read_manifest(tool_id: str, ds_home: Path | None = None) -> dict[str, Any] | None:
    path = get_manifest_path(tool_id, ds_home)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def write_manifest(tool_id: str, manifest: dict[str, Any], ds_home: Path | None = None) -> None:
    path = get_manifest_path(tool_id, ds_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def compute_hash(content: str | bytes) -> str:
    """SHA-256 hex digest of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def build_manifest(
    *,
    tool: str,
    scope: str,
    ds_version: str,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "tool": tool,
        "scope": scope,
        "ds_version": ds_version,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }


def verify_file_hashes(manifest: dict[str, Any]) -> list[str]:
    """Compare manifest content_hash fields against current disk state.

    Returns a list of drift descriptions (empty = all match).
    """
    drifted: list[str] = []
    for entry in manifest.get("files", []):
        path = Path(entry.get("path", ""))
        expected_hash = entry.get("content_hash", "")
        if entry.get("operation") == "skip":
            continue
        if not path.exists():
            drifted.append(f"missing: {path}")
            continue
        actual_hash = compute_hash(path.read_text(encoding="utf-8"))
        if actual_hash != expected_hash:
            drifted.append(f"hash_mismatch: {path}")
    return drifted
