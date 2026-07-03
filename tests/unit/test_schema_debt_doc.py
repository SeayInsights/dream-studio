"""Guard: the aspirational-schema-debt log must not lag the migration chain.

The fcd8cf14 independent review found docs/architecture/aspirational-schema-debt.md
stuck at migration 120 while the chain had reached 136. Every migration lands with
a dated review entry in that document; this test fails the moment a new migration
merges without one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "architecture" / "aspirational-schema-debt.md"


def test_schema_debt_doc_mentions_latest_migration():
    from core.config.sqlite_bootstrap import latest_migration_version

    latest = latest_migration_version()
    text = DOC.read_text(encoding="utf-8")
    mentioned = {int(n) for n in re.findall(r"migrations?\s+(\d{2,3})", text)}
    # Ranges like "migrations 134-136" only capture the first number; expand them.
    for start, end in re.findall(r"migrations?\s+(\d{2,3})-(\d{2,3})", text):
        mentioned.update(range(int(start), int(end) + 1))
    assert latest in mentioned, (
        f"docs/architecture/aspirational-schema-debt.md has no entry mentioning"
        f" migration {latest} — add a dated review comment for the new migration(s)"
    )
