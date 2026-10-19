"""`ds profile create --claude-config-dir` is read: the active profile's directory is the
Claude Code root when CLAUDE_CONFIG_DIR is not set. Its help said "stored only; not yet
wired"."""

from __future__ import annotations

import argparse


def _create_option_help(dest: str) -> str:
    from interfaces.cli.commands import profile

    parser = argparse.ArgumentParser()
    profile.register(parser.add_subparsers())
    profile_parser = parser._subparsers._group_actions[0].choices["profile"]
    create = profile_parser._subparsers._group_actions[0].choices["create"]
    return next(a.help for a in create._actions if a.dest == dest)


def test_claude_config_dir_help_says_how_it_is_used():
    text = _create_option_help("claude_config_dir")
    assert "not yet wired" not in text, text
    assert "CLAUDE_CONFIG_DIR" in text, text
