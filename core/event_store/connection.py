"""SQLite analytics backend for dream-studio (WAL, migrations, retry, CLI)."""

from __future__ import annotations
import sys
import functools
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.config import paths  # noqa: E402
from core.config.database import get_connection, transaction  # noqa: E402

# Import adapters for skill execution normalization (TC-007)
try:
    from core.adapters.normalizers import EventNormalizer, ClaudeAdapter

    _event_normalizer = EventNormalizer()
    _event_normalizer.register_adapter("claude", ClaudeAdapter())
    _NORMALIZER_AVAILABLE = True
except ImportError:
    _NORMALIZER_AVAILABLE = False

# Import canonical event store for dual-write migration (Phase 1)
try:
    from core.event_store.event_store import EventStore
    from core.event_store.legacy_bridge import LegacyBridge
    from core.validation.event_validator import EventValidator

    # Initialize EventStore with validation
    _validator = None
    _event_store = None
    _legacy_bridge = None
    _EVENT_STORE_AVAILABLE = True
except ImportError as e:
    _EVENT_STORE_AVAILABLE = False
    _IMPORT_ERROR = str(e)

# Canonical event emission for activity_log retirement (TA0c)
try:
    from canonical.events.envelope import CanonicalEventEnvelope
    from canonical.events.types import EventType as _CanonicalEventType
    from emitters.shared.spool_writer import write_envelopes as _write_envelopes

    _SPOOL_WRITER_AVAILABLE = True
except ImportError:
    _SPOOL_WRITER_AVAILABLE = False
    # Bind fallbacks so sibling modules can import these unconditionally; every
    # runtime use is guarded by _SPOOL_WRITER_AVAILABLE (WO-SPLIT-STUDIO-DB).
    CanonicalEventEnvelope = None  # type: ignore[assignment,misc]
    _CanonicalEventType = None  # type: ignore[assignment,misc]
    _write_envelopes = None  # type: ignore[assignment,misc]


def _NOW() -> str:
    return datetime.now(UTC).isoformat()


def _try_emit_canonical(
    event_type: _CanonicalEventType,
    payload: dict,
    *,
    session_id: str | None = None,
    task_id: str | None = None,
    prd_id: str | None = None,
    skill_id: str | None = None,
) -> None:
    """Emit a canonical event to spool. No-op if spool writer is unavailable."""
    if not _SPOOL_WRITER_AVAILABLE:
        return
    try:
        _write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=event_type.value,
                    session_id=session_id,
                    payload={k: v for k, v in payload.items() if v is not None},
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )
    except Exception:
        pass  # best-effort: never fail production writes due to telemetry


def _db_path() -> Path:
    return paths.state_dir() / "studio.db"


def _get_event_store(
    override_db_path: Path | None = None, override_conn: sqlite3.Connection | None = None
):
    """
    Lazily initialize EventStore for canonical event emission.

    Args:
        override_db_path: Optional database path (for testing)
        override_conn: Optional connection (for testing with temp DB)

    Returns LegacyBridge instance or None if not available.
    This was previously called from _insert_activity_log for dual-write (retired in TA0c).
    """
    global _validator, _event_store, _legacy_bridge

    if not _EVENT_STORE_AVAILABLE:
        return None

    # For testing: create new instance with override
    if override_db_path is not None or override_conn is not None:
        try:
            repo_root = Path(__file__).resolve().parents[2]
            docs_dir = repo_root / "docs" / "canonical"

            if not docs_dir.exists():
                return None

            taxonomy_path = str(docs_dir / "event_taxonomy_v1.json")
            schema_path = str(docs_dir / "canonical_event_v1_schema.json")

            if not Path(taxonomy_path).exists() or not Path(schema_path).exists():
                return None

            test_validator = EventValidator(taxonomy_path, schema_path)
            test_event_store = EventStore(
                db_path=str(override_db_path or _db_path()),
                validator=test_validator,
                emit_validation_failures=True,
                shared_connection=override_conn,
            )
            return LegacyBridge(test_event_store)
        except Exception:
            return None

    # Production: use global singleton
    if _event_store is None:
        try:
            # Initialize validator with taxonomy and schema from docs/canonical/
            repo_root = Path(__file__).resolve().parents[2]
            docs_dir = repo_root / "docs" / "canonical"

            if not docs_dir.exists():
                # Canonical schema not found - skip event emission
                return None

            taxonomy_path = str(docs_dir / "event_taxonomy_v1.json")
            schema_path = str(docs_dir / "canonical_event_v1_schema.json")

            if not Path(taxonomy_path).exists() or not Path(schema_path).exists():
                # Schema files missing - skip event emission
                return None

            _validator = EventValidator(taxonomy_path, schema_path)
            _event_store = EventStore(
                db_path=str(_db_path()), validator=_validator, emit_validation_failures=True
            )
            _legacy_bridge = LegacyBridge(_event_store)
        except Exception:
            # Log error for debugging but don't fail legacy writes
            # This ensures backward compatibility during migration
            return None

    return _legacy_bridge


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is not None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
    else:
        conn = get_connection()
    conn.execute("PRAGMA synchronous=NORMAL")
    # Local import breaks the connection<->migration_runner cycle (WO-SPLIT-STUDIO-DB).
    from .migration_runner import _run_migrations

    _run_migrations(conn)
    # Migrations may issue PRAGMA foreign_keys = OFF internally. Restore it.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _db_transaction(db_path: Path | None = None):
    """Yield a connection inside a transaction, honoring db_path for test isolation."""
    if db_path is None:
        with transaction() as c:
            yield c
    else:
        conn = _connect(db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _with_retry(fn=None, *, retries=3, backoffs=(0.1, 0.5, 2.0)):
    """Decorator: retry on SQLITE_BUSY with exponential backoff."""
    if fn is None:
        return lambda f: _with_retry(f, retries=retries, backoffs=backoffs)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        for attempt in range(retries + 1):
            try:
                return fn(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < retries:
                    time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    continue
                raise
        return fn(*args, **kwargs)

    return wrapper


def _reraise_if_busy(e: Exception) -> None:
    """Re-raise SQLITE_BUSY so the retry decorator can handle it."""
    if isinstance(e, sqlite3.OperationalError) and "database is locked" in str(e):
        raise
