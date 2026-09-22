"""Config and pulse state I/O with schema-version guards.

Configuration lives at `~/.dream-studio/config.json`.
Pulse snapshots live at `~/.dream-studio/meta/pulse-latest.json`.

Schema versioning: every persisted document carries `schema_version`.
Readers refuse to load a document whose schema is newer than the code
understands — better to fail loudly than silently misinterpret future
fields.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import paths

# Event store for dual-write migration (Phase 2)
try:
    from core.event_store.event_store import EventStore
    from core.event_store.legacy_bridge import LegacyBridge
    from core.validation.event_validator import EventValidator

    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

SCHEMA_VERSION = 1
CONFIG_FILENAME = "config.json"
PULSE_FILENAME = "pulse-latest.json"

# Lazy initialization of event bridge
_bridge = None
_bridge_initialized = False


def _get_bridge():
    """Lazily initialize LegacyBridge for event emission."""
    global _bridge, _bridge_initialized

    if _bridge_initialized:
        return _bridge

    _bridge_initialized = True

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
            db_path=str(paths.state_dir() / "studio.db"),
            validator=validator,
            emit_validation_failures=True,
        )
        _bridge = LegacyBridge(event_store)
        return _bridge
    except Exception:
        return None


class SchemaVersionError(RuntimeError):
    """Stored document's schema_version is newer than this code supports."""


def _config_path() -> Path:
    return paths.user_data_dir() / CONFIG_FILENAME


def _pulse_path() -> Path:
    return paths.meta_dir() / PULSE_FILENAME


def _check_schema(doc: dict[str, Any], source: Path) -> None:
    stored = doc.get("schema_version", 1)
    if not isinstance(stored, int) or stored > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{source} has schema_version={stored!r}, but this dream-studio "
            f"only understands up to {SCHEMA_VERSION}. Upgrade the plugin "
            "to read this file."
        )


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically via temp file + rename to prevent partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_config() -> dict[str, Any]:
    """Return the user config dict, or a default stub if the file is absent or corrupt."""
    path = _config_path()
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION}
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"schema_version": SCHEMA_VERSION}
    _check_schema(doc, path)
    return doc


def write_config(data: dict[str, Any]) -> Path:
    """Persist the user config atomically, stamping schema_version."""
    path = _config_path()
    _atomic_write(path, {**data, "schema_version": SCHEMA_VERSION})

    # DUAL-WRITE: Emit canonical event (Phase 2)
    try:
        bridge = _get_bridge()
        if bridge:
            bridge.emit_from_legacy(
                activity_type="execution.completed",
                stream_id="config",
                stream_type="config",
                event_data={
                    "operation": "write_config",
                    "path": str(path),
                    "schema_version": SCHEMA_VERSION,
                },
                status="completed",
                severity="info",
            )
    except Exception:
        # Never fail on event emission
        pass

    return path


def read_pulse() -> dict[str, Any]:
    """Return the latest pulse snapshot, or an empty dict if none exists."""
    path = _pulse_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    _check_schema(doc, path)
    return doc


def write_pulse(data: dict[str, Any]) -> Path:
    """Persist the latest pulse snapshot atomically, stamping schema_version."""
    path = _pulse_path()
    _atomic_write(path, {**data, "schema_version": SCHEMA_VERSION})
    backup_db()

    # DUAL-WRITE: Emit canonical event (Phase 2)
    try:
        bridge = _get_bridge()
        if bridge:
            bridge.emit_from_legacy(
                activity_type="execution.completed",
                stream_id="pulse",
                stream_type="pulse",
                event_data={
                    "operation": "write_pulse",
                    "path": str(path),
                    "schema_version": SCHEMA_VERSION,
                },
                status="completed",
                severity="info",
            )
    except Exception:
        # Never fail on event emission
        pass

    return path


# A full-file copy of studio.db is O(database size), and the database only grows.
# This ran on every write_pulse() -- i.e. on the UserPromptSubmit critical path --
# and at 1.1 GB it measured 5.4 s per prompt, silently getting worse as the DB grew.
# A local dev backup does not need to be minute-fresh; once a day is the right
# trade. Override with DS_BACKUP_MIN_INTERVAL_SEC (0 forces a backup every call).
BACKUP_MIN_INTERVAL_SEC = int(os.environ.get("DS_BACKUP_MIN_INTERVAL_SEC", str(24 * 3600)))


def _backup_is_fresh(bak_path: Path) -> bool:
    if BACKUP_MIN_INTERVAL_SEC <= 0:
        return False
    try:
        if not bak_path.is_file():
            return False
        return (time.time() - bak_path.stat().st_mtime) < BACKUP_MIN_INTERVAL_SEC
    except OSError:
        return False


def _maybe_vacuum(db_path: Path) -> None:
    """VACUUM at most once a month.

    The day-1 check alone re-VACUUMed a 1.1 GB database on every single pulse
    for the whole of the first -- the worst latency spikes in the timing log.
    """
    if datetime.now(UTC).day != 1:
        return
    stamp = db_path.parent / ".vacuumed"
    this_month = datetime.now(UTC).strftime("%Y-%m")
    try:
        if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == this_month:
            return
    except OSError:
        pass
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    try:
        stamp.write_text(this_month, encoding="utf-8")
    except OSError:
        pass


def backup_db(force: bool = False) -> Path | None:
    """Back up studio.db using the SQLite online backup API. Monthly VACUUM on day 1.

    Rate-limited to BACKUP_MIN_INTERVAL_SEC; pass force=True for an explicit
    operator-requested backup.
    """
    db_path = paths.state_dir() / "studio.db"
    if not db_path.is_file():
        return None
    bak_path = db_path.with_suffix(".db.bak")
    if not force and _backup_is_fresh(bak_path):
        return bak_path
    try:
        src = sqlite3.connect(str(db_path))
        # The passive autocheckpoint loses to the hook processes that hold this
        # database open, so the WAL only grows. This daily, rate-limited path is
        # the one place with a good chance of a quiet moment; TRUNCATE resets the
        # file rather than just flushing it. Best-effort -- a BUSY here is normal.
        try:
            src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        dst = sqlite3.connect(str(bak_path))
        src.backup(dst)
        dst.close()
        src.close()
        _maybe_vacuum(db_path)
        _maybe_cloud_push()
        return bak_path
    except Exception:
        return None


def _maybe_cloud_push() -> None:
    """If auto-push is enabled in backup-config.json, push to cloud (non-blocking)."""
    try:
        cfg_path = paths.state_dir() / "backup-config.json"
        if not cfg_path.is_file():
            return
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not config.get("auto_push") or not config.get("remote"):
            return

        script = paths.plugin_root() / "interfaces" / "cli" / "studio_backup.py"
        if not script.is_file():
            return

        subprocess.Popen(
            [sys.executable, str(script), "--cloud", "push"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Log push attempt as sentinel
        from core.event_store import studio_db

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        studio_db.set_sentinel(f"cloud-push-{today}", "backup")
    except Exception:
        pass


def get_quiet_mode() -> int:
    """Return the number of turns advisory hooks should remain suppressed (0 = normal)."""
    try:
        return int(read_config().get("quiet_mode", 0))
    except (TypeError, ValueError):
        return 0


def set_quiet_mode(turns: int) -> None:
    """Set how many turns advisory hooks should be suppressed.

    Hooks call this to decrement the counter each turn:
        remaining = get_quiet_mode()
        if remaining > 0:
            set_quiet_mode(remaining - 1)
            return  # suppressed this turn
    """
    cfg = read_config()
    cfg["quiet_mode"] = max(0, int(turns))
    write_config(cfg)
