"""WO eefe0c44: the CLI reference must document the new dashboard lifecycle flags
so operators discover --restart/stop/--reload (added by WO-DASH-RESTART)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
CLI_REF = REPO_ROOT / "docs" / "reference" / "cli.md"


def test_cli_ref_documents_dashboard_restart():
    text = CLI_REF.read_text(encoding="utf-8")
    assert "ds dashboard --restart" in text, "cli.md must document `ds dashboard --restart`"
    assert "ds dashboard stop" in text or "--stop" in text, "cli.md must document dashboard stop"
    assert "ds dashboard --reload" in text, "cli.md must document `ds dashboard --reload`"
