"""Attribute historical AI events to a project, from session evidence only.

Lives under core/event_store/ rather than core/telemetry/ because it MUTATES
ai_canonical_events. test_state_contract_boundaries forbids telemetry modules
from writing to the canonical event tables, and that boundary is right:
telemetry produces events, the event store owns them. A backfill is event-store
maintenance, not telemetry.

Migration 156 added ai_canonical_events.project_id. Every row written before it
has the column NULL, so all historical AI spend aggregates across every client at
once — SeayInsights, Fulcrum and Hypershift inflating one another.

The evidence is the Claude Code transcript layout, NOT anything in the database.

Two in-database sources look usable and are not:

  * raw_claude_code_events.project_id — a UUID value here is the GLOBALLY-ACTIVE
    project at write time, the same defect this change exists to fix. Rows naming
    the Fulcrum project begin on 2026-07-23, the exact day that project was
    created, and then dominate every session through today INCLUDING sessions
    doing nothing but Dream Studio work. A backfill built on it attributed
    $19,405 of Dream Studio spend to the Fulcrum engagement before a spot-check
    caught it. Directory-slug values in the same column ARE trustworthy, but only
    88 sessions carry one.
  * event payloads — Dream Studio deliberately does not retain tool arguments or
    prompt text (raw_retained / args_retained / contents_retained are all false),
    so there is no content to classify. Exactly 2 rows in 418k carry a file_path.

What does work: Claude Code writes each session transcript under a directory whose
name encodes the working directory it ran in
(``C--Users-Example-User-builds-dream-studio-clean``), and every transcript entry
carries a uuid that token.consumed events are derived from. So

    token event_id  ->  transcript entry uuid  ->  transcript file
                    ->  its directory          ->  the cwd

is exact: the directory IS where the work happened, recorded by the harness
rather than inferred. Measured on the live store: 68,276 of 68,457 token events
(99.7%) resolve this way.

The operator's classification rule maps a cwd to a client:

    ...\\Fulcrum\\...     -> fulcrum
    ...\\Hypershift\\...  -> hypershift
    ...\\builds\\...      -> seayinsights

A project is assigned by longest-prefix match against business_projects.
project_path, so Fulcrum subdirectories land on the Fulcrum project registered at
its root. A cwd under no registered project is left NULL rather than guessed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

#: Path segments that name a client, checked as whole directory components so
#: "rebuilds" never matches "builds". Order matters only in that the first hit
#: wins; a path under Fulcrum is Fulcrum work even if it also sits under builds.
_CLIENT_BY_SEGMENT: tuple[tuple[str, str], ...] = (
    ("fulcrum", "fulcrum"),
    ("hypershift", "hypershift"),
    ("builds", "seayinsights"),
)

SEP = "\\"


def _resolve_db(db_path: Path | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    from core.config.database import db_path as default_db_path

    return Path(default_db_path())


def _transcript_root() -> Path:
    return Path.home() / ".claude" / "projects"


def decode_transcript_dir(name: str) -> str:
    """Recover an approximate cwd from a Claude Code transcript directory name.

    ``C--Users-Example-User-builds-dream-studio-clean`` was produced by replacing
    the path separators and the drive colon with dashes. The mapping is lossy —
    a directory whose own name contains a dash is indistinguishable from a
    separator — which is why this is used ONLY to read whole path segments for
    client classification, never to reconstruct an exact path.
    """
    return name.replace("--", ":" + SEP, 1).replace("-", SEP)


def classify_client(cwd: str) -> str:
    """Apply the operator's rule.

        ...\\Fulcrum\\...     -> fulcrum
        ...\\Hypershift\\...  -> hypershift
        everything else       -> seayinsights

    Named engagements are opt-IN and everything else is internal work, so the
    default is seayinsights rather than None. That matters for directories that
    are neither under builds nor under an engagement — ``~/round-table/*`` alone
    accounts for ~1.5k events a day — which would otherwise fall out of every
    client total and make the numbers quietly incomplete.

    Segments are compared whole, so "rebuilds" never matches "builds".
    """
    segments = {s for s in cwd.replace("/", SEP).lower().split(SEP) if s}
    for segment, client_id in _CLIENT_BY_SEGMENT:
        if segment in segments:
            return client_id
    return "seayinsights"


def _index_transcripts() -> tuple[dict[str, str], dict[str, int]]:
    """Map every transcript entry uuid -> the cwd its transcript ran in.

    This is the one trustworthy record of where work happened: Claude Code wrote
    the directory name itself at the time, so it cannot drift the way an
    "active project" pointer does.
    """
    root = _transcript_root()
    uuid_to_cwd: dict[str, str] = {}
    per_cwd: dict[str, int] = {}
    if not root.is_dir():
        return uuid_to_cwd, per_cwd
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        # The directory NAME is kept verbatim: it is matched against encoded
        # project paths, and only decoded for whole-segment client classification.
        cwd = directory.name
        for transcript in directory.glob("*.jsonl"):
            try:
                text = transcript.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(entry, dict):
                    uid = entry.get("uuid")
                    if uid:
                        uuid_to_cwd[str(uid)] = cwd
                        per_cwd[cwd] = per_cwd.get(cwd, 0) + 1
    return uuid_to_cwd, per_cwd


def encode_cwd(path: str) -> str:
    """Encode a real path the way Claude Code names its transcript directory.

    ``C:\\Users\\Example User\\builds\\dream-studio-clean``
      -> ``c--users-example-user-builds-dream-studio-clean``

    Matching is done in THIS direction, never by decoding the directory name.
    Decoding is lossy — every dash becomes a separator, so "Example User" and
    "dream-studio-clean" both shatter — and a lossy decode matched no project at
    all. Encoding is exact because it is the same transformation Claude Code
    applied in the first place.
    """
    out = str(path).strip().rstrip("\\/")
    for ch in (":", "\\", "/", " "):
        out = out.replace(ch, "-")
    return out.lower()


def _project_roots(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(encoded project_path, project_id), longest first so subdirectories match
    the deepest registered project rather than an ancestor."""
    roots: list[tuple[str, str]] = []
    for project_id, project_path in conn.execute(
        "SELECT project_id, project_path FROM business_projects"
        " WHERE project_path IS NOT NULL AND status != 'deleted'"
    ):
        encoded = encode_cwd(str(project_path))
        if encoded:
            roots.append((encoded, project_id))
    roots.sort(key=lambda r: -len(r[0]))
    return roots


def _project_for_dir(dir_name: str, roots: list[tuple[str, str]]) -> str | None:
    """Match a transcript directory name against encoded project paths.

    A Fulcrum subdirectory such as ``c--users-example-user-fulcrum-demo`` starts
    with the encoded Fulcrum root, so it lands on the Fulcrum project.
    """
    low = dir_name.strip().lower()
    for root, project_id in roots:
        if low == root or low.startswith(root + "-"):
            return project_id
    return None


def backfill_ai_event_projects(
    *, db_path: Path | None = None, dry_run: bool = True
) -> dict[str, Any]:
    """Attribute AI events to the project whose directory produced them.

    With dry_run=True (the default) nothing is written, so the outcome can be
    inspected first — which is how an earlier, wrong attribution was caught.
    """
    db = _resolve_db(db_path)
    uuid_to_cwd, per_cwd = _index_transcripts()
    if not uuid_to_cwd:
        return {
            "ok": False,
            "error": f"no transcripts found under {_transcript_root()}",
        }

    conn = sqlite3.connect(str(db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(ai_canonical_events)")}
        if "project_id" not in cols:
            return {
                "ok": False,
                "error": "ai_canonical_events.project_id is missing — apply migration 156 first",
            }

        roots = _project_roots(conn)
        cwd_to_project = {d: _project_for_dir(d, roots) for d in per_cwd}

        rows = conn.execute(
            "SELECT event_id FROM ai_canonical_events WHERE project_id IS NULL"
        ).fetchall()

        before = len(rows)
        updates: list[tuple[str, str]] = []
        unmatched = 0
        no_project = 0
        by_client: dict[str, int] = {}
        for (event_id,) in rows:
            key = event_id[4:] if str(event_id).startswith("tok-") else str(event_id)
            cwd = uuid_to_cwd.get(key)
            if cwd is None:
                unmatched += 1
                continue
            project_id = cwd_to_project.get(cwd)
            if not project_id:
                no_project += 1
                continue
            updates.append((project_id, event_id))
            client = classify_client(decode_transcript_dir(cwd))
            by_client[client] = by_client.get(client, 0) + 1

        if updates:
            conn.executemany(
                "UPDATE ai_canonical_events SET project_id = ?"
                " WHERE event_id = ? AND project_id IS NULL",
                updates,
            )
            if dry_run:
                conn.rollback()
            else:
                conn.commit()

        per_project: dict[str, int] = {}
        for project_id, _ in updates:
            per_project[project_id] = per_project.get(project_id, 0) + 1

        return {
            "ok": True,
            "dry_run": dry_run,
            "transcript_entries_indexed": len(uuid_to_cwd),
            "rows_null_before": before,
            "rows_attributed": len(updates),
            "rows_no_transcript_match": unmatched,
            "rows_cwd_outside_any_project": no_project,
            "by_client": dict(sorted(by_client.items(), key=lambda kv: -kv[1])),
            "by_project": dict(sorted(per_project.items(), key=lambda kv: -kv[1])),
        }
    finally:
        conn.close()


def client_rollup(*, db_path: Path | None = None) -> dict[str, Any]:
    """Token spend and event counts per client — the question this all exists for.

    Joins ai_canonical_events -> business_projects -> business_clients. Events
    that could not be attributed are reported under an explicit "(unattributed)"
    bucket rather than being folded into any client.
    """
    import json

    from core.pricing.claude_models import compute_cost

    db = _resolve_db(db_path)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT COALESCE(c.name, CASE WHEN e.project_id IS NULL THEN '(unattributed)'"
            "        ELSE '(unknown client)' END) AS client,"
            "       COALESCE(p.name, '(unattributed)') AS project,"
            "       e.model_id, e.payload"
            " FROM ai_canonical_events e"
            " LEFT JOIN business_projects p ON p.project_id = e.project_id"
            " LEFT JOIN business_clients  c ON c.client_id  = p.client_id"
            " WHERE e.event_type = 'token.consumed'"
        ).fetchall()
    finally:
        conn.close()

    by_client: dict[str, dict[str, Any]] = {}
    for client, project, model, payload in rows:
        try:
            d = json.loads(payload) if payload else {}
        except (ValueError, TypeError):
            d = {}
        usd = compute_cost(
            model or d.get("model") or "",
            int(d.get("input_tokens") or 0),
            int(d.get("output_tokens") or 0),
            int(d.get("cache_creation_input_tokens") or 0),
            int(d.get("cache_read_input_tokens") or 0),
        )
        bucket = by_client.setdefault(
            client, {"client": client, "events": 0, "usd": 0.0, "projects": {}}
        )
        bucket["events"] += 1
        bucket["usd"] += usd
        bucket["projects"][project] = round(bucket["projects"].get(project, 0.0) + usd, 4)

    out = sorted(by_client.values(), key=lambda b: -b["usd"])
    for b in out:
        b["usd"] = round(b["usd"], 2)
        b["projects"] = dict(sorted(b["projects"].items(), key=lambda kv: -kv[1]))
    return {"ok": True, "by_client": out, "total_usd": round(sum(b["usd"] for b in out), 2)}
