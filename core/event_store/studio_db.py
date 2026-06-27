"""SQLite analytics backend for dream-studio (WAL, migrations, retry, CLI)."""

from __future__ import annotations
import sys
import argparse, functools, hashlib, json, re, sqlite3, sys, time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.config import paths  # noqa: E402
from core.config.database import get_connection, transaction
from core.config.sqlite_bootstrap import (
    migrations_dir as _canonical_migrations_dir,
    run_migrations as _canonical_run_migrations,
    split_statements as _canonical_split_statements,
)

# Import adapters for skill execution normalization (TC-007)
try:
    from core.adapters.normalizers import EventNormalizer, ClaudeAdapter
    from core.adapters.models import CanonicalEvent
    from core.events.trace import TraceContext

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

_NOW = lambda: datetime.now(timezone.utc).isoformat()


def _try_emit_canonical(
    event_type: "_CanonicalEventType",
    payload: dict,
    *,
    session_id: "str | None" = None,
    task_id: "str | None" = None,
    prd_id: "str | None" = None,
    skill_id: "str | None" = None,
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


# ── Event Store Initialization (Lazy) ──────────────────────────────────────


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


# ── SQL statement splitter ──────────────────────────────────────────────────


def _split_statements(sql_text: str) -> list[str]:
    """Split SQL into individual statements, respecting trigger BEGIN/END blocks."""
    return _canonical_split_statements(sql_text)


# ── Migration runner ────────────────────────────────────────────────────────


def _migrations_dir() -> Path:
    return _canonical_migrations_dir()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending schema migrations from core/event_store/migrations/*.sql."""
    _canonical_run_migrations(conn)


# ── Connection ──────────────────────────────────────────────────────────────


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


# ── Retry infrastructure ───────────────────────────────────────────────────


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


# ── Workflow functions ──────────────────────────────────────────────────────


@_with_retry
def archive_workflow(
    run_key: str,
    wf: dict,
    db_path: Path | None = None,
    *,
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
) -> bool:
    """
    Archive workflow run to raw_workflow_runs and raw_workflow_nodes.

    Writes to activity_log FIRST via EventNormalizer, then links via activity_id (Phase 3 traceability).

    Args:
        run_key: Unique workflow run identifier
        wf: Workflow dict with keys: workflow, yaml_path, status, started, nodes
        db_path: Optional database path
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        session_id: Optional session ID for cross-domain linkage
    """
    try:
        nodes = wf.get("nodes", {})
        started_at = wf.get("started", _NOW())
        status = wf["status"]

        # Calculate duration if workflow is finished
        duration_ms = None
        if wf.get("finished"):
            try:
                start = datetime.fromisoformat(started_at)
                end = datetime.fromisoformat(wf["finished"])
                duration_ms = int((end - start).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass

        with _db_transaction(db_path) as c:
            # 1. Emit canonical event (TA0c: activity_log retired)
            _try_emit_canonical(
                _CanonicalEventType.WORKFLOW_COMPLETED,
                {
                    "workflow": wf["workflow"],
                    "yaml_path": wf.get("yaml_path", ""),
                    "status": status,
                    "node_count": len(nodes),
                    "nodes_done": sum(
                        1 for n in nodes.values() if n.get("status") in ("completed", "skipped")
                    ),
                    "duration_ms": duration_ms,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
            )
            activity_id = None  # deprecated FK column

            # 2. Insert into raw_workflow_runs with activity_id FK
            c.execute(
                """INSERT INTO raw_workflow_runs
                   (run_key, workflow, yaml_path, status, started_at,
                    node_count, nodes_done, activity_id, prd_id, task_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_key,
                    wf["workflow"],
                    wf["yaml_path"],
                    status,
                    started_at,
                    len(nodes),
                    sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped")),
                    activity_id,
                    prd_id,
                    task_id,
                ),
            )

            # 3. Insert workflow nodes (with individual activity_id entries)
            for nid, nd in nodes.items():
                node_status = nd.get("status", "")
                node_duration_ms = None

                # Calculate node duration if available
                if nd.get("started") and nd.get("finished"):
                    try:
                        node_start = datetime.fromisoformat(nd["started"])
                        node_end = datetime.fromisoformat(nd["finished"])
                        node_duration_ms = int((node_end - node_start).total_seconds() * 1000)
                    except (ValueError, TypeError):
                        pass

                # Emit canonical event for workflow node (TA0c: activity_log retired)
                _try_emit_canonical(
                    _CanonicalEventType.WORKFLOW_NODE_COMPLETED,
                    {
                        "node_id": nid,
                        "workflow": wf["workflow"],
                        "status": node_status,
                        "output": nd.get("output", ""),
                        "duration_ms": node_duration_ms,
                    },
                    session_id=session_id,
                    task_id=task_id,
                    prd_id=prd_id,
                )
                node_activity_id = None  # deprecated FK column

                # Insert into raw_workflow_nodes with activity_id FK
                c.execute(
                    """INSERT INTO raw_workflow_nodes
                       (run_key, node_id, status, started_at, finished_at,
                        duration_s, output, activity_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_key,
                        nid,
                        node_status,
                        nd.get("started"),
                        nd.get("finished"),
                        nd.get("duration_s"),
                        nd.get("output"),
                        node_activity_id,
                    ),
                )
        _emit_workflow_telemetry(
            run_key=run_key,
            wf=wf,
            status=status,
            duration_ms=duration_ms,
            prd_id=prd_id,
            task_id=task_id,
            session_id=session_id,
            db_path=db_path,
        )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def _emit_workflow_telemetry(
    *,
    run_key: str,
    wf: dict,
    status: str,
    duration_ms: int | None,
    prd_id: str | None,
    task_id: str | None,
    session_id: str | None,
    db_path: Path | None,
) -> None:
    """Best-effort dual-write from legacy workflow archive tables."""

    try:
        from core.telemetry.emitters import TelemetryContext, emit_workflow_invocation

        emit_workflow_invocation(
            workflow_id=str(wf.get("workflow") or "unknown"),
            status=status,
            run_key=run_key,
            yaml_path=str(wf.get("yaml_path") or ""),
            started_at=wf.get("started"),
            ended_at=wf.get("finished"),
            duration_ms=duration_ms,
            nodes=wf.get("nodes", {}),
            context=TelemetryContext(
                project_id="dream-studio",
                milestone_id=prd_id,
                task_id=task_id,
                process_run_id=run_key,
                source_refs=("core/event_store/studio_db.py",),
                evidence_refs=(f"raw_workflow_runs:{run_key}",),
            ),
            metadata={"session_id": session_id},
            db_path=db_path,
        )
    except Exception:
        return


def last_run(workflow_name: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT run_key,status,started_at,finished_at FROM raw_workflow_runs WHERE workflow=? ORDER BY finished_at DESC LIMIT 1",
                (workflow_name,),
            ).fetchone()
            return dict(r) if r else None
        finally:
            c.close()
    except Exception:
        return None


def run_count(workflow_name: str, db_path: Path | None = None) -> int:
    try:
        c = _connect(db_path)
        try:
            n = c.execute(
                "SELECT COUNT(*) FROM raw_workflow_runs WHERE workflow=?", (workflow_name,)
            ).fetchone()[0]
            return n
        finally:
            c.close()
    except Exception:
        return 0


@_with_retry
def import_buffer(buffer_path: Path, db_path: Path | None = None) -> int:
    try:
        raw = buffer_path.read_bytes()
        if not raw.strip():
            return 0
        bid = hashlib.sha256(raw).hexdigest()
        with _db_transaction(db_path) as c:
            if c.execute("SELECT 1 FROM log_batch_imports WHERE batch_id=?", (bid,)).fetchone():
                return 0
            rows = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
            for r in rows:
                c.execute(
                    "INSERT INTO raw_skill_telemetry(skill_name,invoked_at,model,input_tokens,output_tokens,success,execution_time_s) VALUES(?,?,?,?,?,?,?)",
                    (
                        r["skill_name"],
                        r.get("invoked_at", _NOW()),
                        r.get("model"),
                        r.get("input_tokens"),
                        r.get("output_tokens"),
                        int(r["success"]),
                        r.get("execution_time_s"),
                    ),
                )
            c.execute(
                "INSERT INTO log_batch_imports(batch_id,imported_at,row_count) VALUES(?,?,?)",
                (bid, _NOW(), len(rows)),
            )
        return len(rows)
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def rebuild_summaries(db_path: Path | None = None) -> None:
    try:
        with _db_transaction(db_path) as c:
            c.executescript(
                """DELETE FROM sum_skill_summary;
INSERT INTO sum_skill_summary SELECT skill_name,COUNT(*),AVG(success),AVG(input_tokens),AVG(output_tokens),AVG(execution_time_s),MAX(CASE WHEN success=1 THEN invoked_at END),MAX(CASE WHEN success=0 THEN invoked_at END),datetime('now') FROM (SELECT * FROM effective_skill_runs WHERE skill_name IN (SELECT skill_name FROM raw_skill_telemetry GROUP BY skill_name HAVING COUNT(*)>=5) ORDER BY id DESC LIMIT 30) GROUP BY skill_name;"""
            )
    except Exception as e:
        _reraise_if_busy(e)


@_with_retry
def rolling_window_prune(db_path: Path | None = None) -> int:
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        with _db_transaction(db_path) as c:
            d1 = c.execute(
                "DELETE FROM raw_skill_telemetry WHERE id NOT IN (SELECT id FROM raw_skill_telemetry t2 WHERE t2.skill_name=raw_skill_telemetry.skill_name ORDER BY id DESC LIMIT 100)"
            ).rowcount
            d2 = c.execute(
                "DELETE FROM raw_workflow_nodes WHERE run_key IN (SELECT run_key FROM raw_workflow_runs WHERE finished_at<?)",
                (cutoff,),
            ).rowcount
            d3 = c.execute("DELETE FROM raw_workflow_runs WHERE finished_at<?", (cutoff,)).rowcount
            d4 = c.execute("DELETE FROM raw_approaches WHERE captured_at<?", (cutoff,)).rowcount
        return d1 + d2 + d3 + d4
    except Exception as e:
        _reraise_if_busy(e)
        return 0


def get_skill_summaries(db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute("SELECT * FROM sum_skill_summary").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                fail_ids = c.execute(
                    "SELECT id FROM effective_skill_runs WHERE skill_name=? AND success=0 ORDER BY id DESC LIMIT 3",
                    (d["skill_name"],),
                ).fetchall()
                d["recent_failure_ids"] = [row[0] for row in fail_ids]
                result.append(d)
            return result
        finally:
            c.close()
    except Exception:
        return []


# skill_correct removed — cor_skill_corrections dropped migration 131


@_with_retry
def insert_operational_snapshot(
    snapshot_date: str,
    project_slug: str,
    *,
    ci_status: str | None = None,
    open_prs: int | None = None,
    stale_branches: int | None = None,
    pending_drafts: int | None = None,
    open_escalations: int | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO raw_operational_snapshots
                   (snapshot_date, project_slug, ci_status, open_prs,
                    stale_branches, pending_drafts, open_escalations, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_date,
                    project_slug,
                    ci_status,
                    open_prs,
                    stale_branches,
                    pending_drafts,
                    open_escalations,
                    _NOW(),
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Approach functions ──────────────────────────────────────────────────────


@_with_retry
def insert_approach(
    skill_id: str,
    approach: str,
    outcome: str,
    *,
    context: str = "",
    why: str = "",
    tokens_used: int | None = None,
    duration_s: float | None = None,
    model: str | None = None,
    session_date: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        if db_path is not None and not Path(db_path).parent.exists():
            return False
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT INTO raw_approaches
                   (skill_id, session_date, approach, outcome, context,
                    why_worked, tokens_used, duration_s, model, captured_at,
                    project_id, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill_id,
                    session_date or _NOW()[:10],
                    approach,
                    outcome,
                    context or None,
                    why or None,
                    tokens_used,
                    duration_s,
                    model,
                    _NOW(),
                    project_id,
                    session_id,
                ),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.APPROACH_CAPTURED,
                {
                    "skill_id": skill_id,
                    "approach": approach,
                    "outcome": outcome,
                    "model": model,
                    "duration_s": duration_s,
                    "tokens_used": tokens_used,
                },
                session_id=session_id,
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_approach_patterns(skill_id: str | None = None, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            if skill_id:
                rows = c.execute(
                    "SELECT * FROM vw_approach_patterns WHERE skill_id=? ORDER BY success_pct DESC",
                    (skill_id,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM vw_approach_patterns ORDER BY success_pct DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_best_approaches(skill_id: str, limit: int = 3, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM vw_approach_patterns WHERE skill_id=? ORDER BY success_pct DESC, times_tried DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def capture_approach(
    skill: str,
    approach: str,
    outcome: str,
    context: str = "",
    why: str = "",
) -> bool:
    """High-level convenience: write approach to DB, fall back to text file."""
    ok = insert_approach(skill, approach, outcome, context=context, why=why, db_path=_db_path())
    if not ok:
        try:
            fallback = paths.meta_dir() / "approaches.log"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%H:%M")
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(f"{ts} | approach:{skill} | {outcome} | {approach}\n")
            return True
        except Exception:
            return False
    return True


# ── Registry query functions ─────────────────────────────────────────────────


@_with_retry
def upsert_gotcha(
    gotcha_id: str,
    skill_id: str,
    severity: str,
    title: str,
    *,
    context: str = "",
    fix: str = "",
    keywords: str = "",
    discovered: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO reg_gotchas
                   (gotcha_id, skill_id, severity, title, context, fix,
                    keywords, discovered, times_hit, last_hit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                           COALESCE((SELECT times_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?), 0),
                           (SELECT last_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?))""",
                (
                    gotcha_id,
                    skill_id,
                    severity,
                    title,
                    context,
                    fix,
                    keywords,
                    discovered,
                    gotcha_id,
                    skill_id,
                    gotcha_id,
                    skill_id,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def search_gotchas_db(keyword: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            try:
                rows = c.execute(
                    "SELECT g.* FROM reg_gotchas g "
                    "INNER JOIN fts_gotchas f ON g.rowid = f.rowid "
                    "WHERE fts_gotchas MATCH ? ORDER BY g.severity",
                    (keyword,),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = c.execute(
                    "SELECT * FROM reg_gotchas WHERE keywords LIKE ? OR title LIKE ? "
                    "OR context LIKE ? ORDER BY severity",
                    (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_gotchas_for_skill(skill_id: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM reg_gotchas WHERE skill_id=? ORDER BY severity", (skill_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


@_with_retry
def clear_registry(db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute("DELETE FROM reg_gotchas")  # noqa: S608
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Project functions ──────────────────────────────────────────────────────


@_with_retry
def upsert_project(
    project_id: str,
    project_path: str,
    *,
    project_name: str | None = None,
    project_type: str | None = None,
    git_remote: str | None = None,
    db_path: Path | None = None,
) -> bool:
    # reg_projects deleted in migration 084. Writes to business_projects instead.
    # project_type maps to detected_stack; git_remote has no equivalent column (ignored).
    # INSERT OR IGNORE preserves existing rows, then selectively UPDATE changed fields.
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "INSERT OR IGNORE INTO business_projects"
                " (project_id, name, project_path, detected_stack, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'active', ?, ?)",
                (
                    project_id,
                    project_name or project_id,
                    project_path,
                    project_type,
                    _NOW(),
                    _NOW(),
                ),
            )
            # Update mutable fields only when the row already existed
            c.execute(
                "UPDATE business_projects SET"
                " project_path = ?,"
                " updated_at = ?"
                " WHERE project_id = ?",
                (project_path, _NOW(), project_id),
            )
            if project_name:
                c.execute(
                    "UPDATE business_projects SET name = ? WHERE project_id = ? AND name = ?",
                    (project_name, project_id, project_id),
                )
            if project_type:
                c.execute(
                    "UPDATE business_projects SET detected_stack = ? WHERE project_id = ?",
                    (project_type, project_id),
                )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_project(project_id: str, db_path: Path | None = None) -> dict | None:
    # reg_projects deleted in migration 084. Query business_projects instead.
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT project_id, name AS project_name, description, status,"
                " project_path, detected_stack AS project_type,"
                " total_sessions, total_tokens, last_session_at,"
                " created_at, updated_at"
                " FROM business_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            return dict(r) if r else None
        finally:
            c.close()
    except Exception:
        return None


def list_projects(db_path: Path | None = None) -> list[dict]:
    # reg_projects deleted in migration 084. Query business_projects instead.
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT project_id, name AS project_name, description, status,"
                " project_path, total_sessions, total_tokens, last_session_at,"
                " created_at, updated_at"
                " FROM business_projects"
                " ORDER BY last_session_at DESC, updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


@_with_retry
def update_project_stats(
    project_id: str, *, sessions_delta: int = 0, tokens_delta: int = 0, db_path: Path | None = None
) -> bool:
    # reg_projects deleted in migration 084. Update business_projects instead.
    # Only applies when project_id is a UUID that exists in business_projects.
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """UPDATE business_projects SET
                    total_sessions = total_sessions + ?,
                    total_tokens = total_tokens + ?,
                    last_session_at = ?,
                    updated_at = ?
                   WHERE project_id = ?""",
                (sessions_delta, tokens_delta, _NOW(), _NOW(), project_id),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.PROJECT_STATS_UPDATED,
                {
                    "project_id": project_id,
                    "sessions_delta": sessions_delta,
                    "tokens_delta": tokens_delta,
                },
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Session functions ──────────────────────────────────────────────────────


@_with_retry
def insert_session(
    session_id: str,
    project_id: str,
    *,
    topic: str | None = None,
    pipeline_phase: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT INTO raw_sessions
                   (session_id, project_id, topic, started_at, pipeline_phase)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, project_id, topic, _NOW(), pipeline_phase),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.SESSION_RECORDED,
                {
                    "session_id": session_id,
                    "project_id": project_id,
                    "topic": topic,
                    "pipeline_phase": pipeline_phase,
                },
                session_id=session_id,
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_session(session_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        try:
            r = c.execute("SELECT * FROM raw_sessions WHERE session_id=?", (session_id,)).fetchone()
            return dict(r) if r else None
        finally:
            c.close()
    except Exception:
        return None


def get_latest_session(project_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT * FROM raw_sessions WHERE project_id=? ORDER BY started_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return dict(r) if r else None
        finally:
            c.close()
    except Exception:
        return None


@_with_retry
def mark_handoff_consumed(session_id: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "UPDATE raw_sessions SET handoff_consumed=1 WHERE session_id=?", (session_id,)
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def end_session(
    session_id: str,
    *,
    outcome: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    tasks_completed: int | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        started = None
        with _db_transaction(db_path) as c:
            row = c.execute(
                "SELECT started_at FROM raw_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                except (ValueError, TypeError):
                    pass
            now = _NOW()
            duration = (datetime.fromisoformat(now) - started).total_seconds() if started else None
            c.execute(
                """UPDATE raw_sessions SET
                    ended_at=?, duration_s=?, outcome=?,
                    input_tokens=COALESCE(?, input_tokens),
                    output_tokens=COALESCE(?, output_tokens),
                    tasks_completed=COALESCE(?, tasks_completed)
                   WHERE session_id=?""",
                (now, duration, outcome, input_tokens, output_tokens, tasks_completed, session_id),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.SESSION_CLOSED,
                {
                    "session_id": session_id,
                    "outcome": outcome,
                    "duration_s": duration,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "tasks_completed": tasks_completed,
                },
                session_id=session_id,
            )

        # Session-end friction signal harvest (Phase 19.2).
        # Non-blocking: session close completes regardless of harvester outcome.
        try:
            from projections.core.analyzers.friction_signals import FrictionSignalHarvester

            _hconn = get_connection()
            try:
                harvester = FrictionSignalHarvester(_hconn, session_id=session_id)
                harvester.harvest()
            finally:
                _hconn.close()
        except Exception:
            pass

        # Session-end gap classification (Phase 19.3).
        # Runs after harvester; classifies newly-captured signals.
        # Non-blocking: session close completes regardless of classifier outcome.
        try:
            from projections.core.analyzers.gap_classifier import GapClassifier

            _gconn = get_connection()
            try:
                classifier = GapClassifier(_gconn, session_id=session_id)
                classifier.classify_all()
            finally:
                _gconn.close()
        except Exception:
            pass

        # Session-end workflow pattern analysis (Phase 19.4).
        # Detects skill co-occurrence patterns across sessions and upserts to
        # ds_workflow_pattern_signals. Runs after gap classification so the
        # current session's friction signals are already captured.
        # Non-blocking: session close completes regardless of analyzer outcome.
        try:
            from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

            _pconn = get_connection()
            try:
                analyzer = WorkflowPatternAnalyzer(_pconn)
                analyzer.analyze()
            finally:
                _pconn.close()
        except Exception:
            pass

        # Session-end retroactive validation (Phase 19.5).
        # Increments past_wo_count for experimental extensions whose skills ran
        # this session; triggers full validation when count crosses 5.
        # Non-blocking: session close completes regardless of validation outcome.
        try:
            from core.expansion.validation import RetroactiveValidator

            _vconn = get_connection()
            try:
                validator = RetroactiveValidator(_vconn)
                validator.increment_for_session(session_id=session_id)
            finally:
                _vconn.close()
        except Exception:
            pass

        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Handoff functions ──────────────────────────────────────────────────────


@_with_retry
def insert_handoff(
    session_id: str,
    project_id: str,
    topic: str,
    *,
    plan_path: str | None = None,
    pipeline_phase: str | None = None,
    current_task_id: str | None = None,
    current_task_name: str | None = None,
    tasks_completed: int | None = None,
    tasks_total: int | None = None,
    branch: str | None = None,
    last_commit: str | None = None,
    working: list | None = None,
    broken: list | None = None,
    pending_decisions: list | None = None,
    active_files: list | None = None,
    next_action: str | None = None,
    lessons_json: list | None = None,
    gotchas_hit: list | None = None,
    approaches_json: list | None = None,
    file_id: str | None = None,
    checksum: str | None = None,
    db_path: Path | None = None,
) -> int | None:
    try:
        with _db_transaction(db_path) as c:
            cur = c.execute(
                """INSERT INTO raw_handoffs
                   (session_id, project_id, topic, plan_path, pipeline_phase,
                    current_task_id, current_task_name, tasks_completed, tasks_total,
                    branch, last_commit, working, broken, pending_decisions,
                    active_files, next_action, lessons_json, gotchas_hit,
                    approaches_json, file_id, checksum, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    project_id,
                    topic,
                    plan_path,
                    pipeline_phase,
                    current_task_id,
                    current_task_name,
                    tasks_completed,
                    tasks_total,
                    branch,
                    last_commit,
                    json.dumps(working) if working is not None else None,
                    json.dumps(broken) if broken is not None else None,
                    json.dumps(pending_decisions) if pending_decisions is not None else None,
                    json.dumps(active_files) if active_files is not None else None,
                    next_action,
                    json.dumps(lessons_json) if lessons_json is not None else None,
                    json.dumps(gotchas_hit) if gotchas_hit is not None else None,
                    json.dumps(approaches_json) if approaches_json is not None else None,
                    file_id,
                    checksum,
                    _NOW(),
                ),
            )
            handoff_id = cur.lastrowid

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.HANDOFF_CREATED,
                {
                    "handoff_id": str(handoff_id),
                    "project_id": project_id,
                    "session_id": session_id,
                    "topic": topic,
                    "branch": branch,
                },
                session_id=session_id,
            )

            return handoff_id
    except Exception as e:
        _reraise_if_busy(e)
        return None


def get_latest_handoff(project_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT * FROM raw_handoffs WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        finally:
            c.close()
        if not r:
            return None
        d = dict(r)
        for col in (
            "working",
            "broken",
            "pending_decisions",
            "active_files",
            "lessons_json",
            "gotchas_hit",
            "approaches_json",
        ):
            if d.get(col):
                try:
                    d[col] = json.loads(d[col])
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):  # cq-006-suppress: intentional graceful degradation on malformed event payload. See: docs/architecture/event-store-corruption-tolerance.md
                    pass
        return d
    except Exception:
        return None


def get_latest_unconsumed_handoff(db_path: Path | None = None) -> dict | None:
    """Return the most recent handoff that has not been consumed, across all projects."""
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                """SELECT h.* FROM raw_handoffs h
               LEFT JOIN raw_sessions s ON h.session_id = s.session_id
               WHERE COALESCE(s.handoff_consumed, 0) = 0
               ORDER BY h.created_at DESC LIMIT 1""",
            ).fetchone()
        finally:
            c.close()
        if not r:
            return None
        d = dict(r)
        for col in (
            "working",
            "broken",
            "pending_decisions",
            "active_files",
            "lessons_json",
            "gotchas_hit",
            "approaches_json",
        ):
            if d.get(col):
                try:
                    d[col] = json.loads(d[col])
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):  # cq-006-suppress: intentional graceful degradation on malformed event payload. See: docs/architecture/event-store-corruption-tolerance.md
                    pass
        return d
    except Exception:
        return None


def get_handoffs_for_project(
    project_id: str, limit: int = 20, db_path: Path | None = None
) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM raw_handoffs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


# Spec + Task functions removed — raw_specs / raw_tasks dropped in migration 128.


# ── Lesson functions ───────────────────────────────────────────────────────


@_with_retry
def insert_lesson(
    lesson_id: str,
    source: str,
    title: str,
    *,
    what_happened: str | None = None,
    lesson: str | None = None,
    evidence: str | None = None,
    confidence: str = "medium",
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    skill_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Insert lesson into raw_lessons table.

    Writes to activity_log FIRST via EventNormalizer, then links via activity_id (Phase 3 traceability).

    Args:
        lesson_id: Unique lesson identifier
        source: Source of the lesson (e.g., 'build', 'review', 'debug')
        title: Short lesson title
        what_happened: Description of what occurred
        lesson: The actual lesson learned
        evidence: Evidence supporting the lesson
        confidence: Confidence level ('low', 'medium', 'high')
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        session_id: Optional session ID for cross-domain linkage
        skill_id: Optional skill ID for cross-domain linkage
        db_path: Optional database path
    """
    try:
        with _db_transaction(db_path) as c:
            # 1. Emit canonical event (TA0c: activity_log retired)
            _try_emit_canonical(
                _CanonicalEventType.LESSON_CAPTURED,
                {
                    "lesson_id": lesson_id,
                    "source": source,
                    "title": title,
                    "confidence": confidence,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
                skill_id=skill_id,
            )
            activity_id = None  # deprecated FK column

            # 2. Insert into raw_lessons with activity_id FK
            c.execute(
                """INSERT OR IGNORE INTO raw_lessons
                   (lesson_id, source, title, what_happened, lesson,
                    evidence, confidence, created_at, activity_id,
                    prd_id, task_id, skill_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lesson_id,
                    source,
                    title,
                    what_happened,
                    lesson,
                    evidence,
                    confidence,
                    _NOW(),
                    activity_id,
                    prd_id,
                    task_id,
                    skill_id,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def draft_lesson(
    source: str,
    title: str,
    *,
    lesson_id: str | None = None,
    what_happened: str | None = None,
    lesson: str | None = None,
    evidence: str | None = None,
    confidence: str = "medium",
    db_path: Path | None = None,
) -> bool:
    """Create a draft lesson in raw_lessons. Single authoritative entry point.

    lesson_id defaults to a UUID if not supplied. Callers that need deterministic
    deduplication (e.g., file-based writers that deduplicated by filename) should
    supply a stable lesson_id (e.g., the old filename stem).
    """
    import uuid as _uuid

    lid = lesson_id if lesson_id is not None else str(_uuid.uuid4())
    return insert_lesson(
        lid,
        source,
        title,
        what_happened=what_happened,
        lesson=lesson,
        evidence=evidence,
        confidence=confidence,
        db_path=db_path,
    )


def get_lessons(
    source: str | None = None, status: str | None = None, db_path: Path | None = None
) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            query = "SELECT * FROM raw_lessons"
            params: list = []
            clauses: list[str] = []
            if source:
                clauses.append("source=?")
                params.append(source)
            if status:
                clauses.append("status=?")
                params.append(status)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC"
            rows = c.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


@_with_retry
def promote_lesson(lesson_id: str, promoted_to: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """UPDATE raw_lessons SET
                    status='promoted', promoted_to=?, reviewed_at=?
                   WHERE lesson_id=?""",
                (promoted_to, _NOW(), lesson_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def reject_lesson(lesson_id: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "UPDATE raw_lessons SET status='rejected', reviewed_at=? WHERE lesson_id=?",
                (_NOW(), lesson_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_pending_lessons(db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM raw_lessons WHERE status='draft' ORDER BY created_at DESC",
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


# ── Research functions ─────────────────────────────────────────────────────
# insert_research removed — raw_research dropped migration 131


@_with_retry
def cache_research(
    topic: str,
    focus_areas: list[str],
    sources: list[dict],
    findings: str,
    *,
    confidence_score: float = 0.5,
    triangulation_score: float = 0.5,
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    ttl_days: int = 30,
    db_path: Path | None = None,
) -> bool:
    """
    Cache research results in research_cache table.

    Writes to activity_log FIRST via EventNormalizer, then links via activity_id (Phase 3 traceability).

    Args:
        topic: Research topic
        focus_areas: List of focus areas (JSON array)
        sources: List of source dicts with {url, title, summary, tier}
        findings: Markdown summary of research findings
        confidence_score: Overall confidence (0.0-1.0)
        triangulation_score: Source triangulation score (0.0-1.0)
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        session_id: Optional session ID for cross-domain linkage
        ttl_days: Time-to-live in days (default 30)
        db_path: Optional database path
    """
    try:
        cache_id = hashlib.sha256(topic.encode()).hexdigest()[:16]
        expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()

        with _db_transaction(db_path) as c:
            # 1. Emit canonical event (TA0c: activity_log retired)
            _try_emit_canonical(
                _CanonicalEventType.RESEARCH_CACHE_STORED,
                {
                    "cache_id": cache_id,
                    "topic": topic,
                    "source_count": len(sources),
                    "confidence_score": confidence_score,
                    "triangulation_score": triangulation_score,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
            )
            activity_id = None  # deprecated FK column

            # 2. Insert into research_cache with activity_id FK
            c.execute(
                """INSERT OR REPLACE INTO research_cache
                   (cache_id, topic, focus_areas, sources, findings,
                    confidence_score, triangulation_score, activity_id,
                    prd_id, task_id, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cache_id,
                    topic,
                    json.dumps(focus_areas),
                    json.dumps(sources),
                    findings,
                    confidence_score,
                    triangulation_score,
                    activity_id,
                    prd_id,
                    task_id,
                    expires_at,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_research_cache(topic: str, db_path: Path | None = None) -> dict | None:
    """Get cached research for a topic (if not expired)."""
    try:
        cache_id = hashlib.sha256(topic.encode()).hexdigest()[:16]
        c = _connect(db_path)
        try:
            r = c.execute(
                """SELECT * FROM research_cache
               WHERE cache_id=? AND (expires_at IS NULL OR expires_at > ?)""",
                (cache_id, _NOW()),
            ).fetchone()
        finally:
            c.close()
        if not r:
            return None
        d = dict(r)
        # Parse JSON fields
        for col in ("focus_areas", "sources"):
            if d.get(col):
                try:
                    d[col] = json.loads(d[col])
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):  # cq-006-suppress: intentional graceful degradation on malformed event payload. See: docs/architecture/event-store-corruption-tolerance.md
                    pass
        return d
    except Exception:
        return None


def get_research_by_task(task_id: str, db_path: Path | None = None) -> list[dict]:
    """Get all research linked to a specific task."""
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                """SELECT * FROM raw_research
               WHERE task_id=? ORDER BY created_at DESC""",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_research_by_prd(prd_id: str, db_path: Path | None = None) -> list[dict]:
    """Get all research linked to a specific PRD."""
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                """SELECT * FROM raw_research
               WHERE prd_id=? ORDER BY created_at DESC""",
                (prd_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


# ── Sentinel functions ─────────────────────────────────────────────────────


@_with_retry
def set_sentinel(
    sentinel_key: str,
    sentinel_type: str,
    *,
    expires_at: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO raw_sentinels
                   (sentinel_key, sentinel_type, created_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (sentinel_key, sentinel_type, _NOW(), expires_at),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def has_sentinel(sentinel_key: str, db_path: Path | None = None) -> bool:
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT expires_at FROM raw_sentinels WHERE sentinel_key=?", (sentinel_key,)
            ).fetchone()
        finally:
            c.close()
        if not r:
            return False
        if r["expires_at"]:
            return datetime.fromisoformat(r["expires_at"]) > datetime.now(timezone.utc)
        return True
    except Exception:
        return False


@_with_retry
def clear_expired_sentinels(db_path: Path | None = None) -> int:
    try:
        with _db_transaction(db_path) as c:
            n = c.execute(
                "DELETE FROM raw_sentinels WHERE expires_at IS NOT NULL AND expires_at < ?",
                (_NOW(),),
            ).rowcount
        return n
    except Exception as e:
        _reraise_if_busy(e)
        return 0


# ── Hook tracking functions ────────────────────────────────────────────────


@_with_retry
def insert_hook_execution(
    hook_name: str,
    hook_type: str,
    trigger_context: dict,
    started_at: str,
    completed_at: Optional[str] = None,
    duration_ms: Optional[int] = None,
    exit_code: int = 0,
    status: str = "success",
    output: Optional[str] = None,
    error_message: Optional[str] = None,
    cpu_time_ms: Optional[int] = None,
    memory_mb: Optional[float] = None,
    prd_id: Optional[str] = None,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    db_path: Path | None = None,
) -> Optional[int]:
    """
    Emit the HOOK_EXECUTION_LOGGED canonical event for a hook execution.

    The SQLite hook_executions projection table was dropped in migration 129
    (WO-READMODELS-DUCKDB). Hook executions are now served by the DuckDB
    hook_executions VIEW in aggregate_metrics.db, derived from this canonical
    event via the events_fact pipeline. This function only emits the canonical
    event; it no longer writes a SQLite projection row.

    Returns None (activity_id is a retired FK column).
    Uses fire-and-forget pattern with DB lock fallback to text file.
    """
    try:
        with _db_transaction(db_path):
            # Emit canonical event (TA0c: activity_log retired). The DuckDB
            # hook_executions view is derived from this event via events_fact.
            _try_emit_canonical(
                _CanonicalEventType.HOOK_EXECUTION_LOGGED,
                {
                    "hook_name": hook_name,
                    "hook_type": hook_type,
                    "trigger_context": trigger_context,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                    "exit_code": exit_code,
                    "status": status,
                    "output": output,
                    "error_message": error_message,
                    "cpu_time_ms": cpu_time_ms,
                    "memory_mb": memory_mb,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
            )
            return None
    except Exception as e:
        # 3. If DB locked: write to fallback file
        _reraise_if_busy(e)
        try:
            fallback = paths.state_dir() / "hook_executions_fallback.jsonl"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "hook_name": hook_name,
                            "hook_type": hook_type,
                            "trigger_context": trigger_context,
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                            "exit_code": exit_code,
                            "status": status,
                            "output": output,
                            "error_message": error_message,
                            "cpu_time_ms": cpu_time_ms,
                            "memory_mb": memory_mb,
                            "prd_id": prd_id,
                            "task_id": task_id,
                            "session_id": session_id,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass  # Fire-and-forget - don't fail the hook
        return -1  # Return sentinel value for fallback


# ── Skill execution functions (TC-007) ────────────────────────────────────


def log_skill_execution(
    skill_name: str,
    skill_args: str = "",
    *,
    status: str = "success",
    model: str = "unspecified",
    session_id: str | None = None,
    project_id: str | None = None,
    prd_id: str | None = None,
    task_id: str | None = None,
    duration_ms: int | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_message: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Log skill execution to activity_log via EventNormalizer (TC-007).

    This function integrates the EventNormalizer with skill invocations, ensuring
    all skill outputs are normalized before being written to activity_log.

    Args:
        skill_name: Skill identifier (e.g., "ds-core", "ds-quality")
        skill_args: Skill arguments/mode (e.g., "build", "debug")
        status: Execution status ("success", "failed", "error")
        model: Optional tool/model metadata label
        session_id: Tool/session ID
        project_id: Project identifier
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        duration_ms: Execution duration in milliseconds
        input_tokens: Input token count
        output_tokens: Output token count
        error_message: Optional error message if status != "success"
        db_path: Optional database path

    Returns:
        True on success, False on failure
    """
    try:
        # Generate unique skill execution ID
        skill_exec_id = hashlib.sha256(
            f"{skill_name}:{skill_args}:{session_id}:{_NOW()}".encode()
        ).hexdigest()[:16]

        # Map user-friendly status to DB-compatible status
        # DB schema only allows: 'pending', 'in_progress', 'completed', 'failed', 'cancelled'
        status_map = {
            "success": "completed",
            "error": "failed",
            "pending": "pending",
            "in_progress": "in_progress",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }
        db_status = status_map.get(status, "completed")  # Default to "completed" for unknown

        # Emit canonical event (TA0c: activity_log retired)
        _try_emit_canonical(
            _CanonicalEventType.SKILL_EXECUTED,
            {
                "skill_exec_id": skill_exec_id,
                "skill_name": skill_name,
                "skill_args": skill_args,
                "model": model,
                "status": db_status,
                "duration_ms": duration_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "error_message": error_message,
                "session_id": session_id,
                "project_id": project_id,
            },
            session_id=session_id,
            task_id=task_id,
            prd_id=prd_id,
            skill_id=skill_name,
        )

        return True
    except Exception as e:
        _reraise_if_busy(e)
        # Fallback: write to JSONL file if DB write fails
        try:
            fallback = paths.state_dir() / "skill_executions_fallback.jsonl"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "skill_name": skill_name,
                            "skill_args": skill_args,
                            "status": status,
                            "model": model,
                            "session_id": session_id,
                            "project_id": project_id,
                            "error_message": error_message,
                            "logged_at": _NOW(),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass  # Fire-and-forget - don't fail the hook
        return False


# ── Token usage functions ─────────────────────────────────────────────────


@_with_retry
def insert_token_usage(
    *,
    session_id: str | None = None,
    project_id: str | None = None,
    skill_name: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT INTO raw_token_usage
                   (session_id, project_id, skill_name, input_tokens,
                    output_tokens, model, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, project_id, skill_name, input_tokens, output_tokens, model, _NOW()),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_token_summary(
    project_id: str | None = None, days: int = 7, db_path: Path | None = None
) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            if project_id:
                rows = c.execute(
                    """SELECT skill_name,
                          SUM(input_tokens) AS total_input,
                          SUM(output_tokens) AS total_output,
                          SUM(input_tokens + output_tokens) AS total_tokens,
                          COUNT(*) AS call_count
                   FROM raw_token_usage
                   WHERE project_id=? AND recorded_at>=?
                   GROUP BY skill_name ORDER BY total_tokens DESC""",
                    (project_id, cutoff),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT project_id,
                          SUM(input_tokens) AS total_input,
                          SUM(output_tokens) AS total_output,
                          SUM(input_tokens + output_tokens) AS total_tokens,
                          COUNT(*) AS call_count
                   FROM raw_token_usage
                   WHERE recorded_at>=?
                   GROUP BY project_id ORDER BY total_tokens DESC""",
                    (cutoff,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


# ── Schema introspection ───────────────────────────────────────────────────


def schema_version(db_path: Path | None = None) -> int:
    try:
        c = _connect(db_path)
        try:
            v = c.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
            return v
        finally:
            c.close()
    except Exception:
        return 0


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description="studio_db CLI")
    sub = ap.add_subparsers(dest="cmd")
    # skill-correct subcommand removed — cor_skill_corrections dropped migration 131
    ib = sub.add_parser("import-and-rebuild")
    ib.add_argument("--buffer", required=True)
    sub.add_parser("prune")
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "import-and-rebuild":
        n = import_buffer(Path(args.buffer))
        rebuild_summaries()
        print(f"imported {n} rows")
    elif args.cmd == "prune":
        print(f"pruned {rolling_window_prune()} rows")
    elif args.cmd == "status":
        c = _connect()
        tables = [
            "raw_workflow_runs",
            "raw_workflow_nodes",
            "raw_skill_telemetry",
            # cor_skill_corrections dropped migration 131
            "sum_skill_summary",
            "log_batch_imports",
            "raw_operational_snapshots",
            "raw_approaches",
            "reg_gotchas",
            "reg_projects",
            "raw_sessions",
            "raw_handoffs",
            "raw_lessons",
            "raw_sentinels",
            "raw_token_usage",
            "_schema_version",
        ]
        v = c.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
        print(f"Schema version: {v}")
        fk = c.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"Foreign keys: {'ON' if fk else 'OFF'}")
        print(f"\n{'Table':<30} {'Rows':>8}\n" + "-" * 40)
        for t in tables:
            try:
                n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                print(f"{t:<30} {n:>8}")
            except sqlite3.OperationalError:
                print(f"{t:<30} {'N/A':>8}")
        c.close()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
