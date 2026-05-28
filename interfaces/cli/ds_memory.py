"""ds memory subcommands (Slice 5d) — session history and planning ingest."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────

_TRIGGER_RE = re.compile(
    r"(?:^|\n)(?:#{1,3}\s*)?(?P<keyword>What broke|Root cause|Fix|Prevention|Gotcha|GOTCHA)"
    r":\s*(?P<inline>[^\n]*)",
)

_DATE_IN_PATH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_ANYWHERE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

_SKILL_KEYWORDS: dict[str, list[str]] = {
    "ds-domains": ["canvas", "editor", "iframe", "breakpoint", "animation", "renderer", "viewport"],
    "ds-quality": ["test", "pytest", "coverage", "lint", "mock", "assertion", "fixture"],
    "ds-security": ["security", "auth", "injection", "xss", "csrf", "token", "password", "secret"],
    "ds-core": [
        "migration",
        "database",
        "sqlite",
        "schema",
        "handoff",
        "session",
        "plan",
        "deploy",
    ],
}

_SEVERITY_CRITICAL_RE = re.compile(
    r"\b(?:regression|broke production|production broke|production down)\b", re.IGNORECASE
)
_SEVERITY_HIGH_RE = re.compile(
    r"\b(?:blocked|failed ci|data loss|data corrupt|data corruption|cannot deploy)\b", re.IGNORECASE
)

_ARCH_PATTERNS = [
    "CONSTITUTION.md",
    "ADR-*.md",
    "ARCHITECTURE*.md",
    "*-ARCHITECTURE.md",
    "STATE-MANAGEMENT-ARCHITECTURE.md",
    "STYLING-ARCHITECTURE.md",
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _slugify(text: str, max_len: int = 60) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len]


def _infer_skill_id(text: str) -> str:
    text_lower = text.lower()
    for skill_id, keywords in _SKILL_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return skill_id
    return "ds-core"


def _infer_severity(text: str) -> str:
    if _SEVERITY_CRITICAL_RE.search(text):
        return "critical"
    if _SEVERITY_HIGH_RE.search(text):
        return "high"
    return "medium"


def _discover_date_from_path(path: Path) -> str:
    """Extract YYYY-MM-DD from the first path part matching that pattern, else use mtime."""
    for part in reversed(path.parts):
        if _DATE_IN_PATH_RE.match(part):
            return part
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except OSError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _extract_fix(text: str) -> str | None:
    """Return text after the first 'Fix:' marker in block, or None."""
    m = re.search(
        r"(?:^|\n)(?:#{1,3}\s*)?Fix:\s*(.+?)(?:\n\n|\n(?=(?:#{1,3}\s+)?\w+:)|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()[:1000]
    return None


def _find_gotcha_blocks(content: str, filename: str) -> list[dict]:
    """Extract gotcha blocks from file content.

    GOTCHAS.md: each ## heading is one gotcha.
    handoff/recap files: sections separated by --- that contain a trigger keyword.
    """
    blocks: list[dict] = []

    if filename == "GOTCHAS.md":
        # Split on ## headings; each heading is a gotcha entry
        sections = re.split(r"\n(?=## )", "\n" + content)
        for section in sections:
            lines = section.strip().splitlines()
            if not lines:
                continue
            first = lines[0].lstrip("#").strip()
            if not first or first.startswith("#"):
                continue
            blocks.append(
                {
                    "title": first[:120],
                    "context": section.strip(),
                    "fix": _extract_fix(section),
                }
            )
    else:
        # Split on horizontal-rule separators to get semantic sections
        sections = re.split(r"\n-{3,}\n", content)
        for section in sections:
            m = _TRIGGER_RE.search(section)
            if not m:
                continue
            keyword = m.group("keyword")
            inline = m.group("inline").strip()
            if inline:
                title = f"{keyword}: {inline}"
            else:
                # First non-empty line after the trigger
                rest_lines = [l.strip() for l in section[m.end() :].splitlines() if l.strip()]
                next_line = rest_lines[0] if rest_lines else ""
                title = f"{keyword}: {next_line}" if next_line else keyword
            blocks.append(
                {
                    "title": title[:120],
                    "context": section.strip(),
                    "fix": _extract_fix(section),
                }
            )

    return blocks


def _collect_handoff_recap_files(sessions_dir: Path, project: str | None) -> list[Path]:
    """Collect handoff-*.md, recap-*.md, and GOTCHAS.md from the sessions tree."""
    if not sessions_dir.exists():
        return []
    base = (sessions_dir / project) if project else sessions_dir
    if not base.exists():
        return []
    files: list[Path] = []
    for pattern in ("**/handoff-*.md", "**/recap-*.md", "**/GOTCHAS.md"):
        files.extend(base.glob(pattern))
    return files


def _collect_architecture_files(planning_dir: Path, project: str | None) -> list[Path]:
    """Collect architecture-related docs from planning_dir (deduplicated)."""
    base = (planning_dir / project) if (project and planning_dir.exists()) else planning_dir
    if not base.exists():
        return []
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in _ARCH_PATTERNS:
        for f in base.glob(f"**/{pattern}"):
            resolved = f.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(f)
    return files


def _find_latest_handoff(project_dir: Path) -> Path | None:
    """Find most recent handoff: latest YYYY-MM-DD subdir, alphabetically last file."""
    date_dirs = sorted(
        (d for d in project_dir.iterdir() if d.is_dir() and _DATE_IN_PATH_RE.match(d.name)),
        reverse=True,
    )
    for date_dir in date_dirs:
        handoffs = sorted(date_dir.glob("handoff-*.md"))
        if handoffs:
            return handoffs[-1]
    # Fallback: look directly in project_dir
    handoffs = sorted(project_dir.glob("handoff-*.md"))
    return handoffs[-1] if handoffs else None


def _find_reg_project_id(conn: sqlite3.Connection, dir_name: str) -> str | None:
    """Match project directory name against reg_projects by path or name."""
    row = conn.execute(
        "SELECT project_id FROM reg_projects"
        " WHERE project_path LIKE ? OR project_name = ? OR project_path = ?",
        (f"%{dir_name}%", dir_name, dir_name),
    ).fetchone()
    return row[0] if row else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pass 1: Gotcha extraction ─────────────────────────────────────────────────


def _pass1_gotchas(
    sessions_dir: Path,
    planning_dir: Path,
    project: str | None,
    conn: sqlite3.Connection | None,
    dry_run: bool,
) -> dict:
    files = _collect_handoff_recap_files(sessions_dir, project)
    # Also pick up GOTCHAS.md from planning_dir tree
    if planning_dir.exists():
        gotcha_files = (
            (planning_dir / project).glob("**/GOTCHAS.md")
            if project
            else planning_dir.glob("**/GOTCHAS.md")
        )
        for f in gotcha_files:
            if f not in files:
                files.append(f)

    new_count = 0
    skipped_count = 0

    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        discovered = _discover_date_from_path(path)
        blocks = _find_gotcha_blocks(content, path.name)

        for block in blocks:
            gotcha_id = _slugify(block["title"])
            if not gotcha_id:
                continue
            skill_id = _infer_skill_id(block["context"])
            severity = _infer_severity(block["context"])

            if conn is not None:
                exists = conn.execute(
                    "SELECT 1 FROM reg_gotchas WHERE gotcha_id = ?", (gotcha_id,)
                ).fetchone()
                if exists:
                    skipped_count += 1
                    continue

            if not dry_run and conn is not None:
                try:
                    conn.execute(
                        "INSERT INTO reg_gotchas"
                        " (gotcha_id, skill_id, severity, title, context, fix, discovered, times_hit)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                        (
                            gotcha_id,
                            skill_id,
                            severity,
                            block["title"],
                            block["context"],
                            block["fix"],
                            discovered,
                        ),
                    )
                except sqlite3.IntegrityError:
                    skipped_count += 1
                    continue

            new_count += 1

    return {"new": new_count, "skipped": skipped_count}


# ── Pass 2: Architecture decision extraction ──────────────────────────────────


def _pass2_architecture(
    planning_dir: Path,
    project: str | None,
    conn: sqlite3.Connection | None,
    dry_run: bool,
) -> dict:
    files = _collect_architecture_files(planning_dir, project)
    new_count = 0
    skipped_count = 0
    now = _now_iso()

    for path in files:
        source_path = str(path.resolve())

        if conn is not None:
            exists = conn.execute(
                "SELECT 1 FROM ds_documents WHERE source_path = ?", (source_path,)
            ).fetchone()
            if exists:
                skipped_count += 1
                continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        title = path.stem.replace("-", " ").replace("_", " ")

        project_id = None
        if conn is not None:
            if project:
                project_id = _find_reg_project_id(conn, project)
            else:
                # Try to infer project from path components
                for part in reversed(path.parts):
                    if part in ("planning", "sessions", ".planning", ".sessions"):
                        continue
                    pid = _find_reg_project_id(conn, part)
                    if pid:
                        project_id = pid
                        break

        try:
            mtime = path.stat().st_mtime
            created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            created_at = now

        if not dry_run and conn is not None:
            conn.execute(
                "INSERT INTO ds_documents"
                " (doc_type, project_id, title, content, source_path, created_at, updated_at)"
                " VALUES ('architecture_decision', ?, ?, ?, ?, ?, ?)",
                (project_id, title, content, source_path, created_at, now),
            )

        new_count += 1

    return {"new": new_count, "skipped": skipped_count}


# ── Pass 3: Session continuity extraction ─────────────────────────────────────


def _pass3_session_handoffs(
    sessions_dir: Path,
    project: str | None,
    conn: sqlite3.Connection | None,
    dry_run: bool,
) -> dict:
    if not sessions_dir.exists():
        return {"updated": 0}

    if project:
        candidate = sessions_dir / project
        project_dirs = [candidate] if candidate.is_dir() else []
    else:
        project_dirs = [d for d in sessions_dir.iterdir() if d.is_dir()]

    updated_count = 0
    now = _now_iso()

    for proj_dir in project_dirs:
        latest = _find_latest_handoff(proj_dir)
        if not latest:
            continue

        project_name = proj_dir.name
        title = f"Latest handoff — {project_name}"
        source_path = str(latest.resolve())

        try:
            content = latest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        project_id = None
        if conn is not None:
            project_id = _find_reg_project_id(conn, project_name)

        try:
            mtime = latest.stat().st_mtime
            created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            created_at = now

        if not dry_run and conn is not None:
            # Upsert: delete existing entry for this project, then insert fresh
            conn.execute(
                "DELETE FROM ds_documents WHERE doc_type = 'session_handoff' AND title = ?",
                (title,),
            )
            conn.execute(
                "INSERT INTO ds_documents"
                " (doc_type, project_id, title, content, source_path, created_at, updated_at)"
                " VALUES ('session_handoff', ?, ?, ?, ?, ?, ?)",
                (project_id, title, content, source_path, created_at, now),
            )

        updated_count += 1

    return {"updated": updated_count}


# ── Main entry point ──────────────────────────────────────────────────────────


def run_memory_ingest(
    *,
    sessions_dir: Path,
    planning_dir: Path,
    project: str | None,
    dry_run: bool,
    db_path: Path,
) -> dict:
    """Run all three extraction passes and return a summary report."""
    if not dry_run and not db_path.exists():
        raise RuntimeError(
            f"Dream Studio SQLite authority is missing at {db_path}. "
            "Run rehearsal-install first."
        )

    conn: sqlite3.Connection | None = None
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

    try:
        pass1 = _pass1_gotchas(sessions_dir, planning_dir, project, conn, dry_run)
        pass2 = _pass2_architecture(planning_dir, project, conn, dry_run)
        pass3 = _pass3_session_handoffs(sessions_dir, project, conn, dry_run)

        if conn is not None and not dry_run:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()

    total_rows = (pass1["new"] + pass2["new"] + pass3["updated"]) if not dry_run else 0

    return {
        "ok": True,
        "dry_run": dry_run,
        "gotchas": {"new": pass1["new"], "skipped": pass1["skipped"]},
        "architecture_docs": {"new": pass2["new"], "skipped": pass2["skipped"]},
        "session_handoffs": {"updated": pass3["updated"]},
        "total_rows_written": total_rows,
    }


# ── Parser registration ────────────────────────────────────────────────────────


def cmd_memory_ingest(args) -> int:
    """Entry point for `ds memory ingest`."""
    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else Path.home() / ".sessions"
    planning_dir = Path(args.planning_dir) if args.planning_dir else Path.home() / ".planning"

    try:
        from core.installed_runtime import resolve_installed_runtime_paths

        paths = resolve_installed_runtime_paths(source_root=REPO_ROOT, dream_studio_home=None)
        db_path = paths.sqlite_path
    except Exception:
        db_path = Path.home() / ".dream-studio" / "state" / "studio.db"

    project = getattr(args, "project", None)
    dry_run = getattr(args, "dry_run", False)

    try:
        result = run_memory_ingest(
            sessions_dir=sessions_dir,
            planning_dir=planning_dir,
            project=project,
            dry_run=dry_run,
            db_path=db_path,
        )
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


_CONSENT_TEXT = """\
Dream Studio will scan your Claude Code session history in:
  {claude_projects_dir}

It will extract derived metadata only:
  - Error->fix patterns (gotchas)
  - Skill invocation records
  - Architecture document paths (not content)
  - File type usage counts

Raw conversation content, prompts, assistant responses, and file contents
are NEVER stored.

Type 'yes' to proceed, or press Enter to cancel: """


def cmd_memory_ingest_sessions(args) -> int:
    """Entry point for `ds memory ingest-sessions`."""
    import os

    if args.claude_projects_dir:
        claude_projects_dir = Path(args.claude_projects_dir)
    else:
        if sys.platform == "win32":
            user_profile = os.environ.get("USERPROFILE", str(Path.home()))
            claude_projects_dir = Path(user_profile) / ".claude" / "projects"
        else:
            claude_projects_dir = Path.home() / ".claude" / "projects"

    dry_run: bool = getattr(args, "dry_run", False)
    no_consent_prompt: bool = getattr(args, "no_consent_prompt", False)

    if not no_consent_prompt:
        print(_CONSENT_TEXT.format(claude_projects_dir=claude_projects_dir), end="")
        try:
            answer = input()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
        if answer.strip().lower() != "yes":
            print("Cancelled.")
            return 0

    try:
        from core.installed_runtime import resolve_installed_runtime_paths

        paths = resolve_installed_runtime_paths(source_root=REPO_ROOT, dream_studio_home=None)
        db_path = paths.sqlite_path
    except Exception:
        db_path = Path.home() / ".dream-studio" / "state" / "studio.db"

    try:
        from spool.session_harvester import SessionHarvester

        harvester = SessionHarvester()
        result = harvester.harvest(
            claude_projects_dir=claude_projects_dir,
            db_path=db_path,
            dry_run=dry_run,
            consent=not dry_run,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    label = "[dry-run] " if dry_run else ""
    print(f"\n{label}Session harvest complete:")
    print(f"  Gotchas extracted:    {result.gotchas_new} new, {result.gotchas_skipped} skipped")
    print(
        f"  Skill approaches:     {result.approaches_new} new, {result.approaches_skipped} skipped"
    )
    print(f"  Architecture docs:    {result.arch_docs_found} found")
    print(f"  Technology signals:   {result.tech_signals_recorded} file types recorded")
    print(f"  Sessions processed:   {result.sessions_processed}")
    print(f"  Sessions skipped:     {result.sessions_skipped}")
    return 0


def cmd_memory_ingest_entries(args) -> int:
    """Entry point for `ds memory ingest-entries`.

    Syncs domain tables (reg_gotchas, raw_lessons, corrections, decisions) into
    memory_entries via run_all_ingestion(). Chain 7 prerequisite — populates the
    SQLite table queried by the on-context-inject hook.
    """
    dry_run = getattr(args, "dry_run", False)
    if dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "note": "dry-run: no changes written"}))
        return 0

    try:
        from core.memory.ingestion import run_all_ingestion
        from core.memory.store import MemoryStore

        store = MemoryStore()
        results = run_all_ingestion(store=store)
        summary = {
            "ok": True,
            "consumers": [
                {
                    "name": r.consumer_name,
                    "records_found": r.records_found,
                    "records_ingested": r.records_ingested,
                    "records_updated": r.records_updated,
                    "records_skipped": r.records_skipped,
                    "errors": r.errors,
                }
                for r in results
            ],
            "total_ingested": sum(r.records_ingested for r in results),
            "total_updated": sum(r.records_updated for r in results),
        }
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


def cmd_memory_ingest_status(args) -> int:
    """Entry point for `ds memory ingest-status`.

    Reads ~/.dream-studio/state/memory-ingest-last-run.json and prints the
    last automated ingestion run summary.
    """
    import os
    from pathlib import Path

    state_file = (
        Path(os.path.expanduser("~")) / ".dream-studio" / "state" / "memory-ingest-last-run.json"
    )
    if not state_file.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "No ingestion run recorded yet. Memory ingestion fires automatically at session end via the Stop hook.",
                }
            )
        )
        return 0

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": f"Could not read state file: {exc}"}), file=sys.stderr
        )
        return 1

    print(json.dumps(data, indent=2))
    return 0


def add_memory_subcommand(subparsers) -> None:
    """Register the 'memory' subcommand group onto the parent parser."""
    memory_parser = subparsers.add_parser("memory", help="Memory intelligence commands")
    memory_sub = memory_parser.add_subparsers(dest="memory_cmd", required=True)

    ingest = memory_sub.add_parser(
        "ingest", help="Ingest session history and planning files into SQLite"
    )
    ingest.add_argument("--project", default=None, help="Scope to a single project name")
    ingest.add_argument(
        "--sessions-dir",
        default=None,
        dest="sessions_dir",
        help="Override default ~/.sessions/ location",
    )
    ingest.add_argument(
        "--planning-dir",
        default=None,
        dest="planning_dir",
        help="Override default ~/.planning/ location",
    )
    ingest.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report what would be ingested without writing",
    )
    ingest.set_defaults(func=cmd_memory_ingest)

    ingest_sessions = memory_sub.add_parser(
        "ingest-sessions",
        help="Harvest intelligence from Claude Code session history in ~/.claude/projects/",
    )
    ingest_sessions.add_argument(
        "--claude-projects-dir",
        default=None,
        dest="claude_projects_dir",
        help="Override default ~/.claude/projects/ location",
    )
    ingest_sessions.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report counts without writing to DB",
    )
    ingest_sessions.add_argument(
        "--no-consent-prompt",
        action="store_true",
        default=False,
        dest="no_consent_prompt",
        help="Skip consent prompt (for automated testing only)",
    )
    ingest_sessions.set_defaults(func=cmd_memory_ingest_sessions)

    ingest_entries = memory_sub.add_parser(
        "ingest-entries",
        help="Sync reg_gotchas, raw_lessons, corrections, and decisions into memory_entries (Chain 7)",
    )
    ingest_entries.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report counts without writing to DB",
    )
    ingest_entries.set_defaults(func=cmd_memory_ingest_entries)

    ingest_status = memory_sub.add_parser(
        "ingest-status",
        help="Show last automated memory ingestion run (from ~/.dream-studio/state/memory-ingest-last-run.json)",
    )
    ingest_status.set_defaults(func=cmd_memory_ingest_status)
