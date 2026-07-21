"""WO-HOOK-ENFORCE-EXEC-STATS follow-on (46fe128b): doctor hook-freshness drift check.

The two blocking enforce hooks (on-edit-enforce, on-stop-enforce) are wired
directly in hooks.json and copied into the install tree; `ds update` is
version-gated, so a canonical edit can leave the deployed copy silently stale.
`_check_hook_freshness` flags that drift so `ds doctor` surfaces it (and `--fix`
re-projects). These tests are hermetic — they never read the operator's real
~/.claude install.
"""

from __future__ import annotations

from pathlib import Path

from core.health.doctor import _ENTRY_HOOK_RELPATHS, _check_hook_freshness


def _write_hook(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_hook_freshness_clean(tmp_path: Path) -> None:
    source = tmp_path / "src"
    claude = tmp_path / "claude"
    for rel in _ENTRY_HOOK_RELPATHS:
        _write_hook(source, rel, "print('canonical')\n")
        _write_hook(claude / "hooks", rel, "print('canonical')\n")
    result = _check_hook_freshness(source, claude)
    assert result == {"checked": len(_ENTRY_HOOK_RELPATHS), "stale": [], "ok": True}


def test_hook_freshness_detects_stale(tmp_path: Path) -> None:
    source = tmp_path / "src"
    claude = tmp_path / "claude"
    rel = _ENTRY_HOOK_RELPATHS[0]
    other = _ENTRY_HOOK_RELPATHS[1]
    _write_hook(source, rel, "print('new canonical with log_hook_execution')\n")
    _write_hook(claude / "hooks", rel, "print('stale pre-refactor copy')\n")
    _write_hook(source, other, "print('same')\n")
    _write_hook(claude / "hooks", other, "print('same')\n")
    result = _check_hook_freshness(source, claude)
    assert result["checked"] == 2
    assert result["stale"] == [rel]
    assert result["ok"] is False


def test_hook_freshness_crlf_insensitive(tmp_path: Path) -> None:
    """A CRLF-normalized Windows install must not read as drifted vs an LF source."""
    source = tmp_path / "src"
    claude = tmp_path / "claude"
    rel = _ENTRY_HOOK_RELPATHS[0]
    (source / rel).parent.mkdir(parents=True, exist_ok=True)
    (source / rel).write_bytes(b"line1\nline2\n")
    dep = claude / "hooks" / rel
    dep.parent.mkdir(parents=True, exist_ok=True)
    dep.write_bytes(b"line1\r\nline2\r\n")
    # Only this one file present on both sides.
    result = _check_hook_freshness(source, claude)
    assert result["stale"] == []
    assert result["checked"] == 1


def test_hook_freshness_skips_absent_deployed(tmp_path: Path) -> None:
    """A hook with no deployed copy is not counted and does not flag (fail-open)."""
    source = tmp_path / "src"
    claude = tmp_path / "claude"
    for rel in _ENTRY_HOOK_RELPATHS:
        _write_hook(source, rel, "print('canonical')\n")
    # No deployed copies written.
    result = _check_hook_freshness(source, claude)
    assert result == {"checked": 0, "stale": [], "ok": True}
