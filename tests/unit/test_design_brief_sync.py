"""Regression test for WO 2325f95d — DesignBriefProjection missing from sync_tick.

The design-brief mutations are emit-only ("projection is the sole writer"): they
write a spool event and rely on a projection pass to materialize the read-model
row. The synchronous Pattern C tick (``sync_tick``) is the only projection pass
available in a one-shot process with no daemon — but it registered
WorkOrder/Task/Milestone/Project projections and NOT DesignBriefProjection.

So a one-process caller that did ``create_design_brief`` → ``sync_tick`` →
``update_design_brief_field`` still hit "Brief not found": the tick never
materialized the brief. This test drives the full lifecycle (create → update all
six fields → lock) in one interpreter with ``sync_tick`` as the only projection
pass and asserts the read model reflects every step. Fails on main (the brief is
never materialized, so the first update returns "Brief not found"); passes once
DesignBriefProjection is registered in ``sync_tick``.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
import uuid
from datetime import UTC, datetime

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00.000000Z"

# Six canonical brief fields (raw_output excluded — it is the wizard's scratch dump).
SIX_FIELDS = [
    ("purpose", "Help new drivers pass the written exam"),
    ("audience", "First-time license applicants"),
    ("tone", "Encouraging and clear"),
    ("design_system", "tech-minimal"),
    ("font_pairing", "Inter / Source Serif"),
    ("brand_tokens", "primary=#1e40af; radius=8px"),
]


def _reset_db_runtime() -> None:
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()


@pytest.fixture
def live_like_home(tmp_path, monkeypatch):
    """A bootstrapped studio.db wired as the resolved authority for both the
    mutations (via dream_studio_home) and the projection engine (via
    DREAM_STUDIO_DB_PATH + DS_SPOOL_ROOT + a DatabaseRuntime reset), so
    ``sync_tick`` reads/writes this temp DB and not the live one.
    """
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    _reset_db_runtime()
    bootstrap_database(db)
    yield tmp_path, db
    _reset_db_runtime()


def _seed_project(db) -> str:
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, "Test", "", "active", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


def test_brief_lifecycle_syncs_in_one_interpreter(live_like_home):
    home, db = live_like_home
    project_id = _seed_project(db)

    from core.design_briefs.mutations import (
        create_design_brief,
        lock_design_brief,
        update_design_brief_field,
    )
    from core.projections.runner import sync_tick

    created = create_design_brief(project_id=project_id, source_root=home, dream_studio_home=home)
    assert created["ok"] is True
    brief_id = created["brief_id"]

    # The only projection pass — no daemon. Pre-fix this is a no-op for briefs
    # because DesignBriefProjection is not registered in sync_tick, so the row is
    # never materialized and the first update below returns "Brief not found".
    sync_tick()

    for field, value in SIX_FIELDS:
        res = update_design_brief_field(
            brief_id=brief_id,
            field=field,
            value=value,
            source_root=home,
            dream_studio_home=home,
        )
        assert res["ok"] is True, f"update {field!r} failed: {res}"

    locked = lock_design_brief(brief_id=brief_id, source_root=home, dream_studio_home=home)
    assert locked["ok"] is True

    # Materialize the six field updates + the lock.
    sync_tick()

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT status, purpose, audience, tone, design_system, font_pairing, brand_tokens"
            " FROM business_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "brief row must be materialized by sync_tick after the fix"
    status, purpose, audience, tone, design_system, font_pairing, brand_tokens = row
    assert status == "locked"
    assert purpose == "Help new drivers pass the written exam"
    assert audience == "First-time license applicants"
    assert tone == "Encouraging and clear"
    assert design_system == "tech-minimal"
    assert font_pairing == "Inter / Source Serif"
    assert brand_tokens == "primary=#1e40af; radius=8px"


# -- the one-shot CLI: every `ds design-brief ...` is its own process -------------------
#
# The test above ticks by hand between calls. An operator cannot: `ds design-brief
# create` printed "Draft brief created: <id>" and exited, nothing projected the event
# (no daemon in a one-shot process), so `show` said "No design brief" and `lock <id>`
# said "Brief not found". Each CLI call below must leave the read model current on its
# own -- no sync_tick() in this test.


def _cli(capsys, home, *argv: str) -> tuple[int, str]:
    from interfaces.cli.ds import main

    capsys.readouterr()
    rc = main(["--home", str(home), *argv])
    return rc, capsys.readouterr().out


def test_cli_create_is_visible_to_the_next_command_without_a_daemon(live_like_home, capsys):
    home, db = live_like_home
    project_id = _seed_project(db)

    rc, out = _cli(capsys, home, "design-brief", "create", project_id)
    assert rc == 0, out
    brief_id = out.split("Draft brief created:")[1].split()[0]

    rc, out = _cli(capsys, home, "design-brief", "show", project_id)
    assert rc == 0
    assert brief_id in out, f"created brief is not readable by the next command: {out!r}"

    rc, out = _cli(
        capsys, home, "design-brief", "update", brief_id, "--field", "purpose", "--value", "p"
    )
    assert rc == 0, out
    rc, out = _cli(capsys, home, "design-brief", "set-system", brief_id, "tech-minimal")
    assert rc == 0, out
    rc, out = _cli(capsys, home, "design-brief", "lock", brief_id)
    assert rc == 0, out

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT status, purpose, design_system FROM business_design_briefs"
            " WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("locked", "p", "tech-minimal")


def test_cli_create_for_an_unregistered_project_fails_instead_of_claiming_success(
    live_like_home, capsys
):
    home, _db = live_like_home

    rc, out = _cli(capsys, home, "design-brief", "create", str(uuid.uuid4()))

    assert rc == 1
    assert "Project not found" in out
    assert "Draft brief created" not in out


# -- what each mutation emits, and that the effect lands ---------------------------------
#
# These run the functions. The checks they replace read the module's source for the event
# name, which a helper's error message also contains, so a wrong event type passed them.


@pytest.fixture
def recorded(monkeypatch):
    """Every envelope the mutations write to the spool (still written for real)."""
    import spool.writer as spool_writer

    real = spool_writer.write_event
    events: list[dict] = []

    def record(envelope, root=None):
        events.append(envelope)
        return real(envelope, root)

    monkeypatch.setattr(spool_writer, "write_event", record)
    return events


def _kw(home) -> dict:
    return {"source_root": home, "dream_studio_home": home}


def _row(db, brief_id, *columns):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            f"SELECT {', '.join(columns)} FROM business_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
    finally:
        conn.close()


def _new_brief(home, db) -> tuple[str, str]:
    from core.design_briefs.mutations import create_design_brief

    project_id = _seed_project(db)
    created = create_design_brief(project_id=project_id, **_kw(home))
    assert created["ok"] is True, created
    return project_id, created["brief_id"]


def test_each_mutation_emits_its_event_and_the_effect_is_visible(live_like_home, recorded):
    from core.design_briefs.mutations import (
        create_design_brief,
        lock_design_brief,
        set_design_system,
        update_design_brief_field,
    )

    home, db = live_like_home
    project_id = _seed_project(db)

    created = create_design_brief(project_id=project_id, **_kw(home))
    brief_id = created["brief_id"]
    assert [e["event_type"] for e in recorded] == ["design_brief.created"]
    assert recorded[-1]["payload"] == {
        "brief_id": brief_id,
        "project_id": project_id,
        "status": "draft",
    }
    assert _row(db, brief_id, "status") == ("draft",)

    update_design_brief_field(brief_id=brief_id, field="tone", value="warm", **_kw(home))
    assert recorded[-1]["event_type"] == "design_brief.updated"
    assert recorded[-1]["payload"] == {"brief_id": brief_id, "field": "tone", "new_value": "warm"}
    assert _row(db, brief_id, "tone") == ("warm",)

    set_design_system(brief_id=brief_id, system_name="tech-minimal", **_kw(home))
    assert recorded[-1]["event_type"] == "design_brief.updated"
    assert recorded[-1]["payload"] == {
        "brief_id": brief_id,
        "field": "design_system",
        "new_value": "tech-minimal",
    }
    assert _row(db, brief_id, "design_system") == ("tech-minimal",)

    lock_design_brief(brief_id=brief_id, **_kw(home))
    assert recorded[-1]["event_type"] == "design_brief.locked"
    assert recorded[-1]["payload"] == {"brief_id": brief_id}
    assert _row(db, brief_id, "status") == ("locked",)
    assert len(recorded) == 4


def test_unknown_field_or_design_system_is_refused_and_emits_nothing(live_like_home, recorded):
    from core.design_briefs.mutations import set_design_system, update_design_brief_field

    home, db = live_like_home
    _project_id, brief_id = _new_brief(home, db)
    del recorded[:]

    bad_field = update_design_brief_field(brief_id=brief_id, field="status", value="x", **_kw(home))
    bad_system = set_design_system(brief_id=brief_id, system_name="no-such-system", **_kw(home))

    assert bad_field["ok"] is False and "Unknown field" in bad_field["error"]
    assert bad_system["ok"] is False and "Invalid design system" in bad_system["error"]
    assert recorded == [], "a refused change must not reach the spool"
    assert _row(db, brief_id, "status") == ("draft",)


def test_cli_update_with_an_unknown_field_exits_1(live_like_home, capsys):
    home, db = live_like_home
    _project_id, brief_id = _new_brief(home, db)

    rc, out = _cli(
        capsys, home, "design-brief", "update", brief_id, "--field", "nope", "--value", "x"
    )

    assert rc == 1
    assert "Unknown field" in out


# -- an emit or a projection that did not happen is an error, not a brief ------------------

_MUTATIONS = ["create", "lock", "update", "set_system"]


def _run_mutation(name, home, project_id, brief_id):
    from core.design_briefs.mutations import (
        create_design_brief,
        lock_design_brief,
        set_design_system,
        update_design_brief_field,
    )

    if name == "create":
        return create_design_brief(project_id=project_id, **_kw(home))
    if name == "lock":
        return lock_design_brief(brief_id=brief_id, **_kw(home))
    if name == "update":
        return update_design_brief_field(brief_id=brief_id, field="tone", value="warm", **_kw(home))
    return set_design_system(brief_id=brief_id, system_name="tech-minimal", **_kw(home))


def _prepare(name, home, db):
    """A project for create (which needs a clean slate), a draft brief for the rest."""
    if name == "create":
        return _seed_project(db), None
    return _new_brief(home, db)


@pytest.mark.parametrize("name", _MUTATIONS)
def test_a_failed_write_is_returned_as_an_error(live_like_home, name):
    """The events directory is a file, so the spool write raises. It used to be swallowed
    (`except Exception: pass`) and the call reported success for an event never written."""
    home, db = live_like_home
    project_id, brief_id = _prepare(name, home, db)
    spool = home / "spool-root"
    shutil.rmtree(spool, ignore_errors=True)
    spool.write_text("not a directory", encoding="utf-8")

    result = _run_mutation(name, home, project_id, brief_id)

    assert result["ok"] is False, result
    assert "not emitted" in result["error"]
    if brief_id:
        assert _row(db, brief_id, "status", "tone") == ("draft", None)


@pytest.mark.parametrize("name", _MUTATIONS)
def test_a_tick_that_applied_nothing_is_returned_as_an_error(live_like_home, monkeypatch, name):
    """sync_tick swallows its own failures by design, so a tick that applied nothing looked
    like success and the call printed a brief id the next command could not find."""
    home, db = live_like_home
    project_id, brief_id = _prepare(name, home, db)
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    result = _run_mutation(name, home, project_id, brief_id)

    assert result["ok"] is False, result
    assert "not in the read model" in result["error"]
    assert list((home / "spool-root" / "spool").glob("*.json")), "the event stays queued"


def test_a_writer_lock_on_the_authority_is_returned_as_an_error(live_like_home, monkeypatch):
    """A writer holds studio.db: the projection cannot apply the event. The real tick is
    used, with its 30 s busy timeout shortened (a test cannot wait 43 s)."""
    home, db = live_like_home
    project_id = _seed_project(db)
    real_connect = sqlite3.connect

    class ShortBusy(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.replace(" ", "").lower().startswith("pragmabusy_timeout"):
                sql = "PRAGMA busy_timeout=150"
            return super().execute(sql, *args, **kwargs)

    def short_connect(*args, **kwargs):
        kwargs["timeout"] = 0.15
        kwargs["factory"] = ShortBusy
        return real_connect(*args, **kwargs)

    holder = real_connect(str(db), timeout=1, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    monkeypatch.setattr(sqlite3, "connect", short_connect)
    try:
        started = time.monotonic()
        from core.design_briefs.mutations import create_design_brief

        result = create_design_brief(project_id=project_id, **_kw(home))
        elapsed = time.monotonic() - started
    finally:
        monkeypatch.setattr(sqlite3, "connect", real_connect)
        holder.execute("ROLLBACK")
        holder.close()

    assert result["ok"] is False, result
    assert "not in the read model" in result["error"]
    assert elapsed < 30, f"the test must not wait out the real busy timeout ({elapsed:.1f}s)"
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM business_design_briefs").fetchone() == (0,)
    finally:
        conn.close()


@pytest.mark.parametrize("name", _MUTATIONS)
def test_a_call_for_another_home_is_refused_before_anything_is_written(
    live_like_home, tmp_path_factory, recorded, name
):
    """The event went to the spool the ENVIRONMENT names and dead-lettered there on the
    foreign key, while the call for the other home returned ok."""
    home, db = live_like_home
    other = tmp_path_factory.mktemp("other-home")
    other_db = other / "state" / "studio.db"
    other_db.parent.mkdir(parents=True)
    bootstrap_database(other_db)
    project_id = _seed_project(other_db)
    brief_id = str(uuid.uuid4())
    if name != "create":  # create is the call that must find no draft yet
        _insert_brief(other_db, project_id, brief_id, "draft", NOW)

    result = _run_mutation(name, other, project_id, brief_id)

    assert result["ok"] is False, result
    assert "not emitted" in result["error"]
    assert "different home" in result["error"]
    assert recorded == [], "nothing may be emitted into the environment's spool"
    assert not (home / "spool-root").exists()
    assert _row(other_db, brief_id, "status") in (None, ("draft",))


# -- one brief is "the" brief, and its lock time does not move -----------------------------


def test_locking_a_locked_brief_keeps_the_original_lock_time(live_like_home, recorded):
    from core.design_briefs.mutations import lock_design_brief

    home, db = live_like_home
    _project_id, brief_id = _new_brief(home, db)
    first = lock_design_brief(brief_id=brief_id, **_kw(home))
    locked_at = _row(db, brief_id, "updated_at")[0]
    emitted = len(recorded)

    second = lock_design_brief(brief_id=brief_id, **_kw(home))

    assert first["ok"] and second["ok"]
    assert "already locked" in second["message"]
    assert second["locked_at"] == locked_at
    assert _row(db, brief_id, "updated_at") == (locked_at,), "re-locking moved the lock time"
    assert len(recorded) == emitted, "a no-op lock must not emit another event"


def _emit_raw(event_type, brief_id, project_id, payload):
    import spool.writer as spool_writer

    from canonical.events.envelope import CanonicalEventEnvelope
    from core.projections.runner import sync_tick

    spool_writer.write_event(
        CanonicalEventEnvelope(
            event_type=event_type,
            session_id=None,
            payload=payload,
            timestamp=datetime.now(UTC).isoformat(),
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": project_id,
                "brief_id": brief_id,
                "attribution_status": "fully_attributed",
            },
        ).to_dict()
    )
    sync_tick()


def test_the_projection_does_not_move_the_lock_time_either(live_like_home):
    """A second design_brief.locked (or an update) arriving from anywhere but the CLI must
    not refresh updated_at: brief_currency measures staleness from it."""
    from core.design_briefs.mutations import lock_design_brief

    home, db = live_like_home
    project_id, brief_id = _new_brief(home, db)
    lock_design_brief(brief_id=brief_id, **_kw(home))
    locked_at = _row(db, brief_id, "updated_at")[0]

    _emit_raw("design_brief.locked", brief_id, project_id, {"brief_id": brief_id})
    assert _row(db, brief_id, "updated_at") == (locked_at,)

    _emit_raw(
        "design_brief.updated",
        brief_id,
        project_id,
        {"brief_id": brief_id, "field": "tone", "new_value": "changed after lock"},
    )
    assert _row(db, brief_id, "updated_at", "tone") == (locked_at, None)


def test_creating_a_brief_after_a_locked_one_makes_a_new_draft(live_like_home, capsys):
    """Revising a locked brief is a new draft; only a draft blocks another create."""
    from core.design_briefs.mutations import create_design_brief, lock_design_brief

    home, db = live_like_home
    project_id, first = _new_brief(home, db)
    lock_design_brief(brief_id=first, **_kw(home))

    again = create_design_brief(project_id=project_id, **_kw(home))
    assert again["created"] is True and again["brief_id"] != first

    rc, out = _cli(capsys, home, "design-brief", "show", project_id)
    assert rc == 0 and again["brief_id"] in out and "DRAFT" in out

    rc, out = _cli(capsys, home, "design-brief", "create", project_id)
    assert rc == 0
    assert f"Draft brief already exists: {again['brief_id']}" in out


def test_cli_lock_twice_says_so(live_like_home, capsys):
    home, db = live_like_home
    _project_id, brief_id = _new_brief(home, db)
    _cli(capsys, home, "design-brief", "lock", brief_id)

    rc, out = _cli(capsys, home, "design-brief", "lock", brief_id)

    assert rc == 0
    assert "already locked" in out


def _insert_brief(db, project_id, brief_id, status, created_at):
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_design_briefs (brief_id, project_id, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (brief_id, project_id, status, created_at, created_at),
    )
    conn.commit()
    conn.close()


@pytest.mark.parametrize(
    ("older", "newer", "gate_passes"),
    [("locked", "draft", False), ("draft", "locked", True), ("locked", "locked", True)],
)
def test_the_close_gate_and_show_read_the_same_newest_brief(
    live_like_home, capsys, older, newer, gate_passes
):
    """`show`, the start context and the project state read the NEWEST brief; the gate and
    brief_currency accepted ANY locked one, so an older locked brief behind a newer draft
    passed the gate while show said DRAFT."""
    from core.gates.brief_currency import brief_currency
    from core.work_orders.close import run_gate_check

    home, db = live_like_home
    project_id = _seed_project(db)
    _insert_brief(db, project_id, "older", older, "2026-03-01T00:00:00+00:00")
    _insert_brief(db, project_id, "newer", newer, "2026-04-01T00:00:00+00:00")

    rc, out = _cli(capsys, home, "design-brief", "show", project_id)
    assert rc == 0 and '"brief_id": "newer"' in out

    conn = sqlite3.connect(str(db))
    try:
        passed, reason = run_gate_check(
            "design_brief_locked",
            planning_root=home / ".planning",
            work_order_id="wo",
            project_id=project_id,
            conn=conn,
        )
        info = brief_currency(project_id, conn=conn, db_path=db)
    finally:
        conn.close()
    assert passed is gate_passes, reason
    assert info["exists"] is gate_passes
