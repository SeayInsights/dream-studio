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


def test_resolve_protocol_by_short_id_full_stem_and_unknown(tmp_path: Path):
    """A short id (PROTOCOL-0001) must resolve to the descriptively-named file, the full
    stem must resolve exactly, an unknown id returns None, and an ambiguous id raises —
    covering the success path the CLI documents (`--protocol PROTOCOL-0001`)."""
    from core.work_orders.verify_main import _resolve_protocol

    d = tmp_path / "docs" / "verification-protocols"
    d.mkdir(parents=True)
    (d / "PROTOCOL-0001-three-store-architecture.md").write_text("x", encoding="utf-8")

    assert _resolve_protocol(d, "PROTOCOL-0001").name == "PROTOCOL-0001-three-store-architecture.md"
    assert (
        _resolve_protocol(d, "PROTOCOL-0001-three-store-architecture").name
        == "PROTOCOL-0001-three-store-architecture.md"
    )
    assert _resolve_protocol(d, "PROTOCOL-9999") is None

    # Ambiguous short id → ValueError (never a silent wrong pick).
    (d / "PROTOCOL-0001-second-file.md").write_text("y", encoding="utf-8")
    try:
        _resolve_protocol(d, "PROTOCOL-0001")
        raise AssertionError("ambiguous short id should have raised")
    except ValueError as exc:
        assert "ambiguous" in str(exc).lower(), exc


def test_shipped_worked_protocol_resolves_under_documented_short_id():
    """The shipped worked protocol must be reachable by the short id the skill text and the
    protocol itself document — this is the exact defect the CLI-flag review caught."""
    from core.work_orders.verify_main import _resolve_protocol

    d = REPO / "docs" / "verification-protocols"
    resolved = _resolve_protocol(d, "PROTOCOL-0001")
    assert resolved is not None, "documented `--protocol PROTOCOL-0001` does not resolve"
    assert resolved.name.startswith("PROTOCOL-0001-"), resolved
