from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

GENERIC_CORE_PATHS = (
    REPO_ROOT / "core" / "work_orders",
    REPO_ROOT / "interfaces" / "cli" / "ds_work_order.py",
)

FORBIDDEN_TARGET_TERMS = (
    "dreamysuite",
    "phase 17u",
    "fix/drag-and-selection-scaling",
    "3163323",
    "04c5ddc",
    "9034648",
    "bgimage",
    "breakpointframe",
    "prod-backup.sql",
    "blocks.test.ts",
)


def _python_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(item for item in path.rglob("*.py") if "__pycache__" not in item.parts)


def test_generic_work_order_core_has_no_target_specific_fixture_text() -> None:
    offenders: list[str] = []
    for root in GENERIC_CORE_PATHS:
        for path in _python_files(root):
            text = path.read_text(encoding="utf-8").lower()
            matches = [term for term in FORBIDDEN_TARGET_TERMS if term in text]
            if matches:
                relative = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{relative}: {', '.join(matches)}")

    assert offenders == []


def test_work_order_operations_doc_uses_current_target_neutral_framing() -> None:
    operations = (REPO_ROOT / "docs" / "operations" / "work-orders.md").read_text(encoding="utf-8")

    assert "Phase: 17Y" not in operations
    assert "## DreamySuite Boundary" not in operations
    assert "Phase 16A validation" not in operations
    assert "DreamySuite remains Phase 17 only" not in operations
    assert "| `regenerate-handoff` |" in operations
    assert "Current generic operations guidance is target-neutral" in operations
    assert "Historical case-study note" in operations
