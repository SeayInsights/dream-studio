"""WO-CLIENT-ENGINE: the event-sourced client engine — mutations emit the right canonical events,
the projections materialize business_clients / business_projects.client_id, the queries resolve the
default + fit proposed work to a client's projects, and the backfill classifies by name/path."""

from __future__ import annotations

import subprocess
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-08-08T00:00:00.000000Z"


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    return db


def _seed_project(conn, pid, name, client_id=None, path=None, status="active"):
    conn.execute(
        "INSERT INTO business_projects (project_id, name, status, created_at, updated_at,"
        " project_path, client_id) VALUES (?,?,?,?,?,?,?)",
        (pid, name, status, NOW, NOW, path, client_id),
    )


def _seed_work_order(conn, wo_id, project_id):
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, NOW, NOW),
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def _make_repo(root: Path) -> Path:
    """A real git repository, the way `tests/unit/test_multiroot_review.py` builds one --
    the round-table-unwrapping logic is driven against real git markers for the same reason
    that file gives: the repo/worktree distinction is exactly the thing an invented fixture
    would get wrong."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "file.txt").write_text("x", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


# ── classify (pure) ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,path,expected",
    [
        ("Fulcrum Skill Library", r"C:\x\Fulcrum", "fulcrum"),
        ("Some App", r"C:\clients\hypershift\app", "hypershift"),
        ("Hypershift Ops", None, "hypershift"),
        ("Dream Studio", r"C:\x\dream-studio", "seayinsights"),
        ("Acme", None, "seayinsights"),
    ],
)
def test_classify_project(name, path, expected):
    from core.clients.backfill import classify_project

    assert classify_project(name, path) == expected


def test_classify_project_prefers_a_resolved_root_over_the_bare_path():
    """THE ROUND-TABLE BUG, at the pure-function level: a project's own project_path can
    name the reviewing tool's working directory rather than the client's repository, and a
    resolved_root -- once something upstream has gone and found the real one -- must win
    over that bare string, not merely supplement it."""
    from core.clients.backfill import classify_project

    assert (
        classify_project(
            "plat-roundtable",
            r"C:\Users\danni\round-table\_reviews\plat-roundtable",
            resolved_root=r"C:\Users\danni\Fulcrum\platform",
        )
        == "fulcrum"
    )
    # With no resolved_root, the bare path alone still mistags it -- the precondition that
    # makes the line above a real fix rather than a no-op.
    assert (
        classify_project("plat-roundtable", r"C:\Users\danni\round-table\_reviews\plat-roundtable")
        == "seayinsights"
    )


# ── projections (direct handler calls) ──────────────────────────────────────


def test_client_projection_created_and_archived(tmp_path: Path):
    from core.projections.client_projection import ClientProjection

    conn = sqlite3.connect(str(_db(tmp_path)))
    try:
        proj = ClientProjection()
        proj.handle(
            {
                "event_id": "e1",
                "event_type": "client.created",
                "event_timestamp": NOW,
                "payload": {"client_id": "acme", "name": "Acme", "description": "d"},
            },
            conn,
        )
        conn.commit()
        row = conn.execute(
            "SELECT name, status FROM business_clients WHERE client_id='acme'"
        ).fetchone()
        assert row == ("Acme", "active")

        proj.handle(
            {
                "event_id": "e2",
                "event_type": "client.archived",
                "event_timestamp": NOW,
                "payload": {"client_id": "acme"},
            },
            conn,
        )
        conn.commit()
        assert (
            conn.execute("SELECT status FROM business_clients WHERE client_id='acme'").fetchone()[0]
            == "archived"
        )
    finally:
        conn.close()


def test_client_projection_deleted(tmp_path: Path):
    from core.projections.client_projection import ClientProjection

    conn = sqlite3.connect(str(_db(tmp_path)))
    try:
        proj = ClientProjection()
        proj.handle(
            {
                "event_id": "c1",
                "event_type": "client.created",
                "event_timestamp": NOW,
                "payload": {"client_id": "temp", "name": "Temp"},
            },
            conn,
        )
        proj.handle(
            {
                "event_id": "c2",
                "event_type": "client.deleted",
                "event_timestamp": NOW,
                "payload": {"client_id": "temp"},
            },
            conn,
        )
        conn.commit()
        assert (
            conn.execute("SELECT status FROM business_clients WHERE client_id='temp'").fetchone()[0]
            == "deleted"
        )
    finally:
        conn.close()


def test_project_client_assigned_handler_sets_client_id(tmp_path: Path):
    from core.projections.project_projection import ProjectProjection

    conn = sqlite3.connect(str(_db(tmp_path)))
    try:
        _seed_project(conn, "p1", "Fulcrum Skill Library")
        conn.commit()
        ProjectProjection().handle(
            {
                "event_id": "e3",
                "event_type": "project.client_assigned",
                "event_timestamp": NOW,
                "project_id": "p1",
                "payload": {"project_id": "p1", "client_id": "fulcrum"},
            },
            conn,
        )
        conn.commit()
        assert (
            conn.execute(
                "SELECT client_id FROM business_projects WHERE project_id='p1'"
            ).fetchone()[0]
            == "fulcrum"
        )
    finally:
        conn.close()


# ── queries ─────────────────────────────────────────────────────────────────


def test_resolve_default_client_is_seayinsights(tmp_path: Path):
    from core.clients.queries import resolve_default_client

    assert resolve_default_client(db_path=_db(tmp_path)) == "seayinsights"


def test_list_and_projects_for_client(tmp_path: Path):
    from core.clients import queries

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    _seed_project(conn, "p1", "A", client_id="fulcrum")
    _seed_project(conn, "p2", "B", client_id="seayinsights")
    conn.commit()
    conn.close()

    ids = {c["client_id"] for c in queries.list_clients(db_path=db)}
    assert {"seayinsights", "fulcrum", "hypershift"} <= ids
    ful = queries.projects_for_client("fulcrum", db_path=db)
    assert [p["project_id"] for p in ful] == ["p1"]


def test_get_client_show(tmp_path: Path):
    from core.clients import queries

    db = _db(tmp_path)
    assert queries.get_client("fulcrum", db_path=db)["name"] == "Fulcrum"
    assert queries.get_client("nonexistent", db_path=db) is None


def test_candidate_projects_ambiguous(tmp_path: Path):
    from core.clients.queries import candidate_projects_for_work

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    # Two projects that BOTH clearly overlap the work terms -> ambiguous.
    _seed_project(conn, "p1", "Billing Payments Service", client_id="fulcrum")
    conn.execute(
        "UPDATE business_projects SET description='billing payments invoices stripe' WHERE"
        " project_id='p1'"
    )
    _seed_project(conn, "p2", "Payments Reconciliation", client_id="fulcrum")
    conn.execute(
        "UPDATE business_projects SET description='payments invoices reconciliation ledger' WHERE"
        " project_id='p2'"
    )
    conn.commit()
    conn.close()
    r = candidate_projects_for_work(
        "fulcrum", "new payments invoices work", "billing payments invoices", db_path=db
    )
    assert r["verdict"] == "ambiguous"


def test_candidate_projects_verdict_ladder(tmp_path: Path):
    from core.clients.queries import candidate_projects_for_work

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    # One client, two clearly-distinct projects (the Fulcrum case).
    _seed_project(conn, "p-acct", "Back-Office Accounting", client_id="fulcrum")
    conn.execute(
        "UPDATE business_projects SET description='CostPoint accounting payments invoices"
        " reconciliation ledger' WHERE project_id='p-acct'"
    )
    _seed_project(conn, "p-portal", "Partner Portal", client_id="fulcrum")
    conn.execute(
        "UPDATE business_projects SET description='partner portal login dashboard react frontend'"
        " WHERE project_id='p-portal'"
    )
    conn.commit()
    conn.close()

    clear = candidate_projects_for_work(
        "fulcrum", "reconcile CostPoint invoices", "accounting ledger payments", db_path=db
    )
    assert clear["verdict"] == "clear_single" and clear["best"] == "p-acct"

    nofit = candidate_projects_for_work(
        "fulcrum", "kubernetes autoscaler tuning", "helm pods", db_path=db
    )
    assert nofit["verdict"] == "no_fit" and nofit["best"] is None

    empty = candidate_projects_for_work("hypershift", "anything", "x", db_path=db)
    assert empty["verdict"] == "no_projects"


# ── mutations emit the right events ─────────────────────────────────────────


def test_create_client_emits_event(monkeypatch):
    import spool.writer as sw
    from core.clients import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    result = mutations.create_client(name="Acme Corp", description="a client")
    assert result["ok"] and result["client_id"] == "acme-corp"
    assert len(captured) == 1
    ev = captured[0]
    assert ev["event_type"] == "client.created"
    assert ev["payload"]["client_id"] == "acme-corp"
    assert ev["trace"]["attribution_status"] == "fully_attributed"


def test_slugify_client():
    from core.clients.mutations import slugify_client

    assert slugify_client("Acme Corp!") == "acme-corp"
    assert slugify_client("Fulcrum") == "fulcrum"
    assert slugify_client("  Multi   Word  ") == "multi-word"
    assert slugify_client("") != ""  # non-empty uuid fallback


def test_archive_client_emits_event(monkeypatch):
    import spool.writer as sw
    from core.clients import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    result = mutations.archive_client(client_id="acme")
    assert result["status"] == "archived"
    assert captured[0]["event_type"] == "client.archived"
    assert captured[0]["payload"] == {"client_id": "acme"}


def test_delete_client_emits_event(monkeypatch):
    import spool.writer as sw
    from core.clients import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    mutations.delete_client(client_id="acme")
    assert captured[0]["event_type"] == "client.deleted"
    assert captured[0]["payload"] == {"client_id": "acme"}


def test_detach_reassigns_to_default(monkeypatch):
    import spool.writer as sw
    from core.clients import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    mutations.detach_project_client(project_id="p1")
    ev = captured[0]
    assert ev["event_type"] == "project.client_assigned"
    assert ev["payload"] == {"project_id": "p1", "client_id": "seayinsights"}


def test_register_project_assigns_default_client(tmp_path: Path, monkeypatch):
    """New-project default = SeayInsights: register_project assigns the default client when the
    client layer is live (client_id column present)."""
    import spool.writer as sw
    from core.clients import mutations
    from core.projects import mutations_register

    db = _db(tmp_path)
    monkeypatch.setattr(mutations_register, "_require_db", lambda *a, **k: db)
    monkeypatch.setattr(sw, "write_event", lambda d: None)
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)
    assigns = []
    monkeypatch.setattr(
        mutations, "assign_project_client", lambda **kw: assigns.append(kw) or {"ok": True}
    )

    mutations_register.register_project(
        name="Brand New App", write_marker=False, source_root=Path("."), dream_studio_home=None
    )
    assert len(assigns) == 1
    assert assigns[0]["client_id"] == "seayinsights"


def test_assign_project_client_emits_event(monkeypatch):
    import spool.writer as sw
    from core.clients import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    mutations.assign_project_client(project_id="p1", client_id="fulcrum")
    ev = captured[0]
    assert ev["event_type"] == "project.client_assigned"
    assert ev["payload"] == {"project_id": "p1", "client_id": "fulcrum"}
    assert ev["trace"]["project_id"] == "p1"


# ── backfill classifies + emits per project ─────────────────────────────────


def test_backfill_emits_assignment_per_null_project(tmp_path: Path, monkeypatch):
    from core.clients import backfill

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    _seed_project(conn, "p-ful", "Fulcrum Skill Library", path=r"C:\x\Fulcrum")
    _seed_project(conn, "p-ds", "Dream Studio", path=r"C:\x\dream-studio")
    _seed_project(conn, "p-has", "Already", client_id="seayinsights")  # not NULL -> skipped
    conn.commit()
    conn.close()

    assigns = []
    from core.clients import mutations

    # backfill imports assign_project_client from core.clients.mutations at call time.
    monkeypatch.setattr(
        mutations, "assign_project_client", lambda **kw: assigns.append(kw) or {"ok": True}
    )
    result = backfill.backfill_project_clients(db_path=db)
    got = {a["project_id"]: a["client_id"] for a in assigns}
    assert got == {"p-ful": "fulcrum", "p-ds": "seayinsights"}  # p-has skipped (already assigned)
    assert all(a["attribution_status"] == "backfill" for a in assigns)
    assert result["assigned"]["fulcrum"] == 1 and result["assigned"]["seayinsights"] == 1


# ── the round-table bug: classify by the repo under review, not the tool's own path ──


def test_classify_project_for_work_order_unwraps_a_worktree_to_its_repository(
    tmp_path: Path,
):
    """THE EXACT REPORTED BUG. The operator's own project_path for the mistagged project
    was a round-table review session's own working directory
    (``round-table/_reviews/plat-roundtable``) -- a worktree checked out there for a one-off
    inspection of Fulcrum's platform repo, which itself lives somewhere else entirely
    (``Fulcrum/platform``, per the operator's own correctly-tagged sibling project). The bare
    path has no "fulcrum" in it; the repository the worktree branches from does."""
    from core.clients.backfill import classify_project_for_work_order

    fulcrum_repo = _make_repo(tmp_path / "Fulcrum" / "platform")
    review_session = tmp_path / "round-table" / "_reviews" / "plat-roundtable"
    review_session.parent.mkdir(parents=True)
    _git(fulcrum_repo, "worktree", "add", "-q", "-b", "pr-under-review", str(review_session))

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    pid, wo = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_project(conn, pid, "plat-roundtable", path=str(review_session))
    _seed_work_order(conn, wo, pid)
    conn.commit()
    conn.close()

    assert classify_project_for_work_order(wo, db_path=db) == "fulcrum"
    # And the precondition that makes this a real fix: the bare heuristic alone, on the
    # worktree's own path, still gets it wrong.
    from core.clients.backfill import classify_project

    assert classify_project("plat-roundtable", str(review_session)) == "seayinsights"


def test_classify_project_for_work_order_tags_dream_studios_own_review_correctly(
    tmp_path: Path,
):
    """Round-table also reviews Dream Studio's own PRs -- the case a blanket
    ``round-table/ -> fulcrum`` mapping would have flipped the other way. A plain repository
    (not a worktree of something else) resolves through the same path unchanged, and must
    still land on whatever client Dream Studio's own project resolves to: SeayInsights, the
    registry default (`core.clients.queries.DEFAULT_CLIENT_ID`), confirmed independently by
    `test_classify_project`'s own ``("Dream Studio", ..., "seayinsights")`` case rather than
    assumed here by name alone."""
    from core.clients.backfill import classify_project_for_work_order
    from core.clients.queries import DEFAULT_CLIENT_ID

    assert DEFAULT_CLIENT_ID == "seayinsights"

    ds_repo = _make_repo(tmp_path / "round-table")  # the tool reviewing itself, at HEAD

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    pid, wo = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_project(conn, pid, "Dream Studio", path=str(ds_repo))
    _seed_work_order(conn, wo, pid)
    conn.commit()
    conn.close()

    assert classify_project_for_work_order(wo, db_path=db) == "seayinsights"


def test_classify_project_for_work_order_falls_back_with_nothing_resolvable(tmp_path: Path):
    """No project_path on record -- the genuinely standalone case -- returns None so the
    caller falls back to the bare heuristic, rather than inventing a guess."""
    from core.clients.backfill import classify_project_for_work_order

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    pid, wo = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_project(conn, pid, "No Path Project")  # path left NULL
    _seed_work_order(conn, wo, pid)
    conn.commit()
    conn.close()

    assert classify_project_for_work_order(wo, db_path=db) is None
    assert classify_project_for_work_order("no-such-work-order", db_path=db) is None


def test_reconcile_project_client_from_review_upgrades_a_default_tag(tmp_path, monkeypatch):
    """The live wiring `dispatch_review_round` calls: a project still sitting on the
    SeayInsights default (exactly the state `register_project`'s own blind default, or a
    prior backfill miss, leaves a mistagged round-table project in) is corrected once a real
    round-table dispatch resolves the worktree to its actual repository."""
    from core.clients import mutations
    from core.clients.backfill import reconcile_project_client_from_review
    from core.work_orders.project_roots import resolve_project_roots

    fulcrum_repo = _make_repo(tmp_path / "Fulcrum" / "platform")
    review_session = tmp_path / "round-table" / "_reviews" / "plat-roundtable"
    review_session.parent.mkdir(parents=True)
    _git(fulcrum_repo, "worktree", "add", "-q", "-b", "pr-under-review", str(review_session))

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    pid, wo = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_project(conn, pid, "plat-roundtable", client_id="seayinsights", path=str(review_session))
    _seed_work_order(conn, wo, pid)
    conn.commit()
    conn.close()

    assigns = []
    monkeypatch.setattr(
        mutations, "assign_project_client", lambda **kw: assigns.append(kw) or {"ok": True}
    )

    roots = resolve_project_roots(wo, db)
    result = reconcile_project_client_from_review(wo, roots, db_path=db)

    assert result == {"ok": True}
    assert assigns == [
        {"project_id": pid, "client_id": "fulcrum", "attribution_status": "backfill"}
    ]


def test_reconcile_project_client_from_review_never_overwrites_an_explicit_client(
    tmp_path, monkeypatch
):
    """The adversarial case round-table reviewing its OWN PRs would hit with a blanket
    mapping, generalised: a project already carrying a NON-default client is never silently
    reassigned, even when the resolved root disagrees with it -- this module has no way to
    tell a deliberate choice from a stale guess, so it must not guess."""
    from core.clients import mutations
    from core.clients.backfill import reconcile_project_client_from_review
    from core.work_orders.project_roots import resolve_project_roots

    fulcrum_repo = _make_repo(tmp_path / "Fulcrum" / "platform")
    review_session = tmp_path / "round-table" / "_reviews" / "plat-roundtable"
    review_session.parent.mkdir(parents=True)
    _git(fulcrum_repo, "worktree", "add", "-q", "-b", "pr-under-review", str(review_session))

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    pid, wo = str(uuid.uuid4()), str(uuid.uuid4())
    # Already explicitly on a DIFFERENT non-default client.
    _seed_project(conn, pid, "plat-roundtable", client_id="hypershift", path=str(review_session))
    _seed_work_order(conn, wo, pid)
    conn.commit()
    conn.close()

    assigns = []
    monkeypatch.setattr(
        mutations, "assign_project_client", lambda **kw: assigns.append(kw) or {"ok": True}
    )

    roots = resolve_project_roots(wo, db)
    result = reconcile_project_client_from_review(wo, roots, db_path=db)

    assert result is None
    assert assigns == []


def test_backfill_prefers_the_resolved_work_order_root_over_the_bare_project_path(
    tmp_path: Path, monkeypatch
):
    """`backfill_project_clients` wires the same preference in for the one-time
    migration-activation path: a NULL-client project with a work order on record is
    classified by the resolved root, not the bare project_path column."""
    from core.clients import backfill

    fulcrum_repo = _make_repo(tmp_path / "Fulcrum" / "platform")
    review_session = tmp_path / "round-table" / "_reviews" / "plat-roundtable"
    review_session.parent.mkdir(parents=True)
    _git(fulcrum_repo, "worktree", "add", "-q", "-b", "pr-under-review", str(review_session))

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    pid, wo = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_project(conn, pid, "plat-roundtable", path=str(review_session))  # client_id NULL
    _seed_work_order(conn, wo, pid)
    conn.commit()
    conn.close()

    assigns = []
    from core.clients import mutations

    monkeypatch.setattr(
        mutations, "assign_project_client", lambda **kw: assigns.append(kw) or {"ok": True}
    )

    result = backfill.backfill_project_clients(db_path=db)

    assert assigns == [
        {"project_id": pid, "client_id": "fulcrum", "attribution_status": "backfill"}
    ]
    assert result["assigned"] == {"fulcrum": 1}
