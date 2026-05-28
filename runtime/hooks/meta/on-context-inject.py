#!/usr/bin/env python3
"""Hook: on-context-inject — inject relevant SQLite memory_entries before prompt processing.

Chain 7 (Memory Loop) closure — 18.4.4.

This hook complements on-memory-retrieve.py (file-based memory). Both run
independently under UserPromptSubmit via on-prompt-dispatch.py HANDLERS list.
Each writes its own XML block to stdout. No coordination between them.

  on-memory-retrieve.py  → searches file-based ~/.dream-studio/memory/
  on-context-inject.py   → searches SQLite memory_entries (this file)

Memory_entries sources: reg_gotchas (cross-project, project=NULL),
raw_lessons (project-specific), raw_approaches (project-specific).
Gotchas with project=NULL are included in all project-scoped queries
because they are cross-project by design.

Output format: <project-memory> XML block, plain text, stdout.
No additionalContext JSON — hooks write stdout, not hookSpecificOutput.

Failure mode: fail-open. Any error produces empty output. Never blocks prompt.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

# ── Configuration defaults (overridden by config.yml if present) ───────────
_CFG_ENABLED = True
_CFG_MAX_PER_INJECT = 3
_CFG_MAX_PER_SESSION = 50
_CFG_MIN_SCORE = 0.0  # placeholder — calibrate after first real data run
_CFG_DEDUP = True
_CFG_TIMEOUT_MS = 800


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _load_config() -> dict:
    """Load intelligence_surfacing section from config.yml. Fail-open."""
    try:
        import yaml  # optional dep — not always present

        cfg_path = _PLUGIN_ROOT / "config.yml"
        if cfg_path.is_file():
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            return data.get("intelligence_surfacing", {})
    except Exception:
        pass
    return {}


def _get_db_path() -> Optional[Path]:
    """Resolve Dream Studio SQLite path. Fail-open."""
    try:
        override = os.environ.get("DREAM_STUDIO_DB_PATH")
        if override:
            return Path(override)
        return Path.home() / ".dream-studio" / "state" / "studio.db"
    except Exception:
        return None


def _resolve_active_project(conn: sqlite3.Connection) -> Optional[str]:
    """Return active project_id or None if not found."""
    try:
        row = conn.execute(
            "SELECT project_id FROM business_projects"
            " WHERE status='active' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _fts_query(prompt: str) -> str:
    """Convert a free-text prompt into an FTS5 OR query.

    FTS5 default is AND semantics: "modal dialog focus" requires all three.
    For a relevance hook we want OR semantics so any matching term surfaces
    a memory. We extract meaningful words (length > 2, alpha-only) and join
    them as quoted token ORs: '"modal" OR "focus" OR "inert"'.

    Limited to 12 terms to avoid FTS5 query complexity limits.
    """
    import re

    words = re.findall(r"[a-zA-Z]{3,}", prompt)
    # Deduplicate while preserving order; skip common stop words.
    _STOP = {
        "the",
        "and",
        "for",
        "are",
        "not",
        "but",
        "was",
        "has",
        "had",
        "can",
        "will",
        "this",
        "that",
        "with",
        "from",
        "use",
        "need",
        "you",
        "your",
        "our",
        "its",
        "all",
        "how",
        "when",
        "what",
        "which",
        "who",
        "get",
        "set",
        "run",
        "add",
    }
    seen: set[str] = set()
    terms: list[str] = []
    for w in words:
        lower = w.lower()
        if lower not in _STOP and lower not in seen:
            seen.add(lower)
            terms.append(lower)
        if len(terms) >= 12:
            break
    if not terms:
        return prompt  # fallback to raw prompt
    return " OR ".join(f'"{t}"' for t in terms)


def _search_memories(
    conn: sqlite3.Connection,
    prompt: str,
    project_id: Optional[str],
    max_results: int,
    min_score: float,
    dedup: bool,
) -> list[dict]:
    """FTS5 search over memory_entries with project + dedup filtering.

    NULL-project entries (gotchas, signals) are included for all queries
    because they are cross-project by design — see GotchaIngestionConsumer.

    FTS5 rank is negative (more negative = better match). Score =
    abs(rank) * importance so higher importance memories rank higher on
    equal FTS match quality.
    """
    try:
        params: list = [_fts_query(prompt)]

        project_clause = ""
        if project_id is not None:
            # Include NULL-project entries (cross-project gotchas) for all queries.
            project_clause = "AND (me.project = ? OR me.project IS NULL)"
            params.append(project_id)

        dedup_clause = ""
        if dedup:
            # Exclude entries surfaced in the last 24 hours (proxy for "current session").
            # Hooks spawn fresh processes per invocation so in-memory dedup isn't viable.
            dedup_clause = (
                "AND (me.intelligence_surfaced_at IS NULL"
                " OR me.intelligence_surfaced_at < datetime('now', '-24 hours'))"
            )

        params.append(max_results)

        rows = conn.execute(
            f"""
            SELECT me.memory_id, me.content, me.project, me.skill,
                   me.importance, me.category, me.tags,
                   fts.rank
            FROM memory_fts fts
            JOIN memory_entries me ON me.memory_id = fts.memory_id
            WHERE memory_fts MATCH ?
              {project_clause}
              {dedup_clause}
            ORDER BY (fts.rank * -1.0) * me.importance DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        results = []
        for row in rows:
            score = abs(float(row[7])) * float(row[4])  # abs(rank) * importance
            if score < min_score:
                continue
            results.append(
                {
                    "memory_id": row[0],
                    "content": row[1],
                    "project": row[2],
                    "skill": row[3],
                    "importance": row[4],
                    "category": row[5],
                    "score": score,
                }
            )
        return results
    except Exception:
        return []


def _stamp_surfaced(conn: sqlite3.Connection, memory_ids: list[str], now: str) -> None:
    """Mark entries as surfaced in this session (best-effort, non-blocking)."""
    try:
        conn.executemany(
            "UPDATE memory_entries SET intelligence_surfaced_at = ? WHERE memory_id = ?",
            [(now, mid) for mid in memory_ids],
        )
        conn.commit()
    except Exception:
        pass


def _format_output(results: list[dict], total_matches: int) -> str:
    """Format results as plain-text XML block safe for prompt injection.

    Mirrors the on-memory-retrieve.py <relevant-context> pattern.
    No nested JSON, no code blocks, no tool-call-shaped structures.
    """
    if not results:
        return ""

    importance_label = {
        True: "high",  # importance >= 0.8
        False: None,
    }

    lines = ["<project-memory>"]
    lines.append("Prior lessons and gotchas relevant to this project:")
    lines.append("")
    for r in results:
        imp = r["importance"]
        if imp >= 0.8:
            label = "high"
        elif imp >= 0.5:
            label = "medium"
        else:
            label = "low"
        # Truncate long content to ~120 chars for context budget discipline
        content = r["content"].replace("\n", " ").strip()
        if len(content) > 120:
            content = content[:117] + "..."
        skill_hint = f" (skill: {r['skill']})" if r["skill"] else ""
        lines.append(f"- [{label}]{skill_hint} {content}")

    shown = len(results)
    if total_matches > shown:
        lines.append("")
        lines.append(
            f"({shown} of {total_matches} matching memories shown, top by relevance x importance)"
        )

    lines.append("</project-memory>")
    return "\n".join(lines)


def main(payload: dict) -> None:
    t_start = time.monotonic()

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return

    cfg = _load_config()
    if not cfg.get("enabled", _CFG_ENABLED):
        return

    max_per_inject = int(cfg.get("max_memory_entries_per_inject", _CFG_MAX_PER_INJECT))
    min_score = float(cfg.get("min_relevance_score", _CFG_MIN_SCORE))
    dedup = bool(cfg.get("dedupe_within_session", _CFG_DEDUP))

    db_path = _get_db_path()
    if db_path is None or not db_path.exists():
        return

    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    session_start = payload.get("session_id")  # use as dedup anchor if present

    try:
        conn = sqlite3.connect(str(db_path), timeout=0.8)
        conn.row_factory = sqlite3.Row
    except Exception:
        return

    try:
        # Timeout guard: if we're past 750ms, bail out early.
        if (time.monotonic() - t_start) * 1000 > 750:
            return

        project_id = _resolve_active_project(conn)

        results = _search_memories(
            conn=conn,
            prompt=prompt,
            project_id=project_id,
            max_results=max_per_inject + 5,  # fetch extra to count total before trimming
            min_score=min_score,
            dedup=dedup,
        )

        if not results:
            return

        total_matches = len(results)
        results = results[:max_per_inject]

        output = _format_output(results, total_matches)
        if not output:
            return

        # Stamp surfaced entries for dedup.
        if dedup:
            _stamp_surfaced(conn, [r["memory_id"] for r in results], now)

        # Log injection to diagnostics (non-blocking).
        try:
            from core.telemetry.debug import debug

            debug(
                "on-context-inject",
                f"Injected {len(results)} memories (project={project_id}, prompt_len={len(prompt)})",
            )
        except Exception:
            pass

        print(output, flush=True)

    except Exception:
        pass  # Fail-open: any error produces empty output, never blocks prompt
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        main(data)
    except Exception:
        pass
