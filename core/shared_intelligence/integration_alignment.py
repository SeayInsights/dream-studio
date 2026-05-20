"""Integration alignment — replaces adapter_alignment.py.

Validates that an installed integration matches the canonical/ contract:
skill schema present, event envelope schema correct, no version skew.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def validate_integration_alignment(
    tool_id: str,
    config_root: Path,
    *,
    canonical_root: Path | None = None,
    ds_home: Path | None = None,
) -> dict[str, Any]:
    """Check alignment between installed files and canonical/ definitions.

    Returns a dict with 'aligned' bool and list of 'violations'.
    """
    from integrations.manifest import read_manifest, compute_hash

    violations: list[str] = []

    manifest = read_manifest(tool_id, ds_home)
    if manifest is None:
        return {
            "aligned": False,
            "violations": ["no manifest — tool not installed"],
            "tool_id": tool_id,
        }

    # Check skill file aligns with canonical source
    _root = canonical_root or _default_canonical_root()
    canonical_skill = _root / "skills" / "ds-bootstrap" / "SKILL.md"
    if canonical_skill.is_file():
        canonical_hash = compute_hash(canonical_skill.read_bytes())
        for entry in manifest.get("files", []):
            if "ds-bootstrap/SKILL.md" in entry.get("path", ""):
                installed_hash = entry.get("content_hash", "")
                if installed_hash != canonical_hash:
                    violations.append(
                        "ds-bootstrap/SKILL.md: installed version differs from canonical/"
                    )

    # Verify envelope schema is still valid (check canonical/events/envelope.py parseable)
    try:
        from canonical.events.envelope import SCHEMA_VERSION, REQUIRED_FIELDS

        if SCHEMA_VERSION < 1:
            violations.append("envelope schema_version < 1")
        if not REQUIRED_FIELDS:
            violations.append("envelope REQUIRED_FIELDS is empty")
    except ImportError as exc:
        violations.append(f"canonical event envelope not importable: {exc}")

    return {
        "aligned": len(violations) == 0,
        "violations": violations,
        "tool_id": tool_id,
        "model_name": "dream_studio_integration_alignment",
        "derived_view": True,
        "primary_authority": False,
    }


def _default_canonical_root() -> Path:
    return Path(__file__).resolve().parents[2] / "canonical"
