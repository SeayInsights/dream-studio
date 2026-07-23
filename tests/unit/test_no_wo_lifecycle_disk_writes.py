"""WO-FILESDB-C6: regression guard — WO-lifecycle artifacts stay in tables, not on disk.

The "Files in Database" milestone moved WO-lifecycle state/artifacts off loose disk
files into tables:

- **Packet system** (portable executor-handoff artifacts, authority-free): evals (C3),
  decisions (C4), reports/results/rendered packets (C5) all live in the packet store
  (``core/work_orders/packet_store.py`` -> packets.db). These modules are FULLY
  migrated — they must contain no artifact disk writes and no fallback.
- **Authority** (context, review_verdict — C2): stored in ``business_work_order_artifacts``
  DB-first, with a ``.planning`` disk *fallback* retained ONLY until the artifact-table
  migration (144/152) is released (``ds migrate activate`` / ac814dc3). This guard pins
  that those disk writes are strictly DB-first fallbacks (a ``set_wo_artifact`` attempt
  precedes the disk write), never the primary path.

This grep-based guard (mirroring tests/unit/test_dashboard_no_dead_audit_fetch.py) pins
the migration so loose WO-artifact disk writes never creep back in.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WO = REPO_ROOT / "core" / "work_orders"


def _module_surface(py_path: Path) -> str:
    """Full source surface of a module: the file itself plus any facade-split
    ``<stem>_*.py`` siblings beside it. A god-file split (WO-GF-*) reduces a module
    to a thin re-export facade over siblings, so a source-text contract check must
    read the whole surface — otherwise relocated content reads as missing (and, for
    absence checks, would read as a false pass). ``evals.py`` was split this way in
    WO-GF-WO-LIFECYCLE (#536); the other packet modules have no siblings and read as
    themselves."""
    parts = [py_path.read_text(encoding="utf-8")]
    for sib in sorted(py_path.parent.glob(f"{py_path.stem}_*.py")):
        parts.append(sib.read_text(encoding="utf-8"))
    return "\n".join(parts)


# Packet-system artifact writers — fully migrated to packet_store, zero disk writes.
_PACKET_MODULES = (
    "evals.py",
    "decisions.py",
    "reporting.py",
    "results.py",
    "renderers.py",
)


def test_packet_system_modules_have_no_artifact_disk_writes():
    """evals/decisions/reporting/results/renderers persist via packet_store only."""
    offenders: list[str] = []
    for name in _PACKET_MODULES:
        src = _module_surface(WO / name)
        if ".write_text(" in src:
            offenders.append(name)
    assert offenders == [], (
        "WO packet-system modules must persist artifacts via packet_store (packets.db), "
        f"not .write_text() to disk — offenders: {offenders}. "
        "See WO-FILESDB-C3/C4/C5."
    )


def test_packet_system_modules_use_packet_store():
    """Positive check: the packet writers actually go through the packet store."""
    missing: list[str] = []
    for name in _PACKET_MODULES:
        src = _module_surface(WO / name)
        if "packet_store" not in src:
            missing.append(name)
    assert (
        missing == []
    ), f"packet-system modules must import/use packet_store — missing in: {missing}"


def test_authority_context_verdict_are_db_first():
    """context (start.py) and review_verdict (verify.py) store DB-first; any disk write is
    a transition-only fallback (removed when the artifact-table migration is released).
    Guard: each module attempts set_wo_artifact before any .planning disk write."""
    for name in ("start.py", "verify.py"):
        src = _module_surface(WO / name)
        if ".write_text(" not in src:
            continue  # no disk write at all is fine (post-release end state)
        assert "set_wo_artifact(" in src, (
            f"{name} still writes a WO artifact to disk without a DB-first "
            "set_wo_artifact() attempt — the disk write must be a fallback only (WO-FILESDB-C2)."
        )
