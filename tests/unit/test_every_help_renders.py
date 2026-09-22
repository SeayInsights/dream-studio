"""Every `ds` command and subcommand can print its own help.

`ds work-order create --help` raised `TypeError: %o format: an integer is required, not
dict`. A help string said "78-100% on projects", argparse interpolates `%` in help text,
and `% o` is a format directive. The door still worked; its documentation did not, and
the failure only appeared when an operator asked for it. Sixty-odd other subcommands
rendered fine, which is why nobody noticed the one that did not.

This walks the real parser tree -- every subparser action, recursively -- and formats
each one's help. A `%` written into a help string tomorrow fails here, not in front of an
operator. It does not shell out per command: the parser is in-process, so the whole tree
costs well under a second.
"""

from __future__ import annotations

import argparse

import pytest

from interfaces.cli.ds import build_parser


def _walk(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    yield path, parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                yield from _walk(sub, (*path, name))


def _all_parsers():
    return list(_walk(build_parser()))


def test_the_walk_reaches_the_tree_not_a_stub():
    """A guard that inspected one parser would pass on a stub. The real tree is deep
    (`ds work-order create` is three levels), and wide -- dozens of commands."""
    parsers = _all_parsers()
    assert len(parsers) > 60, f"only {len(parsers)} parsers reached; has build_parser moved?"
    assert any(path == ("work-order", "create") for path, _ in parsers)


@pytest.mark.parametrize(
    "path, parser",
    [(p, parser) for p, parser in _all_parsers()],
    ids=[" ".join(("ds", *p)) or "ds" for p, _ in _all_parsers()],
)
def test_help_renders(path, parser):
    """format_help() is exactly what `--help` prints; a raise here is a raise there."""
    text = parser.format_help()
    assert text.strip(), f"empty help for ds {' '.join(path)}"
