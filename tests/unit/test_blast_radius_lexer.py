"""The single-pass lexer behind the changed-signature detector's `def` reading.

Round-two review of the string-literal rule (tests/unit/test_blast_radius_string_literal_defs.py)
found it correct but weaker than it should be:

1. QUADRATIC TIME. `_signature_on_line` rescanned the whole prefix for every `function`
   match that sat inside a literal: one 100 KB line `"` + `function f(a) ` x 7,142 + `"` in a
   non-Python file took 43 s (main: 0.000 s). The lexer now walks the line ONCE, carrying
   its state, and only looks for a definition at positions where it is in code.
2. SWALLOWED REAL DEFS. Matches did not overlap, so an unclosed `function foo(` inside a
   literal or comment swallowed a real `function bar(a)` later on the line, and a regex
   literal containing a quote (`/'/`) was read as the start of a string.
3. A UTF-8 BOM on line 1 of a .py file lost its def.
4. `#` comments in .rb / .sh / .yml files were read as definitions.
5. Mutants that survived: whitespace shapes of a Python def, `/*/`, a backslash outside a
   string, and what a `.pyi` stub is.

Timing bounds are generous (a 1 MB line must finish in seconds, not minutes) so they pin
the complexity class without being flaky.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.gates.hanging_detectors import (
    _comment_style,
    _in_literal_or_comment,
    _is_python_path,
    _signature_on_line,
    detect_changed_signature_callers,
)

BUDGET_SECONDS = 5.0
BOM = chr(0xFEFF)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _diff(removed: list[str], added: list[str], path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,1 +1,1 @@\n"
        + "".join(f"-{ln}\n" for ln in removed)
        + "".join(f"+{ln}\n" for ln in added)
    )


def _timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


# --- 1. linear time ---------------------------------------------------------

HOSTILE = {
    "defs-inside-one-string": ('"' + "function f(a) " * 75_000 + '"', "c", None),
    "defs-inside-one-template": ("`" + "function f(a) " * 75_000 + "`", "c", None),
    "defs-inside-one-block-comment": ("/* " + "function f(a) " * 75_000 + "*/", "c", None),
    "defs-inside-a-line-comment": ("// " + "function f(a) " * 75_000, "c", None),
    "defs-inside-a-hash-comment": ("# " + "function f(a) " * 75_000, "hash", None),
    "unclosed-defs-inside-a-string": ("'" + "function f( " * 90_000 + "'", "c", None),
    "many-small-strings": ("'a' " * 250_000, "c", None),
    "many-unclosed-regex-candidates": ("x = / " * 170_000, "c", None),
    "many-block-comments-then-a-real-def": (
        "/* function g(q) */ " * 50_000 + "function real(a) {",
        "c",
        ("real", "a", False),
    ),
    "many-strings-then-a-real-def": (
        "'function g(q)' " * 60_000 + "function real(a) {",
        "c",
        ("real", "a", False),
    ),
    "many-defs-no-closing-paren": ("function f( " * 90_000, "c", None),
    # Every `/` here opens a regex class that never closes: each attempt would scan to the
    # end of the line, so without the "stop trying" flag this is quadratic.
    "many-regex-candidates-that-never-close": ("x = /[ " * 170_000, "c", None),
}


@pytest.mark.parametrize("line,style,expected", HOSTILE.values(), ids=HOSTILE)
def test_a_hostile_one_megabyte_line_is_read_in_linear_time(line, style, expected) -> None:
    assert len(line) > 600_000
    result, seconds = _timed(lambda: _signature_on_line(line, is_py=False, style=style))
    assert result == expected
    assert seconds < BUDGET_SECONDS, f"{seconds:.1f}s on a {len(line)} character line"


def test_a_hostile_line_through_the_whole_detector_is_linear(tmp_path: Path) -> None:
    _write(tmp_path / "web" / "caller.js", "function go() { do_work(1); }\n")
    line = '"' + "function do_work(a) " * 50_000 + '"'
    diff = _diff([line], [line + " "], "web/lib.js")
    result, seconds = _timed(lambda: detect_changed_signature_callers(diff, repo_root=tmp_path))
    assert result == []
    assert seconds < BUDGET_SECONDS


def test_a_hostile_python_line_is_linear() -> None:
    line = "def f(" + "a, " * 400_000
    result, seconds = _timed(lambda: _signature_on_line(line, is_py=True))
    assert result is None
    assert seconds < BUDGET_SECONDS


def test_the_prefix_scanner_is_linear() -> None:
    prefix = "'a' " * 250_000
    result, seconds = _timed(lambda: _in_literal_or_comment(prefix))
    assert result is False
    assert seconds < BUDGET_SECONDS


# --- 2. real defs the old matcher swallowed ---------------------------------

BAR = ("bar", "a", False)
REAL_AFTER_TROUBLE = {
    "unclosed-def-in-a-string": ("x = 'function foo(' + y; function bar(a) {}", BAR),
    "unclosed-def-in-a-double-string": ('x = "function foo(" + y; function bar(a) {}', BAR),
    "unclosed-def-in-a-block-comment": ("/* see function foo( */ function bar(a) {}", BAR),
    "regex-with-a-quote": ("x = /'/; function bar(a){}", BAR),
    "regex-with-a-double-quote": ('x = /"/; function bar(a){}', BAR),
    "regex-with-a-backtick": ("x = /`/; function bar(a){}", BAR),
    "regex-with-an-escaped-slash": ("x = /\\/'/; function bar(a){}", BAR),
    "regex-with-a-slash-in-a-class": ("x = /[/]'/; function bar(a){}", BAR),
    "regex-with-flags": ("x = /'/gi; function bar(a){}", BAR),
    "regex-after-a-paren": ("f(/'/); function bar(a){}", BAR),
    "regex-after-a-comma": ("f(1, /'/); function bar(a){}", BAR),
    "regex-at-the-start-of-the-line": ("/'/.test(s); function bar(a){}", BAR),
    "regex-after-a-colon": ("o = {k: /'/}; function bar(a){}", BAR),
    "division-is-not-a-regex": ("x = a / 2 + 'it'; function bar(a){}", BAR),
    "division-after-a-paren": ("x = (a) / 2 / 3; function bar(a){}", BAR),
    "division-after-an-index": ("x = a[0] / 2; function bar(a){}", BAR),
}


@pytest.mark.parametrize("line,expected", REAL_AFTER_TROUBLE.values(), ids=REAL_AFTER_TROUBLE)
def test_a_real_function_after_trouble_on_the_line_is_read(line, expected) -> None:
    assert _signature_on_line(line, is_py=False) == expected


def test_a_def_inside_a_regex_literal_is_text() -> None:
    assert _signature_on_line("x = /function foo(a)/; y = 1", is_py=False) is None


def test_an_unclosed_regex_candidate_is_a_division_not_a_swallowed_line() -> None:
    """`x = / ...` with no closing slash cannot be a regex, so the `/` is an operator and
    the later definition is still read."""
    assert _signature_on_line("x = / b; function bar(a) {", is_py=False) == BAR


def test_a_slash_after_a_string_is_a_division() -> None:
    """After a string value a `/` is an operator. Read as a regex it would run on to the
    next slash and swallow the quote that opens the string holding the `function`."""
    line = "a = \"x\" / 2 + 'y / 3; function bar(b){}'"
    assert _signature_on_line(line, is_py=False) is None


def test_regex_literals_exist_only_in_c_like_files() -> None:
    line = "x = /'/; function bar(a){}"
    assert _signature_on_line(line, is_py=False, style="c") == BAR
    assert _signature_on_line(line, is_py=False, style="hash") is None
    assert _signature_on_line(line, is_py=False, style="sql") is None


def test_block_comments_exist_in_sql_but_not_in_hash_files() -> None:
    assert _signature_on_line("/* function f(a) */", is_py=False, style="sql") is None
    assert _signature_on_line("/* function f(a) {", is_py=False, style="hash") == ("f", "a", False)
    assert _signature_on_line("/* function f(a) */", is_py=False, style="c") is None


def test_known_limit_a_regex_after_a_keyword_is_read_as_division() -> None:
    """`return /'/.test(s)`: the previous token is a word, which could end an expression, so
    the slash is taken as division and the quote opens a string. Pinned as a documented
    false negative (a real `function` later on that line would be missed)."""
    assert _signature_on_line("return /'/.test(s); function bar(a){}", is_py=False) is None


# --- scanner semantics ------------------------------------------------------

SCANNER = [
    # (prefix, style, ends inside a literal or comment)
    ("/*/ ", "c", True),  # `/*/` opens a comment; its `/` is not a closing `*/`
    ("/*/ x */ ", "c", False),
    ("/**/ ", "c", False),
    ("/* a */ /*/ ", "c", True),
    ("x = /'/; ", "c", False),
    ("x = /'/ + '", "c", True),
    ('echo \\" ', "c", True),  # in C-like text a backslash outside a string is nothing
    ('echo \\" ', "hash", False),  # in shell/ruby/yaml it escapes the quote
    ("echo \\\\ ", "hash", False),
    ("echo \\# not a comment ", "hash", False),  # an escaped `#` is not a comment
    ("echo # ", "hash", True),
    ("echo '#' ", "hash", False),
    ("a -- b ", "sql", True),
    ("a - b ", "sql", False),
    ("'--' ", "sql", False),
    ("/* a */ x ", "sql", False),
    ("// not a comment ", "hash", False),
    ("# not a comment ", "c", False),
]


@pytest.mark.parametrize(
    "prefix,style,expected", SCANNER, ids=[f"{s}:{p!r}" for p, s, _ in SCANNER]
)
def test_the_scanner_by_style(prefix: str, style: str, expected: bool) -> None:
    assert _in_literal_or_comment(prefix, style=style) is expected


def test_a_backslash_outside_a_string_only_escapes_in_hash_files() -> None:
    line = 'echo \\"function f(a)'
    assert _signature_on_line(line, is_py=False, style="hash") == ("f", "a", False)
    assert _signature_on_line(line, is_py=False, style="c") is None


# --- 4. `#` comments in files where `#` is a comment ------------------------

HASH_FILES = ["lib/thing.rb", "ops/run.sh", "ops/run.bash", "conf/app.yml", "conf/app.yaml"]


@pytest.mark.parametrize("path", HASH_FILES)
def test_a_hash_comment_is_not_a_definition(tmp_path: Path, path: str) -> None:
    _write(tmp_path / "web" / "caller.js", "function go() { do_work(1); }\n")
    diff = _diff(["# def do_work(a)"], ["# def do_work(a, b)"], path)
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []
    assert _signature_on_line("# def do_work(a)", is_py=False, style=_comment_style(path)) is None


@pytest.mark.parametrize("path", HASH_FILES)
def test_a_trailing_hash_comment_is_not_a_definition(path: str) -> None:
    style = _comment_style(path)
    assert _signature_on_line("run  # function do_work(a)", is_py=False, style=style) is None
    assert _signature_on_line("run; function do_work(a) {", is_py=False, style=style) == (
        "do_work",
        "a",
        False,
    )


def test_a_real_ruby_def_is_still_read(tmp_path: Path) -> None:
    _write(tmp_path / "web" / "caller.js", "function go() { do_work(1); }\n")
    diff = _diff(["def do_work(a)"], ["def do_work(a, b)"], "lib/thing.rb")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "web/caller.js" in {f["path"] for f in findings}


def test_a_hash_inside_a_string_is_not_a_comment() -> None:
    line = "echo '#'; function do_work(a) {"
    assert _signature_on_line(line, is_py=False, style="hash") == ("do_work", "a", False)


@pytest.mark.parametrize(
    "path,style",
    [
        ("lib/thing.rb", "hash"),
        ("ops/run.sh", "hash"),
        ("ops/run.bash", "hash"),
        ("ops/run.zsh", "hash"),
        ("conf/app.yml", "hash"),
        ("conf/app.yaml", "hash"),
        ("conf/app.toml", "hash"),
        ("db/schema.sql", "sql"),
        ("lua/x.lua", "sql"),
        ("core/x.py", "py"),
        ("core/x.pyi", "py"),
        ("web/x.js", "c"),
        ("web/x.ts", "c"),
        ("web/x.html", "c"),
        ("docs/x.md", "c"),
        ("noextension", "c"),
        ("UPPER/X.YML", "hash"),
    ],
)
def test_the_comment_style_by_file_type(path: str, style: str) -> None:
    assert _comment_style(path) == style


def test_sql_dashes_are_a_comment() -> None:
    assert _signature_on_line("-- function f(a)", is_py=False, style="sql") is None
    assert _signature_on_line("select 1; function f(a) {", is_py=False, style="sql") == (
        "f",
        "a",
        False,
    )


# --- 3. a BOM ---------------------------------------------------------------


def test_a_byte_order_mark_does_not_hide_a_python_def() -> None:
    assert _signature_on_line(BOM + "def f(a):", is_py=True) == ("f", "a", True)
    assert _signature_on_line(BOM + "    async def f(a):", is_py=True) == ("f", "a", True)


def test_a_bom_def_is_reported_through_the_detector(tmp_path: Path) -> None:
    _write(tmp_path / "tests" / "unit" / "test_caller.py", "def test_it():\n    do_work('a')\n")
    diff = _diff([BOM + "def do_work(a):"], [BOM + "def do_work(a, b):"], "core/thing.py")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "tests/unit/test_caller.py" in {f["path"] for f in findings}


# --- 5. whitespace shapes of a Python def, and what a stub is ----------------

PY_SPACING = {
    "two-spaces-after-def": "def  f(a):",
    "tab-after-def": "def" + chr(9) + "f(a):",
    "mixed-after-def": "def " + chr(9) + " f(a):",
    "space-before-paren": "def f (a):",
    "tab-before-paren": "def f" + chr(9) + "(a):",
    "two-spaces-after-async": "async  def f(a):",
    "tab-after-async": "async" + chr(9) + "def f(a):",
    "async-space-before-paren": "async def f (a):",
    "leading-tab": chr(9) + "def f(a):",
    "deep-indent": "            def f(a):",
}


@pytest.mark.parametrize("line", PY_SPACING.values(), ids=PY_SPACING)
def test_every_legal_python_spacing_of_a_def_is_read(line: str) -> None:
    assert _signature_on_line(line, is_py=True) == ("f", "a", True)


NOT_PY_SPACING = {
    "no-space-after-def": "deff(a):",
    "def-glued-to-name": "defx(a)",
    "async-glued-to-def": "asyncdef f(a):",
    "def-prefix-word": "undef f(a):",
    "name-starts-with-digit": "def 1f(a):",
}


@pytest.mark.parametrize("line", NOT_PY_SPACING.values(), ids=NOT_PY_SPACING)
def test_text_that_is_not_a_def_is_not_read(line: str) -> None:
    assert _signature_on_line(line, is_py=True) is None


def test_a_stub_file_is_python() -> None:
    assert _is_python_path("core/thing.py")
    assert _is_python_path("core/thing.pyi")
    assert _is_python_path("CORE/THING.PY")
    assert _is_python_path("core/thing.PYI")
    assert not _is_python_path("core/thing.pyx")
    assert not _is_python_path("web/thing.js")
    assert not _is_python_path("core/thing.py.txt")
    assert not _is_python_path("README")


def test_a_stub_file_gets_the_python_compatibility_analysis(tmp_path: Path) -> None:
    _write(tmp_path / "tests" / "unit" / "test_caller.py", "def test_it():\n    do_work('a')\n")
    diff = _diff(["def do_work(a): ..."], ["def do_work(a, *, extra=1): ..."], "core/thing.pyi")
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []
    diff = _diff(["def do_work(a): ..."], ["def do_work(a, *, extra): ..."], "core/thing.pyi")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "tests/unit/test_caller.py" in {f["path"] for f in findings}


def test_a_string_def_in_a_stub_file_is_text(tmp_path: Path) -> None:
    _write(tmp_path / "tests" / "unit" / "test_caller.py", "def test_it():\n    do_work('a')\n")
    diff = _diff(['X = "def do_work(a)"'], ['X = "def do_work(a, b)"'], "core/thing.pyi")
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []
