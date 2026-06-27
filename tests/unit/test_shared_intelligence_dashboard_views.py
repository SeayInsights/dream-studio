from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.dashboard_views import (
    learning_hardening_dashboard_view,
    validate_learning_hardening_dashboard_view,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "dashboard-learning-views" / "studio.db"


# test_learning_hardening_dashboard_view_composes_dashboard_sections removed —
# seed data relied on record_learning_event, record_hardening_candidate,
# record_hardening_validation, record_model_provider_profile — all deleted;
# backing tables dropped migration 131.


def test_learning_hardening_dashboard_view_empty_state_is_non_authoritative(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        view = learning_hardening_dashboard_view(conn, project_id="missing")

    assert validate_learning_hardening_dashboard_view(view) == []
    assert view["sections"]["lessons_learned"]["count"] == 0
    assert view["sections"]["attention_queue"]["empty_state"] == (
        "No learning or hardening attention items are pending."
    )
    assert db_path.is_file()
    assert db_path != live_db


def test_learning_hardening_dashboard_validator_rejects_authority_drift(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        view = learning_hardening_dashboard_view(conn)

    view["primary_authority"] = True
    view["execution_authorized"] = True

    assert validate_learning_hardening_dashboard_view(view) == [
        "primary_authority must be false",
        "execution_authorized must be false",
    ]
