"""Skill telemetry processing for on-skill-telemetry hook."""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Event store bridge for dual-write migration
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.event_store.legacy_bridge import LegacyBridge
    from core.event_store.event_store import EventStore
    from core.validation.event_validator import EventValidator

    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

FAIL_WORDS = frozenset(
    ["error", "traceback", "failed", "exception", "cannot", "unable to", "not found"]
)


def detect_success(payload: dict) -> bool:
    """Heuristic: scan last assistant message for failure keywords."""
    for msg in reversed(payload.get("messages") or []):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        text = (
            content
            if isinstance(content, str)
            else " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        )
        if text and any(w in text.lower() for w in FAIL_WORDS):
            return False
    return True


def get_session_skills(usage_path: Path, session_id: str) -> list[dict]:
    """Read skill-usage.jsonl and extract unique skills for this session."""
    if not usage_path.is_file():
        return []
    try:
        records = [
            json.loads(ln)
            for ln in usage_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    except Exception:
        return []
    seen, skills = set(), []
    for r in records:
        if r.get("session") == session_id:
            name = r.get("skill", "unknown")
            if name not in seen:
                seen.add(name)
                skills.append({"name": name, "ts": r.get("ts", "")})
    return skills


def _get_bridge():
    """Lazy init bridge for event emission."""
    if not _BRIDGE_AVAILABLE:
        return None
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
            db_path=str(repo_root / ".dream-studio" / "data" / "studio.db"),
            validator=validator,
            emit_validation_failures=True,
        )
        return LegacyBridge(event_store)
    except Exception:
        return None


def write_telemetry(buf_path: Path, skills: list[dict], success: bool) -> None:
    """Append skill telemetry records to buffer."""
    now = datetime.now(timezone.utc).isoformat()
    skill_count = len(skills)
    success_rate = 1.0 if success else 0.0

    try:
        with buf_path.open("a", encoding="utf-8") as f:
            for skill in skills:
                f.write(
                    json.dumps(
                        {
                            "skill_name": skill["name"],
                            "invoked_at": skill["ts"] or now,
                            "success": 1 if success else 0,
                        }
                    )
                    + "\n"
                )
    except Exception:
        pass

    try:
        from core.telemetry.emitters import emit_skill_invocations

        emit_skill_invocations(
            skills,
            success=success,
            context={
                "source_refs": [
                    "runtime/hooks/meta/on-skill-telemetry.py",
                    "core/telemetry/processor.py",
                ]
            },
        )
    except Exception:
        pass

    # Emit canonical event (dual-write)
    try:
        bridge = _get_bridge()
        if bridge:
            bridge.emit_from_legacy(
                activity_type="ingestion.event.normalized",
                stream_id="telemetry",
                stream_type="telemetry",
                event_data={
                    "skill_count": skill_count,
                    "success_rate": success_rate,
                    "skills": [s["name"] for s in skills],
                },
            )
    except Exception:
        pass
