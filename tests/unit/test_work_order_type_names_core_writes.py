"""Every work-order type name core writes is either built in or reserved.

WHY THIS FILE EXISTS. A pack may declare work-order types, and a declared type decides how a work
order of that name is reviewed and closed. Core also writes type names of its own without going
through the declared set: `verify_gaps` files gap work orders as `cleanup` (and defaults a gap
with no type to it) straight into the table, bypassing `create_work_order`'s check, and the
review prompts tell the grader which types to answer with. A pack declaring `cleanup` as an
exempt document type would have retroactively changed how every one of those work orders is
reviewed. So the loader refuses every name in `RESERVED_WORK_ORDER_TYPES`.

That set was found by this scan, so it must stay findable: a new core writer that files a name
which is neither built in nor reserved would reopen the hole for that name, and fails here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core.work_orders.type_registry import RESERVED_WORK_ORDER_TYPES, builtin_work_order_type_names

REPO = Path(__file__).resolve().parents[2]

#: Directories that are not production code. Everything else holding a .py file is scanned.
_NOT_PRODUCTION = frozenset(
    {
        "tests",
        "dist",
        "docs",
        ".git",
        ".claude",
        ".venv",
        "venv",
        "node_modules",
        "build",
        "__pycache__",
        "templates",
        "examples",
    }
)

_PROMPT_SCHEMA = re.compile(r'"work_order_type"\s*:\s*((?:"[a-z_]+"\s*\|?\s*)+)')
_SQL_COMPARISON = re.compile(r"work_order_type\s*(?:=|IN|in)\s*\(?\s*((?:'[a-z_]+'\s*,?\s*)+)")


def types_written_by(source: str) -> dict[str, int]:
    """Type names ``source`` files or tells a grader to file, with the line of the first.

    Four shapes, all literal: a dict entry keyed ``"work_order_type"``, a ``work_order_type=``
    keyword argument, a ``.get("work_order_type", "<default>")`` default, and a string that
    spells out a type schema (``"work_order_type": "a" | "b"``) or compares the column to
    quoted names. A name computed at run time cannot be found by any scan; the loader's other
    guards (the reserved set, the explicit flags, the operator's allowance) do not depend on
    this one being complete, and the limit is recorded in the contract.
    """
    found: dict[str, int] = {}

    def note(name: str, line: int) -> None:
        found.setdefault(name, line)

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "work_order_type"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    note(value.value, value.lineno)
        elif isinstance(node, ast.keyword):
            if (
                node.arg == "work_order_type"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                note(node.value.value, node.value.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "work_order_type"
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            note(node.args[1].value, node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for match in _PROMPT_SCHEMA.finditer(node.value):
                for name in re.findall(r'"([a-z_]+)"', match.group(1)):
                    note(name, node.lineno)
            for match in _SQL_COMPARISON.finditer(node.value):
                for name in re.findall(r"'([a-z_]+)'", match.group(1)):
                    note(name, node.lineno)
    return found


def _production_writers() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for py in REPO.rglob("*.py"):
        rel = py.relative_to(REPO)
        if _NOT_PRODUCTION & set(rel.parts[:-1]):
            continue
        try:
            names = types_written_by(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for name, line in names.items():
            found.setdefault(name, []).append(f"{rel.as_posix()}:{line}")
    return found


def test_every_type_name_core_writes_is_built_in_or_reserved():
    known = set(builtin_work_order_type_names()) | set(RESERVED_WORK_ORDER_TYPES)
    unknown = {n: w for n, w in _production_writers().items() if n not in known}
    assert unknown == {}, (
        "core writes a work-order type that is neither built in nor in"
        " type_registry.RESERVED_WORK_ORDER_TYPES, so a pack could declare it and change how"
        f" those work orders are reviewed: {unknown}. Reserve it (with the reason) or declare it."
    )


def test_the_scan_still_finds_what_it_found_the_reserved_name_from():
    """Guards the guard: a scan that stopped finding anything would pass the test above."""
    writers = _production_writers()
    assert "cleanup" in writers and any("verify_gaps.py" in w for w in writers["cleanup"])
    assert {"infrastructure", "documentation"} <= set(writers)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param('x = {"work_order_type": "chore2"}', {"chore2"}, id="dict-entry"),
        pytest.param("emit(work_order_type='sweep')", {"sweep"}, id="keyword"),
        pytest.param('t = gap.get("work_order_type", "tidy")', {"tidy"}, id="get-default"),
        pytest.param(
            'P = """{"work_order_type": "fix" | "polish" | "audit"}"""',
            {"fix", "polish", "audit"},
            id="prompt-schema",
        ),
        pytest.param(
            "Q = \"SELECT 1 FROM business_work_orders WHERE work_order_type IN ('a_b', 'c')\"",
            {"a_b", "c"},
            id="sql-in",
        ),
        pytest.param("Q = \"... WHERE work_order_type = 'solo'\"", {"solo"}, id="sql-equals"),
        pytest.param('y = {"title": "cleanup"}', set(), id="other-key-is-not-a-type"),
        pytest.param("work_order_type = compute()", set(), id="computed-is-not-findable"),
    ],
)
def test_the_scan_recognises_each_literal_shape(source, expected):
    assert set(types_written_by(source)) == expected


def test_a_planted_writer_of_an_unknown_name_would_fail_the_test_above():
    known = set(builtin_work_order_type_names()) | set(RESERVED_WORK_ORDER_TYPES)
    planted = types_written_by('spawn(work_order_type="brand_new_sweep")')
    assert set(planted) - known == {"brand_new_sweep"}


def test_reserved_names_that_are_still_written_are_the_derived_ones():
    """`cleanup` is reserved because core writes it; the other three are historical and cannot be
    derived from today's code, which is said in the registry rather than hidden."""
    writers = _production_writers()
    derived = {n for n in RESERVED_WORK_ORDER_TYPES if n in writers}
    assert derived == {"cleanup"}
    for name in set(RESERVED_WORK_ORDER_TYPES) - derived:
        assert "earlier versions" in RESERVED_WORK_ORDER_TYPES[name]
