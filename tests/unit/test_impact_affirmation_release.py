"""WO 6a1722d9 — the change_impact_affirmed gate must stay satisfiable.

Root cause: #575 shipped migration 154 (adds the ``impact_affirmation`` artifact kind) AND
the change_impact_affirmed close gate that requires it, but never bumped
``core/event_store/migrations/.released_version``. So 154 stayed unreleased on live authority
DBs, the kind was absent from the CHECK, and every post-cutover WO's affirm-impact failed with
a raw CHECK error — blocking close.

Two invariants guard against recurrence:
  1. The migration that backs the (calendar-active) gate is released.
  2. The artifact write path degrades to a no-op False on a stale CHECK, never a raw raise.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import released_migration_version

# The migration that adds the ``impact_affirmation`` artifact kind (core/event_store/
# migrations/154_wo_artifacts_impact_affirmation.sql). The change_impact_affirmed gate is
# active by calendar (IMPACT_AFFIRM_ENFORCED_AFTER=2026-08-02, already past), so this
# migration MUST be released for the gate to be satisfiable.
IMPACT_AFFIRMATION_MIGRATION = 154


def test_affirmation_migration_released_and_write_degrades_gracefully(tmp_path: Path):
    # 1. The gate's backing migration is released (not "unreleased" on live DBs).
    assert released_migration_version() >= IMPACT_AFFIRMATION_MIGRATION, (
        "migration that adds impact_affirmation is unreleased while the change_impact_affirmed "
        "gate is active by calendar — affirm-impact cannot store, close is blocked"
    )

    # 2. set_wo_artifact returns False (no raise) when the table's CHECK rejects the kind —
    #    the stale-schema case an unreleased migration would produce.
    from core.work_orders.artifacts import set_wo_artifact

    db = tmp_path / "stale.db"
    conn = sqlite3.connect(str(db))
    try:
        # A business_work_order_artifacts table whose CHECK predates impact_affirmation.
        conn.execute(
            "CREATE TABLE business_work_order_artifacts ("
            " work_order_id TEXT NOT NULL, kind TEXT NOT NULL"
            "   CHECK (kind IN ('report')),"
            " instance_key TEXT NOT NULL DEFAULT '',"
            " content TEXT, created_at TEXT, updated_at TEXT,"
            " PRIMARY KEY (work_order_id, kind, instance_key))"
        )
        conn.commit()
    finally:
        conn.close()

    stored = set_wo_artifact("wo-x", "impact_affirmation", "body", db_path=db)
    assert stored is False, "stale-CHECK write must return False (no-op), not raise IntegrityError"
