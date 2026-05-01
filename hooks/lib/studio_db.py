"""SQLite analytics backend for dream-studio (WAL, prefixed schema, CLI)."""
from __future__ import annotations
import argparse, hashlib, json, sqlite3, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths  # noqa: E402

_DDL = """PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS raw_workflow_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_key TEXT NOT NULL UNIQUE, workflow TEXT NOT NULL, yaml_path TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, node_count INTEGER, nodes_done INTEGER);
CREATE TABLE IF NOT EXISTS raw_workflow_nodes (id INTEGER PRIMARY KEY AUTOINCREMENT, run_key TEXT NOT NULL REFERENCES raw_workflow_runs(run_key), node_id TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT, finished_at TEXT, duration_s REAL, output TEXT);
CREATE TABLE IF NOT EXISTS raw_skill_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, skill_name TEXT NOT NULL, invoked_at TEXT NOT NULL, model TEXT, input_tokens INTEGER, output_tokens INTEGER, success INTEGER NOT NULL, execution_time_s REAL);
CREATE TABLE IF NOT EXISTS cor_skill_corrections (id INTEGER PRIMARY KEY AUTOINCREMENT, telemetry_id INTEGER NOT NULL REFERENCES raw_skill_telemetry(id), corrected_success INTEGER NOT NULL, reason TEXT, corrected_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sum_skill_summary (skill_name TEXT PRIMARY KEY, times_used INTEGER, success_rate REAL, avg_input_tokens REAL, avg_output_tokens REAL, avg_exec_time_s REAL, last_success TEXT, last_failure TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS log_batch_imports (batch_id TEXT PRIMARY KEY, imported_at TEXT NOT NULL, row_count INTEGER NOT NULL);
CREATE VIEW IF NOT EXISTS effective_skill_runs AS SELECT t.id, t.skill_name, t.invoked_at, COALESCE(c.corrected_success, t.success) AS success, CASE WHEN c.id IS NOT NULL THEN 'corrected' ELSE 'heuristic' END AS signal_source, t.input_tokens, t.output_tokens, t.execution_time_s FROM raw_skill_telemetry t LEFT JOIN cor_skill_corrections c ON c.telemetry_id = t.id;
CREATE TABLE IF NOT EXISTS raw_pulse_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_date TEXT NOT NULL UNIQUE, health_score INTEGER NOT NULL, health_status TEXT NOT NULL, ci_status TEXT, open_prs INTEGER, stale_branches INTEGER, pending_drafts INTEGER, open_escalations INTEGER, raw_content TEXT);
CREATE TABLE IF NOT EXISTS raw_planning_specs (id INTEGER PRIMARY KEY AUTOINCREMENT, spec_path TEXT NOT NULL UNIQUE, title TEXT, created_date TEXT, task_count INTEGER, has_build_commit INTEGER DEFAULT 0, last_checked TEXT);
CREATE TABLE IF NOT EXISTS sum_analytics_run (id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL, pulse_rows INTEGER, spec_rows INTEGER, skill_rows INTEGER, output_path TEXT);
CREATE TABLE IF NOT EXISTS raw_operational_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_date TEXT NOT NULL, project_slug TEXT NOT NULL, ci_status TEXT, open_prs INTEGER, stale_branches INTEGER, pending_drafts INTEGER, open_escalations INTEGER, captured_at TEXT NOT NULL, UNIQUE(snapshot_date, project_slug));
CREATE TABLE IF NOT EXISTS raw_approaches (id INTEGER PRIMARY KEY AUTOINCREMENT, skill_id TEXT NOT NULL, session_date TEXT NOT NULL, approach TEXT NOT NULL, outcome TEXT NOT NULL, context TEXT, why_worked TEXT, tokens_used INTEGER, duration_s REAL, model TEXT, captured_at TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS vw_approach_patterns AS SELECT skill_id, approach, COUNT(*) AS times_tried, SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) AS successes, ROUND(CAST(SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) AS success_pct, CAST(AVG(tokens_used) AS INTEGER) AS avg_tokens, ROUND(AVG(duration_s), 1) AS avg_duration FROM raw_approaches GROUP BY skill_id, approach HAVING COUNT(*) >= 2;"""

_NOW = lambda: datetime.now(timezone.utc).isoformat()

def _db_path() -> Path: return paths.state_dir() / "studio.db"

def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or _db_path()), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn

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
    except Exception: return False

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
    except Exception: return 0

def rebuild_summaries(db_path: Path | None = None) -> None:
    try:
        with _connect(db_path) as c:
            c.executescript("""DELETE FROM sum_skill_summary;
INSERT INTO sum_skill_summary SELECT skill_name,COUNT(*),AVG(success),AVG(input_tokens),AVG(output_tokens),AVG(execution_time_s),MAX(CASE WHEN success=1 THEN invoked_at END),MAX(CASE WHEN success=0 THEN invoked_at END),datetime('now') FROM (SELECT * FROM effective_skill_runs WHERE skill_name IN (SELECT skill_name FROM raw_skill_telemetry GROUP BY skill_name HAVING COUNT(*)>=5) ORDER BY id DESC LIMIT 30) GROUP BY skill_name;""")
    except Exception: pass

def rolling_window_prune(db_path: Path | None = None) -> int:
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        with _connect(db_path) as c:
            d1 = c.execute("DELETE FROM raw_skill_telemetry WHERE id NOT IN (SELECT id FROM raw_skill_telemetry t2 WHERE t2.skill_name=raw_skill_telemetry.skill_name ORDER BY id DESC LIMIT 100)").rowcount
            d2 = c.execute("DELETE FROM raw_workflow_nodes WHERE run_key IN (SELECT run_key FROM raw_workflow_runs WHERE finished_at<?)", (cutoff,)).rowcount
            d3 = c.execute("DELETE FROM raw_workflow_runs WHERE finished_at<?", (cutoff,)).rowcount
            d4 = c.execute("DELETE FROM raw_approaches WHERE captured_at<?", (cutoff,)).rowcount
        return d1 + d2 + d3 + d4
    except Exception: return 0

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

def skill_correct(telemetry_id: int, success: int, reason: str = "", db_path: Path | None = None) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute("INSERT INTO cor_skill_corrections(telemetry_id,corrected_success,reason,corrected_at) VALUES(?,?,?,?)", (telemetry_id, success, reason, _NOW()))
        return True
    except Exception: return False

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
    except Exception:
        return False


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
    db_path: Path | None = None,
) -> bool:
    try:
        with _connect(db_path) as c:
            c.execute(
                """INSERT INTO raw_approaches
                   (skill_id, session_date, approach, outcome, context,
                    why_worked, tokens_used, duration_s, model, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (skill_id, session_date or _NOW()[:10], approach, outcome,
                 context or None, why or None, tokens_used, duration_s, model, _NOW()),
            )
        return True
    except Exception:
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
        c = _connect(); tables = ["raw_workflow_runs","raw_workflow_nodes","raw_skill_telemetry","cor_skill_corrections","sum_skill_summary","log_batch_imports","raw_pulse_snapshots","raw_planning_specs","sum_analytics_run","raw_operational_snapshots","raw_approaches"]
        print(f"{'Table':<30} {'Rows':>8}\n" + "-"*40)
        for t in tables: print(f"{t:<30} {c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>8}")  # noqa: S608
        c.close()
    else: ap.print_help()

if __name__ == "__main__": main()
