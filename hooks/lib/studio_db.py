"""SQLite analytics backend for dream-studio (WAL, migrations, retry, CLI)."""
from __future__ import annotations
import argparse, functools, hashlib, json, re, sqlite3, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths  # noqa: E402

_NOW = lambda: datetime.now(timezone.utc).isoformat()

def _db_path() -> Path: return paths.state_dir() / "studio.db"


# ── SQL statement splitter ──────────────────────────────────────────────────

def _split_statements(sql_text: str) -> list[str]:
    """Split SQL into individual statements, respecting trigger BEGIN/END blocks."""
    statements: list[str] = []
    current: list[str] = []
    depth = 0

    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        current.append(line)
        upper = stripped.upper()

        if re.search(r"\bBEGIN\b", upper):
            depth += 1

        if stripped.endswith(";"):
            end_token = upper.rstrip(";").rstrip()
            if depth > 0 and end_token.endswith("END"):
                depth -= 1

            if depth == 0:
                stmt = "\n".join(current).strip().rstrip(";").strip()
                if stmt:
                    statements.append(stmt)
                current = []

    if current:
        stmt = "\n".join(current).strip().rstrip(";").strip()
        if stmt:
            statements.append(stmt)

    return statements


# ── Migration runner ────────────────────────────────────────────────────────

def _migrations_dir() -> Path:
    return Path(__file__).parent / "migrations"


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending schema migrations from hooks/lib/migrations/*.sql."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()

    current = conn.execute(
        "SELECT MAX(version) FROM _schema_version"
    ).fetchone()[0] or 0

    mdir = _migrations_dir()
    if not mdir.is_dir():
        return

    files = sorted(mdir.glob("[0-9]*.sql"))
    if not files:
        return

    latest_code = max(int(f.stem.split("_")[0]) for f in files)

    if current > latest_code:
        raise RuntimeError(
            f"Database schema v{current} is newer than code v{latest_code}. "
            "Update dream-studio to a compatible version."
        )

    for f in files:
        version = int(f.stem.split("_")[0])
        if version <= current:
            continue

        sql_text = f.read_text(encoding="utf-8")
        for stmt in _split_statements(sql_text):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "duplicate column name" in msg:
                    continue
                if "no such module" in msg:
                    continue
                if "no such table" in msg and "fts_gotchas" in msg:
                    continue
                raise

        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, ?)",
            (version, _NOW()),
        )
        conn.commit()


# ── Connection ──────────────────────────────────────────────────────────────

def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or _db_path()), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    _run_migrations(conn)
    return conn


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
def archive_workflow(run_key: str, wf: dict, db_path: Path | None = None) -> bool:
    try:
        nodes = wf.get("nodes", {})
        with _connect(db_path) as c:
            c.execute("INSERT INTO raw_workflow_runs(run_key,workflow,yaml_path,status,started_at,node_count,nodes_done) VALUES(?,?,?,?,?,?,?)",
                      (run_key, wf["workflow"], wf["yaml_path"], wf["status"], wf.get("started", _NOW()), len(nodes),
                       sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))))
            for nid, nd in nodes.items():
                c.execute("INSERT INTO raw_workflow_nodes(run_key,node_id,status,started_at,finished_at,duration_s,output) VALUES(?,?,?,?,?,?,?)",
                          (run_key, nid, nd.get("status",""), nd.get("started"), nd.get("finished"), nd.get("duration_s"), nd.get("output")))
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def last_run(workflow_name: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        r = c.execute("SELECT run_key,status,started_at,finished_at FROM raw_workflow_runs WHERE workflow=? ORDER BY finished_at DESC LIMIT 1", (workflow_name,)).fetchone()
        c.close(); return dict(r) if r else None
    except Exception: return None


def run_count(workflow_name: str, db_path: Path | None = None) -> int:
    try:
        c = _connect(db_path); n = c.execute("SELECT COUNT(*) FROM raw_workflow_runs WHERE workflow=?", (workflow_name,)).fetchone()[0]; c.close(); return n
    except Exception: return 0


@_with_retry
def import_buffer(buffer_path: Path, db_path: Path | None = None) -> int:
    try:
        raw = buffer_path.read_bytes()
        if not raw.strip(): return 0
        bid = hashlib.sha256(raw).hexdigest()
        with _connect(db_path) as c:
            if c.execute("SELECT 1 FROM log_batch_imports WHERE batch_id=?", (bid,)).fetchone(): return 0
            rows = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
            for r in rows:
                c.execute("INSERT INTO raw_skill_telemetry(skill_name,invoked_at,model,input_tokens,output_tokens,success,execution_time_s) VALUES(?,?,?,?,?,?,?)",
                          (r["skill_name"], r.get("invoked_at", _NOW()), r.get("model"), r.get("input_tokens"), r.get("output_tokens"), int(r["success"]), r.get("execution_time_s")))
            c.execute("INSERT INTO log_batch_imports(batch_id,imported_at,row_count) VALUES(?,?,?)", (bid, _NOW(), len(rows)))
        return len(rows)
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def rebuild_summaries(db_path: Path | None = None) -> None:
    try:
        with _connect(db_path) as c:
            c.executescript("""DELETE FROM sum_skill_summary;
INSERT INTO sum_skill_summary SELECT skill_name,COUNT(*),AVG(success),AVG(input_tokens),AVG(output_tokens),AVG(execution_time_s),MAX(CASE WHEN success=1 THEN invoked_at END),MAX(CASE WHEN success=0 THEN invoked_at END),datetime('now') FROM (SELECT * FROM effective_skill_runs WHERE skill_name IN (SELECT skill_name FROM raw_skill_telemetry GROUP BY skill_name HAVING COUNT(*)>=5) ORDER BY id DESC LIMIT 30) GROUP BY skill_name;""")
    except Exception as e:
        _reraise_if_busy(e)


@_with_retry
def rolling_window_prune(db_path: Path | None = None) -> int:
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        with _connect(db_path) as c:
            d1 = c.execute("DELETE FROM raw_skill_telemetry WHERE id NOT IN (SELECT id FROM raw_skill_telemetry t2 WHERE t2.skill_name=raw_skill_telemetry.skill_name ORDER BY id DESC LIMIT 100)").rowcount
            d2 = c.execute("DELETE FROM raw_workflow_nodes WHERE run_key IN (SELECT run_key FROM raw_workflow_runs WHERE finished_at<?)", (cutoff,)).rowcount
            d3 = c.execute("DELETE FROM raw_workflow_runs WHERE finished_at<?", (cutoff,)).rowcount
            d4 = c.execute("DELETE FROM raw_approaches WHERE captured_at<?", (cutoff,)).rowcount
        return d1 + d2 + d3 + d4
    except Exception as e:
        _reraise_if_busy(e)
        return 0


def get_skill_summaries(db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
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
        c.close()
        return result
    except Exception:
        return []


@_with_retry
def skill_correct(telemetry_id: int, success: int, reason: str = "", db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute("INSERT INTO cor_skill_corrections(telemetry_id,corrected_success,reason,corrected_at) VALUES(?,?,?,?)", (telemetry_id, success, reason, _NOW()))
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


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
        with _connect(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO raw_operational_snapshots
                   (snapshot_date, project_slug, ci_status, open_prs,
                    stale_branches, pending_drafts, open_escalations, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_date, project_slug, ci_status, open_prs,
                 stale_branches, pending_drafts, open_escalations, _NOW()),
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
        with _connect(db_path) as c:
            c.execute(
                """INSERT INTO raw_approaches
                   (skill_id, session_date, approach, outcome, context,
                    why_worked, tokens_used, duration_s, model, captured_at,
                    project_id, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (skill_id, session_date or _NOW()[:10], approach, outcome,
                 context or None, why or None, tokens_used, duration_s, model, _NOW(),
                 project_id, session_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_approach_patterns(skill_id: str | None = None, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        if skill_id:
            rows = c.execute("SELECT * FROM vw_approach_patterns WHERE skill_id=? ORDER BY success_pct DESC", (skill_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM vw_approach_patterns ORDER BY success_pct DESC").fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_best_approaches(skill_id: str, limit: int = 3, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute(
            "SELECT * FROM vw_approach_patterns WHERE skill_id=? ORDER BY success_pct DESC, times_tried DESC LIMIT ?",
            (skill_id, limit),
        ).fetchall()
        c.close()
        return [dict(r) for r in rows]
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
    ok = insert_approach(skill, approach, outcome, context=context, why=why)
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
def upsert_skill(skill_id: str, pack: str, mode: str, skill_path: str, *,
                 description: str = "", triggers: str = "", gotchas_path: str | None = None,
                 word_count: int | None = None, chains_to: str | None = None,
                 db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO reg_skills
                   (skill_id, pack, mode, description, triggers, skill_path,
                    gotchas_path, word_count, chains_to, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (skill_id, pack, mode, description, triggers, skill_path,
                 gotchas_path, word_count, chains_to, _NOW()),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_skill(skill_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        r = c.execute("SELECT * FROM reg_skills WHERE skill_id=?", (skill_id,)).fetchone()
        c.close()
        return dict(r) if r else None
    except Exception:
        return None


def find_skills_by_trigger(keyword: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute("SELECT * FROM reg_skills WHERE triggers LIKE ?", (f"%{keyword}%",)).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def upsert_gotcha(gotcha_id: str, skill_id: str, severity: str, title: str, *,
                  context: str = "", fix: str = "", keywords: str = "",
                  discovered: str | None = None, db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO reg_gotchas
                   (gotcha_id, skill_id, severity, title, context, fix,
                    keywords, discovered, times_hit, last_hit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                           COALESCE((SELECT times_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?), 0),
                           (SELECT last_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?))""",
                (gotcha_id, skill_id, severity, title, context, fix,
                 keywords, discovered, gotcha_id, skill_id, gotcha_id, skill_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def search_gotchas_db(keyword: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
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
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_gotchas_for_skill(skill_id: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute("SELECT * FROM reg_gotchas WHERE skill_id=? ORDER BY severity", (skill_id,)).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def upsert_workflow(workflow_id: str, yaml_path: str, *, description: str = "",
                    node_count: int | None = None, skills_used: str = "",
                    category: str = "", est_tokens: int | None = None,
                    db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO reg_workflows
                   (workflow_id, yaml_path, description, node_count,
                    skills_used, category, est_tokens, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (workflow_id, yaml_path, description, node_count,
                 skills_used, category, est_tokens, _NOW()),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_workflows_by_category(category: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute("SELECT * FROM reg_workflows WHERE category=?", (category,)).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def upsert_skill_dep(from_skill: str, to_skill: str, dep_type: str,
                     db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute("INSERT OR REPLACE INTO reg_skill_deps VALUES (?, ?, ?)",
                      (from_skill, to_skill, dep_type))
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_skill_deps(skill_id: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute("SELECT * FROM reg_skill_deps WHERE from_skill=?", (skill_id,)).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def clear_registry(db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            for t in ("reg_skills", "reg_gotchas", "reg_workflows", "reg_skill_deps"):
                c.execute(f"DELETE FROM {t}")  # noqa: S608
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Project functions ──────────────────────────────────────────────────────

@_with_retry
def upsert_project(project_id: str, project_path: str, *,
                   project_name: str | None = None, project_type: str | None = None,
                   git_remote: str | None = None, db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT INTO reg_projects
                   (project_id, project_path, project_name, project_type,
                    git_remote, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id) DO UPDATE SET
                    project_path=excluded.project_path,
                    project_name=COALESCE(excluded.project_name, reg_projects.project_name),
                    project_type=COALESCE(excluded.project_type, reg_projects.project_type),
                    git_remote=COALESCE(excluded.git_remote, reg_projects.git_remote)""",
                (project_id, project_path, project_name, project_type,
                 git_remote, _NOW()),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_project(project_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        r = c.execute("SELECT * FROM reg_projects WHERE project_id=?", (project_id,)).fetchone()
        c.close()
        return dict(r) if r else None
    except Exception:
        return None


def list_projects(db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute("SELECT * FROM reg_projects ORDER BY last_session_at DESC").fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def update_project_stats(project_id: str, *, sessions_delta: int = 0,
                         tokens_delta: int = 0, db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """UPDATE reg_projects SET
                    total_sessions = total_sessions + ?,
                    total_tokens = total_tokens + ?,
                    last_session_at = ?
                   WHERE project_id = ?""",
                (sessions_delta, tokens_delta, _NOW(), project_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Session functions ──────────────────────────────────────────────────────

@_with_retry
def insert_session(session_id: str, project_id: str, *,
                   topic: str | None = None, pipeline_phase: str | None = None,
                   db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT INTO raw_sessions
                   (session_id, project_id, topic, started_at, pipeline_phase)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, project_id, topic, _NOW(), pipeline_phase),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_session(session_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        r = c.execute("SELECT * FROM raw_sessions WHERE session_id=?", (session_id,)).fetchone()
        c.close()
        return dict(r) if r else None
    except Exception:
        return None


def get_latest_session(project_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        r = c.execute(
            "SELECT * FROM raw_sessions WHERE project_id=? ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        c.close()
        return dict(r) if r else None
    except Exception:
        return None


@_with_retry
def mark_handoff_consumed(session_id: str, db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute("UPDATE raw_sessions SET handoff_consumed=1 WHERE session_id=?",
                      (session_id,))
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def end_session(session_id: str, *, outcome: str | None = None,
                input_tokens: int | None = None, output_tokens: int | None = None,
                tasks_completed: int | None = None,
                db_path: Path | None = None) -> bool:
    try:
        started = None
        with _connect(db_path) as c:
            row = c.execute("SELECT started_at FROM raw_sessions WHERE session_id=?",
                            (session_id,)).fetchone()
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
                (now, duration, outcome, input_tokens, output_tokens,
                 tasks_completed, session_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Handoff functions ──────────────────────────────────────────────────────

@_with_retry
def insert_handoff(session_id: str, project_id: str, topic: str, *,
                   plan_path: str | None = None, pipeline_phase: str | None = None,
                   current_task_id: str | None = None, current_task_name: str | None = None,
                   tasks_completed: int | None = None, tasks_total: int | None = None,
                   branch: str | None = None, last_commit: str | None = None,
                   working: list | None = None, broken: list | None = None,
                   pending_decisions: list | None = None, active_files: list | None = None,
                   next_action: str | None = None, lessons_json: list | None = None,
                   gotchas_hit: list | None = None, approaches_json: list | None = None,
                   db_path: Path | None = None) -> int | None:
    try:
        with _connect(db_path) as c:
            cur = c.execute(
                """INSERT INTO raw_handoffs
                   (session_id, project_id, topic, plan_path, pipeline_phase,
                    current_task_id, current_task_name, tasks_completed, tasks_total,
                    branch, last_commit, working, broken, pending_decisions,
                    active_files, next_action, lessons_json, gotchas_hit,
                    approaches_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, project_id, topic, plan_path, pipeline_phase,
                 current_task_id, current_task_name, tasks_completed, tasks_total,
                 branch, last_commit,
                 json.dumps(working) if working is not None else None,
                 json.dumps(broken) if broken is not None else None,
                 json.dumps(pending_decisions) if pending_decisions is not None else None,
                 json.dumps(active_files) if active_files is not None else None,
                 next_action,
                 json.dumps(lessons_json) if lessons_json is not None else None,
                 json.dumps(gotchas_hit) if gotchas_hit is not None else None,
                 json.dumps(approaches_json) if approaches_json is not None else None,
                 _NOW()),
            )
            return cur.lastrowid
    except Exception as e:
        _reraise_if_busy(e)
        return None


def get_latest_handoff(project_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        r = c.execute(
            "SELECT * FROM raw_handoffs WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        c.close()
        if not r:
            return None
        d = dict(r)
        for col in ("working", "broken", "pending_decisions", "active_files",
                     "lessons_json", "gotchas_hit", "approaches_json"):
            if d.get(col):
                try:
                    d[col] = json.loads(d[col])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
    except Exception:
        return None


def get_handoffs_for_project(project_id: str, limit: int = 20,
                             db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute(
            "SELECT * FROM raw_handoffs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Spec + Task functions ──────────────────────────────────────────────────

@_with_retry
def upsert_spec(spec_id: str, project_id: str, title: str, *,
                status: str = "draft", task_count: int | None = None,
                spec_content: str | None = None, plan_content: str | None = None,
                pr_numbers: list | None = None,
                db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT INTO raw_specs
                   (spec_id, project_id, title, status, task_count,
                    spec_content, plan_content, created_at, pr_numbers)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(spec_id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    task_count=COALESCE(excluded.task_count, raw_specs.task_count),
                    spec_content=COALESCE(excluded.spec_content, raw_specs.spec_content),
                    plan_content=COALESCE(excluded.plan_content, raw_specs.plan_content),
                    pr_numbers=COALESCE(excluded.pr_numbers, raw_specs.pr_numbers),
                    completed_at=CASE WHEN excluded.status='completed'
                                      THEN COALESCE(raw_specs.completed_at, ?)
                                      ELSE raw_specs.completed_at END""",
                (spec_id, project_id, title, status, task_count,
                 spec_content, plan_content, _NOW(),
                 json.dumps(pr_numbers) if pr_numbers else None,
                 _NOW()),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_spec(spec_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        r = c.execute("SELECT * FROM raw_specs WHERE spec_id=?", (spec_id,)).fetchone()
        c.close()
        return dict(r) if r else None
    except Exception:
        return None


def list_specs(project_id: str | None = None, status: str | None = None,
               db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        query = "SELECT * FROM raw_specs"
        params: list = []
        clauses: list[str] = []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        rows = c.execute(query, params).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def upsert_task(task_id: str, spec_id: str, project_id: str, title: str, *,
                status: str = "planned", depends_on: list | None = None,
                estimated_hours: float | None = None,
                db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT INTO raw_tasks
                   (task_id, spec_id, project_id, title, status,
                    depends_on, estimated_hours)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_id, spec_id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    depends_on=COALESCE(excluded.depends_on, raw_tasks.depends_on),
                    estimated_hours=COALESCE(excluded.estimated_hours, raw_tasks.estimated_hours)""",
                (task_id, spec_id, project_id, title, status,
                 json.dumps(depends_on) if depends_on else None,
                 estimated_hours),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_tasks_for_spec(spec_id: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute(
            "SELECT * FROM raw_tasks WHERE spec_id=? ORDER BY task_id",
            (spec_id,),
        ).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_blocked_tasks(project_id: str | None = None,
                      db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        if project_id:
            rows = c.execute(
                "SELECT t.*, s.title AS spec_title FROM raw_tasks t "
                "JOIN raw_specs s ON t.spec_id=s.spec_id "
                "WHERE t.status='blocked' AND t.project_id=?",
                (project_id,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT t.*, s.title AS spec_title FROM raw_tasks t "
                "JOIN raw_specs s ON t.spec_id=s.spec_id "
                "WHERE t.status='blocked'",
            ).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def update_task_status(task_id: str, spec_id: str, status: str, *,
                       commit_sha: str | None = None,
                       actual_hours: float | None = None,
                       assigned_session: str | None = None,
                       db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            completed_at = _NOW() if status == "completed" else None
            c.execute(
                """UPDATE raw_tasks SET
                    status=?,
                    commit_sha=COALESCE(?, commit_sha),
                    actual_hours=COALESCE(?, actual_hours),
                    assigned_session=COALESCE(?, assigned_session),
                    completed_at=COALESCE(?, completed_at)
                   WHERE task_id=? AND spec_id=?""",
                (status, commit_sha, actual_hours, assigned_session,
                 completed_at, task_id, spec_id),
            )
            if status == "completed":
                c.execute(
                    "UPDATE raw_specs SET tasks_done = "
                    "(SELECT COUNT(*) FROM raw_tasks WHERE spec_id=? AND status='completed') "
                    "WHERE spec_id=?",
                    (spec_id, spec_id),
                )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


# ── Lesson functions ───────────────────────────────────────────────────────

@_with_retry
def insert_lesson(lesson_id: str, source: str, title: str, *,
                  what_happened: str | None = None, lesson: str | None = None,
                  evidence: str | None = None, confidence: str = "medium",
                  db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT OR IGNORE INTO raw_lessons
                   (lesson_id, source, title, what_happened, lesson,
                    evidence, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (lesson_id, source, title, what_happened, lesson,
                 evidence, confidence, _NOW()),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_lessons(source: str | None = None, status: str | None = None,
                db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
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
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@_with_retry
def promote_lesson(lesson_id: str, promoted_to: str,
                   db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
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


def get_pending_lessons(db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        rows = c.execute(
            "SELECT * FROM raw_lessons WHERE status='draft' ORDER BY created_at DESC",
        ).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Sentinel functions ─────────────────────────────────────────────────────

@_with_retry
def set_sentinel(sentinel_key: str, sentinel_type: str, *,
                 expires_at: str | None = None,
                 db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
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
        r = c.execute("SELECT expires_at FROM raw_sentinels WHERE sentinel_key=?",
                      (sentinel_key,)).fetchone()
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
        with _connect(db_path) as c:
            n = c.execute(
                "DELETE FROM raw_sentinels WHERE expires_at IS NOT NULL AND expires_at < ?",
                (_NOW(),),
            ).rowcount
        return n
    except Exception as e:
        _reraise_if_busy(e)
        return 0


# ── Token usage functions ─────────────────────────────────────────────────

@_with_retry
def insert_token_usage(*, session_id: str | None = None, project_id: str | None = None,
                       skill_name: str | None = None, input_tokens: int = 0,
                       output_tokens: int = 0, model: str | None = None,
                       db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT INTO raw_token_usage
                   (session_id, project_id, skill_name, input_tokens,
                    output_tokens, model, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, project_id, skill_name, input_tokens,
                 output_tokens, model, _NOW()),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def get_token_summary(project_id: str | None = None, days: int = 7,
                      db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
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
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Schema introspection ───────────────────────────────────────────────────

def schema_version(db_path: Path | None = None) -> int:
    try:
        c = _connect(db_path)
        v = c.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
        c.close()
        return v
    except Exception:
        return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="studio_db CLI"); sub = ap.add_subparsers(dest="cmd")
    sc = sub.add_parser("skill-correct"); sc.add_argument("telemetry_id"); sc.add_argument("result", choices=["success","failure"]); sc.add_argument("--reason", default="")
    ib = sub.add_parser("import-and-rebuild"); ib.add_argument("--buffer", required=True)
    sub.add_parser("prune"); sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "skill-correct":
        print("corrected" if skill_correct(int(args.telemetry_id), 1 if args.result=="success" else 0, args.reason) else "error")
    elif args.cmd == "import-and-rebuild":
        n = import_buffer(Path(args.buffer)); rebuild_summaries(); print(f"imported {n} rows")
    elif args.cmd == "prune":
        print(f"pruned {rolling_window_prune()} rows")
    elif args.cmd == "status":
        c = _connect()
        tables = [
            "raw_workflow_runs", "raw_workflow_nodes", "raw_skill_telemetry",
            "cor_skill_corrections", "sum_skill_summary", "log_batch_imports",
            "raw_pulse_snapshots", "raw_planning_specs", "sum_analytics_run",
            "raw_operational_snapshots", "raw_approaches",
            "reg_skills", "reg_gotchas", "reg_workflows", "reg_skill_deps",
            "reg_projects", "raw_sessions", "raw_handoffs",
            "raw_specs", "raw_tasks", "raw_lessons",
            "raw_sentinels", "raw_token_usage",
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
    else: ap.print_help()

if __name__ == "__main__": main()
