"""ds memory ingest — session/planning gotcha, architecture, and handoff extraction.

Split from interfaces/cli/ds_memory.py (WO-GF-CLI-split). This module owns the
`ds memory ingest` implementation: the three extraction passes (gotchas,
architecture decisions, session handoffs) and their shared helpers/constants.
`ds_memory_sessions.py` imports ``REPO_ROOT`` from here for the (separate)
`ds memory ingest-sessions` command.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, UTC
from pathlib import Path


# Deferred import: avoid heavy top-level cost when ds_memory is imported as a CLI module.
def _connect_docs() -> sqlite3.Connection:
    """Open a connection to files.db with ds_documents schema ensured."""
    from core.files.store import connect_files, ensure_files_schema
    from core.storage.document_store import ensure_documents_schema

    conn = connect_files()
    ensure_files_schema(conn)
    ensure_documents_schema(conn)
    return conn


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
        return datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
    except OSError:
        return datetime.now(UTC).strftime("%Y-%m-%d")


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


def _find_project_id(conn: sqlite3.Connection, dir_name: str) -> str | None:
    """Match project directory name against business_projects by path or name."""
    row = conn.execute(
        "SELECT project_id FROM business_projects"
        " WHERE project_path LIKE ? OR name = ? OR project_path = ?",
        (f"%{dir_name}%", dir_name, dir_name),
    ).fetchone()
    return row[0] if row else None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Pass 1: Gotcha extraction ─────────────────────────────────────────────────


def _docstore_gotcha_sources(project: str | None) -> list[tuple[Path, str]]:
    """GOTCHAS.md entries from the files.db docstore as (pseudo-path, content) pairs.

    WO-FILESDB-P3: .planning working state (incl. GOTCHAS.md) lives in the docstore
    (category 'planning', name = path relative to .planning). The pseudo-path is that
    relative name, so _discover_date_from_path / .name behave as they did for disk files.
    """
    from core.files.store import list_files, read_file_by_name

    out: list[tuple[Path, str]] = []
    for row in list_files(category="planning"):
        name = row["name"]
        if not name.endswith("GOTCHAS.md"):
            continue
        if project and not name.startswith(f"{project}/"):
            continue
        try:
            full = read_file_by_name(name)
        except KeyError:
            continue
        content = full["content"]
        text = (
            content.decode("utf-8", "replace")
            if isinstance(content, (bytes, bytearray))
            else str(content)
        )
        out.append((Path(name), text))
    return out


def _pass1_gotchas(
    sessions_dir: Path,
    planning_dir: Path,
    project: str | None,
    conn: sqlite3.Connection | None,
    dry_run: bool,
) -> dict:
    # (source-label, content) pairs. Session handoff/recap files stay on disk
    # (sessions_dir is ~/.dream-studio/.sessions, not .planning).
    sources: list[tuple[Path, str]] = []
    for f in _collect_handoff_recap_files(sessions_dir, project):
        try:
            sources.append((f, f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue

    # GOTCHAS.md now lives in the files.db docstore; read from there, then fall back to
    # any .planning disk files not yet migrated (transition — removed in S4).
    seen: set[str] = set()
    for label, content in _docstore_gotcha_sources(project):
        seen.add(label.as_posix())
        sources.append((label, content))
    if planning_dir.exists():
        disk_gotchas = (
            (planning_dir / project).glob("**/GOTCHAS.md")
            if project
            else planning_dir.glob("**/GOTCHAS.md")
        )
        for f in disk_gotchas:
            try:
                rel = f.relative_to(planning_dir).as_posix()
            except ValueError:
                rel = f.name
            if rel in seen:
                continue
            try:
                sources.append((Path(rel), f.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue

    new_count = 0
    skipped_count = 0

    for path, content in sources:
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
    docs_conn: sqlite3.Connection | None = None,
) -> dict:
    files = _collect_architecture_files(planning_dir, project)
    new_count = 0
    skipped_count = 0
    now = _now_iso()

    for path in files:
        source_path = str(path.resolve())

        if docs_conn is not None:
            exists = docs_conn.execute(
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
                project_id = _find_project_id(conn, project)
            else:
                # Try to infer project from path components
                for part in reversed(path.parts):
                    if part in ("planning", "sessions", ".planning", ".sessions"):
                        continue
                    pid = _find_project_id(conn, part)
                    if pid:
                        project_id = pid
                        break

        try:
            mtime = path.stat().st_mtime
            created_at = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
        except OSError:
            created_at = now

        if not dry_run and docs_conn is not None:
            docs_conn.execute(
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
    docs_conn: sqlite3.Connection | None = None,
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
            project_id = _find_project_id(conn, project_name)

        try:
            mtime = latest.stat().st_mtime
            created_at = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
        except OSError:
            created_at = now

        if not dry_run and docs_conn is not None:
            # Upsert: delete existing entry for this project, then insert fresh
            docs_conn.execute(
                "DELETE FROM ds_documents WHERE doc_type = 'session_handoff' AND title = ?",
                (title,),
            )
            docs_conn.execute(
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

    # studio.db connection for authority reads (reg_gotchas, business_projects)
    conn: sqlite3.Connection | None = None
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

    # files.db connection for ds_documents reads/writes (three-store arch)
    docs_conn: sqlite3.Connection | None = None
    if not dry_run:
        try:
            docs_conn = _connect_docs()
        except Exception:
            pass  # docs writes are optional; degrade gracefully

    try:
        pass1 = _pass1_gotchas(sessions_dir, planning_dir, project, conn, dry_run)
        pass2 = _pass2_architecture(planning_dir, project, conn, dry_run, docs_conn)
        pass3 = _pass3_session_handoffs(sessions_dir, project, conn, dry_run, docs_conn)

        if conn is not None and not dry_run:
            conn.commit()
        if docs_conn is not None and not dry_run:
            docs_conn.commit()
    finally:
        if conn is not None:
            conn.close()
        if docs_conn is not None:
            docs_conn.close()

    total_rows = (pass1["new"] + pass2["new"] + pass3["updated"]) if not dry_run else 0

    return {
        "ok": True,
        "dry_run": dry_run,
        "gotchas": {"new": pass1["new"], "skipped": pass1["skipped"]},
        "architecture_docs": {"new": pass2["new"], "skipped": pass2["skipped"]},
        "session_handoffs": {"updated": pass3["updated"]},
        "total_rows_written": total_rows,
    }


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
