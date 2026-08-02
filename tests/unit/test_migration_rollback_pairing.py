"""R3 — reversible authority migrations: the rollback-pairing gate.

Every forward migration >= ROLLBACK_ENFORCED_FROM (154) must have a paired reverse
under core/event_store/migrations/rollback/. Migrations <= 153 are grandfathered.
See docs/migrations.md and core/gates/migration_rollback_pairing.py.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.migration_rollback_pairing import (
    ROLLBACK_ENFORCED_FROM,
    find_unpaired_migrations,
)


def test_every_forward_migration_has_rollback():
    """The live migrations tree has no unpaired forward migration in the enforced
    range (>= 154). Grandfathered migrations (<= 153) must NOT be flagged."""
    assert find_unpaired_migrations() == []


def _write(path: Path, text: str = "-- sql\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_unpaired_enforced_migration_is_detected(tmp_path: Path):
    """A forward migration in the enforced range without a paired rollback fails;
    adding the rollback makes it pass; a grandfathered (< cutover) one never fails."""
    migrations = tmp_path / "migrations"
    rollback = migrations / "rollback"

    # Grandfathered forward migration (< cutover), deliberately unpaired.
    _write(migrations / "153_grandfathered.sql")
    # Enforced forward migration (>= cutover), initially unpaired.
    _write(migrations / f"{ROLLBACK_ENFORCED_FROM}_new_change.sql")

    unpaired = find_unpaired_migrations(migrations, rollback, ROLLBACK_ENFORCED_FROM)
    assert unpaired == [f"{ROLLBACK_ENFORCED_FROM}_new_change.sql"], unpaired

    # Pair it (match is by number, not exact filename) → now clean.
    _write(rollback / f"{ROLLBACK_ENFORCED_FROM}_new_change.sql", "-- reverse\n")
    assert find_unpaired_migrations(migrations, rollback, ROLLBACK_ENFORCED_FROM) == []


def test_rollback_subdir_is_not_treated_as_a_forward_migration(tmp_path: Path):
    """A numbered file living only under rollback/ must never be reported as an
    unpaired forward migration (the forward glob is non-recursive)."""
    migrations = tmp_path / "migrations"
    rollback = migrations / "rollback"
    _write(rollback / f"{ROLLBACK_ENFORCED_FROM}_orphan.sql", "-- reverse\n")

    assert find_unpaired_migrations(migrations, rollback, ROLLBACK_ENFORCED_FROM) == []
