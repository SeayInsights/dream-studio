"""
session_cache.py — Read session files from a session directory and output to stdout.

CLI:
    py hooks/lib/session_cache.py --session-dir <path> --query <filename|*|all>

Module API:
    read_session_file(session_dir, filename) -> str
    read_all_session_files(session_dir) -> str
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is in path for event store imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.event_store.legacy_bridge import LegacyBridge
    from core.event_store.event_store import EventStore
    from core.validation.event_validator import EventValidator
    from core.event_store.studio_db import _db_path

    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

ALLOWED_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".txt"}


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
            db_path=str(_db_path()), validator=validator, emit_validation_failures=True
        )
        return LegacyBridge(event_store)
    except Exception:
        return None


def read_session_file(session_dir: str, filename: str) -> str:
    """Return the contents of <filename> inside <session_dir>, or empty string."""
    base = Path(session_dir)
    if not base.is_dir():
        return ""
    target = base / filename
    if not target.is_file():
        return ""
    if target.suffix.lower() not in ALLOWED_EXTENSIONS:
        return ""
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def read_all_session_files(session_dir: str) -> str:
    """Return all allowed files in <session_dir> concatenated with separators."""
    base = Path(session_dir)
    if not base.is_dir():
        return ""

    files = sorted(
        f for f in base.iterdir() if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    )

    if not files:
        return ""

    parts: list[str] = []
    for f in files:
        try:
            contents = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parts.append(f"--- {f.name} ---\n{contents}")

    result = "\n\n".join(parts)

    # DUAL-WRITE: Emit canonical event after successful read
    try:
        bridge = _get_bridge()
        if bridge:
            bridge.emit_from_legacy(
                activity_type="execution.completed",
                stream_id=f"session-cache-{base.name}",
                stream_type="session",
                event_data={
                    "session_dir": str(base),
                    "files_read": len(parts),
                    "total_chars": len(result),
                    "operation": "read_all_session_files",
                },
                status="completed",
            )
    except Exception:
        pass  # Never fail on event emission

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve session files to stdout.")
    parser.add_argument("--session-dir", required=True, help="Path to the session directory")
    parser.add_argument(
        "--query", required=True, help="Filename to read, or '*'/'all' for all files"
    )
    args = parser.parse_args()

    if args.query in ("*", "all"):
        output = read_all_session_files(args.session_dir)
    else:
        output = read_session_file(args.session_dir, args.query)

    sys.stdout.write(output)


if __name__ == "__main__":
    main()
