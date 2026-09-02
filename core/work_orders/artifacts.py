"""Authority-backed store for work-order ceremony artifacts (WO-FILESDB-P1).

Replaces the ``.planning/work-orders/<id>/*.{md,json}`` files that the
close/verify gates read. The store degrades gracefully when the
``business_work_order_artifacts`` table is absent (migration 144 stays
unreleased on the live authority DB until ``ds migrate activate``) — callers
fall back to the legacy ``.planning`` files during the transition.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from core.config import paths

_TABLE = "business_work_order_artifacts"

# Artifact kind -> legacy .planning filename (disk fallback + backfill mapping).
# Only the WO-FILESDB-P1 ceremony kinds have a single-file .planning mapping; the
# newer kinds (WO-FILESDB-C*) are authority-only.
KIND_TO_FILENAME: dict[str, str] = {
    "api_contract": "api-contract.md",
    "security_scan": "security-scan.md",
    "design_audit": "design-audit.md",
    "review_verdict": "review-verdict.json",
    "context": "context.md",
    "impact_affirmation": "impact-affirmation.md",
}

# All kinds accepted by the table's CHECK constraint (migration 152, extended by 154).
# Singleton kinds use the default instance_key=''; multi-instance kinds (eval) key each
# row by instance_key (e.g. the eval_type). Keep in sync with the latest migration's CHECK.
VALID_KINDS: frozenset[str] = frozenset(
    {
        "api_contract",
        "security_scan",
        "design_audit",
        "review_verdict",
        "context",
        "operator_decision",
        "decision_request",
        "escalation",
        "report",
        "eval",
        "impact_affirmation",
    }
)


def _resolve_db(db_path: Path | None) -> Path:
    return db_path or (paths.state_dir() / "studio.db")


# A write that loses a lock race should wait and try again, not degrade. These are small
# because an artifact write is one statement; a caller stuck here for a whole second is
# already in trouble and should hear about it rather than be kept waiting.
_LOCK_ATTEMPTS = 4
_LOCK_BACKOFF_SECONDS = 0.15


def _is_stale_schema(exc: sqlite3.OperationalError) -> bool:
    """Is this a schema older than this write, or a real fault?

    SQLite reports both through OperationalError. Reading False as "table absent" when it
    was actually "database is locked" is what sent 154 review verdicts to disk in August,
    so this is deliberately narrow.

    TWO shapes are the same fact. "no such table" is migration 144 unreleased. A missing
    COLUMN is 144 released and 152 not -- a real intermediate state on a live authority,
    and one that raising would turn into a crash mid-verify on a database that merely
    needs ``ds migrate activate``. Narrowing to "no such table" alone was a regression,
    caught by this module's own test running the real 144-only DDL.

    SQLite words the column case two ways and an INSERT gets the SECOND one: "no such
    column: x" from an expression, "table t has no column named x" from a column list.
    Matching only the first read as a fault and raised -- which is why this predicate is
    tested against the actual migration files rather than a hand-built table.
    """
    text = str(exc).lower()
    return "no such table" in text or "no such column" in text or "has no column named" in text


def _is_locked(exc: sqlite3.OperationalError) -> bool:
    text = str(exc).lower()
    return "locked" in text or "busy" in text


FALLBACK_RULE = "artifact_disk_fallback"


def record_artifact_fallback(
    work_order_id: str, kind: str, *, reason: str, db_path: Path | None = None
) -> None:
    """Count a disk fallback so somebody can ask how often it fires.

    THIS IS THE PART THAT WAS MISSING, and it is why the lock bug survived a month. The
    fallback itself is legitimate -- an authority whose artifact migration is unreleased
    has nowhere else to put a verdict. What was not legitimate is that it fired 154 times
    without leaving a single countable trace, so "are artifacts reaching the authority?"
    had no answer short of comparing a directory listing against a table by hand.

    Recorded through ``record_observation`` (HOOK_EXECUTION_LOGGED via trigger_context),
    which ``observations_report`` already groups by rule -- so the count surface exists
    for free and no new event type or migration is needed. Off-label in one respect: this
    is a library write, not a hook, so ``hook_name``/``hook_type`` name the write site
    rather than a hook. That is a smaller cost than a second event registry to keep in
    sync, and the drift between those two registries has already broken this repo once.

    Best-effort by construction. An artifact that reached disk is stored; failing the
    write because its telemetry failed would trade a countable degradation for a real
    loss.
    """
    try:
        from runtime.lib.enforcement import record_observation

        record_observation(
            hook_name="artifact_write",
            hook_type="library",
            rule=FALLBACK_RULE,
            reason=(
                f"artifact {kind} for work order {work_order_id} was written to .planning "
                f"instead of the authority: {reason}. Gates and `ds project state` read the "
                f"authority, so this artifact is invisible to them. Recover with "
                f"`ds work-order backfill-artifacts`."
            ),
            tier="warn",
            # THE COUNT BELONGS TO THE AUTHORITY THAT LOST THE WRITE. Without this the
            # observation lands in the DEFAULT authority no matter which database the
            # fallback happened on -- so a count attributed to the operator's live DB
            # could have come from anywhere, which is the same "invisible where it
            # matters" failure one level up. Found by trying to test the round-trip.
            db_path=db_path,
        )
    except Exception:  # noqa: BLE001 - telemetry must never cost a stored artifact
        pass


def set_wo_artifact(
    work_order_id: str,
    kind: str,
    content: str,
    *,
    instance_key: str = "",
    db_path: Path | None = None,
    generator: str | None = None,
    project_root: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Upsert an artifact. Returns False (no-op) when the table is absent.

    Pass ``conn`` to write through a connection the CALLER already holds. Opening a second
    connection to a file whose outer transaction is still open blocks on the write lock
    until it times out -- measured 2026-09-02 as the reason 154 of August's review verdicts
    landed on disk instead of in the authority, because all four _persist_review_verdict
    call sites run inside an open `with _connect(db_path)`. When ``conn`` is given the write
    joins that transaction and its commit, so there is no second writer to lose to.

    Singleton artifacts use the default instance_key=''; multi-instance kinds
    (e.g. ``eval``) pass instance_key (e.g. the eval_type) so each coexists.

    WO-VERIFY-PROVENANCE: when ``generator`` is given, the content is stored
    inside a provenance envelope (generator identity, created_at, and the HEAD
    commit of ``project_root``) so close gates can verify who produced the
    artifact and against which commit. ``get_wo_artifact`` unwraps
    transparently; ``get_wo_artifact_envelope`` exposes the metadata.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown artifact kind: {kind!r}")
    if generator is not None:
        from core.work_orders.artifact_envelope import git_head_sha, wrap

        content = wrap(content, generator=generator, head_commit_sha=git_head_sha(project_root))
    now = datetime.now(UTC).isoformat()
    borrowed = conn is not None
    if not borrowed:
        try:
            # A busy timeout is the cheap half of the lock fix: SQLite waits for the holder
            # instead of failing instantly. It is not the whole fix -- a caller holding an
            # open transaction for the length of a verify outlasts any timeout, which is
            # what `conn` is for.
            conn = sqlite3.connect(str(_resolve_db(db_path)), timeout=2.0)
        except sqlite3.Error:
            return False
    try:
        for attempt in range(_LOCK_ATTEMPTS):
            try:
                conn.execute(
                    f"INSERT INTO {_TABLE}"
                    " (work_order_id, kind, instance_key, content, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(work_order_id, kind, instance_key) DO UPDATE SET"
                    " content=excluded.content, updated_at=excluded.updated_at",
                    (work_order_id, kind, instance_key, content, now, now),
                )
                # A borrowed connection's transaction belongs to the caller; committing
                # it here would end a transaction still being used around us.
                if not borrowed:
                    conn.commit()
                return True
            except sqlite3.OperationalError as exc:
                # Retry a lock; anything else is not a race and gets handled below.
                if not _is_locked(exc) or attempt == _LOCK_ATTEMPTS - 1:
                    raise
                time.sleep(_LOCK_BACKOFF_SECONDS * (attempt + 1))
        return True
    except sqlite3.OperationalError as exc:
        # FALSE MEANS ONE THING: this schema predates the write. It used to mean that OR any
        # other OperationalError, and "database is locked" is the one that mattered.
        #
        # MEASURED 2026-09-02: of August's review verdicts, 154 went to disk and 23 to the
        # authority. All four _persist_review_verdict call sites run INSIDE an open
        # `with _connect(db_path)` block, so this function opened a second connection to a
        # file the outer transaction held, got "database is locked", returned False, and
        # the caller read that as "the artifact table does not exist" and wrote to disk.
        # mutations.py already carries this exact lesson for the delivery-boundary stamp;
        # the verdict write never got the same treatment.
        if _is_stale_schema(exc):
            return False
        raise
    except sqlite3.IntegrityError as exc:
        # The table exists but its ``kind`` CHECK does not yet accept this kind — a stale
        # schema from an unreleased migration (e.g. impact_affirmation before migration 154
        # is released). That is the documented no-op. A FOREIGN KEY failure lands in the
        # same exception class and is NOT that: it means the work order does not exist, and
        # swallowing it would report a stored artifact that no reader can ever find.
        if "CHECK constraint" in str(exc):
            return False
        raise
    finally:
        if not borrowed:
            conn.close()


def get_wo_artifact(
    work_order_id: str, kind: str, *, instance_key: str = "", db_path: Path | None = None
) -> str | None:
    """Return the stored artifact content, or None if absent / table missing.

    Provenance-enveloped artifacts (WO-VERIFY-PROVENANCE) are unwrapped
    transparently — callers always receive the bare artifact text.
    """
    content, _ = get_wo_artifact_envelope(
        work_order_id, kind, instance_key=instance_key, db_path=db_path
    )
    return content


def get_wo_artifact_envelope(
    work_order_id: str, kind: str, *, instance_key: str = "", db_path: Path | None = None
) -> tuple[str | None, dict | None]:
    """Return ``(content, envelope | None)`` for a stored artifact.

    ``envelope`` is None for legacy bare-text artifacts and for absent rows.
    """
    from core.work_orders.artifact_envelope import unwrap

    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return None, None
    try:
        row = conn.execute(
            f"SELECT content FROM {_TABLE} WHERE work_order_id=? AND kind=? AND instance_key=?",
            (work_order_id, kind, instance_key),
        ).fetchone()
        return unwrap(row[0]) if row else (None, None)
    except sqlite3.OperationalError:
        return None, None
    finally:
        conn.close()


def has_wo_artifact(
    work_order_id: str, kind: str, *, instance_key: str = "", db_path: Path | None = None
) -> bool:
    return (
        get_wo_artifact(work_order_id, kind, instance_key=instance_key, db_path=db_path) is not None
    )


def list_wo_artifacts(
    work_order_id: str, kind: str, *, db_path: Path | None = None
) -> list[tuple[str, str]]:
    """Return ``[(instance_key, content), ...]`` for all rows of a kind (e.g. every
    eval stage for a WO), ordered by instance_key. Empty when absent / table missing."""
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            f"SELECT instance_key, content FROM {_TABLE}"
            " WHERE work_order_id=? AND kind=? ORDER BY instance_key",
            (work_order_id, kind),
        ).fetchall()
        from core.work_orders.artifact_envelope import unwrap

        return [(r[0], unwrap(r[1])[0] or "") for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def list_artifacts_by_kind(
    kind: str, *, db_path: Path | None = None
) -> list[tuple[str, str, str, str]]:
    """Return every artifact of a kind across all work orders.

    Yields ``[(work_order_id, instance_key, content, updated_at), ...]`` ordered
    by ``updated_at`` descending (most-recent first). Complements
    ``list_wo_artifacts`` (which is scoped to a single WO) for operator-facing
    cross-WO queries such as ``ds escalation list``. Empty when the artifact
    table is absent (unreleased migration on the live authority DB).
    """
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            f"SELECT work_order_id, instance_key, content, updated_at FROM {_TABLE}"
            " WHERE kind=? ORDER BY updated_at DESC, work_order_id, instance_key",
            (kind,),
        ).fetchall()
        from core.work_orders.artifact_envelope import unwrap

        return [(r[0], r[1], unwrap(r[2])[0] or "", r[3]) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def backfill_wo_artifacts(planning_root: Path, *, db_path: Path | None = None) -> int:
    """One-time migration: copy existing .planning/work-orders/<id>/*.{md,json}
    ceremony artifacts into the authority table. Returns the number written.

    Idempotent (upsert). A no-op on a DB where the table is absent (returns 0) —
    run it after ``ds migrate activate`` releases migration 144. Files are left in
    place (gitignored) until Phase 3 retires them.
    """
    wo_root = planning_root / "work-orders"
    if not wo_root.is_dir():
        return 0
    filename_to_kind = {fname: kind for kind, fname in KIND_TO_FILENAME.items()}
    written = 0
    for wo_dir in sorted(wo_root.iterdir()):
        if not wo_dir.is_dir():
            continue
        for fname, kind in filename_to_kind.items():
            fpath = wo_dir / fname
            if fpath.is_file():
                content = fpath.read_text(encoding="utf-8", errors="replace")
                if set_wo_artifact(wo_dir.name, kind, content, db_path=db_path):
                    written += 1
    return written
