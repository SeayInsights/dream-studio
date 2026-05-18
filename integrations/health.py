"""Integration health state machine — nine states, hybrid persist/compute model.

ODP-7 resolution: manifest persists last known state and content hashes.
doctor() recomputes state fresh by comparing manifest to disk. State transitions
emit integration.health.changed events to spool when a change is detected.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any


class IntegrationState(str, Enum):
    NOT_DETECTED = "not_detected"
    DETECTED_NOT_INTEGRATED = "detected_not_integrated"
    PLAN_AVAILABLE = "plan_available"
    INSTALLED_UNVERIFIED = "installed_unverified"
    INSTALLED_VERIFIED = "installed_verified"
    INSTALLED_DRIFTED = "installed_drifted"
    EVENTS_EMITTING = "events_emitting"
    INGEST_VERIFIED = "ingest_verified"
    BROKEN = "broken"


def _canonical_readable(canonical_root: Path | None) -> bool:
    """True if canonical/skills/ds-bootstrap/SKILL.md is readable."""
    if canonical_root is None:
        return False
    skill_md = canonical_root / "skills" / "ds-bootstrap" / "SKILL.md"
    return skill_md.is_file()


def _check_spool(spool_root: Path | None, tool_id: str) -> str | None:
    """Check spool directories for events from this tool.

    Returns 'ingest_verified', 'events_emitting', or None.
    """
    if spool_root is None:
        try:
            from spool.config import get_spool_root
            spool_root = get_spool_root()
        except Exception:
            return None

    try:
        processed = spool_root / "processed"
        if processed.is_dir() and any(processed.glob("*.json")):
            return "ingest_verified"
        spool_dir = spool_root / "spool"
        if spool_dir.is_dir() and any(spool_dir.glob("*.json")):
            return "events_emitting"
    except Exception:
        pass
    return None


def _emit_health_changed(
    tool_id: str,
    old_state: str,
    new_state: str,
    spool_root: Path | None = None,
) -> None:
    """Emit integration.health.changed event to spool (best-effort)."""
    try:
        from canonical.events.envelope import CanonicalEventEnvelope
        from emitters.shared.spool_writer import write_envelopes

        env = CanonicalEventEnvelope(
            event_type="integration.health.changed",
            session_id=None,
            payload={
                "tool_id": tool_id,
                "previous_state": old_state,
                "new_state": new_state,
            },
        )
        write_envelopes([env])
    except Exception:
        pass


def doctor(
    tool_id: str,
    config_root: Path,
    *,
    ds_home: Path | None = None,
    canonical_root: Path | None = None,
    spool_root: Path | None = None,
) -> dict[str, Any]:
    """Compute integration health state for a tool.

    Returns a dict with 'state', 'tool_id', 'config_root', and diagnostic fields.
    Emits integration.health.changed to spool if state changed from manifest.
    """
    from integrations.manifest import read_manifest, verify_file_hashes

    result: dict[str, Any] = {
        "tool_id": tool_id,
        "config_root": str(config_root),
        "drift": [],
        "notes": [],
    }

    try:
        if not config_root.is_dir():
            state = IntegrationState.NOT_DETECTED
            result["state"] = state.value
            _maybe_emit_transition(tool_id, ds_home, state.value)
            return result

        manifest = read_manifest(tool_id, ds_home)

        if manifest is None:
            if _canonical_readable(canonical_root):
                state = IntegrationState.PLAN_AVAILABLE
            else:
                state = IntegrationState.DETECTED_NOT_INTEGRATED
            result["state"] = state.value
            _maybe_emit_transition(tool_id, ds_home, state.value)
            return result

        schema_ver = manifest.get("schema_version", "")
        if "ds.integration.manifest" not in schema_ver:
            state = IntegrationState.BROKEN
            result["state"] = state.value
            result["notes"].append("manifest schema_version unrecognised")
            _maybe_emit_transition(tool_id, ds_home, state.value)
            return result

        drift = verify_file_hashes(manifest)
        result["drift"] = drift

        if drift:
            state = IntegrationState.INSTALLED_DRIFTED
        else:
            spool_upgrade = _check_spool(spool_root, tool_id)
            if spool_upgrade == "ingest_verified":
                state = IntegrationState.INGEST_VERIFIED
            elif spool_upgrade == "events_emitting":
                state = IntegrationState.EVENTS_EMITTING
            else:
                state = IntegrationState.INSTALLED_VERIFIED

        result["state"] = state.value
        _maybe_emit_transition(tool_id, ds_home, state.value)
        return result

    except Exception as exc:
        result["state"] = IntegrationState.BROKEN.value
        result["notes"].append(f"exception: {exc}")
        _maybe_emit_transition(tool_id, ds_home, IntegrationState.BROKEN.value)
        return result


def _maybe_emit_transition(
    tool_id: str, ds_home: Path | None, new_state: str
) -> None:
    """Emit health.changed event only when state differs from manifest's last_state."""
    try:
        from integrations.manifest import read_manifest
        manifest = read_manifest(tool_id, ds_home)
        last_state = (manifest or {}).get("last_health_state")
        if last_state is not None and last_state != new_state:
            _emit_health_changed(tool_id, last_state, new_state)
    except Exception:
        pass
