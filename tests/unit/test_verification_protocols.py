"""R7 — re-runnable, scope-constrained verification protocols.

A protocol constrains HOW a fresh-context review looks (scope / anti-bias / conflict /
re-runnable) so the same review yields the same verdict. `ds work-order verify --protocol
<name>` runs the review under one. See docs/verification-protocols/ and
core/work_orders/verify_main.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify import verify_work_order

REPO = Path(__file__).resolve().parents[2]
PROTO_DIR = REPO / "docs" / "verification-protocols"

# The four rule blocks every protocol must carry.
REQUIRED_BLOCKS = (
    "Scope constraint",
    "Shape, not current behavior",
    "Conflict rule",
    "Re-runnable by fresh context",
)


def test_protocol_template_and_worked_example_exist():
    template = (PROTO_DIR / "PROTOCOL-000-template.md").read_text(encoding="utf-8")
    for block in REQUIRED_BLOCKS:
        assert block in template, f"template missing rule block: {block}"

    # A worked protocol (a numbered PROTOCOL-NNNN, not the template) exists and is complete.
    # The glob PROTOCOL-[0-9]*.md also matches PROTOCOL-000-template.md, so the template must be
    # excluded by name — otherwise this assertion would pass on the template alone (a worked
    # example could be deleted without failing the suite).
    worked = [p for p in PROTO_DIR.glob("PROTOCOL-[0-9]*.md") if "template" not in p.name.lower()]
    assert (
        worked
    ), "no worked protocol (non-template PROTOCOL-NNNN) under docs/verification-protocols/"
    body = worked[0].read_text(encoding="utf-8")
    for block in REQUIRED_BLOCKS:
        assert block in body, f"worked protocol {worked[0].name} missing block: {block}"


def test_verify_resolves_named_protocol(tmp_path: Path):
    """verify accepts a named protocol and fails fast on an unknown one — proving the
    review path resolves the protocol before any grader runs (gap→WO behavior untouched)."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id,project_id,milestone_id,title,description,status,"
            " work_order_type,created_at,updated_at)"
            " VALUES ('wo-p','p','m','WO',NULL,'in_progress','infrastructure','2026-08-03','2026-08-03')"
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id,work_order_id,project_id,title,description,status,created_at,updated_at)"
            " VALUES ('t','wo-p','p','T','d','complete','2026-08-03','2026-08-03')"
        )
        conn.commit()
    finally:
        conn.close()

    result = verify_work_order(
        work_order_id="wo-p",
        source_root=REPO,
        dream_studio_home=tmp_path,
        protocol="PROTOCOL-DOES-NOT-EXIST",
    )
    assert result["ok"] is False, result
    assert "protocol not found" in result["error"].lower(), result
