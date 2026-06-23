"""Skill metrics processing for on-skill-metrics hook."""

import json
import sys
from datetime import datetime, UTC
from pathlib import Path

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import paths

# Import event emission bridge for dual-write pattern
try:
    from core.event_store.legacy_bridge import LegacyBridge
    from core.event_store.event_store import EventStore
    from core.validation.event_validator import EventValidator

    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

_bridge_instance = None


def _get_bridge():
    """Lazy init of LegacyBridge for event emission."""
    global _bridge_instance
    if not _BRIDGE_AVAILABLE:
        return None
    if _bridge_instance is None:
        try:
            repo_root = Path(__file__).resolve().parents[2]
            docs_dir = repo_root / "docs" / "canonical"
            if not docs_dir.exists():
                return None

            taxonomy_path = str(docs_dir / "event_taxonomy_v1.json")
            schema_path = str(docs_dir / "canonical_event_v1_schema.json")

            if not Path(taxonomy_path).exists() or not Path(schema_path).exists():
                return None

            validator = EventValidator(taxonomy_path, schema_path)
            event_store = EventStore(
                db_path=str(paths.state_dir() / "studio.db"),
                validator=validator,
                emit_validation_failures=True,
            )
            _bridge_instance = LegacyBridge(event_store)
        except Exception:
            return None
    return _bridge_instance


def build_display_name(skill_name: str, skill_args: str) -> tuple[str, str | None]:
    """Return (display_name, mode) from skill name and args."""
    pack = skill_name.removeprefix("ds-")
    mode = skill_args.split()[0] if skill_args.strip() else None
    display_name = f"{pack}:{mode}" if mode else pack
    return display_name, mode


def write_skill_usage(
    state_dir: Path, display_name: str, mode: str | None, session_id: str, model: str
) -> None:
    """Append skill usage record to skill-usage.jsonl."""
    state_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "skill": display_name,
        "mode": mode or "",
        "session": session_id,
        "recommended_model": model,
    }
    with (state_dir / "skill-usage.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    # Emit skill metrics recorded event
    try:
        bridge = _get_bridge()
        if bridge:
            bridge.emit_from_legacy(
                activity_type="execution.completed",
                stream_id=f"skill-{display_name}",
                stream_type="skill",
                event_data={
                    "skill_id": display_name,
                    "mode": mode or "",
                    "session_id": session_id,
                    "recommended_model": model,
                    "metrics_recorded": True,
                },
            )
    except Exception:
        pass  # Never fail on event emission
