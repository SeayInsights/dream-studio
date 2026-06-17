"""Contract tests for `ds uninstall` (WO-UNINSTALL T1).

The contract doc must enumerate, unambiguously, what each tier removes and what
it preserves, plus the dry-run-default and second-confirm-for-purge invariants.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "uninstall-contract.md"


def test_contract_enumerates_removed_and_preserved_targets() -> None:
    assert CONTRACT_PATH.is_file(), f"missing contract doc: {CONTRACT_PATH}"
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    # Enumerates the removed-vs-preserved distinction explicitly.
    assert "removed" in lowered
    assert "preserved" in lowered

    # The three flags are documented.
    for flag in ("--execute", "--force", "--purge-state"):
        assert flag in text, f"contract must document {flag}"

    # Removed targets: the .claude hook wiring (both copies) and the global launchers.
    assert ".claude" in text
    assert "settings.json" in text
    assert "both" in lowered  # both generated .claude copies
    assert "ds.cmd" in text and "ds.ps1" in text

    # Preserved target under integration teardown: the state tier (studio.db).
    assert "studio.db" in text
    assert "~/.dream-studio" in text

    # Mandatory non-destructive preview + dry-run default.
    assert "uninstall-check" in text
    assert "dry-run" in lowered

    # Second-confirmation + automatic backup model for the state purge.
    assert "second confirmation" in lowered
    assert "backup" in lowered
