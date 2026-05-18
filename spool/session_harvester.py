"""Session intelligence harvester for Dream Studio.

Extracts derived metadata from Claude Code JSONL session files in
~/.claude/projects/ and seeds the Dream Studio database.

Privacy guarantee: raw conversation content, prompts, assistant responses,
and file contents are NEVER stored. Only derived metadata is stored:
error patterns, skill usage, timestamps, tool types, technology signals,
and written architectural document paths.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


# ── Sanitization ──────────────────────────────────────────────────────────────

_PATH_RE = re.compile(r"[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]*|"
                      r"/(?:[^\s/]+/)*[^\s/]+")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_TOKEN_URL_RE = re.compile(r"https?://[^\s]*[?&](token|key|secret|auth)=[^\s&]+", re.IGNORECASE)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)


def _sanitize(text: str) -> str:
    """Remove personal data from text before storage."""
    text = _TOKEN_URL_RE.sub("[URL]", text)  # must run before _PATH_RE eats the URL path
    text = _PATH_RE.sub("[PATH]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _UUID_RE.sub("[UUID]", text)
    return text


# ── Architecture document patterns ────────────────────────────────────────────

_ARCH_SUFFIXES = frozenset([
    "CONSTITUTION.md",
    "GOTCHAS.md",
])
_ARCH_PREFIXES = frozenset(["ADR-", "ARCHITECTURE"])
_ARCH_CONTAINS = frozenset(["ARCHITECTURE"])


def _is_architecture_doc(path_str: str) -> bool:
    name = Path(path_str).name
    if name in _ARCH_SUFFIXES:
        return True
    for prefix in _ARCH_PREFIXES:
        if name.startswith(prefix) and name.endswith(".md"):
            return True
    return False


# ── JSONL parsing ─────────────────────────────────────────────────────────────

def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield parsed JSON objects from a JSONL file, skipping bad lines."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class HarvestResult:
    gotchas_new: int = 0
    gotchas_skipped: int = 0
    approaches_new: int = 0
    approaches_skipped: int = 0
    arch_docs_found: int = 0
    tech_signals_recorded: int = 0
    sessions_processed: int = 0
    sessions_skipped: int = 0


# ── Main harvester ────────────────────────────────────────────────────────────

class SessionHarvester:
    """
    Extracts intelligence from Claude Code JSONL session files in
    ~/.claude/projects/.

    Processes four signal types:
    1. Gotchas — error→fix cycles
    2. Skill invocations — Skill() tool call records
    3. Architecture documents — written doc file paths
    4. Technology signals — file extensions detected from tool calls

    Privacy guarantee: never stores raw content. Only stores derived metadata.
    """

    def harvest(
        self,
        claude_projects_dir: Path,
        db_path: Path,
        dry_run: bool = False,
        consent: bool = False,
    ) -> HarvestResult:
        """
        Main entry point.
        consent=False → count only, no DB writes.
        consent=True → write to DB.
        dry_run=True → report counts, no writes regardless of consent.
        """
        result = HarvestResult()

        if not claude_projects_dir.exists():
            return result

        # Collect all JSONL files
        jsonl_files = list(claude_projects_dir.rglob("*.jsonl"))
        if not jsonl_files:
            return result

        # Open DB if we will write
        conn: sqlite3.Connection | None = None
        if consent and not dry_run and db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            # Ensure migration 055 table exists
            conn.execute(
                "CREATE TABLE IF NOT EXISTS ds_technology_signals ("
                "  signal_id TEXT PRIMARY KEY,"
                "  extension TEXT NOT NULL,"
                "  count INTEGER NOT NULL DEFAULT 0,"
                "  last_seen TEXT NOT NULL"
                ")"
            )
            conn.commit()

        ext_counts: dict[str, int] = {}
        seen_approaches: set[tuple[str, str, str]] = set()

        try:
            for jsonl_path in jsonl_files:
                records = list(_iter_jsonl(jsonl_path))
                if not records:
                    result.sessions_skipped += 1
                    continue

                result.sessions_processed += 1
                session_id = _extract_session_id(records, jsonl_path)
                session_ts = _extract_session_timestamp(records, jsonl_path)

                # Process records sequentially to detect error→fix patterns
                self._process_records(
                    records=records,
                    session_id=session_id,
                    session_ts=session_ts,
                    conn=conn,
                    result=result,
                    ext_counts=ext_counts,
                    seen_approaches=seen_approaches,
                )

            # Write technology signals
            if ext_counts:
                result.tech_signals_recorded = len(ext_counts)
                if conn is not None:
                    _write_tech_signals(conn, ext_counts)

        finally:
            if conn is not None:
                conn.commit()
                conn.close()

        return result

    def _process_records(
        self,
        records: list[dict[str, Any]],
        session_id: str,
        session_ts: str,
        conn: sqlite3.Connection | None,
        result: HarvestResult,
        ext_counts: dict[str, int],
        seen_approaches: set[tuple[str, str, str]],
    ) -> None:
        for i, record in enumerate(records):
            msg_type = record.get("type", "")
            message = record.get("message", {})

            if msg_type == "user":
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            if item.get("is_error"):
                                # Error found — look for fix in next 3 assistant messages
                                error_text = _extract_error_text(item)
                                fix_type = _find_fix_in_next(records, i + 1, 4)
                                if fix_type and error_text:
                                    self._record_gotcha(
                                        error_text=error_text,
                                        fix_type=fix_type,
                                        session_ts=session_ts,
                                        records=records,
                                        idx=i,
                                        conn=conn,
                                        result=result,
                                    )

            elif msg_type == "assistant":
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            continue
                        item_type = item.get("type", "")
                        name = item.get("name", "")

                        if item_type == "tool_use":
                            # Skill invocations
                            if name == "Skill":
                                self._record_approach(
                                    item=item,
                                    session_id=session_id,
                                    session_ts=session_ts,
                                    message=message,
                                    conn=conn,
                                    result=result,
                                    seen_approaches=seen_approaches,
                                )

                            # Architecture document writes
                            if name in ("Write", "Create", "str_replace_editor"):
                                file_path = _extract_file_path(item)
                                if file_path and _is_architecture_doc(file_path):
                                    self._record_arch_doc(
                                        file_path=file_path,
                                        conn=conn,
                                        result=result,
                                    )

                            # Technology signals
                            file_path = _extract_file_path(item)
                            if file_path:
                                ext = Path(file_path).suffix.lower()
                                if ext and len(ext) <= 10:
                                    ext_counts[ext] = ext_counts.get(ext, 0) + 1

    def _record_gotcha(
        self,
        error_text: str,
        fix_type: str,
        session_ts: str,
        records: list[dict[str, Any]],
        idx: int,
        conn: sqlite3.Connection | None,
        result: HarvestResult,
    ) -> None:
        sanitized = _sanitize(error_text[:200])
        gotcha_id = hashlib.sha256(sanitized.encode()).hexdigest()[:32]

        if conn is not None:
            exists = conn.execute(
                "SELECT 1 FROM reg_gotchas WHERE gotcha_id = ?", (gotcha_id,)
            ).fetchone()
            if exists:
                result.gotchas_skipped += 1
                return

            severity = _infer_error_severity(sanitized)
            skill_id = _infer_skill_from_context(records, idx)
            title = sanitized.splitlines()[0][:120] if sanitized else "Unknown error"

            try:
                conn.execute(
                    "INSERT INTO reg_gotchas"
                    " (gotcha_id, skill_id, severity, title, context, fix, discovered, times_hit)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                    (gotcha_id, skill_id, severity, title, sanitized, fix_type, session_ts),
                )
                result.gotchas_new += 1
            except sqlite3.IntegrityError:
                result.gotchas_skipped += 1
        else:
            result.gotchas_new += 1

    def _record_approach(
        self,
        item: dict[str, Any],
        session_id: str,
        session_ts: str,
        message: dict[str, Any],
        conn: sqlite3.Connection | None,
        result: HarvestResult,
        seen_approaches: set[tuple[str, str, str]],
    ) -> None:
        inp = item.get("input", {})
        skill_id = inp.get("skill", "")
        mode = (inp.get("args", "") or "").split()[0] if inp.get("args") else ""
        if not skill_id:
            return

        key = (skill_id, mode, session_id)
        if key in seen_approaches:
            result.approaches_skipped += 1
            return
        seen_approaches.add(key)

        if conn is not None:
            try:
                approach_id = hashlib.sha256(
                    f"{skill_id}:{mode}:{session_id}".encode()
                ).hexdigest()[:32]
                model = message.get("model", "")
                conn.execute(
                    "INSERT OR IGNORE INTO raw_approaches"
                    " (approach_id, skill_id, approach, model, project_id, created_at)"
                    " VALUES (?, ?, ?, ?, NULL, ?)",
                    (approach_id, skill_id, mode or "default", model, session_ts),
                )
                result.approaches_new += 1
            except sqlite3.Error:
                result.approaches_skipped += 1
        else:
            result.approaches_new += 1

    def _record_arch_doc(
        self,
        file_path: str,
        conn: sqlite3.Connection | None,
        result: HarvestResult,
    ) -> None:
        result.arch_docs_found += 1
        if conn is not None:
            abs_path = file_path
            try:
                exists = conn.execute(
                    "SELECT 1 FROM ds_documents WHERE source_path = ?", (abs_path,)
                ).fetchone()
                if not exists:
                    doc_id = hashlib.sha256(abs_path.encode()).hexdigest()[:32]
                    title = Path(abs_path).stem
                    conn.execute(
                        "INSERT OR IGNORE INTO ds_documents"
                        " (doc_id, doc_type, title, content, source_path, created_at)"
                        " VALUES (?, ?, ?, NULL, ?, ?)",
                        (doc_id, "architecture_decision", title, abs_path,
                         datetime.now(timezone.utc).isoformat()),
                    )
            except sqlite3.Error:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_session_id(records: list[dict], path: Path) -> str:
    for r in records:
        sid = r.get("sessionId") or r.get("session_id")
        if sid:
            return str(sid)
    return path.stem


def _extract_session_timestamp(records: list[dict], path: Path) -> str:
    for r in records:
        ts = r.get("timestamp")
        if ts:
            return str(ts)
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return datetime.now(timezone.utc).isoformat()


def _extract_error_text(item: dict[str, Any]) -> str:
    content = item.get("content", "")
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text", ""))
            elif isinstance(c, str):
                parts.append(c)
        return " ".join(parts).strip()[:500]
    return str(content)[:500]


def _find_fix_in_next(records: list[dict], start: int, count: int) -> str | None:
    """Look at the next `count` records for a fix signal."""
    checked = 0
    for i in range(start, min(start + count * 3, len(records))):
        if checked >= count:
            break
        r = records[i]
        if r.get("type") != "assistant":
            continue
        checked += 1
        content = r.get("message", {}).get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    name = item.get("name", "")
                    if name in ("Write", "Edit", "Create", "str_replace_editor"):
                        return "file_write"
                    if name == "Bash":
                        return "bash"
    return None


def _extract_file_path(item: dict[str, Any]) -> str | None:
    inp = item.get("input", {})
    if not isinstance(inp, dict):
        return None
    for key in ("file_path", "path", "filename", "target"):
        val = inp.get(key)
        if val and isinstance(val, str):
            return val
    # For str_replace_editor / code edits
    return inp.get("new_string", None) and None  # don't use content as path


def _infer_error_severity(text: str) -> str:
    lower = text.lower()
    if "traceback" in lower or "exception" in lower:
        return "critical"
    if "error" in lower:
        return "high"
    return "medium"


def _infer_skill_from_context(records: list[dict], idx: int) -> str:
    # Look backward for nearby Skill() calls
    for i in range(max(0, idx - 5), idx):
        r = records[i]
        if r.get("type") == "assistant":
            content = r.get("message", {}).get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("name") == "Skill":
                        return item.get("input", {}).get("skill", "ds-core")
    return "ds-core"


def _write_tech_signals(conn: sqlite3.Connection, ext_counts: dict[str, int]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for ext, count in ext_counts.items():
        signal_id = hashlib.sha256(ext.encode()).hexdigest()[:32]
        conn.execute(
            "INSERT INTO ds_technology_signals (signal_id, extension, count, last_seen)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(signal_id) DO UPDATE SET"
            " count = count + excluded.count, last_seen = excluded.last_seen",
            (signal_id, ext, count, now),
        )
