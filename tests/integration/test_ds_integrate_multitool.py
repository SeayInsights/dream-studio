"""WO-P20-TOOL-TARGETS T2/T3: `ds integrate install <tool>` supports new targets."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_integrate_install_supports_new_tools(tmp_path, monkeypatch):
    """`ds integrate install codex --execute` writes AGENTS.md to the project root."""
    from interfaces.cli.ds import main as ds_main

    monkeypatch.chdir(tmp_path)
    rc = ds_main(["integrate", "install", "codex", "--execute"])
    assert rc == 0
    written = tmp_path / "AGENTS.md"
    assert written.is_file(), "codex install must write AGENTS.md to the project root"
    assert "Pack-Based Routing" in written.read_text(encoding="utf-8")


def test_install_requires_mode(tmp_path, monkeypatch):
    """Without --dry-run/--execute the install refuses (nonzero, writes nothing)."""
    from interfaces.cli.ds import main as ds_main

    monkeypatch.chdir(tmp_path)
    rc = ds_main(["integrate", "install", "codex"])
    assert rc != 0, "install without a mode flag must refuse"
    assert not (tmp_path / "AGENTS.md").exists()


def test_detect_all_includes_new_targets():
    from integrations.detector import detect_all

    ids = {t.tool_id for t in detect_all()}
    for expected in ("claude_code", "codex", "gemini_cli", "windsurf", "aider", "cursor"):
        assert expected in ids, f"detect_all missing {expected}"


def test_install_agents_subset_via_the_real_cli(tmp_path, monkeypatch):
    """The actual gap an operator hit right after per-seat model shipped: installing
    codex and gemini_cli each gave all nine reviewers to both, with no way to split a
    mixed roster (some seats on one tool, some on another) between them. --agents is
    the fix; this proves it end to end through the real argv parser, not just the
    installer classes directly.

    codex only (project-scoped, safely isolated by chdir alone) -- cursor's user scope
    needs home= too, which the CLI does not expose a test hook for, so it stays out of
    CLI-level integration tests the same way test_end_to_end above already excludes it.
    """
    from interfaces.cli.ds import main as ds_main

    monkeypatch.chdir(tmp_path)
    rc = ds_main(
        [
            "integrate",
            "install",
            "codex",
            "--agents",
            "Finding integrity, review-boundary-semantics",
            "--execute",
        ]
    )
    assert rc == 0
    written = {p.name for p in (tmp_path / ".codex" / "agents").iterdir()}
    assert written == {"review-finding-integrity.toml", "review-boundary-semantics.toml"}


def test_install_agents_subset_dry_run_reports_the_files_via_the_real_cli(tmp_path, monkeypatch):
    import json

    from interfaces.cli.ds import main as ds_main

    monkeypatch.chdir(tmp_path)
    # Capture stdout the same way the other CLI tests in this module rely on _print's
    # side effect being observable -- via the real files it does or doesn't write,
    # except a dry-run writes nothing, so this one reads the JSON _print emits instead.
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = ds_main(
            ["integrate", "install", "gemini_cli", "--agents", "Finding integrity", "--dry-run"]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["specialist_agents"]["files"] == ["review-finding-integrity.md"]
    assert payload["specialist_agents"]["written"] == []
    assert not (tmp_path / ".gemini").exists()


def test_install_agents_subset_on_claude_code_via_the_real_cli(tmp_path, monkeypatch):
    """claude_code's reviewers are installed by a separate, older path
    (ClaudeCodeInstaller) than codex/gemini_cli/cursor's -- --agents narrowed those
    three but silently did nothing here, so claude_code still got all nine regardless
    of the flag. --scope project keeps this test's writes inside tmp_path/.claude,
    never the operator's real ~/.claude/ (see detect_claude_code's scope_override)."""
    from interfaces.cli.ds import main as ds_main

    monkeypatch.chdir(tmp_path)
    rc = ds_main(
        [
            "integrate",
            "install",
            "claude_code",
            "--scope",
            "project",
            "--agents",
            "Finding integrity",
            "--execute",
        ]
    )
    assert rc == 0
    agents_dir = tmp_path / ".claude" / "agents"
    reviewer_names = {p.name for p in agents_dir.glob("review-*.md")}
    assert reviewer_names == {"review-finding-integrity.md"}
    # Domain specialists are a different bench --agents has never covered; at least
    # one must still be present, proving the subset didn't silently narrow those too.
    assert any(not p.name.startswith("review-") for p in agents_dir.glob("*.md"))


def test_end_to_end(tmp_path, monkeypatch):
    """Dry-run writes nothing; execute writes; every project-scoped tool lands AGENTS.md."""
    from interfaces.cli.ds import main as ds_main

    monkeypatch.chdir(tmp_path)

    # Dry run: no file.
    assert ds_main(["integrate", "install", "windsurf", "--dry-run"]) == 0
    assert not (tmp_path / "AGENTS.md").exists()

    # Execute each project-root tool → AGENTS.md present and current.
    for tool in ("codex", "gemini_cli", "windsurf", "aider"):
        (tmp_path / "AGENTS.md").unlink(missing_ok=True)
        assert ds_main(["integrate", "install", tool, "--execute"]) == 0
        out = tmp_path / "AGENTS.md"
        assert out.is_file(), f"{tool}: AGENTS.md missing"
        text = out.read_text(encoding="utf-8")
        assert "GENERATED by integrations/compiler/agents_md.py" in text
        assert "## Work Order Types" in text
