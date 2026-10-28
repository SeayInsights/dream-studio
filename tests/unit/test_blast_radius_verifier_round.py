"""Findings F1-F9 of the independent verification of 8aeb826a, and the mutant gaps.

F1  The per-hunk Python string state came from the working tree, so an uncommitted edit
    (or a hunk with no matching copy) could put a hunk "inside a string" and hide a real
    changed def: main reported it, the tip did not. The detector now takes a `file_reader`
    (the blast-radius gate hands it `git show HEAD:path`), and a copy that does not carry
    the hunk's own lines is not trusted.
F2  A lone CR inside a docstring shifted the line index (`read_text` treats it as a
    newline, git does not).
F3  In C-like files `/` after `<` was read as a regex start, so `</p> <script>function
    foo(a){}</script>` lost its def. Regex-versus-division now follows the previous token
    the way a JS lexer does.
F4  `$#` and `${#x}` were read as shell comments. A `#` comment starts at a token.
F5  Nested same-type triple quotes in a 3.12 f-string and backslash-continued strings
    broke the hand lexer. `tokenize` is the source of truth for files that tokenize.
F6  Alias resolution was quadratic: a reverse chain of 2,000 links took 13.7 s.
F7  A dropped shape that is not a duplicate of a surviving one is a signature change.
F8  More introspection forms: getattr with a dunder name, `sig = inspect.signature`,
    helpers wrapping it, getmembers, `with ... as`, match captures.
F9  A non-UTF-8 file under the root crashed the scan; the definition walk ran once per name.
"""

from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import sys
import sysconfig
import time
import tokenize
from pathlib import Path

import pytest

from core.gates import blast_radius as br
from core.gates import hanging_detectors as hd
from core.gates.hanging_detectors import (
    _classify_changes,
    _in_literal_or_comment,
    _inspects_symbol,
    _py_ignorable_lines,
    _py_line_end_state,
    _py_start_states,
    _signature_on_line,
    detect_changed_signature_callers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CALLER = "tests/unit/test_caller.py"
PLAIN = "def test_it():\n    do_work('a')\n"
COMPAT = (["a"], ["a, *, extra=1"])
BREAKING = (["a"], ["a, *, extra"])
BUDGET = 5.0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _def_diff(removed: list[str], added: list[str], path: str = "core/thing.py") -> str:
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n"
        + "".join(f"-def do_work({p}):\n" for p in removed)
        + "".join(f"+def do_work({p}):\n" for p in added)
    )


def _hunk_diff(path: str, new_start: int, lines: list[str]) -> str:
    n_old = sum(1 for ln in lines if ln[0] in " -")
    n_new = sum(1 for ln in lines if ln[0] in " +")
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
        f"@@ -{new_start},{n_old} +{new_start},{n_new} @@\n" + "\n".join(lines) + "\n"
    )


def _flagged(tmp_path: Path, caller: str, change=COMPAT, **kwargs) -> bool:
    _write(tmp_path / CALLER, caller)
    findings = detect_changed_signature_callers(_def_diff(*change), repo_root=tmp_path, **kwargs)
    return CALLER in {f["path"] for f in findings}


def _record(path: str, *hunks: tuple[int, list[tuple[str, str]]]) -> dict:
    lines = [ln for _, hunk in hunks for ln in hunk]
    return {
        "path": path,
        "removed": [t for tag, t in lines if tag == "-"],
        "added": [t for tag, t in lines if tag == "+"],
        "hunks": [{"new_start": start, "lines": hunk} for start, hunk in hunks],
    }


# --- F1: the state of a hunk comes from the diff's head, not the working tree ----------


def test_a_dirty_working_tree_cannot_hide_a_real_def_when_the_head_is_read(
    tmp_path: Path,
) -> None:
    """The working tree carries an UNCOMMITTED opener above the def. The committed file (what
    the diff describes) does not. With the head's text as the reader the def is real."""
    _write(
        tmp_path / "core" / "x.py",
        "S = '''\nx\ndef do_work(a, b):\n    pass\n'''\n",
    )
    head = "A = 1\nB = 2\ndef do_work(a, b):\n    pass\n"
    diff = _hunk_diff("core/x.py", 3, ["-def do_work(a):", "+def do_work(a, b):", "     pass"])
    _write(tmp_path / CALLER, PLAIN)
    findings = detect_changed_signature_callers(
        diff, repo_root=tmp_path, file_reader=lambda path: head
    )
    assert CALLER in {f["path"] for f in findings}


def test_without_a_reader_the_working_tree_is_the_best_effort_source(tmp_path: Path) -> None:
    """KNOWN LIMIT, pinned: the default reads the working tree, and a dirty tree that still
    carries the hunk's own lines is believed. The blast-radius gate does not rely on this: it
    passes the git object."""
    _write(
        tmp_path / "core" / "x.py",
        "S = '''\nx\ndef do_work(a, b):\n    pass\n'''\n",
    )
    diff = _hunk_diff("core/x.py", 3, ["-def do_work(a):", "+def do_work(a, b):", "     pass"])
    _write(tmp_path / CALLER, PLAIN)
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []


def test_a_copy_that_does_not_carry_the_hunks_lines_is_not_trusted(tmp_path: Path) -> None:
    """A dirty tree that SHIFTED the lines: line 3 of the copy is not the hunk's first line,
    so the copy says nothing about the hunk and its state starts in code."""
    _write(
        tmp_path / "core" / "x.py",
        "X = 0\nS = '''\nx\ndef do_work(a, b):\n    pass\n'''\n",
    )
    diff = _hunk_diff("core/x.py", 3, ["-def do_work(a):", "+def do_work(a, b):", "     pass"])
    _write(tmp_path / CALLER, PLAIN)
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


def test_a_copy_with_fewer_lines_than_the_hunk_is_not_trusted(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "x.py", "S = '''\nx\n")
    f = _record("core/x.py", (3, [("-", "def a(p):"), ("+", "def a(p, q):"), (" ", "pass")]))
    assert _py_ignorable_lines(f, tmp_path) == (set(), set())


def test_trailing_whitespace_is_part_of_the_line_when_a_copy_is_compared(tmp_path: Path) -> None:
    """Only a CR is forgiven at a line's end: a copy whose line differs by trailing spaces is
    a different line, and a copy that matches them exactly is trusted."""
    _write(tmp_path / "core" / "x.py", "S = '''   \ndef do_work(a, b):   \n'''\n")
    same = _record("core/x.py", (2, [("-", "def do_work(a):   "), ("+", "def do_work(a, b):   ")]))
    assert _py_ignorable_lines(same, tmp_path) == ({0}, {0})
    different = _record("core/x.py", (2, [("-", "def do_work(a):"), ("+", "def do_work(a, b):")]))
    assert _py_ignorable_lines(different, tmp_path) == (set(), set())


def test_a_deleted_file_has_no_copy_and_starts_in_code(tmp_path: Path) -> None:
    f = _record("core/gone.py", (1, [("-", "def a(p):")]))
    assert _py_ignorable_lines(f, tmp_path) == (set(), set())


def test_a_new_file_is_judged_by_its_own_lines(tmp_path: Path) -> None:
    """No copy on disk: every line of a new file is in the hunk, and the string state is
    carried through it from the first line."""
    lines = [
        "+SRC = '''",
        "+def do_work(a):",
        "+    return 1",
        "+'''",
        "+def real(a):",
        "+    return 2",
    ]
    diff = (
        "diff --git a/core/new.py b/core/new.py\nnew file mode 100644\n--- /dev/null\n"
        "+++ b/core/new.py\n@@ -0,0 +1,6 @@\n" + "\n".join(lines) + "\n"
    )
    f = hd._parse_diff(diff)[0]
    assert _py_ignorable_lines(f, tmp_path) == (set(), {1, 2, 3})


def test_a_reader_may_decline_and_the_hunk_starts_in_code(tmp_path: Path) -> None:
    f = _record("core/x.py", (3, [("-", "def a(p):"), ("+", "def a(p, q):")]))
    assert _py_ignorable_lines(f, tmp_path, file_reader=lambda path: None) == (set(), set())


def test_the_reader_is_asked_for_the_diffs_path_once_per_file(tmp_path: Path) -> None:
    asked = []

    def reader(path):
        asked.append(path)
        return "S = '''\nx\ndef a(p, q):\n'''\ndef b(p, q):\n'''\n"

    f = _record(
        "core/x.py",
        (3, [("-", "def a(p):"), ("+", "def a(p, q):")]),
        (5, [("-", "def b(p):"), ("+", "def b(p, q):")]),
    )
    removed, added = _py_ignorable_lines(f, tmp_path, file_reader=reader)
    assert asked == ["core/x.py"]
    assert removed == {0} and added == {0}


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def test_the_gate_reads_the_head_object_not_the_working_tree(tmp_path: Path) -> None:
    """End to end in a real repository: commit a def change, then dirty the working tree with
    an opener ABOVE the hunk that keeps every line number, so the copy on disk still carries
    the hunk's own lines. Read from disk the committed def would be hidden inside a string;
    the gate's reader is `git show HEAD:path`, so it is a definition."""
    try:
        _git(tmp_path, "init", "-q")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    filler = "".join(f"v{i} = {i}\n" for i in range(1, 9))
    _write(tmp_path / "core" / "x.py", filler + "def do_work(a):\n    pass\n")
    _write(tmp_path / CALLER, PLAIN)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    committed = filler + "def do_work(a, b):\n    pass\n"
    _write(tmp_path / "core" / "x.py", committed)
    _git(tmp_path, "commit", "-q", "-am", "change")
    dirty = committed.replace("v2 = 2\n", "S = '''\n")
    assert dirty.count("\n") == committed.count("\n")
    _write(tmp_path / "core" / "x.py", dirty)
    _git(tmp_path, "add", "core/x.py")  # staged too: the INDEX is not HEAD either
    diff, changed = br._resolve_diff_and_changed(tmp_path, "HEAD~1")
    assert "+def do_work(a, b):" in diff
    assert changed == ["core/x.py"]
    reader = br._git_head_reader(tmp_path)
    assert reader("core/x.py") == committed
    assert reader("core/absent.py") is None
    from core.gates.hanging_detectors import run_all_detectors

    def callers(**kwargs):
        found = run_all_detectors(diff, repo_root=tmp_path, **kwargs)
        return {f["path"] for f in found if f["detector"] == "changed_signature_caller"}

    assert CALLER in callers(file_reader=reader)
    assert callers() == set(), "the working-tree reader is the pinned best-effort default"


def test_the_git_reader_keeps_a_lone_carriage_return(tmp_path: Path) -> None:
    """The text of a blob is decoded from bytes: universal newlines would turn a bare CR into
    a line break that git does not count and shift every line after it."""
    try:
        _git(tmp_path, "init", "-q")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "x.py").write_bytes(b"A = 1\rB = 2\r\nS = 3\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    assert br._git_head_reader(tmp_path)("core/x.py") == "A = 1\rB = 2\r\nS = 3\n"


def test_the_gate_passes_the_head_reader_to_the_detectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = {}

    def spy(diff_text, *, repo_root, file_reader=None):
        seen["reader"] = file_reader
        return []

    import core.gates.hanging_detectors as detectors

    monkeypatch.setattr(detectors, "run_all_detectors", spy)
    monkeypatch.setattr(br, "compute_impact_set", lambda changed, repo_root: {})
    br.evaluate("", [], repo_root=tmp_path, file_reader="sentinel")
    assert seen["reader"] == "sentinel"


def test_main_hands_the_gate_a_git_head_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    seen = {}

    def fake_evaluate(diff_text, changed, *, repo_root, file_reader=None):
        seen["reader"] = file_reader
        return {
            "status": "pass",
            "findings": [],
            "impact_set": {},
            "blocking_finding_count": 0,
        }

    monkeypatch.setattr(br, "evaluate", fake_evaluate)
    monkeypatch.setattr(br, "_resolve_diff_and_changed", lambda root, ref: ("", []))
    assert br.main() == 0
    assert callable(seen["reader"])
    capsys.readouterr()


# --- F2: a lone CR is not a line break --------------------------------------------------


def test_a_lone_carriage_return_does_not_shift_the_line_index(tmp_path: Path) -> None:
    """git counts lines by newline; a bare CR inside a docstring is just a character."""
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "x.py").write_bytes(b"A = 1\rB = 2\nS = '''\ndef do_work(a, b):\n'''\n")
    f = _record("core/x.py", (3, [("-", "def do_work(a):"), ("+", "def do_work(a, b):")]))
    assert _py_ignorable_lines(f, tmp_path) == ({0}, {0})


def test_a_crlf_file_is_read_with_its_lines_intact(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "x.py").write_bytes(b"A = 1\r\nS = '''\r\ndef do_work(a, b):\r\n'''\r\n")
    f = _record("core/x.py", (3, [("-", "def do_work(a):\r"), ("+", "def do_work(a, b):\r")]))
    assert _py_ignorable_lines(f, tmp_path) == ({0}, {0})


def test_start_states_do_not_treat_a_lone_carriage_return_as_a_line() -> None:
    text = "A = 1\rB = 2\nS = '''\ndef f(a):\n'''\n"
    assert _py_start_states(text) == [None, None, "'''", "'''"]


# --- F3: regex or division, by the previous token ---------------------------------------

FOO = ("foo", "a", False)
BAR = ("bar", "a", False)
HTML_SHAPES = {
    "closing-tag-then-script": ("<p>hi</p> <script>function foo(a){}</script>", FOO),
    "script-then-closing-tags": ("<script>function foo(a){}</script><p>x</p></div>", FOO),
    "self-closing-tag": ("<br/><script>function foo(a){}</script>", FOO),
    "jsx-self-closing": ("const x = <Foo />; function bar(a){}", BAR),
    "jsx-closing-tag": ("const x = <div>a</div>; function bar(a){}", BAR),
    "jsx-link": ('return <a href="/x">t</a>; function bar(a){}', BAR),
    "tsx-generic-then-closing": ("const x = <T,>(a: T) => a; </div> function bar(a){}", BAR),
    "slash-text-after-a-tag": ("<a>/</a> <script>function foo(a){}</script>", FOO),
    "arrow-returning-a-regex": ("const f = (s) => /'/.test(s); function bar(a){}", BAR),
    "less-than-then-a-regex": ("const r = a < /'/.test(s); function bar(a){}", BAR),
    "division-of-an-identifier": ("x = total / count + 'it'; function bar(a){}", BAR),
    "closing-tag-with-a-quote-after": ("</p> it's <script>function foo(a){}</script>", None),
}


@pytest.mark.parametrize("line,expected", HTML_SHAPES.values(), ids=HTML_SHAPES)
def test_html_and_jsx_shapes(line: str, expected) -> None:
    assert _signature_on_line(line, is_py=False) == expected


KEYWORDS = [
    "return",
    "typeof",
    "instanceof",
    "in",
    "of",
    "delete",
    "void",
    "throw",
    "case",
    "do",
    "else",
    "yield",
    "await",
]


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_a_slash_after_a_keyword_starts_a_regex(keyword: str) -> None:
    line = f"{keyword} /'/.test(s); function bar(a){{}}"
    assert _signature_on_line(line, is_py=False) == BAR


@pytest.mark.parametrize(
    "word",
    ["myreturn", "return2", "x_in", "typeofx", "undo", "elsewhere", "a1in", "my$return", "$in"],
)
def test_a_slash_after_a_word_that_merely_contains_a_keyword_is_a_division(word: str) -> None:
    """The word is read whole, back to its start: `x_in`, `a1in` and `my$return` end in a
    keyword but are not one. Read as a keyword the slash would be a regex that runs on to
    the slash INSIDE the string below and leaves the quote after it open."""
    line = f"x = {word} / 2 + '/' + y; function bar(a){{}}"
    assert _signature_on_line(line, is_py=False) == BAR


def test_the_known_limit_of_a_regex_after_a_keyword_is_gone() -> None:
    assert _signature_on_line("return /'/.test(s); function bar(a){}", is_py=False) == BAR


def test_a_regex_literal_is_a_division_operand_after_it() -> None:
    """After a regex literal a `/` is a division. Read as a regex it would run on to the next
    slash and swallow the quote that opens the string holding the `function`."""
    line = "x = /a/ / 2 + '/' + y; function bar(b){}"
    assert _signature_on_line(line, is_py=False) == ("bar", "b", False)


def test_a_class_holding_a_slash_and_a_quote_is_one_regex() -> None:
    assert _signature_on_line("x = /[/']/; function bar(a){}", is_py=False) == BAR
    assert _signature_on_line("x = /[']/; function bar(a){}", is_py=False) == BAR
    assert _signature_on_line("x = /[^/]+'/; function bar(a){}", is_py=False) == BAR


def test_a_slash_after_an_arrow_but_not_after_a_bare_greater_than() -> None:
    assert _signature_on_line("f = s => /'/.test(s); function bar(a){}", is_py=False) == BAR
    assert _signature_on_line("<a>/'<b> function bar(a){}", is_py=False) is None
    # After a bare `>` the slash is a division, so the quote opens a string that swallows the
    # def. Read as a regex it would run on to the slash of `</a>` and let the def through.
    assert _signature_on_line("<a>/'</a> function bar(b){}", is_py=False) is None


@pytest.mark.parametrize(
    "line,style",
    [
        ("go();// function f(a)", "c"),
        ("x = 1;// function f(a)", "c"),
        ("select 1;-- function f(a)", "sql"),
        ("select 1--function f(a)", "sql"),
    ],
)
def test_only_a_hash_comment_needs_a_token_start(line: str, style: str) -> None:
    """`//` and `--` start a comment wherever they stand; only `#` is held to a token."""
    assert _signature_on_line(line, is_py=False, style=style) is None


# --- F4: a hash comment starts a token --------------------------------------------------

HASH_LINES = {
    "dollar-hash": ("[ $# -gt 0 ] && function foo() { :; }", ("foo", "", False)),
    "brace-hash": ("echo ${#x}; function foo() { :; }", ("foo", "", False)),
    "hash-mid-word": ("x=a#b; function foo() { :; }", ("foo", "", False)),
    "hash-in-a-url": ("curl http://x/#frag; function foo() { :; }", ("foo", "", False)),
    "comment-at-line-start": ("# function foo()", None),
    "comment-after-a-space": ("run # function foo()", None),
    "comment-after-a-tab": ("run" + chr(9) + "# function foo()", None),
    "indented-comment": ("    # function foo()", None),
    "escaped-hash": ("echo \\# function foo() { :; }", ("foo", "", False)),
}


@pytest.mark.parametrize("line,expected", HASH_LINES.values(), ids=HASH_LINES)
def test_a_hash_comment_starts_a_token(line: str, expected) -> None:
    assert _signature_on_line(line, is_py=False, style="hash") == expected


def test_the_hash_scanner_by_position() -> None:
    assert _in_literal_or_comment("echo a#b ", style="hash") is False
    assert _in_literal_or_comment("echo a #b", style="hash") is True
    assert _in_literal_or_comment("#b", style="hash") is True
    assert _in_literal_or_comment("$#", style="hash") is False
    assert _in_literal_or_comment("${#", style="hash") is False


# --- F5: tokenize is the source of truth for python files -------------------------------

needs_312 = pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 701 f-strings")


@needs_312
def test_nested_same_type_triple_quotes_in_an_f_string_do_not_leak() -> None:
    source = 'x = f"{"""abc"""}"\nS = """\ndef do_work(a, b):\n"""\ndef later(c):\n    pass\n'
    assert _py_start_states(source) == [None, None, '"""', '"""', None, None]


@needs_312
def test_a_multi_line_f_string_is_a_string() -> None:
    source = 'x = f"""\nline {1 + 1}\ndef do_work(a, b):\n"""\ndef later(c):\n    pass\n'
    assert _py_start_states(source) == [None, '"""', '"""', '"""', None, None]


def test_a_backslash_continued_single_quoted_string_is_a_string() -> None:
    source = "S = 'abc\\\ndef do_work(a, b):'\nT = 1\n"
    assert _py_start_states(source) == [None, "'", None]


def test_the_hand_lexer_follows_a_continuation_too() -> None:
    assert _py_line_end_state("S = 'abc\\", None) == "'"
    assert _py_line_end_state("def do_work(a, b):'", "'") is None
    assert _py_line_end_state("x = 'abc\\" + chr(13), None) == "'"
    assert _py_line_end_state('S = "abc\\', None) == '"'
    assert _py_line_end_state("S = 'abc\\\\", None) is None  # an escaped backslash: no continuation
    assert _py_line_end_state("middle of it", "'") is None  # no backslash: the string ends
    assert _py_line_end_state("S = 'abc'", None) is None


@pytest.mark.parametrize(
    "prefix", ["r", "R", "b", "B", "u", "U", "rb", "Rb", "bR", "BR", "f", "F", "rf", "fR", "Rf"]
)
def test_string_prefixes_do_not_change_the_delimiter(prefix: str) -> None:
    source = f"S = {prefix}\"\"\"\nx\n\"\"\"\nT = {prefix}'''\ny\n'''\n"
    states = _py_start_states(source)
    assert states[1] == '"""' and states[2] == '"""'
    assert states[4] == "'''" and states[5] == "'''"


def test_a_continued_single_quote_state_is_read_by_the_hand_lexer() -> None:
    """In the continued string `'` closes it, and what follows is code: a triple opened
    after it is a triple."""
    assert _py_line_end_state("abc' + '''", "'") == "'''"
    assert _py_line_end_state("abc' + '''", None) is None  # not a continuation: it opens one


def test_a_file_that_does_not_tokenize_falls_back_to_the_hand_lexer() -> None:
    source = "x = (\nS = '''\ndef a(p):\n'''\n"
    assert _py_start_states(source) == [None, None, "'''", "'''"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("A = 1\rB = 2\nS = '''\nx\n'''\n", [None, None, "'''", "'''"]),
        ("S = '''a\rb\nc\n'''\nT = 1\n", [None, "'''", "'''", None]),
        ("# a\rb\nS = '''\nx\n'''\n", [None, None, "'''", "'''"]),
        ("S = '''\r\nx\r\n'''\r\nT = 1\r\n", [None, "'''", "'''", None]),
    ],
    ids=["in-code", "in-a-docstring", "in-a-comment", "crlf"],
)
def test_a_lone_carriage_return_is_a_character_for_every_source(text: str, expected) -> None:
    """Both sources count lines by newline: the tokenizer and the hand lexer agree."""
    assert _py_start_states(text) == expected
    assert hd._py_start_states_lexer(text) == expected


def _tokenize_inside(text: str) -> dict[int, bool] | None:
    """An independent reading of `tokenize`: rows that start inside a multi-line string."""
    inside: dict[int, bool] = {}
    stack: list[int] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                inside.update(dict.fromkeys(range(tok.start[0] + 1, tok.end[0] + 1), True))
            elif tok.type == getattr(tokenize, "FSTRING_START", -1):
                stack.append(tok.start[0])
            elif tok.type == getattr(tokenize, "FSTRING_END", -1) and stack:
                start = stack.pop()
                inside.update(dict.fromkeys(range(start + 1, tok.end[0] + 1), True))
    except (tokenize.TokenError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    return inside


def _lexer_only_inside(text: str) -> set[int]:
    state = None
    rows = set()
    for number, line in enumerate(hd._split_source_lines(text), start=1):
        if state is not None:
            rows.add(number)
        state = _py_line_end_state(line, state)
    return rows


def _tracked_python_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if out.returncode != 0 or not out.stdout.strip():
        pytest.skip("not a git checkout")
    return [REPO_ROOT / line for line in out.stdout.splitlines() if line]


def _read(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def test_the_production_states_are_the_tokenizers_on_every_tracked_python_file() -> None:
    checked = 0
    for path in _tracked_python_files():
        text = _read(path)
        if text is None:
            continue
        oracle = _tokenize_inside(text)
        if oracle is None or re.search(r"\r(?!\n)", text):
            continue
        mine = {i + 1 for i, s in enumerate(_py_start_states(text)) if s is not None}
        assert mine == set(oracle), f"{path.name}: {sorted(mine ^ set(oracle))[:6]}"
        checked += 1
    assert checked > 1000


def test_the_hand_lexer_agrees_with_tokenize_on_every_tracked_python_file() -> None:
    """The fallback must be good, not just present: on this repo's own files it agrees with
    `tokenize` everywhere."""
    disagreements = []
    for path in _tracked_python_files():
        text = _read(path)
        if text is None:
            continue
        oracle = _tokenize_inside(text)
        if oracle is None or re.search(r"\r(?!\n)", text):
            continue
        if _lexer_only_inside(text) != set(oracle):
            disagreements.append(path.name)
    assert not disagreements, disagreements[:10]


def test_the_hand_lexer_and_tokenize_on_a_sample_of_site_packages() -> None:
    """A wider corpus than the repo: the third-party code the interpreter ships with. The
    production path IS tokenize, so it agrees by construction; the number measured here is
    how often the FALLBACK would be wrong, and it is bounded."""
    root = Path(sysconfig.get_paths()["purelib"])
    files = sorted(root.rglob("*.py"))[:600]
    if len(files) < 50:
        pytest.skip("no site-packages sample")
    total = bad = 0
    for path in files:
        text = _read(path)
        if text is None or re.search(r"\r(?!\n)", text):
            continue
        oracle = _tokenize_inside(text)
        if oracle is None:
            continue
        total += 1
        production = {i + 1 for i, s in enumerate(_py_start_states(text)) if s is not None}
        assert production == set(oracle), path
        if _lexer_only_inside(text) != set(oracle):
            bad += 1
    assert total > 40
    assert bad / total < 0.03, f"{bad} of {total} files disagree"


# --- F6: alias resolution is linear -----------------------------------------------------


def _chain(n: int, reverse: bool) -> str:
    links = [f"a{i} = a{i - 1}" for i in range(n, 1, -1)]
    if not reverse:
        links.reverse()
    return (
        "import inspect\n\ndef f():\n    return inspect.signature(a%d)\n\n" % n
        + "\n".join(links)
        + "\na1 = do_work\n"
    )


@pytest.mark.parametrize("reverse", [True, False], ids=["reverse-order", "forward-order"])
def test_a_five_thousand_link_alias_chain_is_resolved_in_linear_time(reverse: bool) -> None:
    text = _chain(5000, reverse)
    start = time.perf_counter()
    result = _inspects_symbol(text, "do_work")
    seconds = time.perf_counter() - start
    assert result is True
    assert seconds < BUDGET, f"{seconds:.1f}s for a 5000 link chain"


def test_a_long_chain_that_never_reaches_the_function_is_also_fast() -> None:
    text = _chain(5000, True).replace("a1 = do_work", "a1 = other")
    text += "\nprint(do_work)\n"
    start = time.perf_counter()
    assert _inspects_symbol(text, "do_work") is False
    assert time.perf_counter() - start < BUDGET


def test_many_strings_and_many_aliases_together_stay_linear() -> None:
    lines = ["import inspect", "x0 = do_work"]
    lines += [f"x{i} = x{i - 1}" for i in range(1, 3000)]
    lines += [f"s{i} = 'a.b.c{i}'" for i in range(3000)]
    lines += ["inspect.signature(x2999)"]
    text = "\n".join(lines) + "\n"
    start = time.perf_counter()
    assert _inspects_symbol(text, "do_work") is True
    assert time.perf_counter() - start < BUDGET


# --- F7: a dropped shape that is not a duplicate is a change -----------------------------


def _changed(removed: list[str], added: list[str]) -> bool:
    return _classify_changes([(t, True) for t in removed], [(t, True) for t in added]) is not None


def test_a_dropped_shape_that_does_not_survive_is_reported() -> None:
    assert _changed(["a", "a, b"], ["a, b"])
    assert _changed(["a, b", "c"], ["a, b"])
    assert _changed(["a", "a, b"], ["a"])
    assert _changed(["a", "b"], ["a, c"])


def test_a_dropped_duplicate_of_a_shape_that_survives_is_silent() -> None:
    assert not _changed(["a", "a"], ["a"])
    assert not _changed(["a, b", "a", "a, b"], ["a, b", "a"])
    assert not _changed(["a", "a", "a"], ["a"])


def test_a_dropped_shape_is_reported_through_the_detector(tmp_path: Path) -> None:
    _write(tmp_path / CALLER, PLAIN)
    for removed, added in (
        (["a", "a, b"], ["a, b"]),
        (["a, b", "c"], ["a, b"]),
    ):
        findings = detect_changed_signature_callers(_def_diff(removed, added), repo_root=tmp_path)
        assert CALLER in {f["path"] for f in findings}, (removed, added)


def test_the_two_dropped_duplicates_stay_silent_through_the_detector(tmp_path: Path) -> None:
    _write(tmp_path / CALLER, PLAIN)
    findings = detect_changed_signature_callers(_def_diff(["a", "a"], ["a"]), repo_root=tmp_path)
    assert findings == []


# --- F8: more introspection forms -------------------------------------------------------

FORMS = {
    "getattr-defaults": "getattr(do_work, '__defaults__')\n",
    "getattr-signature": "getattr(do_work, '__signature__')\n",
    "getattr-code": 'getattr(do_work, "__code__")\n',
    "getattr-annotations": "getattr(do_work, '__annotations__', None)\n",
    "getattr-kwdefaults": "getattr(do_work, '__kwdefaults__')\n",
    "getattr-of-an-alias": "fn = do_work\ngetattr(fn, '__defaults__')\n",
    "signature-assigned-to-a-name": "import inspect\nsig = inspect.signature\nsig(do_work)\n",
    "signature-imported-then-assigned": (
        "from inspect import signature\nsig = signature\nsig(do_work)\n"
    ),
    "assigned-twice": "import inspect\na = inspect.signature\nb = a\nb(do_work)\n",
    "helper-def": (
        "import inspect\n\ndef get_sig(fn):\n    return inspect.signature(fn)\n\nget_sig(do_work)\n"
    ),
    "helper-def-with-a-body": (
        "import inspect\n\ndef params(fn):\n    s = inspect.signature(fn)\n    return list(s.parameters)\n\n"
        "params(do_work)\n"
    ),
    "async-helper": (
        "import inspect\n\nasync def get_sig(fn):\n    return inspect.signature(fn)\n\n"
        "get_sig(do_work)\n"
    ),
    "helper-lambda": "import inspect\nget = lambda f: inspect.signature(f)\nget(do_work)\n",
    "helper-of-a-helper": (
        "import inspect\n\ndef one(fn):\n    return inspect.signature(fn)\n\n"
        "def two(g):\n    return one(g)\n\ntwo(do_work)\n"
    ),
    "helper-with-a-keyword-only-parameter": (
        "import inspect\n\ndef get(*, fn):\n    return inspect.signature(fn)\n\nget(fn=do_work)\n"
    ),
    "helper-with-a-positional-only-parameter": (
        "import inspect\n\ndef get(fn, /):\n    return inspect.signature(fn)\n\nget(do_work)\n"
    ),
    "async-for-loop": (
        "import inspect\nREG = [do_work]\n\nasync def f():\n    async for v in REG:\n"
        "        inspect.signature(v)\n"
    ),
    "getmembers": "import inspect\ninspect.getmembers(do_work)\n",
    "getmembers-static": "import inspect\ninspect.getmembers_static(do_work)\n",
    "registry-loop": (
        "import inspect\nREG = {'k': do_work}\nfor k, v in REG.items():\n    inspect.signature(v)\n"
    ),
    "registry-subscript": ("import inspect\nREG = {'k': do_work}\ninspect.signature(REG['k'])\n"),
    "registry-list": "import inspect\nREG = [do_work]\nfor v in REG:\n    inspect.signature(v)\n",
    "with-as": "import inspect\nwith do_work as g:\n    inspect.signature(g)\n",
    "async-with-as": (
        "import inspect\n\nasync def f():\n    async with do_work as g:\n        inspect.signature(g)\n"
    ),
    "match-capture": (
        "import inspect\nmatch do_work:\n    case x:\n        inspect.signature(x)\n"
    ),
    "match-class-capture": (
        "import inspect\nmatch do_work:\n    case Foo(a=y):\n        inspect.signature(y)\n"
    ),
    "match-star-capture": (
        "import inspect\nmatch [do_work]:\n    case [*rest]:\n        inspect.signature(rest)\n"
    ),
    "match-mapping-rest": (
        "import inspect\nmatch {'k': do_work}:\n    case {**rest}:\n        inspect.signature(rest)\n"
    ),
}


@pytest.mark.parametrize("caller", FORMS.values(), ids=FORMS)
def test_more_introspection_forms_are_reported(tmp_path: Path, caller: str) -> None:
    if "match " in caller and sys.version_info < (3, 10):
        pytest.skip("match needs 3.10")
    assert _flagged(tmp_path, caller)


NOT_OURS = {
    # `import inspect; inspect.signature(other)` is here so the file passes the cheap
    # pre-filter and the getattr / helper rules themselves are what is being tested.
    "getattr-with-one-argument": "import inspect\ninspect.signature(other)\ngetattr(do_work)\ndo_work('a')\n",
    "getattr-of-an-ordinary-name": (
        "import inspect\ninspect.signature(other)\ngetattr(do_work, '__name__')\ndo_work('a')\n"
    ),
    "helper-that-measures-its-parameter": (
        "import inspect\ninspect.signature(other)\n\ndef size(fn):\n    return len(fn)\n\n"
        "size(do_work)\ndo_work('a')\n"
    ),
    "getattr-of-another": "getattr(other, '__defaults__')\ndo_work('a')\n",
    "getattr-of-an-ordinary-attribute": "getattr(do_work, '__doc__')\ndo_work('a')\n",
    "getattr-with-a-variable-name": "getattr(do_work, attr)\ndo_work('a')\n",
    "signature-assigned-then-used-on-another": (
        "import inspect\nsig = inspect.signature\nsig(other)\ndo_work('a')\n"
    ),
    "helper-introspecting-something-else": (
        "import inspect\n\ndef get_sig(fn):\n    return inspect.signature(other)\n\n"
        "get_sig(do_work)\ndo_work('a')\n"
    ),
    "helper-that-does-not-introspect": (
        "def run(fn):\n    return fn(1)\n\nrun(do_work)\ndo_work('a')\n"
    ),
    "helper-given-another": (
        "import inspect\n\ndef get_sig(fn):\n    return inspect.signature(fn)\n\n"
        "get_sig(other)\ndo_work('a')\n"
    ),
    "getmembers-of-another": "import inspect\ninspect.getmembers(other)\ndo_work('a')\n",
    "with-as-another": (
        "import inspect\nwith other as g:\n    inspect.signature(g)\ndo_work('a')\n"
    ),
    "match-on-another": (
        "import inspect\nmatch other:\n    case x:\n        inspect.signature(x)\ndo_work('a')\n"
    ),
    "registry-without-it": (
        "import inspect\nREG = {'k': other}\nfor k, v in REG.items():\n    inspect.signature(v)\n"
        "do_work('a')\n"
    ),
}


@pytest.mark.parametrize("caller", NOT_OURS.values(), ids=NOT_OURS)
def test_these_are_not_references(tmp_path: Path, caller: str) -> None:
    if "match " in caller and sys.version_info < (3, 10):
        pytest.skip("match needs 3.10")
    assert not _flagged(tmp_path, caller)


def test_the_genuinely_computed_forms_remain_documented_limits(tmp_path: Path) -> None:
    """No static reading ties these to the function: attribute names and objects computed at
    run time. Pinned so that closing one is a decision."""
    for caller in (
        "import inspect\ndo_work('a')\nfor m in METHODS:\n    getattr(Cls, m)\n",
        "do_work('a')\nvars(Cls)['x']\n",
        "do_work('a')\nCls.__dict__['x'].__defaults__\n",
        "import operator\ndo_work('a')\noperator.attrgetter('__defaults__')(Cls)\n",
    ):
        assert not _flagged(tmp_path, caller)


def test_getattr_needs_a_dunder_that_is_in_the_introspection_set(tmp_path: Path) -> None:
    for attr in ("__defaults__", "__kwdefaults__", "__code__", "__signature__", "__annotations__"):
        assert _flagged(tmp_path, f"getattr(do_work, '{attr}')\n")
    assert not _flagged(tmp_path, "getattr(do_work, '__name__')\ndo_work('a')\n")
    assert not _flagged(tmp_path, "getattr(do_work, '__module__')\ndo_work('a')\n")


# --- the mutant gaps --------------------------------------------------------------------


def test_every_hash_style_suffix_is_a_hash_file() -> None:
    for suffix in hd._HASH_COMMENT_SUFFIXES:
        assert hd._comment_style("dir/file" + suffix) == "hash", suffix
    assert ".ps1" not in hd._HASH_COMMENT_SUFFIXES  # PowerShell has its own style
    assert hd._comment_style("tools/build.ps1") == "ps"
    assert hd._comment_style("lib/Thing.pm") == "hash"
    assert hd._comment_style("lib/thing.pl") == "hash"
    assert hd._comment_style("build/rules.mk") == "hash"


def test_two_introspecting_files_do_not_share_a_parse(tmp_path: Path) -> None:
    """The memo is per file: the second file must be read on its own tree, in both orders."""
    _write(
        tmp_path / "tests" / "unit" / "test_a.py", "import inspect\ninspect.signature(do_work)\n"
    )
    _write(
        tmp_path / "tests" / "unit" / "test_b.py",
        "import inspect\ndo_work('a')\ninspect.signature(other)\n",
    )
    findings = detect_changed_signature_callers(_def_diff(*COMPAT), repo_root=tmp_path)
    assert {f["path"] for f in findings} == {"tests/unit/test_a.py"}


def test_two_introspecting_files_do_not_share_a_parse_reversed(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "unit" / "test_a.py",
        "import inspect\ndo_work('a')\ninspect.signature(other)\n",
    )
    _write(
        tmp_path / "tests" / "unit" / "test_b.py", "import inspect\ninspect.signature(do_work)\n"
    )
    findings = detect_changed_signature_callers(_def_diff(*COMPAT), repo_root=tmp_path)
    assert {f["path"] for f in findings} == {"tests/unit/test_b.py"}


def test_a_hunk_whose_only_def_shaped_line_was_removed_is_still_judged(tmp_path: Path) -> None:
    """Only a removed line is def-shaped here (the added one is not): the hunk must still be
    scanned, or the removed line inside the string would be read as a definition."""
    f = _record(
        "core/x.py",
        (1, [(" ", "S = '''"), ("-", "def a(p):"), ("+", "x = 2"), (" ", "'''")]),
    )
    assert _py_ignorable_lines(f, Path("/nonexistent-root")) == ({0}, {0})


def test_a_hunk_whose_only_def_shaped_line_was_added_is_still_judged(tmp_path: Path) -> None:
    f = _record(
        "core/x.py",
        (1, [(" ", "S = '''"), ("-", "x = 2"), ("+", "def a(p):"), (" ", "'''")]),
    )
    assert _py_ignorable_lines(f, Path("/nonexistent-root")) == ({0}, {0})


# --- F9: a non-utf-8 file, and one walk for the definitions -----------------------------


def test_a_file_that_is_not_utf8_does_not_stop_the_scan(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "latin.py").write_bytes(b"# caf\xe9\nVALUE = 'ol\xe9'\n")
    _write(tmp_path / CALLER, PLAIN)
    findings = detect_changed_signature_callers(_def_diff(*BREAKING), repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


def test_a_non_utf8_file_that_references_the_name_is_still_scanned(tmp_path: Path) -> None:
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / CALLER).write_bytes(b"# caf\xe9\ndef test_it():\n    do_work('a')\n")
    findings = detect_changed_signature_callers(_def_diff(*BREAKING), repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


def test_every_detector_survives_a_non_utf8_file(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "latin.py").write_bytes(b"VALUE = 'ol\xe9'\n")
    assert hd.run_all_detectors(_def_diff(*BREAKING), repo_root=tmp_path) == []


def test_the_tree_is_walked_once_however_many_names_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [f"n{i}" for i in range(40)]
    _write(tmp_path / "tests" / "unit" / "test_big.py", "".join(f"{n}(1)\n" for n in names))
    removed = "".join(f"-def {n}(a):\n" for n in names)
    added = "".join(f"+def {n}(a, *, e):\n" for n in names)
    diff = (
        "diff --git a/core/t.py b/core/t.py\n--- a/core/t.py\n+++ b/core/t.py\n"
        "@@ -1,1 +1,1 @@\n" + removed + added
    )
    walks = []
    real = hd._iter_code_files

    def counting(root):
        walks.append(1)
        return real(root)

    monkeypatch.setattr(hd, "_iter_code_files", counting)
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert len({f["symbol"] for f in findings}) == 40
    assert len(walks) <= 1, f"the tree was walked {len(walks)} times for 40 names"


def test_a_name_defined_twice_is_still_ambiguous_with_the_single_pass(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "one.py", "def do_work(a):\n    return 1\n")
    _write(tmp_path / "core" / "two.py", "def do_work(a):\n    return 2\n")
    _write(tmp_path / "elsewhere.py", "def go():\n    do_work(1)\n")
    findings = detect_changed_signature_callers(
        _def_diff(*BREAKING, path="core/one.py"), repo_root=tmp_path
    )
    assert "elsewhere.py" not in {f["path"] for f in findings}


def test_a_def_inside_a_string_does_not_make_a_name_ambiguous(tmp_path: Path) -> None:
    """Only a def at the start of a line is a definition for the count."""
    _write(tmp_path / "core" / "one.py", "def do_work(a):\n    return 1\n")
    _write(tmp_path / "core" / "note.py", 'HELP = "call def do_work(a) like so"\n')
    _write(tmp_path / "elsewhere.py", "def go():\n    do_work(1)\n")
    findings = detect_changed_signature_callers(
        _def_diff(*BREAKING, path="core/one.py"), repo_root=tmp_path
    )
    assert "elsewhere.py" in {f["path"] for f in findings}


def test_an_async_def_counts_as_a_definition(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "one.py", "def do_work(a):\n    return 1\n")
    _write(tmp_path / "core" / "two.py", "async def do_work(a):\n    return 2\n")
    _write(tmp_path / "elsewhere.py", "def go():\n    do_work(1)\n")
    findings = detect_changed_signature_callers(
        _def_diff(*BREAKING, path="core/one.py"), repo_root=tmp_path
    )
    assert "elsewhere.py" not in {f["path"] for f in findings}


def test_a_name_is_matched_as_an_identifier_not_as_a_substring(tmp_path: Path) -> None:
    """A file naming only `do_work_extra` holds no reference to `do_work`. (The old per-name
    substring test let `patch("pkg.do_work_extra")` through the patch-target pattern.)"""
    _write(
        tmp_path / CALLER,
        "from unittest.mock import patch\n\ndef test_x():\n    with patch('pkg.do_work_extra'):\n        pass\n",
    )
    findings = detect_changed_signature_callers(_def_diff(*BREAKING), repo_root=tmp_path)
    assert CALLER not in {f["path"] for f in findings}


def test_a_name_defined_once_is_not_ambiguous_with_the_single_pass(tmp_path: Path) -> None:
    _write(tmp_path / "elsewhere.py", "def go():\n    do_work(1)\n")
    findings = detect_changed_signature_callers(_def_diff(*BREAKING), repo_root=tmp_path)
    assert "elsewhere.py" in {f["path"] for f in findings}


def test_twenty_thousand_changed_names_finish_in_bounded_time(tmp_path: Path) -> None:
    n = 20_000
    for i in range(30):
        _write(
            tmp_path / "core" / f"m{i}.py",
            "".join(f"def helper_{i}_{j}():\n    pass\n" for j in range(50)),
        )
    _write(tmp_path / "tests" / "unit" / "test_x.py", "n7(1)\nn19999(2)\n")
    removed = "".join(f"-def n{i}(a):\n" for i in range(n))
    added = "".join(f"+def n{i}(a, *, e):\n" for i in range(n))
    diff = (
        "diff --git a/core/t.py b/core/t.py\n--- a/core/t.py\n+++ b/core/t.py\n"
        "@@ -1,1 +1,1 @@\n" + removed + added
    )
    start = time.perf_counter()
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    seconds = time.perf_counter() - start
    assert {f["symbol"] for f in findings} == {"n7", "n19999"}
    assert seconds < 60, f"{seconds:.1f}s for {n} names"


# --- the gate's JSON still reports what it found ----------------------------------------


def test_the_gate_report_is_unchanged_in_shape(tmp_path: Path) -> None:
    report = br.evaluate(
        _def_diff(*COMPAT), ["core/thing.py"], repo_root=tmp_path, file_reader=lambda p: None
    )
    assert report["status"] == "pass"
    assert json.dumps(report)  # serialisable
