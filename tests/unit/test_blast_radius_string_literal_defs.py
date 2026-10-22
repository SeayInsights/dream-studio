"""A `def` inside a string literal or a comment is not a definition.

THE DEFECT (PR #923 failed its own blast-radius gate). tests/unit/test_hanging_detectors.py
builds synthetic diffs in string literals, and one of them was edited from

    "+def _connect_analytics(analytics_db_path=None):\\n"   to   "...(analytics_db_path):\\n"

`_SIG_RE` was applied with `.search` to every changed diff line, so the `def` INSIDE THE
STRING was read as a real definition changing signature. The refinement's stricter rule
(a removed default is incompatible) then fired on it and blocked the very PR that
refined the detector. The old names-only comparison had hidden the hazard: nothing in
that edit changed a parameter NAME.

THE RULE.
* A `.py` file: a signature is read only from a line that STARTS a statement,
  `^\\s*(?:async\\s+)?def name(`. Python cannot put a `def` anywhere else, so a `def` after a
  quote, after `return`, after `#` or inside an f-string is text. Quote-parity is not
  needed there, and anchoring is exact where parity is a heuristic.
* Any other file (JS `function`, `export function`, `async function`): the match must not
  sit inside a string literal or comment on its line (`_in_literal_or_comment`): single,
  double and backtick quotes, triple quotes where the line shows them, backslash escapes,
  `//` and `/* */` comments.

LIMIT, SAID PLAINLY: a line is judged alone. A `def`-shaped line in the MIDDLE of a
multi-line string or docstring that starts the statement inside the text
(`    def f(self):` as an example in a docstring) cannot be told from a definition without
the whole file, and is still read as one. The repo's own test files are checked for it
below.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core.gates.hanging_detectors import (
    _in_literal_or_comment,
    _signature_on_line,
    detect_changed_signature_callers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CALLER = "tests/unit/test_caller.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _diff(removed: list[str], added: list[str], path: str = "core/thing.py") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,1 +1,1 @@\n"
        + "".join(f"-{ln}\n" for ln in removed)
        + "".join(f"+{ln}\n" for ln in added)
    )


def _flagged(tmp_path: Path, removed: str, added: str, path: str = "core/thing.py") -> bool:
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    findings = detect_changed_signature_callers(_diff([removed], [added], path), repo_root=tmp_path)
    return CALLER in {f["path"] for f in findings}


# --- the reproduction -------------------------------------------------------


def test_the_923_line_is_not_a_definition(tmp_path: Path) -> None:
    """The exact changed lines of PR #923's edit to test_hanging_detectors.py."""
    _write(
        tmp_path / "projections" / "api" / "routes" / "analytics.py",
        "def go():\n    return _connect_analytics()\n",
    )
    diff = _diff(
        ['        "+def _connect_analytics(analytics_db_path=None):\\n"'],
        ['        "+def _connect_analytics(analytics_db_path):\\n"'],
        path="tests/unit/test_hanging_detectors.py",
    )
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []


def test_the_same_change_as_a_real_def_is_still_reported(tmp_path: Path) -> None:
    """The other direction, so the rule cannot be 'never report a default removed'."""
    assert _flagged(tmp_path, "def do_work(a=None):", "def do_work(a):")


# --- python: only a statement-start def is a def ----------------------------

NOT_A_DEF_PY = {
    "double-quoted": 'x = "def do_work({p})"',
    "single-quoted": "x = 'def do_work({p})'",
    "return-string": '    return "def do_work({p})"',
    "diff-in-a-string": '        "+def do_work({p}):\\n"',
    "diff-in-a-string-minus": "        '-def do_work({p}):\\n'",
    "f-string": 'x = f"def do_work({p})"',
    "raw-string": 'x = r"def do_work({p})"',
    "bytes-string": 'x = b"def do_work({p})"',
    "triple-opened": 'x = """def do_work({p})',
    "comment": "# def do_work({p})",
    "trailing-comment": "x = 1  # def do_work({p})",
    "after-an-escaped-quote": 'x = "\\"" + "def do_work({p})"',
    "after-a-string": 'print("hi"); "def do_work({p})"',
    "after-return": "    return def_do_work_marker + 'def do_work({p})'",
    "bare-text-after-statement": "    note = 'see def do_work({p})'",
}


@pytest.mark.parametrize("line", NOT_A_DEF_PY.values(), ids=NOT_A_DEF_PY)
def test_python_text_that_looks_like_a_def_is_not_one(tmp_path: Path, line: str) -> None:
    removed = line.format(p="a")
    added = line.format(p="a, b")  # a REQUIRED parameter if it were a def
    assert not _flagged(tmp_path, removed, added)
    assert _signature_on_line(removed, is_py=True) is None


REAL_DEFS_PY = {
    "plain": "def do_work({p}):",
    "indented-method": "    def do_work(self, {p}):",
    "tab-indented": "\tdef do_work({p}):",
    "async": "async def do_work({p}):",
    "async-indented": "    async def do_work({p}):",
    "with-annotation": "def do_work({p}) -> int:",
    "string-default": "def do_work({p}, label='x'):",
}


@pytest.mark.parametrize("line", REAL_DEFS_PY.values(), ids=REAL_DEFS_PY)
def test_a_real_python_def_is_still_read(tmp_path: Path, line: str) -> None:
    removed = line.format(p="a")
    added = line.format(p="a, *, extra")  # a new REQUIRED keyword-only parameter
    assert _flagged(tmp_path, removed, added)
    assert _signature_on_line(removed, is_py=True) is not None


def test_a_decorated_def_is_read_from_its_own_line(tmp_path: Path) -> None:
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    diff = (
        "diff --git a/core/thing.py b/core/thing.py\n"
        "--- a/core/thing.py\n"
        "+++ b/core/thing.py\n"
        "@@ -1,3 +1,3 @@\n"
        " @staticmethod\n"
        "-def do_work(a):\n"
        "+def do_work(a, b):\n"
    )
    assert CALLER in {f["path"] for f in detect_changed_signature_callers(diff, repo_root=tmp_path)}


def test_a_decorator_line_is_not_a_def(tmp_path: Path) -> None:
    assert not _flagged(tmp_path, "@register('def do_work(a)')", "@register('def do_work(a, b)')")


# --- other languages: not inside a string or comment on the line ------------

NOT_A_DEF_JS = {
    "double-quoted": 'const s = "function do_work({p})";',
    "single-quoted": "const s = 'function do_work({p})';",
    "template": "const s = `function do_work({p})`;",
    "line-comment": "// function do_work({p})",
    "trailing-line-comment": "go(); // function do_work({p})",
    "block-comment-open": "/* function do_work({p})",
    "block-comment-closed-same-line": "/* function do_work({p}) */",
    "after-an-escaped-quote": 'const s = "say \\"hi\\" function do_work({p})";',
    "apostrophe-in-a-string": 'const s = "don\'t function do_work({p})";',
}


@pytest.mark.parametrize("line", NOT_A_DEF_JS.values(), ids=NOT_A_DEF_JS)
def test_non_python_text_that_looks_like_a_function_is_not_one(tmp_path: Path, line: str) -> None:
    _write(tmp_path / "web" / "caller.js", "function go() { do_work(1); }\n")
    removed = line.format(p="a")
    added = line.format(p="a, b")
    diff = _diff([removed], [added], path="web/lib.js")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "web/caller.js" not in {f["path"] for f in findings}
    assert _signature_on_line(removed, is_py=False) is None


REAL_DEFS_JS = {
    "function": "function do_work({p}) {{",
    "export": "export function do_work({p}) {{",
    "export-default": "export default function do_work({p}) {{",
    "async": "async function do_work({p}) {{",
    "indented": "    function do_work({p}) {{",
    "assigned": "const g = function do_work({p}) {{",
    "after-a-closed-block-comment": "/* don't */ function do_work({p}) {{",
    "after-a-string": "const s = 'x'; function do_work({p}) {{",
    "after-an-escaped-quote-string": 'const s = "a\\"b"; function do_work({p}) {{',
    "after-a-template": "const s = `x`; function do_work({p}) {{",
    # The prefix judged is what comes BEFORE `function`, not the parameters after it.
    "quote-inside-its-own-parameters": 'function do_work({p}, s=")") {{',
}


@pytest.mark.parametrize("line", REAL_DEFS_JS.values(), ids=REAL_DEFS_JS)
def test_a_real_javascript_function_is_still_read(tmp_path: Path, line: str) -> None:
    _write(tmp_path / "web" / "caller.js", "function go() { do_work(1); }\n")
    removed = line.format(p="a")
    added = line.format(p="a, b")
    diff = _diff([removed], [added], path="web/lib.js")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert "web/caller.js" in {f["path"] for f in findings}
    assert _signature_on_line(removed, is_py=False) is not None


def test_a_def_in_a_non_python_file_is_still_a_name_comparison(tmp_path: Path) -> None:
    """Behaviour kept: a `def` line in a non-Python file is read, with the name comparison
    and no compatibility analysis (the existing test_blast_radius_compatible_signature
    case)."""
    sig = _signature_on_line("def do_work(a, b)", is_py=False)
    assert sig == ("do_work", "a, b", False)


def test_the_first_real_match_on_a_line_wins() -> None:
    """A string mentioning a function, then a real one: the real one is the signature."""
    sig = _signature_on_line("const s = 'function x(q)'; function do_work(a) {", is_py=False)
    assert sig == ("do_work", "a", False)


# --- the scanner itself -----------------------------------------------------

SCANNER = [
    ("", False),
    ("x = 1; ", False),
    ('x = "', True),
    ('x = "a" + ', False),
    ('x = "a" + "', True),
    ("x = '", True),
    ("x = 'a' ; ", False),
    ("x = `", True),
    ("x = `a` ; ", False),
    ('x = "a\\"', True),  # an escaped quote does not close it
    ('x = "a\\\\" ; ', False),  # an escaped backslash does, then the quote closes
    ('x = """', True),
    ('x = """abc""" ; ', False),
    ("x = '''", True),
    ("x = '''abc''' ; ", False),
    ('x = """abc" "', True),  # quotes inside a triple string do not close it
    ('x = f"{y} ', True),
    ('x = f"{y}" ; ', False),
    ('x = r"\\d" ; ', False),
    ("x = r'\\d' ; ", False),
    ("// ", True),
    ("go(); // ", True),
    ('s = "//"; ', False),  # a // inside a string is not a comment
    ("/* ", True),
    ("/* a */ ", False),
    ("/* don't */ ", False),  # the apostrophe is comment text
    ("/* a */ /* ", True),
    ("it's ", True),
    # A lone quote INSIDE a triple string is content: only a recognised triple opens it.
    ('x = """a"b ', True),
    ('x = """a"b""" ; ', False),
    ("x = '''a'b ", True),
    ("x = '''a'b''' ; ", False),
    ('x = """"', True),  # triple, then one more quote that is content
    ('x = """a"""""', False),  # a closed triple, then an empty string
    ("x = ```a`b ", False),  # JS: backticks are never triple, three are empty+open
    ("/* a *// 2 ", False),  # `*/` ends the comment; the next `/` is division, not `//`
]


@pytest.mark.parametrize("prefix,expected", SCANNER, ids=[repr(p) for p, _ in SCANNER])
def test_the_literal_scanner(prefix: str, expected: bool) -> None:
    assert _in_literal_or_comment(prefix) is expected


# --- the gate must never block a PR that edits the gate's own tests ----------


def _own_test_files() -> list[Path]:
    files = [REPO_ROOT / "tests" / "unit" / "test_hanging_detectors.py"]
    files += sorted((REPO_ROOT / "tests" / "unit").glob("test_blast_radius_*.py"))
    files += sorted((REPO_ROOT / "tests" / "unit" / "gates").glob("*.py"))
    return [f for f in files if f.is_file()]


def test_the_own_test_files_exist() -> None:
    assert len(_own_test_files()) >= 6


@pytest.mark.parametrize("path", _own_test_files(), ids=lambda p: p.name)
def test_every_def_read_from_the_own_test_files_is_a_real_def(path: Path) -> None:
    """Over the repo's own test files, a line the detector reads as a definition must BE
    one, judged by `ast`. Catches the residual (a def-shaped statement in the middle of a
    docstring) in a file we control, and any future string that slips past the anchor."""
    source = path.read_text(encoding="utf-8")
    real = {
        n.lineno
        for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    mistaken = [
        (i, line)
        for i, line in enumerate(source.splitlines(), start=1)
        if _signature_on_line(line, is_py=True) is not None and i not in real
    ]
    assert not mistaken, f"{path.name}: read as a def but is not one: {mistaken[:5]}"


@pytest.mark.parametrize("path", _own_test_files(), ids=lambda p: p.name)
def test_editing_the_own_test_files_changes_no_signature(path: Path) -> None:
    """Simulate a PR that edits this test file: every line is removed and re-added, and
    every def-SHAPED line that is not a real def (a string, a comment) is changed to add a
    required parameter. The detector must report nothing: it must never block a PR for
    editing the gate's tests."""
    original = path.read_text(encoding="utf-8").splitlines()
    shape = re.compile(r"\bdef\s+[A-Za-z_]\w*\s*\(")
    edited = []
    changed_lines = 0
    for line in original:
        if shape.search(line) and _signature_on_line(line, is_py=True) is None:
            line = shape.sub(lambda m: m.group(0) + "zz_extra, ", line, count=1)
            changed_lines += 1
        edited.append(line)
    rel = path.relative_to(REPO_ROOT).as_posix()
    diff = _diff(original, edited, path=rel)
    assert detect_changed_signature_callers(diff, repo_root=REPO_ROOT) == []
    if path.name == "test_hanging_detectors.py":
        assert changed_lines > 0, "the simulation changed nothing: it proves nothing"
