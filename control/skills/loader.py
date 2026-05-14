"""Skill loading and validation utilities"""

import re
import sys
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


def extract_skill_name(file_path: str) -> str:
    """Extract skill name from file path"""
    normalized = file_path.replace("\\", "/")
    match = re.search(r"skills/(.+)\.md$", normalized)
    skill_name = match.group(1) if match else Path(file_path).stem

    # Emit skill loading event
    try:
        bridge = _get_bridge()
        if bridge:
            bridge.emit_from_legacy(
                activity_type="skill.execution.started",
                stream_id=f"skill-{skill_name}",
                stream_type="skill",
                event_data={"skill_id": skill_name, "skill_path": file_path},
            )
    except Exception:
        pass  # Never fail on event emission

    return skill_name


def is_safe_skill_path(file_path: str) -> bool:
    """Reject symlinks that resolve outside the user's home directory"""
    try:
        p = Path(file_path)
        if not p.is_symlink():
            return True
        resolved = p.resolve()
        home = Path.home().resolve()
        return str(resolved).replace("\\", "/").startswith(str(home).replace("\\", "/"))
    except Exception:
        return False


def resolve_director_placeholder(file_path: str, director_name: str | None) -> str | None:
    """Check if file contains {{director_name}} placeholder and return resolved value"""
    if not is_safe_skill_path(file_path):
        return None
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    DIRECTOR_PLACEHOLDER = "{{director_name}}"
    if DIRECTOR_PLACEHOLDER not in content:
        return None

    return director_name if director_name else None
