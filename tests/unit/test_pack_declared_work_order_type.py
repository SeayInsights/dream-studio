"""A pack declares a work-order type in its manifest and gets a work order of that type that can be
created, started, reviewed as its declared artifact class, and closed. Core is never edited.

THE ACCEPTANCE TEST FOR THE SLICE (issue #897). Everything in this file runs against a fake
pack manifest in a temp directory, applied with ``scoped_pack_manifest``: no built-in is
touched, no migration is added, no ``business_work_order_types`` row is written for the type,
and the registry is what it was when each test ends.

The lifecycle is driven through the same functions the CLI and the MCP server call
(``create_work_order``, ``start_work_order``, ``close_work_order``), not through the registry:
a registry that answers correctly proves nothing about whether a door honours the answer.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders import type_registry
from core.work_orders.type_registry import scoped_pack_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-20T00:00:00+00:00"
PROMPT = (
    "Review the master services agreement for completeness and accuracy against the order form,"
    " because the renewal terms were edited by hand and nobody has checked them since."
)

MANIFEST = """\
schema_version: 2
packs:
  legal:
    description: Contract and policy review
    skill: legal
    modes: [review]
    contributes:
      work_order_types:
        - name: contract_review
          artifact_class: document
          description: Reviewing a contract or policy for completeness and accuracy
          ui_bearing: false
          exempt_from_verification: false
        - name: compliance_report
          artifact_class: data
          description: A compliance extract the live dashboard must agree with
          ui_bearing: false
          dashboard_truth_gated: true
          exempt_from_verification: true
"""

#: The operator allows the legal pack to declare an exemption (compliance_report is exempt).
TRUSTED = frozenset({"legal"})


@pytest.fixture
def packs_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "pack-home" / "packs.yaml"
    path.parent.mkdir()
    path.write_text(MANIFEST, encoding="utf-8")
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def db_path(home: Path) -> Path:
    target = home / "studio.db"
    bootstrap_database(target)
    return target


@pytest.fixture
def patched_paths(db_path: Path, home: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = home
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


def _scalar(db_path: Path, sql: str, *params: object):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _seed_project_and_milestone(db_path: Path) -> tuple[str, str]:
    project_id, milestone_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, 'Legal', '', 'active', ?, ?)",
            (project_id, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
            " VALUES (?, ?, 'Renewal review', 'active', 0, ?, ?)",
            (milestone_id, project_id, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id, milestone_id


def _create(db_path: Path, home: Path, project_id: str, milestone_id: str, wo_type: str) -> dict:
    """Create a work order through the door, and project the event it emits into the DB.

    The door writes an event and a projection materialises the row. Capturing the event and
    replaying it through the real WorkOrderProjection keeps the whole path: the type is
    admitted by create_work_order, carried in the event, and read back off the projected row.
    """
    from core.projections.work_order_projection import WorkOrderProjection
    from core.work_orders.mutations import create_work_order

    captured: list[dict] = []
    with patch("spool.writer.write_event", side_effect=lambda d, root=None: captured.append(d)):
        result = create_work_order(
            project_id=project_id,
            milestone_id=milestone_id,
            title=f"A {wo_type} work order",
            description=PROMPT,
            work_order_type=wo_type,
            source_root=REPO_ROOT,
            dream_studio_home=home,
        )
    if result.get("ok"):
        created = next(e for e in captured if e["event_type"] == "work_order.created")
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "work_order.created",
            "event_timestamp": NOW,
            "trace": created["trace"],
            "payload": {**created["payload"], "work_order_id": result["work_order_id"]},
            "correlation_id": None,
            "project_id": project_id,
            "milestone_id": milestone_id,
            "work_order_id": result["work_order_id"],
            "_source": "business",
        }
        proj = WorkOrderProjection()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            proj.handle(event, conn)
            conn.commit()
        finally:
            conn.close()
    return result


def _add_tasks(db_path: Path, project_id: str, work_order_id: str, *, done: bool) -> None:
    """Two executable tasks: the close gates refuse one task, and a task with no check."""
    conn = sqlite3.connect(str(db_path))
    try:
        for n in (1, 2):
            conn.execute(
                "INSERT INTO business_tasks"
                " (task_id, work_order_id, project_id, title, status, acceptance_criteria,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'SQL-CHECK: SELECT 1', ?, ?)",
                (
                    str(uuid.uuid4()),
                    work_order_id,
                    project_id,
                    f"Task {n}",
                    "complete" if done else "pending",
                    NOW,
                    NOW,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_sibling(db_path: Path, project_id: str, milestone_id: str) -> None:
    """A milestone must carry more than one work order to close one of them."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
            "  status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Sibling', ?, 'documentation', 'created', ?, ?)",
            (str(uuid.uuid4()), project_id, milestone_id, PROMPT, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _affirm_impact(db_path: Path, work_order_id: str) -> None:
    """The universal change_impact_affirmed gate: a work order created now must record it."""
    from core.gates.change_impact import affirm_change_impact

    assert affirm_change_impact(work_order_id, touched=(), note="fixture", db_path=db_path)


def _dispatch_clean_review(db_path: Path, work_order_id: str) -> None:
    from core.work_orders.review_answers import record_dispatch

    record_dispatch(
        work_order_id,
        sha="0" * 40,
        image="test",
        change_set=[],
        assignments=[],
        db_path=db_path,
    )


def test_the_type_is_not_a_built_in_and_has_no_row_so_the_test_proves_what_it_claims(
    packs_yaml, db_path
):
    """The premise. Without this the lifecycle below could pass for the wrong reason: because
    the type was already known, or because a row had been seeded for it."""
    from core.work_orders.type_registry import builtin_work_order_type_names

    assert "contract_review" not in builtin_work_order_type_names()
    assert _scalar(db_path, "SELECT COUNT(*) FROM business_work_order_types") == 10
    assert (
        _scalar(
            db_path,
            "SELECT COUNT(*) FROM business_work_order_types WHERE type_id = 'contract_review'",
        )
        == 0
    )
    assert type_registry.get_work_order_type("contract_review") is None, "declared by nothing yet"


def test_a_pack_declared_type_is_created_started_reviewed_and_closed(
    packs_yaml, patched_paths, db_path, home
):
    from core.work_orders.close import close_work_order
    from core.work_orders.review_rules import (
        DOCUMENT_STANDARDS,
        artifact_kind,
        render_rules_block,
        resolve_review_rules,
    )
    from core.work_orders.start import start_work_order

    project_id, milestone_id = _seed_project_and_milestone(db_path)
    _seed_sibling(db_path, project_id, milestone_id)

    # Before the manifest is applied the door refuses the type, and says what it knows.
    refused = _create(db_path, home, project_id, milestone_id, "contract_review")
    assert refused["ok"] is False and "contract_review" in refused["error"]

    with scoped_pack_manifest(packs_yaml, trusted=TRUSTED):
        # CREATED, through the door the CLI and MCP share.
        created = _create(db_path, home, project_id, milestone_id, "contract_review")
        assert created["ok"] is True, created
        wo_id = created["work_order_id"]
        assert (
            _scalar(
                db_path,
                "SELECT work_order_type FROM business_work_orders WHERE work_order_id = ?",
                wo_id,
            )
            == "contract_review"
        )
        _add_tasks(db_path, project_id, wo_id, done=False)

        # STARTED, with no business_work_order_types row for it and no migration.
        started = start_work_order(
            work_order_id=wo_id,
            source_root=REPO_ROOT,
            dream_studio_home=home,
            planning_root=home / ".planning",
        )
        assert started["ok"] is True, started
        assert (
            _scalar(
                db_path,
                "SELECT COUNT(*) FROM business_work_order_types"
                " WHERE type_id = 'contract_review'",
            )
            == 0
        ), "starting a declared type must not write a row: the manifest is the declaration"
        assert (
            _scalar(
                db_path, "SELECT status FROM business_work_orders WHERE work_order_id = ?", wo_id
            )
            == "in_progress"
        )

        # REVIEWED AS ITS DECLARED CLASS: a document, so judged on completeness, accuracy and
        # stale description, and not on code-only standards such as dead code.
        row_type = _scalar(
            db_path,
            "SELECT work_order_type FROM business_work_orders WHERE work_order_id = ?",
            wo_id,
        )
        assert artifact_kind(row_type) == "document"
        rules = resolve_review_rules(work_order_type=row_type).rules
        assert all(standard in rules for standard in DOCUMENT_STANDARDS)
        assert not any(rule.startswith("NO DEAD CODE") for rule in rules)
        assert "COMPLETENESS" in render_rules_block(resolve_review_rules(work_order_type=row_type))

        # CLOSED. A document type that is not exempt runs independent review at close.
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE business_tasks SET status = 'complete' WHERE work_order_id = ?", (wo_id,)
            )
            conn.execute(
                "UPDATE business_work_orders SET status = 'pushed' WHERE work_order_id = ?",
                (wo_id,),
            )
            conn.commit()
        finally:
            conn.close()
        _dispatch_clean_review(db_path, wo_id)
        _affirm_impact(db_path, wo_id)
        closed = close_work_order(
            work_order_id=wo_id,
            source_root=REPO_ROOT,
            dream_studio_home=home,
            planning_root=home / ".planning",
        )
        assert closed["ok"] is True, closed
        assert (
            _scalar(
                db_path, "SELECT status FROM business_work_orders WHERE work_order_id = ?", wo_id
            )
            == "closed"
        )

    # The registry is what it was: nothing leaked out of the scope.
    assert type_registry.get_work_order_type("contract_review") is None


def test_a_type_the_manifest_flagged_for_dashboard_truth_is_held_to_it_at_close(
    packs_yaml, patched_paths, db_path, home
):
    """The flag a pack sets in its manifest reaches the close gate, which used to name its
    types in a literal set only core could edit."""
    from core.work_orders.close import close_work_order

    failing = {
        "ok": False,
        "results": [{"name": "token_model_null_fraction", "passed": False, "error": None}],
    }
    project_id, milestone_id = _seed_project_and_milestone(db_path)
    _seed_sibling(db_path, project_id, milestone_id)

    def close_failures(wo_type: str) -> list[str]:
        created = _create(db_path, home, project_id, milestone_id, wo_type)
        assert created["ok"] is True, created
        wo_id = created["work_order_id"]
        _add_tasks(db_path, project_id, wo_id, done=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE business_work_orders SET status = 'pushed' WHERE work_order_id = ?",
                (wo_id,),
            )
            conn.commit()
        finally:
            conn.close()
        with patch("core.gates.dashboard_truth.run_dashboard_truth", return_value=failing):
            result = close_work_order(
                work_order_id=wo_id,
                source_root=REPO_ROOT,
                dream_studio_home=home,
                planning_root=home / ".planning",
            )
        return result.get("failures", [])

    with scoped_pack_manifest(packs_yaml, trusted=TRUSTED):
        assert any("dashboard_truth" in f for f in close_failures("compliance_report"))
        assert not any("dashboard_truth" in f for f in close_failures("contract_review"))


def test_removing_the_manifest_leaves_the_work_order_readable_closable_and_unstartable(
    packs_yaml, patched_paths, db_path, home
):
    """A work order of a pack type outlives the pack's manifest. Reading it never asked the
    registry, so it is still readable; starting it refuses with a message that names the
    cause; closing it treats the type as undeclared (strictest defaults), so it can still be
    closed through the gates rather than being stranded."""
    from core.work_orders.close import close_work_order
    from core.work_orders.queries import list_work_orders
    from core.work_orders.start import start_work_order

    project_id, milestone_id = _seed_project_and_milestone(db_path)
    _seed_sibling(db_path, project_id, milestone_id)
    with scoped_pack_manifest(packs_yaml, trusted=TRUSTED):
        created = _create(db_path, home, project_id, milestone_id, "contract_review")
        assert created["ok"] is True, created
        wo_id = created["work_order_id"]
    _add_tasks(db_path, project_id, wo_id, done=False)

    # The manifest is gone (the scope ended): the type is undeclared again.
    assert type_registry.get_work_order_type("contract_review") is None

    listed = list_work_orders(project_id=project_id, source_root=REPO_ROOT, dream_studio_home=home)
    assert wo_id in {w["id"] for w in listed["work_orders"]}, "still readable"

    refused = start_work_order(
        work_order_id=wo_id,
        source_root=REPO_ROOT,
        dream_studio_home=home,
        planning_root=home / ".planning",
    )
    assert refused["ok"] is False
    assert "contract_review" in refused["error"]
    assert "manifest" in refused["error"], "the message names the cause, not just the symptom"

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE business_tasks SET status = 'complete' WHERE work_order_id = ?", (wo_id,)
        )
        conn.execute(
            "UPDATE business_work_orders SET status = 'pushed' WHERE work_order_id = ?", (wo_id,)
        )
        conn.commit()
    finally:
        conn.close()
    _dispatch_clean_review(db_path, wo_id)
    _affirm_impact(db_path, wo_id)
    closed = close_work_order(
        work_order_id=wo_id,
        source_root=REPO_ROOT,
        dream_studio_home=home,
        planning_root=home / ".planning",
    )
    assert closed["ok"] is True, closed


def test_project_state_labels_a_pack_declared_type_that_has_no_row(
    packs_yaml, patched_paths, db_path, home
):
    """`ds project state` joins business_work_order_types for the label; a type with no row
    would show None. The label is derived from the declaration instead."""
    from core.projects.queries import get_project_state

    project_id, milestone_id = _seed_project_and_milestone(db_path)
    with scoped_pack_manifest(packs_yaml, trusted=TRUSTED):
        created = _create(db_path, home, project_id, milestone_id, "contract_review")
        assert created["ok"] is True, created
        state = get_project_state(
            source_root=REPO_ROOT, dream_studio_home=home, planning_root=home / ".planning"
        )
    nxt = state["projects"][0]["next_work_order"]
    assert nxt["work_order_id"] == created["work_order_id"]
    assert nxt["type"] == "contract_review" and nxt["type_label"] == "Contract Review"
