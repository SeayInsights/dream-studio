"""WO-FILESDB-C3: the authority-free file-backed WO packet store.

Covers core/work_orders/packet_store.py — a self-managed SQLite store (packets.db)
co-located with the packet storage root that holds the file-backed WO packet
system's artifacts (starting with multi-instance evals). It creates its table on
demand (no migration gating, no disk fallback) and NEVER touches the Dream Studio
authority (studio.db).
"""

from __future__ import annotations

from pathlib import Path

from core.work_orders.packet_store import (
    _packet_db,
    get_packet_artifact,
    list_packet_artifacts,
    set_packet_artifact,
)


def test_set_get_roundtrip_and_upsert(tmp_path: Path) -> None:
    root = tmp_path / "store"
    assert set_packet_artifact("wo-1", "eval", '{"a":1}', instance_key="render", storage_root=root)
    assert (
        get_packet_artifact("wo-1", "eval", instance_key="render", storage_root=root) == '{"a":1}'
    )
    # Upsert replaces the same (kind, instance_key).
    set_packet_artifact("wo-1", "eval", '{"a":9}', instance_key="render", storage_root=root)
    assert (
        get_packet_artifact("wo-1", "eval", instance_key="render", storage_root=root) == '{"a":9}'
    )


def test_multi_instance_evals_coexist(tmp_path: Path) -> None:
    root = tmp_path / "store"
    set_packet_artifact("wo-e", "eval", '{"s":"r"}', instance_key="render", storage_root=root)
    set_packet_artifact("wo-e", "eval", '{"s":"k"}', instance_key="skill", storage_root=root)
    listed = list_packet_artifacts("wo-e", "eval", storage_root=root)
    assert listed == [("render", '{"s":"r"}'), ("skill", '{"s":"k"}')]


def test_absent_returns_none(tmp_path: Path) -> None:
    root = tmp_path / "store"
    assert get_packet_artifact("nope", "eval", instance_key="x", storage_root=root) is None
    assert list_packet_artifacts("nope", "eval", storage_root=root) == []


def test_never_touches_authority_studio_db(tmp_path: Path) -> None:
    """The packet store writes packets.db under the storage root, never studio.db."""
    root = tmp_path / "store"
    set_packet_artifact("wo-1", "eval", "{}", instance_key="render", storage_root=root)
    assert _packet_db(root) == root / "packets.db"
    assert (root / "packets.db").is_file()
    # No Dream Studio authority DB anywhere under the storage root.
    assert list(root.rglob("studio.db")) == []
