"""Findings of the independent verification of e28076f1.

1  A hunk holding a separator that `str.splitlines()` honours (CR, VT, FF, FS, GS, RS, NEL,
   U+2028, U+2029) was split into extra lines by `_parse_diff`, and `_git` read its output
   in text mode, where a lone CR is a line break. The hunk's new side was miscounted, the
   trusted-copy check failed, and a def after a docstring's closer was read as an opener's
   body and skipped: main reported it, the tip did not. Both split on LF only now.
2  `tokenize` raises SystemError for a NUL after an indented line (CPython 3.12.10) and
   IndentationError for a bad dedent: neither was caught, so the gate crashed on a changed
   file. Any failure now falls back.
3  Lexer heuristics: `a > /x'/` was missed, PowerShell `<# #>` blocks over-reported, and a
   3.14 template string was not a string prefix.
4  `_inspects_symbol` and its neighbours scanned the whole file once per changed name:
   2000 names against a 20,000-line file took 71 s. The file is indexed once.
5  The mutants that survived the last round.
6  Paths with non-ASCII characters were quoted by git and so invisible; PEP 695 type
   parameters and multi-line parameter lists were not read.
"""

from __future__ import annotations

import subprocess
import sys
import time
import tokenize
from pathlib import Path

import pytest

from core.gates import blast_radius as br
from core.gates import hanging_detectors as hd
from core.gates.hanging_detectors import (
    _inspects_symbol,
    _param_names,
    _py_ignorable_lines,
    _py_start_states,
    _python_signatures,
    _signature_on_line,
    detect_changed_signature_callers,
)

CALLER = "tests/unit/test_caller.py"
BUDGET = 8.0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _def_diff(removed: list[str], added: list[str], path: str = "core/thing.py") -> str:
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n"
        + "".join(f"-{ln}\n" for ln in removed)
        + "".join(f"+{ln}\n" for ln in added)
    )


def _flagged(tmp_path: Path, removed: list[str], added: list[str]) -> bool:
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    findings = detect_changed_signature_callers(_def_diff(removed, added), repo_root=tmp_path)
    return CALLER in {f["path"] for f in findings}


# --- a real repository, driven by the gate's own functions ------------------------------


def _sh(cwd: Path, *args: str) -> bytes:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if r.returncode:
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace"))
    return r.stdout


def _scenario(
    tmp_path: Path,
    base: bytes,
    head: bytes,
    *,
    path: str = "m.py",
    caller: bytes = b"from m import foo\nfoo(1)\n",
) -> list[dict]:
    """Commit ``base``, branch, commit ``head``, then run the gate's own diff, reader and
    detectors on ``base...HEAD``. Returns the changed-signature findings."""
    try:
        _sh(tmp_path, "init", "-q", "-b", "main")
    except (OSError, RuntimeError):
        pytest.skip("git is not available")
    _sh(tmp_path, "config", "user.email", "a@b.c")
    _sh(tmp_path, "config", "user.name", "t")
    _sh(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_bytes(base)
    (tmp_path / "caller.py").write_bytes(caller)
    _sh(tmp_path, "add", "-A")
    _sh(tmp_path, "commit", "-q", "-m", "base")
    _sh(tmp_path, "checkout", "-q", "-b", "feat")
    (tmp_path / path).write_bytes(head)
    _sh(tmp_path, "add", "-A")
    _sh(tmp_path, "commit", "-q", "-m", "head")
    diff, changed = br._resolve_diff_and_changed(tmp_path, "main")
    assert path in changed, (path, changed)
    reader = br._git_head_reader(tmp_path)
    found = hd.run_all_detectors(diff, repo_root=tmp_path, file_reader=reader)
    return [f for f in found if f["detector"] == "changed_signature_caller"]


# --- 1: the nine separators --------------------------------------------------------------

SEPARATORS = {
    "CR": b"\r",
    "VT": b"\x0b",
    "FF": b"\x0c",
    "FS": b"\x1c",
    "GS": b"\x1d",
    "RS": b"\x1e",
    "NEL": chr(0x85).encode("utf-8"),
    "LS": chr(0x2028).encode("utf-8"),
    "PS": chr(0x2029).encode("utf-8"),
}


def _doc_pair(sep: bytes, nl: bytes = b"\n") -> tuple[bytes, bytes]:
    doc = b'S = """' + nl + b"line1" + nl + b"more" + nl + b"has" + sep + b"sep here" + nl
    doc += b'"""' + nl + nl
    return (
        doc + b"def foo(a):" + nl + b"    return a" + nl,
        doc + b"def foo(a, b):" + nl + b"    return a" + nl,
    )


@pytest.mark.parametrize("sep", SEPARATORS.values(), ids=SEPARATORS)
def test_a_separator_inside_a_docstring_does_not_hide_the_def_after_it(
    tmp_path: Path, sep: bytes
) -> None:
    """The hunk starts INSIDE the docstring (the changed def is three lines below its last
    line), so the string state must come from the copy at HEAD, and the copy is trusted only
    if the hunk's lines are counted as git counts them."""
    base, head = _doc_pair(sep)
    assert [f["path"] for f in _scenario(tmp_path, base, head)] == ["caller.py"]


@pytest.mark.parametrize("sep", SEPARATORS.values(), ids=SEPARATORS)
def test_the_same_in_a_crlf_file(tmp_path: Path, sep: bytes) -> None:
    base, head = _doc_pair(sep, nl=b"\r\n")
    assert [f["path"] for f in _scenario(tmp_path, base, head)] == ["caller.py"]


@pytest.mark.parametrize("sep", SEPARATORS.values(), ids=SEPARATORS)
def test_a_def_inside_the_docstring_stays_text_whatever_the_separator(
    tmp_path: Path, sep: bytes
) -> None:
    body = b'S = """\ntext\ntext\nhas' + sep + b"sep here\n"
    base = body + b"def foo(a):\n    return a\n" + b'"""\nt = 1\n'
    head = body + b"def foo(a, b):\n    return a\n" + b'"""\nt = 1\n'
    assert _scenario(tmp_path, base, head) == []


@pytest.mark.parametrize("sep", SEPARATORS.values(), ids=SEPARATORS)
def test_the_diff_parser_counts_lines_by_lf_only(sep: bytes) -> None:
    text = sep.decode("utf-8")
    diff = (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -1,3 +1,3 @@\n"
        f" has{text}sep here\n-def foo(a):\n+def foo(a, b):\n     pass\n"
    )
    (record,) = hd._parse_diff(diff)
    lines = record["hunks"][0]["lines"]
    assert lines == [
        (" ", f"has{text}sep here"),
        ("-", "def foo(a):"),
        ("+", "def foo(a, b):"),
        (" ", "    pass"),
    ]
    assert record["removed"] == ["def foo(a):"]
    assert record["added"] == ["def foo(a, b):"]


def test_a_trailing_newline_adds_no_phantom_line() -> None:
    diff = "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"
    (record,) = hd._parse_diff(diff)
    assert record["hunks"][0]["lines"] == [("-", "x = 1"), ("+", "x = 2")]
    (record,) = hd._parse_diff(diff.rstrip("\n"))
    assert record["hunks"][0]["lines"] == [("-", "x = 1"), ("+", "x = 2")]


def test_the_gate_reads_git_output_as_bytes(tmp_path: Path) -> None:
    """Text mode would turn a lone CR, and the CR of a CRLF, into line breaks."""
    try:
        _sh(tmp_path, "init", "-q", "-b", "main")
    except (OSError, RuntimeError):
        pytest.skip("git is not available")
    _sh(tmp_path, "config", "user.email", "a@b.c")
    _sh(tmp_path, "config", "user.name", "t")
    _sh(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "m.py").write_bytes(b"A = 1\rB = 2\r\nC = 3\n")
    _sh(tmp_path, "add", "-A")
    _sh(tmp_path, "commit", "-q", "-m", "x")
    assert br._git(["show", "HEAD:m.py"], tmp_path) == "A = 1\rB = 2\r\nC = 3\n"
    assert br._git(["show", "HEAD:absent.py"], tmp_path) == ""


def test_the_gate_decodes_a_non_utf8_file_at_head(tmp_path: Path) -> None:
    try:
        _sh(tmp_path, "init", "-q", "-b", "main")
    except (OSError, RuntimeError):
        pytest.skip("git is not available")
    _sh(tmp_path, "config", "user.email", "a@b.c")
    _sh(tmp_path, "config", "user.name", "t")
    (tmp_path / "m.py").write_bytes(b"x = '\xe9'\n")
    _sh(tmp_path, "add", "-A")
    _sh(tmp_path, "commit", "-q", "-m", "x")
    assert br._git_head_reader(tmp_path)("m.py") == "x = '" + chr(0xFFFD) + "'\n"
    assert br._git(["show", "HEAD:m.py"], tmp_path) == "x = '" + chr(0xFFFD) + "'\n"


# --- 2: a parser that fails in a way nobody listed ---------------------------------------


def test_a_nul_after_an_indented_line_does_not_crash_the_state() -> None:
    """The minimal input that makes `tokenize` raise SystemError on CPython 3.12.10."""
    assert _py_start_states(' ""\n\x00') == [None, None]
    assert isinstance(hd._code_only(' ""\n\x00'), str)


@pytest.mark.parametrize(
    "exc",
    [SyntaxError, IndentationError, tokenize.TokenError, SystemError, ValueError, RuntimeError],
)
def test_any_tokenize_failure_falls_back(monkeypatch: pytest.MonkeyPatch, exc) -> None:
    def refuse(*_a, **_k):
        raise exc("refused")

    monkeypatch.setattr(tokenize, "generate_tokens", refuse)
    source = "S = '''\nx\n'''\n"
    assert _py_start_states(source) == [None, "'''", "'''"]
    assert hd._code_only(source) == source


def test_a_bad_dedent_falls_back() -> None:
    """IndentationError is a SyntaxError subclass the narrow clause used to miss."""
    assert _py_start_states("if x:\n    a = 1\n  b = 2\nS = '''\ny\n'''\n") == [
        None,
        None,
        None,
        None,
        "'''",
        "'''",
    ]


@pytest.mark.parametrize("exc", [SyntaxError, SystemError, ValueError, RuntimeError, OverflowError])
def test_any_ast_failure_is_not_a_parameter_list(monkeypatch: pytest.MonkeyPatch, exc) -> None:
    import ast

    def refuse(*_a, **_k):
        raise exc("refused")

    monkeypatch.setattr(ast, "parse", refuse)
    assert hd._signature_compatibility("a", "a, b") == "unparseable"
    assert hd._parsed_tree("x = 1\n") is None


def test_a_changed_file_with_a_nul_does_not_crash_the_detector(tmp_path: Path) -> None:
    diff = (
        "diff --git a/core/thing.py b/core/thing.py\n--- a/core/thing.py\n+++ b/core/thing.py\n"
        "@@ -1,3 +1,3 @@\n x = 1\n-def do_work(a):\n+def do_work(a, b):\n     pass\n"
    )
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "thing.py").write_bytes(b'x = 1\ndef do_work(a, b):\n  ""\n\x00 ')
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    assert CALLER in {f["path"] for f in findings}


# --- 3: lexer heuristics -----------------------------------------------------------------

BAR = ("bar", "a", False)


@pytest.mark.parametrize(
    "line",
    [
        "a > /x'/.source; function bar(a){}",
        "a >= /x'/.source; function bar(a){}",
        "n = a > /'/.test(s); function bar(a){}",
        "a < /x'/.source; function bar(a){}",
        "a ? /x'/ : 1; function bar(a){}",
        "a ? 1 : /x'/; function bar(a){}",
    ],
)
def test_a_slash_after_an_operator_starts_a_regex(line: str) -> None:
    assert _signature_on_line(line, is_py=False) == BAR


@pytest.mark.parametrize(
    "line",
    [
        "<a>/'</a> function bar(a){}",
        "x = a >/'/ 2; function bar(a){}",
        "x = a </'/ 2; function bar(a){}",
    ],
)
def test_a_slash_against_a_bracket_is_markup_or_a_division(line: str) -> None:
    """DOCUMENTED HEURISTIC: no space between the bracket and the slash. The quote then opens
    a string that swallows the def (a false negative for these shapes)."""
    assert _signature_on_line(line, is_py=False) is None


def test_the_known_lexer_limits_are_pinned() -> None:
    # `if (a) /x'/.test(s)`: a regex after `)` is read as a division.
    assert _signature_on_line("if (a) /x'/.test(s); function bar(a){}", is_py=False) is None
    # JSX text with an apostrophe opens a string.
    assert _signature_on_line("<p>it's</p> <script>function foo(a){}</script>", is_py=False) is None
    # `await` and `yield` are always followed by an expression, so a slash after one is a
    # regex: `yield / 2` (an identifier named yield) over-reports.
    assert _signature_on_line("x = yield / 2 + '/' + y; function bar(a){}", is_py=False) is None
    assert _signature_on_line("await /'/.test(s); function bar(a){}", is_py=False) == BAR


PS = {
    "block-comment": ("<# function f(a) #>", None),
    "unclosed-block-comment": ("<# function f(a)", None),
    "line-comment": ("# function f(a)", None),
    "after-a-block": ("<# note #> function f(a) { }", ("f", "a", False)),
    "after-a-line-with-hash-in-a-string": ("'#' ; function f(a) { }", ("f", "a", False)),
    "backslash-is-a-path-separator": (
        '$p = "C:\\dir\\"; function f(a) { }',
        ("f", "a", False),
    ),
    "backtick-escapes-a-quote": ('"a`"b"; function f(a) { }', ("f", "a", False)),
    "backtick-opens-nothing": ("echo ` ; function f(a) { }", ("f", "a", False)),
    "doubled-single-quote": ("'it''s'; function f(a) { }", ("f", "a", False)),
    "def-inside-a-string": ('$x = "function f(a)"', None),
    "hash-inside-a-word-is-no-comment": ("$a#b; function f(a) { }", ("f", "a", False)),
}


@pytest.mark.parametrize("line,expected", PS.values(), ids=PS)
def test_powershell(line: str, expected) -> None:
    assert _signature_on_line(line, is_py=False, style="ps") == expected


def test_powershell_is_its_own_style() -> None:
    for suffix in (".ps1", ".psm1", ".psd1"):
        assert hd._comment_style("tools/build" + suffix) == "ps"
    assert hd._in_literal_or_comment("<# ", style="ps") is True
    assert hd._in_literal_or_comment("<# x #> ", style="ps") is False
    assert hd._in_literal_or_comment("<# a #> <# ", style="ps") is True
    assert hd._in_literal_or_comment("/* ", style="ps") is False
    assert hd._in_literal_or_comment("<# ", style="hash") is False


def test_template_strings_are_a_string_prefix() -> None:
    assert hd._quote_of('t"""x') == '"""'
    assert hd._quote_of("T'''x") == "'''"
    assert hd._quote_of('rt"x') == '"'
    assert hd._quote_of('f"""x') == '"""'


def test_a_template_string_span_is_a_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """3.14 tokenizes `t"..."` as TSTRING_START .. TSTRING_END, like an f-string."""
    start, end, name = 9001, 9002, tokenize.NAME
    monkeypatch.setattr(tokenize, "TSTRING_START", start, raising=False)
    monkeypatch.setattr(tokenize, "TSTRING_END", end, raising=False)

    def tok(kind, string, srow, scol, erow, ecol):
        return tokenize.TokenInfo(kind, string, (srow, scol), (erow, ecol), "")

    def fake(_readline):
        yield tok(name, "x", 1, 0, 1, 1)
        yield tok(start, 't"""', 1, 4, 1, 8)
        yield tok(end, '"""', 3, 0, 3, 3)
        yield tok(name, "y", 4, 0, 4, 1)

    monkeypatch.setattr(tokenize, "generate_tokens", fake)
    assert _py_start_states('x = t"""\nbody\n"""\ny\n') == [None, '"""', '"""', None]


# --- 4: the file is indexed once ---------------------------------------------------------


def _big_caller(names: list[str], filler: int) -> str:
    lines = ["import inspect"]
    lines += [f"{n}(1)" for n in names]
    lines += [f"inspect.signature(other_{i})" for i in range(filler)]
    return "\n".join(lines) + "\n"


def _many_names_diff(names: list[str], *, compatible: bool) -> str:
    sig = "a, *, e=1" if compatible else "a, *, e"
    removed = "".join(f"-def {n}(a):\n" for n in names)
    added = "".join(f"+def {n}({sig}):\n" for n in names)
    return (
        "diff --git a/core/t.py b/core/t.py\n--- a/core/t.py\n+++ b/core/t.py\n"
        "@@ -1,1 +1,1 @@\n" + removed + added
    )


def test_two_thousand_compatible_names_against_a_twenty_thousand_line_file(
    tmp_path: Path,
) -> None:
    names = [f"n{i}" for i in range(2000)]
    _write(tmp_path / "tests" / "unit" / "test_big.py", _big_caller(names, 20_000))
    start = time.perf_counter()
    findings = detect_changed_signature_callers(
        _many_names_diff(names, compatible=True), repo_root=tmp_path
    )
    seconds = time.perf_counter() - start
    assert findings == []  # a compatible change, and no name is introspected
    assert seconds < 20, f"{seconds:.1f}s (was 71 s)"


def test_the_same_file_still_reports_the_one_name_it_introspects(tmp_path: Path) -> None:
    names = [f"n{i}" for i in range(500)]
    text = _big_caller(names, 5000) + "inspect.signature(n42)\n"
    _write(tmp_path / "tests" / "unit" / "test_big.py", text)
    findings = detect_changed_signature_callers(
        _many_names_diff(names, compatible=True), repo_root=tmp_path
    )
    assert {f["symbol"] for f in findings} == {"n42"}


def test_the_file_is_indexed_once_however_many_names_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [f"n{i}" for i in range(50)]
    _write(tmp_path / "tests" / "unit" / "test_big.py", _big_caller(names, 50))
    built = []
    real = hd._ast_bindings

    def counting(nodes):
        built.append(1)
        return real(nodes)

    monkeypatch.setattr(hd, "_ast_bindings", counting)
    detect_changed_signature_callers(_many_names_diff(names, compatible=True), repo_root=tmp_path)
    assert len(built) <= 1, f"the bindings were collected {len(built)} times for 50 names"


def test_a_direct_call_is_not_memoised_across_calls() -> None:
    text = "import inspect\ninspect.signature(do_work)\n"
    assert _inspects_symbol(text, "do_work")
    assert not _inspects_symbol(text.replace("do_work", "other"), "do_work")
    assert hd._Memo.facts_of is None


def test_facts_are_per_file_during_a_run(tmp_path: Path) -> None:
    """Two files, two sets of facts: the second is not read through the first's index."""
    _write(
        tmp_path / "tests" / "unit" / "test_a.py", "import inspect\ninspect.signature(do_work)\n"
    )
    _write(
        tmp_path / "tests" / "unit" / "test_b.py",
        "import inspect\ndo_work('a')\ninspect.signature(other)\n",
    )
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, extra=1):"]), repo_root=tmp_path
    )
    assert {f["path"] for f in findings} == {"tests/unit/test_a.py"}


# --- 5: the survivors --------------------------------------------------------------------


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 701 f-strings")
def test_a_nested_multi_line_f_string_marks_every_row_inside_it() -> None:
    source = "x = f\"\"\"outer\n{f'''inner\nmore'''}\ntail\"\"\"\ny = 1\n"
    # the inner span's rows carry the inner delimiter, the rest the outer's
    assert _py_start_states(source) == [None, '"""', "'''", '"""', None]


def test_a_regex_after_a_question_mark_is_a_regex() -> None:
    assert _signature_on_line("a ? /x'/ : 1; function bar(a){}", is_py=False) == BAR


def test_a_non_utf8_file_without_a_reader_does_not_raise(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "x.py").write_bytes(b"S = '''\xe9\ndef a(p, q):\n'''\n")
    f = {
        "path": "core/x.py",
        "removed": ["def a(p):"],
        "added": ["def a(p, q):"],
        "hunks": [{"new_start": 2, "lines": [("-", "def a(p):"), ("+", "def a(p, q):")]}],
    }
    assert _py_ignorable_lines(f, tmp_path) == ({0}, {0})


def test_a_changed_file_is_not_scanned_for_callers(tmp_path: Path) -> None:
    """The file the diff changes may well call its own function: it is the diff, not a
    caller left behind."""
    _write(tmp_path / "core" / "thing.py", "def do_work(a, *, e):\n    return do_work(1)\n")
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e):"], "core/thing.py"),
        repo_root=tmp_path,
    )
    assert findings == []


def test_a_name_inside_a_longer_identifier_is_not_a_caller(tmp_path: Path) -> None:
    _write(tmp_path / CALLER, "def test_it():\n    xdo_work(1)\n    do_work_two(2)\n")
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e):"]), repo_root=tmp_path
    )
    assert findings == []


def test_the_text_fallback_reads_a_nested_call() -> None:
    broken = "def broken(:\n    pass\n"
    assert _inspects_symbol(broken + "inspect.signature(getattr(mod, 'do_work'))\n", "do_work")
    assert _inspects_symbol(broken + "inspect.signature(a.get(do_work))\n", "do_work")
    assert not _inspects_symbol(broken + "inspect.signature(getattr(mod, 'other'))\n", "do_work")
    # any depth, within 200 characters on the same line
    assert _inspects_symbol(broken + "inspect.signature(a(b(do_work)))\n", "do_work")
    far = "inspect.signature(" + "x, " * 100 + "do_work)\n"
    assert not _inspects_symbol(broken + far, "do_work")


# --- 6: paths, PEP 695, multi-line parameter lists ---------------------------------------


def test_a_changed_def_in_a_non_ascii_path_is_seen(tmp_path: Path) -> None:
    base = b"def foo(a):\n    return a\n"
    head = b"def foo(a, *, b):\n    return a\n"
    findings = _scenario(tmp_path, base, head, path="caf\u00e9.py")
    assert [f["path"] for f in findings] == ["caller.py"]


def test_the_changed_list_holds_the_real_non_ascii_name(tmp_path: Path) -> None:
    findings = _scenario(
        tmp_path,
        b"def foo(a):\n    pass\n",
        b"def foo(a, *, b):\n    pass\n",
        path="d\u00e9j\u00e0/vu.py",
    )
    assert [f["path"] for f in findings] == ["caller.py"]


@pytest.mark.parametrize(
    "line,expected",
    [
        ("def f[T](x: T):", ("f", "x: T", True)),
        ("def f[T: Seq[int]](x):", ("f", "x", True)),
        ("def f[T, *Ts, **P](x, *a):", ("f", "x, *a", True)),
        ("async def g[K, V](self, k: K) -> V:", ("g", "self, k: K", True)),
        ("    def h [T] (x):", ("h", "x", True)),
        ("def f(a, b=g(1)):", ("f", "a, b=g(1)", True)),
        ('def f(a=")", b=1):', ("f", 'a=")", b=1', True)),
        ("def f(a=(1, (2, 3))):", ("f", "a=(1, (2, 3))", True)),
        ("def f():", ("f", "", True)),
    ],
)
def test_python_def_heads(line: str, expected) -> None:
    assert _signature_on_line(line, is_py=True) == expected


def test_a_pep_695_signature_change_is_reported(tmp_path: Path) -> None:
    assert _flagged(tmp_path, ["def do_work[T](a: T):"], ["def do_work[T](a: T, b):"])
    assert not _flagged(tmp_path, ["def do_work[T](a: T):"], ["def do_work[T](a: T, *, e=1):"])
    assert _flagged(tmp_path, ["def do_work(a):"], ["def do_work[T](a: T, b):"])


def test_a_pep_695_def_counts_as_a_definition(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "one.py", "def do_work(a):\n    return 1\n")
    _write(tmp_path / "core" / "two.py", "def do_work[T](a: T):\n    return 2\n")
    _write(tmp_path / "elsewhere.py", "def go():\n    do_work(1)\n")
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e):"], "core/one.py"),
        repo_root=tmp_path,
    )
    assert "elsewhere.py" not in {f["path"] for f in findings}


def test_a_default_holding_a_call_is_read_whole(tmp_path: Path) -> None:
    """`def f(a, b=g(1))`: the old reader stopped at the first `)` and saw `a, b=g(1`."""
    assert _flagged(tmp_path, ["def do_work(a, b=g(1)):"], ["def do_work(a, b=g(1), *, e):"])
    assert not _flagged(tmp_path, ["def do_work(a, b=g(1)):"], ["def do_work(a, b=g(2)):"])


def test_function_generics_in_a_ts_file_are_read(tmp_path: Path) -> None:
    assert _signature_on_line("function f<T>(a: T) {", is_py=False) == ("f", "a: T", False)
    assert _signature_on_line("export function f<T, U>(a) {", is_py=False) == ("f", "a", False)


MULTI = [
    "def do_work(",
    "    a,",
    "    b,",
    "):",
]


def test_a_def_rewrapped_across_lines_is_read(tmp_path: Path) -> None:
    assert _flagged(tmp_path, ["def do_work(a):"], MULTI)
    assert not _flagged(
        tmp_path,
        ["def do_work(a):"],
        ["def do_work(", "    a,", "    *,", "    extra=1,", "):"],
    )
    assert _flagged(tmp_path, MULTI, ["def do_work(a):"])
    assert _flagged(tmp_path, MULTI, ["def do_work(", "    a,", "    c,", "):"])


def test_two_multi_line_defs_are_compared_as_written(tmp_path: Path) -> None:
    old = ["def do_work(", "    a,", "    b=1,", "):"]
    new = ["def do_work(", "    a,", "    b=1,", "    *,", "    extra=1,", "):"]
    assert not _flagged(tmp_path, old, new)
    assert _flagged(tmp_path, old, ["def do_work(", "    a,", "    b,", "):"])


def test_comments_inside_a_multi_line_list_are_not_parameters() -> None:
    lines = ["def f(", "    a,  # the first, or second (see below)", "    b=1,  # ')'", "):"]
    ((name, params, is_py),) = _python_signatures(lines)
    assert (name, is_py) == ("f", True)
    assert _param_names(params) == ("a", "b")


def test_a_multi_line_list_with_a_string_holding_a_paren() -> None:
    lines = ["def f(", '    a=")",', "    b=1,", "):"]
    ((_, params, _),) = _python_signatures(lines)
    assert _param_names(params) == ("a", "b")


def test_a_list_that_never_closes_is_not_a_signature() -> None:
    assert _python_signatures(["def f("] + ["    x,"] * 400) == []
    assert _python_signatures(["def f(", "    x,"]) == []


def test_a_list_closing_within_the_bound_is_read() -> None:
    lines = ["def f("] + ["    x,"] * 299 + ["):"]
    ((_, params, _),) = _python_signatures(lines)
    assert len(_param_names(params)) == 299


def test_a_list_closing_beyond_the_bound_is_not() -> None:
    lines = ["def f("] + ["    x,"] * 301 + ["):"]
    assert _python_signatures(lines) == []


def test_a_line_that_starts_inside_a_string_is_not_a_multi_line_head() -> None:
    lines = ["def f(", "    a,", "):"]
    assert _python_signatures(lines, skip={0}) == []
    assert len(_python_signatures(lines, skip={1})) == 1


def test_a_hundred_thousand_unclosed_heads_are_linear() -> None:
    start = time.perf_counter()
    assert _python_signatures(["def f("] * 100_000) == []
    assert time.perf_counter() - start < BUDGET


def test_a_hundred_thousand_open_lines_after_one_head_are_bounded() -> None:
    start = time.perf_counter()
    assert _python_signatures(["def f("] + ["x" * 100] * 100_000) == []
    assert time.perf_counter() - start < BUDGET


def test_the_header_and_the_closer_are_context_a_documented_limit(tmp_path: Path) -> None:
    """Only the stream's own lines are joined: a def whose header is unchanged context and
    whose parameter lines changed is not seen."""
    diff = (
        "diff --git a/core/thing.py b/core/thing.py\n--- a/core/thing.py\n+++ b/core/thing.py\n"
        "@@ -1,4 +1,4 @@\n def do_work(\n     a,\n-    b,\n+    b, c,\n ):\n"
    )
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []


def test_a_multi_line_def_inside_a_docstring_is_text(tmp_path: Path) -> None:
    diff = (
        "diff --git a/core/thing.py b/core/thing.py\n--- a/core/thing.py\n+++ b/core/thing.py\n"
        "@@ -1,6 +1,7 @@\n S = '''\n-def do_work(\n-    a,\n-):\n+def do_work(\n+    a,\n+    b,\n+):\n '''\n"
    )
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    assert detect_changed_signature_callers(diff, repo_root=tmp_path) == []


# --- more pins (mutants of the new code) -----------------------------------------------------

PRECEDERS = [
    "x =",
    "f(",
    "f(1,",
    "o = {k:",
    "[",
    "!",
    "a &&",
    "a ||",
    "a &",
    "a |",
    "a ?",
    "{",
    "}",
    ";",
    "a +",
    "a -",
    "a *",
    "a %",
    "~",
    "a ^",
]


@pytest.mark.parametrize("prefix", PRECEDERS)
def test_a_slash_after_each_regex_preceder_starts_a_regex(prefix: str) -> None:
    line = f"{prefix} /'/.test(s); function bar(a){{}}"
    assert _signature_on_line(line, is_py=False) == BAR


@pytest.mark.parametrize("closer", [")", "]", '"s"', "1", "a", "a.b"])
def test_a_slash_after_a_value_is_a_division(closer: str) -> None:
    """After a value (a closing bracket, a string, a number, a name) the slash divides, so the
    quote after it opens a string that swallows the def."""
    line = f"x = {closer} /'/ 2; function bar(a){{}}"
    assert _signature_on_line(line, is_py=False) is None


def test_code_only_counts_lines_the_way_its_tokenizer_does() -> None:
    """`str.splitlines()` splits at a form feed or a lone CR; tokenize's readline does not, so
    slicing by the first misaligned every blanked comment and string after it."""
    for sep in ("\x0c", "\r", "\x0b", chr(0x2028)):
        text = f"# a{sep}b\nx = do_work(1)  # tail\ny = 'z'\n"
        code = hd._code_only(text)
        assert "do_work(1)" in code, repr(sep)
        assert "tail" not in code and "'z'" not in code, repr(sep)
        assert len(code) == len(text), repr(sep)


def test_the_first_alias_decides(tmp_path: Path) -> None:
    """`X as name` is looked up by the FIRST binding of the name, as it always was."""
    _write(
        tmp_path / CALLER,
        "from m1 import other as do_work\nfrom m2 import do_work as do_work\n\ndef test_it():\n    do_work(1)\n",
    )
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e):"]), repo_root=tmp_path
    )
    assert findings == []


def test_a_name_after_a_non_ascii_letter_is_a_different_identifier(tmp_path: Path) -> None:
    accent = chr(0xE9)
    _write(tmp_path / CALLER, f"def test_it():\n    {accent}do_work(1)\n    do_work{accent}(2)\n")
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e):"]), repo_root=tmp_path
    )
    assert findings == []


def test_a_non_ascii_function_name_is_a_name(tmp_path: Path) -> None:
    name = "do_w" + chr(0xF6) + "rk"
    _write(tmp_path / CALLER, f"def test_it():\n    {name}(1)\n")
    findings = detect_changed_signature_callers(
        _def_diff([f"def {name}(a):"], [f"def {name}(a, *, e):"]), repo_root=tmp_path
    )
    assert CALLER in {f["path"] for f in findings}


def test_a_list_closing_within_the_character_bound_is_read() -> None:
    lines = ["def f("] + ["    " + "x" * 90 + ","] * 150 + ["):"]  # ~15,000 characters
    assert len(_python_signatures(lines)) == 1


def test_a_list_beyond_the_character_bound_is_not() -> None:
    lines = ["def f("] + ["    " + "x" * 90 + ","] * 250 + ["):"]  # ~25,000 characters
    assert _python_signatures(lines) == []


def test_the_work_budget_stops_a_wall_of_open_lists() -> None:
    """Many short unclosed heads: each would scan up to 300 lines; the budget caps the total
    work, and a def that DOES close early is still read."""
    lines = ["def f("] * 3000 + ["):"] + ["def g(a):"]
    found = _python_signatures(lines)
    assert ("g", "a", True) in found


def test_a_single_line_def_does_not_consume_the_budget() -> None:
    lines = ["def f(a):"] * 20_000
    assert len(_python_signatures(lines)) == 20_000


# --- pins for the second mutation run ---------------------------------------------------------


def test_git_output_of_a_failed_command_is_empty(tmp_path: Path) -> None:
    """`git diff --exit-code` fails (status 1) WITH output when there is a difference: a
    failed command contributes nothing."""
    try:
        _sh(tmp_path, "init", "-q", "-b", "main")
    except (OSError, RuntimeError):
        pytest.skip("git is not available")
    _sh(tmp_path, "config", "user.email", "a@b.c")
    _sh(tmp_path, "config", "user.name", "t")
    (tmp_path / "m.py").write_bytes(b"x = 1\n")
    _sh(tmp_path, "add", "-A")
    _sh(tmp_path, "commit", "-q", "-m", "x")
    (tmp_path / "m.py").write_bytes(b"x = 2\n")
    assert "x = 2" in br._git(["diff"], tmp_path)
    assert br._git(["diff", "--exit-code"], tmp_path) == ""


def test_a_slash_straight_after_an_arrow_is_a_regex() -> None:
    assert _signature_on_line("s =>/'/.test(s); function bar(a){}", is_py=False) == BAR
    assert _signature_on_line("s => /'/.test(s); function bar(a){}", is_py=False) == BAR


def test_a_powershell_backtick_escapes_a_quote_outside_a_string() -> None:
    line = 'echo `"; function f(a) { }'
    assert _signature_on_line(line, is_py=False, style="ps") == ("f", "a", False)
    assert _signature_on_line(line, is_py=False, style="c") is None


def test_an_import_as_its_own_name_is_not_an_alias_of_something_else(tmp_path: Path) -> None:
    """`from m import do_work as do_work` rebinds the name to ITSELF: the call below is a call
    of the changed function. (Only an alias to a DIFFERENT origin is skipped.)"""
    _write(
        tmp_path / CALLER,
        "from m import do_work as do_work\n\ndef test_it():\n    do_work(1)\n",
    )
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e):"]), repo_root=tmp_path
    )
    assert CALLER in {f["path"] for f in findings}


def test_a_file_without_an_introspection_token_is_never_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cheap hint filter is a contract: no token, no parse."""
    import ast

    text = "def test_it():\n    do_work(1)\n"
    _write(tmp_path / CALLER, text)
    real = ast.parse
    seen = []

    def counting(source, *a, **k):
        if source == text:
            seen.append(1)
        return real(source, *a, **k)

    monkeypatch.setattr(ast, "parse", counting)
    detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e=1):"]), repo_root=tmp_path
    )
    assert seen == []


def test_a_name_not_in_the_file_never_builds_its_introspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ast

    text = "import inspect\ninspect.signature(other)\n"
    real = ast.parse
    seen = []

    def counting(source, *a, **k):
        seen.append(1)
        return real(source, *a, **k)

    monkeypatch.setattr(ast, "parse", counting)
    assert hd._FileFacts(text).inspects("absent_name") is False
    assert seen == []
    assert hd._FileFacts(text).inspects("other") is True
    assert seen == [1]


def test_an_import_of_a_dotted_name_as_an_alias_is_the_function(tmp_path: Path) -> None:
    """`import pkg.do_work as dw` binds `dw` to the thing named by the LAST segment."""
    _write(
        tmp_path / CALLER,
        "import inspect\nimport pkg.do_work as dw\n\ndef test_it():\n    inspect.signature(dw)\n",
    )
    findings = detect_changed_signature_callers(
        _def_diff(["def do_work(a):"], ["def do_work(a, *, e=1):"]), repo_root=tmp_path
    )
    assert CALLER in {f["path"] for f in findings}


def test_code_part_cuts_at_a_comment_but_not_at_a_hash_in_a_string() -> None:
    assert hd._code_part("a,  # note") == "a,  "
    assert hd._code_part('x = "#" + y') == 'x = "#" + y'
    assert hd._code_part("x = '#' + y  # note") == "x = '#' + y  "
    assert hd._code_part("x = '\\'#' # note") == "x = '\\'#' "
    assert hd._code_part("no comment") == "no comment"
    assert hd._code_part("# all comment") == ""


def test_a_multi_line_list_keeps_its_line_breaks() -> None:
    ((_, params, _),) = _python_signatures(["def f(", "    a,", "    b,", "):"])
    assert params == "\n    a,\n    b,\n"


def test_the_line_bound_is_exact() -> None:
    """The closer may stand at most 300 lines below the head."""
    at_300 = ["def f("] + ["    x,"] * 299 + ["):"]
    at_301 = ["def f("] + ["    x,"] * 300 + ["):"]
    assert len(_python_signatures(at_300)) == 1
    assert _python_signatures(at_301) == []


def test_the_parameters_on_the_head_line_are_kept() -> None:
    ((_, params, _),) = _python_signatures(["def f(a,", "    b):"])
    assert _param_names(params) == ("a", "b")


def test_nested_parens_that_straddle_lines_do_not_end_the_list_early() -> None:
    """`a=(1,` opens a paren on the head line, `2),` closes it on the next: the list is not
    over there, and the depth must travel from line to line."""
    ((_, params, _),) = _python_signatures(["def f(a=(1,", "    2),", "    b=3):"])
    assert _param_names(params) == ("a", "b")
    ((_, params, _),) = _python_signatures(["def f(a=(", "    1,", "    2),", "    b=3):"])
    assert _param_names(params) == ("a", "b")
    ((_, params, _),) = _python_signatures(
        ["def f(a=((", "    1,", "    2),", "    3),", "    b=4):"]
    )
    assert _param_names(params) == ("a", "b")
