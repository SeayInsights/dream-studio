"""Integration manifest — read/write, hash tracking, drift detection."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "ds.integration.manifest.v1"


def get_ds_home(override: Path | None = None) -> Path:
    """Resolve dream-studio home. Tests redirect via DS_DREAM_STUDIO_HOME; DREAM_STUDIO_HOME
    is the resolver's own name and wins whenever DS_DREAM_STUDIO_HOME is unset (mirrors
    interfaces/cli/ds_render.py's _ds_home() -- both names exist because `--home` sets both,
    but only DREAM_STUDIO_HOME is what a caller who bypasses `--home` would set)."""
    if override is not None:
        return override
    env = os.environ.get("DS_DREAM_STUDIO_HOME")
    if env:
        return Path(env)
    from core.config.paths import home_dir

    return home_dir()


def config_root_key(config_root: Path) -> str:
    """A stable directory name for one config root: readable tail + a hash of the full path."""
    resolved = str(Path(config_root).expanduser().resolve())
    normalized = resolved.lower() if os.name == "nt" else resolved
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    tail = re.sub(r"[^A-Za-z0-9]+", "-", resolved).strip("-")[-48:]
    return f"{tail}-{digest}"


def get_manifest_path(
    tool_id: str, ds_home: Path | None = None, config_root: Path | None = None
) -> Path:
    """The manifest for *tool_id*; with *config_root*, the manifest for that root alone.

    ONE MANIFEST PER CONFIG ROOT. The single integrations/<tool>/manifest.json was shared
    by every config root installed from the home -- an operator with two Claude Code
    identities (~/.claude and a CLAUDE_CONFIG_DIR one) had each install overwrite the
    other's record, so neither knew what it had written. Without *config_root* this still
    names the legacy path, which read_manifest() falls back to for a root it describes.
    """
    base = get_ds_home(ds_home) / "integrations" / tool_id
    if config_root is None:
        return base / "manifest.json"
    return base / "roots" / config_root_key(config_root) / "manifest.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _describes_root(manifest: dict[str, Any], config_root: Path) -> bool:
    """True when a manifest records files written under *config_root*."""
    recorded = manifest.get("config_root")
    root = Path(config_root).expanduser().resolve()
    if recorded:
        return Path(recorded).expanduser().resolve() == root
    if not manifest.get("files"):
        # A legacy manifest that records no files cannot say whose it is. Reading it
        # changes no file (there is nothing to prune) and keeps its state visible.
        return True
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path and root in Path(path).resolve().parents:
            return True
    return False


def read_manifest(
    tool_id: str, ds_home: Path | None = None, config_root: Path | None = None
) -> dict[str, Any] | None:
    """Read the manifest. With *config_root*, the per-root one, else a legacy manifest that
    describes that root (the migration path from the single shared manifest)."""
    if config_root is None:
        return _read_json(get_manifest_path(tool_id, ds_home))
    per_root = _read_json(get_manifest_path(tool_id, ds_home, config_root))
    if per_root is not None:
        return per_root
    legacy = _read_json(get_manifest_path(tool_id, ds_home))
    if legacy is not None and _describes_root(legacy, config_root):
        return legacy
    return None


def write_manifest(
    tool_id: str,
    manifest: dict[str, Any],
    ds_home: Path | None = None,
    config_root: Path | None = None,
) -> None:
    path = get_manifest_path(tool_id, ds_home, config_root)
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
    config_root: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "tool": tool,
        "scope": scope,
        "config_root": str(Path(config_root).expanduser().resolve()) if config_root else None,
        "ds_version": ds_version,
        "installed_at": datetime.now(UTC).isoformat(),
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
        # The file as written, or its text with newlines folded: an install writes LF on every
        # OS now (and copies .cmd/.bat as bytes), and an earlier one wrote platform newlines,
        # which a manifest of the same era hashed folded. A CRLF save of the same text is not
        # drift; a changed character is.
        raw = path.read_bytes()
        if expected_hash not in (compute_hash(raw), compute_hash(raw.replace(b"\r\n", b"\n"))):
            drifted.append(f"hash_mismatch: {path}")
    return drifted
