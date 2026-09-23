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


def test_the_registry_instructs_the_client_level_fit_and_ask():
    """The claim, which outlived the file that carried it.

    Three tests here read canonical/skills/ds-project/SKILL.md for the client-level
    fit-check instruction, the STOP AND ASK posture, and the verdicts that trigger it.
    That pack was narration over commands and was dissolved; the instruction moved to
    `an-ambiguous-reference-stops-and-asks`, which names both layers -- `ds project
    fit-check` and `ds client fit-check` above it -- and says what an ambiguous verdict
    means. A rule the registry holds is a better home than a paragraph in one of ten
    skill files, because the gate refuses a rule that names an enforcer which is not
    there.
    """
    import yaml

    registry = yaml.safe_load((REPO_ROOT / "canonical" / "rules.yml").read_text(encoding="utf-8"))
    rule = next(
        (r for r in registry["rules"] if r["id"] == "an-ambiguous-reference-stops-and-asks"),
        None,
    )
    assert rule is not None, "the client-fit instruction is in no rule"
    body = " ".join(f"{rule['statement']} {rule.get('why', '')}".split())
    assert "ds client fit-check" in body, "the rule does not name the client-level path"
    assert "ds project fit-check" in body, "the rule does not name the project-level path"
    assert "stops and asks" in body or "asks which" in body, body


def test_the_client_fit_check_command_exists():
    """The rule names a runnable path, so the path has to run. This resolves it against
    the real parser tree rather than trusting the string."""
    from interfaces.cli.ds import build_parser

    parser = build_parser()
    top = next(a for a in parser._actions if a.dest == "command")
    client = top.choices.get("client")
    assert client is not None, "`ds client` does not exist"
    sub = next(
        (a for a in client._actions if getattr(a, "choices", None) and "fit-check" in a.choices),
        None,
    )
    assert sub is not None, "`ds client fit-check` does not exist"


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
