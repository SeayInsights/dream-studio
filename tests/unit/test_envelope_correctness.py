"""A0.3 — envelope correctness for work-order and milestone lifecycle events.

Pre-A0, the hand-built dict emissions in ``core/work_orders/start.py``,
``core/work_orders/close.py``, and ``core/milestones/close.py`` omitted
``schema_version``. The ingestor (``spool/ingestor.py:23-25``) requires
it, so those events routed to ``failed/`` with reason
``missing_fields: ['schema_version']``.

These tests pin the post-A0 contract: every event the three lifecycle
modules emit must:

  1. Include every field in ``REQUIRED_FIELDS`` (event_id, event_type,
     timestamp, schema_version).
  2. Use an ``event_type`` registered in ``canonical/events/types.py``.
  3. Pass ``validate_envelope()`` with zero errors.

The pattern is: monkeypatch ``spool.writer.write_event`` to capture the
envelope dict, drive the lifecycle code path with seeded SQLite + a
fake ``resolve_installed_runtime_paths``, then assert against each
captured envelope. The actual spool writer never runs, so this is a
unit test (no I/O against the operator's real spool root).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canonical.events.envelope import REQUIRED_FIELDS, validate_envelope
from canonical.events.types import ALL_EVENT_TYPES
from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-env-corr-0001"
MILESTONE_ID = "ms-env-corr-0001"
WO_ID = "wo-env-corr-0001"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Env Corr Project", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, '', 'active', 0, ?, ?)",
            (MILESTONE_ID, PROJECT_ID, "First", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'created', 'api_endpoint', ?, ?)",
            (WO_ID, PROJECT_ID, MILESTONE_ID, "WO", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


@pytest.fixture
def captured_envelopes(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replace ``spool.writer.write_event`` with a capture-only stub.

    Each lifecycle module re-imports the writer inside its try/except
    block, so the monkeypatch must target the module-level attribute
    on ``spool.writer`` itself.
    """

    captured: list[dict] = []

    def _capture(envelope, root=None):  # noqa: ARG001 — match writer signature
        captured.append(dict(envelope))
        return Path("/dev/null")  # writer normally returns the dest path

    import spool.writer as _writer

    monkeypatch.setattr(_writer, "write_event", _capture)
    return captured


def _assert_envelope_well_formed(envelope: dict) -> None:
    """Each emitted envelope must satisfy the canonical contract."""

    # 1. REQUIRED_FIELDS present.
    missing = REQUIRED_FIELDS - set(envelope)
    assert not missing, f"missing required fields: {missing!r} in envelope: {envelope!r}"

    # 2. event_type is registered in the canonical taxonomy.
    assert (
        envelope["event_type"] in ALL_EVENT_TYPES
    ), f"unregistered event_type: {envelope['event_type']!r}"

    # 3. validate_envelope reports zero errors.
    errors = validate_envelope(envelope)
    assert errors == [], f"validate_envelope errors: {errors!r}"


# ── work_orders.start emits `work_order.started` ─────────────────────────────


def test_start_work_order_emits_well_formed_envelope(
    patched_paths, tmp_path: Path, captured_envelopes: list[dict]
) -> None:
    from core.work_orders.start import start_work_order

    result = start_work_order(
        work_order_id=WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True

    started = [e for e in captured_envelopes if e["event_type"] == "work_order.started"]
    assert len(started) == 1, f"expected 1 work_order.started envelope, got {len(started)}"
    _assert_envelope_well_formed(started[0])

    # Payload preserved from the pre-A0 hand-built dict.
    payload = started[0]["payload"]
    assert payload["work_order_id"] == WO_ID
    assert payload["project_id"] == PROJECT_ID


# ── work_orders.close emits `work_order.closed` + (force) `gate.bypassed` ────


def _seed_passing_artifacts(tmp_path: Path) -> None:
    """No gates configured for the api_endpoint WO in this fixture's WO type,
    so we don't actually need artifacts to close — but the fixture's WO is
    api_endpoint, which has both pre and post gates. Use ``force=True`` instead
    so we exercise both ``gate.bypassed`` and ``work_order.closed``."""


def test_close_work_order_force_emits_well_formed_envelopes(
    patched_paths, db_path: Path, tmp_path: Path, captured_envelopes: list[dict]
) -> None:
    from core.work_orders.close import close_work_order

    # Move the WO to in_progress so close has something to mutate.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET status = 'in_progress' WHERE work_order_id = ?",
        (WO_ID,),
    )
    conn.commit()
    conn.close()

    result = close_work_order(
        work_order_id=WO_ID,
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["forced"] is True

    bypassed = [e for e in captured_envelopes if e["event_type"] == "gate.bypassed"]
    closed = [e for e in captured_envelopes if e["event_type"] == "work_order.closed"]

    assert len(bypassed) >= 1, "expected at least one gate.bypassed envelope"
    assert len(closed) == 1, f"expected 1 work_order.closed envelope, got {len(closed)}"

    for env in bypassed:
        _assert_envelope_well_formed(env)
        assert env["severity"] == "warning"
        assert env["payload"]["work_order_id"] == WO_ID

    _assert_envelope_well_formed(closed[0])
    assert closed[0]["payload"]["forced"] is True


# ── milestones.close emits `milestone.completed` + (force) `gate.bypassed` ───


def test_close_milestone_force_emits_well_formed_envelopes(
    patched_paths, db_path: Path, tmp_path: Path, captured_envelopes: list[dict]
) -> None:
    from core.milestones.close import close_milestone

    # All WOs must be complete for close_milestone to proceed.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET status = 'closed' WHERE work_order_id = ?",
        (WO_ID,),
    )
    conn.commit()
    conn.close()

    result = close_milestone(
        milestone_id=MILESTONE_ID,
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["forced"] is True

    bypassed = [e for e in captured_envelopes if e["event_type"] == "gate.bypassed"]
    completed = [e for e in captured_envelopes if e["event_type"] == "milestone.completed"]

    # api_endpoint WO → no UI → CWV not required; design-audit / security-audit /
    # harden-results are still required. Without artifacts, all three fail —
    # force bypasses them.
    assert len(bypassed) >= 1
    assert len(completed) == 1

    for env in bypassed:
        _assert_envelope_well_formed(env)
        assert env["severity"] == "warning"
        assert env["payload"]["milestone_id"] == MILESTONE_ID

    _assert_envelope_well_formed(completed[0])
    assert completed[0]["payload"]["milestone_id"] == MILESTONE_ID
    assert completed[0]["payload"]["forced"] is True


# ── envelope.to_dict() includes source_type (A0 schema preservation) ─────────


def test_canonical_envelope_to_dict_includes_source_type() -> None:
    """A0 added ``source_type`` to ``CanonicalEventEnvelope``. Pin the
    dataclass shape so future refactors don't drop it silently — the
    canonical event JSON schema treats it as a recognized field."""

    from canonical.events.envelope import CanonicalEventEnvelope

    env = CanonicalEventEnvelope(
        event_type="work_order.started",
        session_id=None,
        payload={"work_order_id": "wo-x"},
    )
    d = env.to_dict()
    assert "source_type" in d
    assert d["source_type"] == "confirmed"
