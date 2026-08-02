"""Migration rollback-pairing gate — reversible authority migrations.

Every forward SQL migration numbered >= ROLLBACK_ENFORCED_FROM must ship a paired
reverse under ``core/event_store/migrations/rollback/`` sharing the same ``NNN_``
number, so a schema change to the authority can be undone. Migrations below the
cutover are grandfathered — the pre-154 chain predates this convention, is anchored
by the 142 baseline squash, and includes irreversible DROP migrations whose reverse
would only recreate an empty tombstoned table. See ``docs/migrations.md`` for the
convention and the grandfather rationale.

The check is invoked by the migration-risk pre-push gate (core/gates/migration_risk.py)
on migration-touching pushes; it is also runnable standalone.

Exit codes:
  0 — every enforced forward migration has a paired rollback
  1 — one or more enforced forward migrations are unpaired (names printed)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "core" / "event_store" / "migrations"
ROLLBACK_DIR = MIGRATIONS_DIR / "rollback"

# First forward-migration number that requires a paired rollback. Everything below
# this is grandfathered (the pre-154 chain predates the convention — see the module
# docstring and docs/migrations.md). Bump this only with a documented rationale.
ROLLBACK_ENFORCED_FROM = 154

_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")


def _migration_number(name: str) -> int | None:
    match = _MIGRATION_RE.match(name)
    return int(match.group(1)) if match else None


def find_unpaired_migrations(
    migrations_dir: Path = MIGRATIONS_DIR,
    rollback_dir: Path | None = None,
    enforced_from: int = ROLLBACK_ENFORCED_FROM,
) -> list[str]:
    """Return forward-migration filenames >= ``enforced_from`` that lack a paired
    rollback (a ``rollback/<same-number>_*.sql``), sorted by filename.

    Pairing is by migration NUMBER, not full filename — one reverse per forward
    number. The forward glob is non-recursive, so the ``rollback/`` subdir is never
    mistaken for a forward migration.
    """
    rollback_dir = rollback_dir if rollback_dir is not None else migrations_dir / "rollback"
    rollback_numbers: set[int] = set()
    if rollback_dir.is_dir():
        for path in rollback_dir.glob("*.sql"):
            number = _migration_number(path.name)
            if number is not None:
                rollback_numbers.add(number)

    unpaired: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        number = _migration_number(path.name)
        if number is None or number < enforced_from:
            continue
        if number not in rollback_numbers:
            unpaired.append(path.name)
    return unpaired


def main() -> int:
    unpaired = find_unpaired_migrations()
    if not unpaired:
        return 0
    print("MIGRATION ROLLBACK PAIRING: unpaired forward migration(s) found")
    print(f"Every forward migration >= {ROLLBACK_ENFORCED_FROM} needs a paired reverse in")
    print(f"  {ROLLBACK_DIR.relative_to(REPO_ROOT)}/<same NNN_>*.sql")
    for name in unpaired:
        print(f"  MISSING rollback for: {name}")
    print("See docs/migrations.md for the convention.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
