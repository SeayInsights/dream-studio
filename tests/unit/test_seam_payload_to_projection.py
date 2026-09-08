"""Seam contract: every key the emitter puts in a payload must reach the projection.

THE SEAM. ``create_work_order`` builds a ``work_order.created`` payload;
``WorkOrderProjection._handle_created`` reads it into ``business_work_orders``. Nothing
connected the two. The emitter did not carry ``description`` and the projection did not
read it, so everything an author typed was accepted and discarded -- 443 of 920 work
orders on the live authority with an empty description, and with it any chance of
declaring the ``Module boundary:`` clause that edit attribution matches against. The rule
was not unenforced; its input could not be supplied.

WHY THIS TEST IS SHAPED THIS WAY. The first version of this check asserted on SOURCE TEXT
-- that ``'"description": payload.get("description")'`` appeared in the projection file.
That proves a string is present, not that a value survives. It would pass against a
projection whose INSERT silently dropped the column, and it says nothing at all about the
NEXT field someone adds.

So the payload key set is derived from the emitter by parsing it, and the row is produced
by running the real projection against a real bootstrapped schema. Add a key to the
emitter and this test demands the projection account for it, without anyone remembering
to come here. That is the difference between a contract and a comment.

The schema comes from ``bootstrap_database`` rather than a fixture DDL for the same
reason: the hand-copied fixture in ``test_phase18_1_5_work_order_projection.py`` omitted
``description``, so the projection that wrote it failed only against the copy. A fixture
narrower than production reports a defect the product does not have -- and hides the one
it does.
"""

from __future__ import annotations

import ast
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.projections.work_order_projection import WorkOrderProjection

REPO_ROOT = Path(__file__).resolve().parents[2]
EMITTER_PATH = REPO_ROOT / "core" / "work_orders" / "mutations.py"

#: Payload keys the projection deliberately does not persist as a value, each with the
#: reason. A key may be added here only when NOT storing it is the correct behaviour --
#: never to quiet this test. `status` is the real example: the projection derives status
#: from the event TYPE, because a payload that says "created" on a `work_order.closed`
#: event must not be able to reopen a closed work order.
_DECLARED_UNPERSISTED = {
    "status": (
        "status is derived from the event type, not the payload -- otherwise a stale or"
        " hostile payload value could contradict the event that carried it"
    ),
}


def _emitter_payload_keys() -> set[str]:
    """The keys ``create_work_order`` actually puts in its payload.

    Parsed from the emitter rather than listed here, so a key added there is picked up
    without anyone having to remember this file exists.
    """
    tree = ast.parse(EMITTER_PATH.read_text(encoding="utf-8"))
    func = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "create_work_order"
        ),
        None,
    )
    assert func is not None, "create_work_order is gone -- this seam no longer exists"

    keys: set[str] = set()
    for node in ast.walk(func):
        # `_payload: dict[str, Any] = {"title": title, ...}`
        if isinstance(node, ast.AnnAssign | ast.Assign) and isinstance(node.value, ast.Dict):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "_payload" for t in targets):
                keys |= {
                    k.value
                    for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
        # `_payload["description"] = ...`
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "_payload"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    keys.add(target.slice.value)
    assert keys, "no payload keys found -- the parser has drifted from the emitter"
    return keys


@pytest.fixture
def authority(tmp_path: Path) -> sqlite3.Connection:
    """A real database, built by the real migration chain. Never a fixture DDL."""
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _created_event(work_order_id: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "work_order.created",
        "event_timestamp": "2026-09-07T12:00:00+00:00",
        "trace": {},
        "payload": {"work_order_id": work_order_id, **payload},
        "correlation_id": None,
        "project_id": "proj-seam",
        "work_order_id": work_order_id,
        "_source": "business",
    }


def test_the_emitter_and_the_projection_agree_on_every_payload_key(authority):
    """Each key the emitter sends must survive into the row, or be declared unpersisted."""
    keys = _emitter_payload_keys()
    # A distinctive value per key, so "did it survive" is answered by looking for the
    # value rather than by guessing which column it maps to. `type` becomes
    # `work_order_type`; matching on names would have to encode that mapping and would
    # then be wrong the next time a column is renamed.
    payload = {key: f"seam-{key}-value" for key in keys}
    work_order_id = "wo-seam-0001"

    projection = WorkOrderProjection()
    projection.setup_tables(authority)
    projection.handle(_created_event(work_order_id, payload), authority)

    row = authority.execute(
        "SELECT * FROM business_work_orders WHERE work_order_id = ?", (work_order_id,)
    ).fetchone()
    assert row is not None, "the projection did not materialize the work order at all"

    stored = {str(value) for value in tuple(row) if value is not None}
    lost = sorted(
        key for key in keys if key not in _DECLARED_UNPERSISTED and payload[key] not in stored
    )
    assert not lost, (
        f"The emitter sends {lost} and the projection stores none of it. Every payload key"
        " must either land in business_work_orders or be listed in _DECLARED_UNPERSISTED"
        " with the reason NOT storing it is correct. This is the exact shape that dropped"
        " `description` for 443 of 920 work orders and made the module boundary"
        " unsupplyable."
    )


def test_description_specifically_survives_the_round_trip(authority):
    """The field whose loss made edit attribution guess, asserted on the value itself."""
    projection = WorkOrderProjection()
    projection.setup_tables(authority)
    described = "Fix the drift check.\n\nModule boundary: interfaces/cli/commands, core/gates."
    projection.handle(
        _created_event(
            "wo-seam-0002", {"title": "t", "type": "documentation", "description": described}
        ),
        authority,
    )

    row = authority.execute(
        "SELECT description FROM business_work_orders WHERE work_order_id = ?", ("wo-seam-0002",)
    ).fetchone()
    assert row["description"] == described


def test_the_stored_description_is_readable_by_the_real_boundary_parser(authority):
    """The full chain: emitter format -> projection row -> the parser attribution uses.

    Storing the description is only half the seam. The clause inside it has to come back
    out in the form ``runtime/lib/enforcement.py`` parses, or attribution still guesses.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "enforcement_seam", REPO_ROOT / "runtime" / "lib" / "enforcement.py"
    )
    enforcement = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(enforcement)

    from core.work_orders.mutations import compose_module_boundary

    described = compose_module_boundary("Add the guardrails.", ["core/gates", "tests/unit"])
    projection = WorkOrderProjection()
    projection.setup_tables(authority)
    projection.handle(
        _created_event(
            "wo-seam-0003", {"title": "t", "type": "documentation", "description": described}
        ),
        authority,
    )

    row = authority.execute(
        "SELECT description FROM business_work_orders WHERE work_order_id = ?", ("wo-seam-0003",)
    ).fetchone()
    assert enforcement.boundary_globs(row["description"]) == ["core/gates", "tests/unit"]


def test_every_declared_exception_states_a_reason():
    """An exception list without reasons becomes a place to hide keys."""
    for key, reason in _DECLARED_UNPERSISTED.items():
        assert len(reason) > 40, f"{key} is declared unpersisted without a real reason"


def test_declared_exceptions_are_still_sent_by_the_emitter():
    """A stale exception is worse than none: it silently covers a future key of that name."""
    keys = _emitter_payload_keys()
    stale = sorted(set(_DECLARED_UNPERSISTED) - keys)
    assert not stale, (
        f"{stale} is declared unpersisted but the emitter no longer sends it. Remove the"
        " entry, or a future payload key of the same name is exempted by accident."
    )


def test_the_projection_ignores_a_payload_status_on_a_closed_event(authority):
    """The reason `status` is declared unpersisted, asserted rather than asserted-about.

    If the projection took status from the payload, a `work_order.closed` event carrying
    `status: created` would reopen a closed work order.
    """
    projection = WorkOrderProjection()
    projection.setup_tables(authority)
    projection.handle(
        _created_event("wo-seam-0004", {"title": "t", "type": "documentation"}), authority
    )
    closed = _created_event("wo-seam-0004", {"status": "created"})
    closed["event_type"] = "work_order.closed"
    projection.handle(closed, authority)

    row = authority.execute(
        "SELECT status FROM business_work_orders WHERE work_order_id = ?", ("wo-seam-0004",)
    ).fetchone()
    assert row["status"] == "closed", (
        "a payload status overrode the event type -- a stale payload can now reopen a"
        " closed work order"
    )


def test_the_canonical_event_payload_is_json_serializable():
    """The seam runs through JSON, so a key whose value is not serializable never arrives."""
    keys = _emitter_payload_keys()
    json.dumps({key: f"seam-{key}" for key in keys})
