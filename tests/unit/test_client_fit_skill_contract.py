"""WO-CLIENT-SKILLS: the ds-project skill surface is client-aware and instructs the client-level
project-fit-and-ask (the layer above the milestone fit-check), backed by a real `ds client
fit-check` invocation path."""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_DS_PROJECT_SKILL = REPO_ROOT / "canonical" / "skills" / "ds-project" / "SKILL.md"
_DS_PROJECT_MANAGE = (
    REPO_ROOT / "canonical" / "skills" / "ds-project" / "modes" / "manage" / "SKILL.md"
)


def test_ds_project_skill_instructs_client_project_fit_and_ask():
    text = _DS_PROJECT_SKILL.read_text(encoding="utf-8")
    # The concrete client-level fit-check invocation path (not a vague "consider the client").
    assert "ds client fit-check" in text, "ds-project skill must reference the client fit-check"
    # Stop-and-ask on a weak/ambiguous project fit (the operator's ask-don't-guess rule).
    assert "STOP AND ASK" in text
    # The verdicts that trigger the ask at the client->project layer.
    assert "no_projects" in text and "ambiguous" in text
    # Client-awareness: registration carries a client + the default is named.
    assert "client_id" in text and "SeayInsights" in text


def test_ds_project_skill_surfaces_active_client_on_resume():
    text = _DS_PROJECT_SKILL.read_text(encoding="utf-8")
    assert "active_client_id" in text
    # Accuracy: the field comes from the `ds project state` CLI, not the raw get_project_state().
    assert "ds project state" in text


def test_ds_project_manage_mode_is_client_aware():
    text = _DS_PROJECT_MANAGE.read_text(encoding="utf-8")
    # Client-grouped listing + client-scoped name resolution (names collide across clients).
    assert "ds project list --by-client" in text
    assert "--client" in text
    assert "STOP AND ASK" in text


def test_client_fit_check_subcommand_registered():
    from interfaces.cli.commands import client as client_cmd

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    client_cmd.register(sub)
    args = parser.parse_args(
        ["client", "fit-check", "--client", "fulcrum", "--title", "T", "--description", "D"]
    )
    assert args.client_command == "fit-check"
    assert args.client_id == "fulcrum"
    assert args.title == "T"
