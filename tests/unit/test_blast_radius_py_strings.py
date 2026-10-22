"""A def-shaped line INSIDE A MULTI-LINE STRING of a Python file is not a definition.

The statement-start anchor (tests/unit/test_blast_radius_string_literal_defs.py) removed
every `def` that follows a quote on its line. It cannot see a line in the middle of a
triple-quoted string that itself starts with `def`: `    def f(self):` as a fixture or a
docstring example. The round-two review counted 131 such lines in tracked .py files; seven
test files outside the gate's own would still raise findings (test_reachability_gate.py 136,
test_fail_open_census_gate.py 91, test_build_mode_dispatcher.py 57, ...).

A diff shows only the changed lines and three lines of context, so the state "am I inside a
triple-quoted string" is not in the diff alone. It is rebuilt from two sources: the hunk
itself, scanned in order (context and changed lines), and the file on disk, which is the NEW
file and so gives the exact state at each hunk's first line. The old side's state at the
start of a hunk is taken to equal the new side's: they share everything before the first
change. A PR that moves a quote's balance in one hunk and edits a def inside the affected
string in a later hunk of the same file is the residual (documented in the detector).

Where the file is not on disk (a synthetic diff) the state starts as "in code".
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from core.gates import hanging_detectors as hd
from core.gates.hanging_detectors import (
    _py_ignorable_lines,
    _py_line_end_state,
    _py_start_states,
    detect_changed_signature_callers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CALLER = "tests/unit/test_caller.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hunk_diff(path: str, new_start: int, lines: list[str], old_start: int | None = None) -> str:
    n_old = sum(1 for ln in lines if ln[0] in " -")
    n_new = sum(1 for ln in lines if ln[0] in " +")
    old_start = new_start if old_start is None else old_start
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -{old_start},{n_old} +{new_start},{n_new} @@\n" + "\n".join(lines) + "\n"
    )


def _flagged(tmp_path: Path, diff: str) -> bool:
    _write(tmp_path / CALLER, "def test_it():\n    do_work('a')\n")
    findings = detect_changed_signature_callers(diff, repo_root=tmp_path)
    return CALLER in {f["path"] for f in findings}


# --- the line lexer ---------------------------------------------------------

END_STATES = [
    # (line, state at its start, state at its end)
    ("x = 1", None, None),
    ('x = """', None, '"""'),
    ("x = '''", None, "'''"),
    ('abc"""', '"""', None),
    ("abc'''", "'''", None),
    ("abc'''", '"""', '"""'),  # the other triple does not close it
    ('"""abc', None, '"""'),
    ('x = """a""" + """', None, '"""'),
    ('x = """a""" + """b"""', None, None),
    ('s = "a # b"', None, None),
    ('s = "a\\"b"', None, None),  # an escaped quote does not close the string
    ('s = "a\\\\"', None, None),  # an escaped backslash does, then the quote closes it
    ('x = \'"""\'', None, None),  # a triple double quote inside single quotes
    ("x = \"'''\"", None, None),  # a triple single quote inside double quotes
    ('# it\'s """ a comment', None, None),
    ("x = 1  # '''", None, None),
    ('    """', '"""', None),
    ('    """  # trailing', '"""', None),
    ("x = 'unterminated", None, None),  # a single-quoted string cannot span a line
    ('x = "unterminated', None, None),
    ("x = r'\\d' + '''", None, "'''"),
    ('x = f"{y}" + """', None, '"""'),
    ('"""', '"""', None),
    ('""""""', None, None),  # an empty triple string
    ('x = """"', None, '"""'),
    ('x = """a""""', None, None),  # a closed triple, then a lone quote on the same line
    ('x = """a\\"""b', None, '"""'),  # inside a triple, a backslash escapes the quote
    ("x = '''a\\'''b", None, "'''"),
    ('x = """a\\\\"""b', None, None),  # an escaped backslash does not: the triple closes
]


@pytest.mark.parametrize(
    "line,start,end", END_STATES, ids=[f"{ln!r}|{st}" for ln, st, _ in END_STATES]
)
def test_the_python_line_lexer(line: str, start: str | None, end: str | None) -> None:
    assert _py_line_end_state(line, start) == end


def test_lines_are_split_on_newlines_only() -> None:
    """A form feed (older stdlib files use one) is not a line break: git and `ast` count
    lines by newline, and a different count would misalign every hunk."""
    text = "A = 1" + chr(12) + "B = '''\ndef f(a):\n'''\n"
    assert _py_start_states(text) == [None, "'''", "'''"]
    assert _py_start_states("A = 1\r\nB = '''\r\nx\r\n'''\r\n") == [None, None, "'''", "'''"]
    assert _py_start_states("") == []
    assert _py_start_states("x = 1") == [None]


def test_the_start_state_of_every_line_of_a_file() -> None:
    text = "A = '''\ndef f(a):\n'''\ndef g(b):\nB = \"\"\"x\"\"\"\ndef h(c):\n"
    assert _py_start_states(text) == [None, "'''", "'''", None, None, None]


def test_the_start_states_agree_with_the_tokenizer_on_this_repos_files() -> None:
    """Cross-check the hand lexer against `tokenize` on real files: a line `tokenize` puts
    inside a multi-line STRING token must be one the lexer says starts inside a string."""
    import io
    import tokenize

    checked = 0
    for path in sorted((REPO_ROOT / "tests" / "unit").glob("test_blast_radius_*.py")) + [
        REPO_ROOT / "core" / "gates" / "hanging_detectors.py",
        REPO_ROOT / "tests" / "unit" / "test_hanging_detectors.py",
    ]:
        text = path.read_text(encoding="utf-8")
        inside: set[int] = set()
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                inside.update(range(tok.start[0] + 1, tok.end[0] + 1))
        states = _py_start_states(text)
        mine = {i + 1 for i, s in enumerate(states) if s is not None}
        assert mine == inside, f"{path.name}: differs on {sorted(mine ^ inside)[:8]}"
        checked += 1
    assert checked >= 5


# --- the detector -----------------------------------------------------------


def test_a_def_in_a_string_opened_in_the_hunk_is_text(tmp_path: Path) -> None:
    diff = _hunk_diff(
        "core/fixtures.py",
        1,
        [" SRC = '''", "-def do_work(a):", "+def do_work(a, b):", "     pass", " '''"],
    )
    assert not _flagged(tmp_path, diff)


def test_a_def_in_a_string_opened_before_the_hunk_is_text_when_the_file_is_on_disk(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "core" / "fixtures.py",
        "SRC = '''\nline1\ndef do_work(a, b):\n    pass\n'''\n",
    )
    diff = _hunk_diff(
        "core/fixtures.py", 3, ["-def do_work(a):", "+def do_work(a, b):", "     pass"]
    )
    assert not _flagged(tmp_path, diff)


def test_the_same_hunk_without_the_file_is_read_as_a_def(tmp_path: Path) -> None:
    """KNOWN LIMIT, pinned: with no file to say the hunk starts inside a string, the state is
    'in code' and a statement-start def is a definition."""
    diff = _hunk_diff(
        "core/fixtures.py", 3, ["-def do_work(a):", "+def do_work(a, b):", "     pass"]
    )
    assert _flagged(tmp_path, diff)


def test_a_def_after_the_string_closes_is_a_definition(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "fixtures.py",
        "SRC = '''\nx\n'''\ndef do_work(a, b):\n    pass\n",
    )
    diff = _hunk_diff(
        "core/fixtures.py", 3, [" '''", "-def do_work(a):", "+def do_work(a, b):", "     pass"]
    )
    assert _flagged(tmp_path, diff)


def test_a_def_after_a_closed_string_in_the_hunk_is_a_definition(tmp_path: Path) -> None:
    diff = _hunk_diff(
        "core/fixtures.py",
        1,
        [" SRC = '''", " x", " '''", "-def do_work(a):", "+def do_work(a, b):"],
    )
    assert _flagged(tmp_path, diff)


def test_a_def_after_a_one_line_triple_string_is_a_definition(tmp_path: Path) -> None:
    diff = _hunk_diff(
        "core/fixtures.py",
        1,
        [' DOC = """one line"""', "-def do_work(a):", "+def do_work(a, b):"],
    )
    assert _flagged(tmp_path, diff)


def test_a_docstring_example_def_is_text(tmp_path: Path) -> None:
    diff = _hunk_diff(
        "core/thing.py",
        1,
        [
            " def helper():",
            '     """Example:',
            "-    def do_work(a):",
            "+    def do_work(a, b):",
            '     """',
        ],
    )
    assert not _flagged(tmp_path, diff)


def test_a_fixture_string_with_many_defs_is_text(tmp_path: Path) -> None:
    """The shape of tests/unit/test_reachability_gate.py: source code embedded in triple
    quotes, edited."""
    lines = [" FIXTURE = textwrap.dedent('''"]
    removed = ["-    def do_work(a):", "-        return 1"]
    added = ["+    def do_work(a, b):", "+        return 1"]
    diff = _hunk_diff("tests/unit/test_gate.py", 1, lines + removed + added + [" ''')"])
    assert not _flagged(tmp_path, diff)


def test_the_removed_side_is_judged_by_the_old_state(tmp_path: Path) -> None:
    """The removed line sits inside the string on the OLD side; the added one closes it
    first on the NEW side. The definition after the new closer is real."""
    _write(
        tmp_path / "core" / "fixtures.py",
        "X = '''\nbody\n'''\ndef do_work(a, b):\n    pass\n",
    )
    diff = _hunk_diff(
        "core/fixtures.py",
        3,
        [" '''", "-def do_work(a):", "+def do_work(a, b):"],
    )
    assert _flagged(tmp_path, diff)


def test_a_real_def_between_two_strings_is_a_definition(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "thing.py",
        "A = '''\nx\n'''\ndef do_work(a, b):\n    pass\nB = '''\ny\n'''\n",
    )
    diff = _hunk_diff(
        "core/thing.py", 4, ["-def do_work(a):", "+def do_work(a, b):", "     pass", " B = '''"]
    )
    assert _flagged(tmp_path, diff)


# --- `_py_ignorable_lines` directly (which side, which index) ---------------


def _record(path: str, *hunks: tuple[int, list[tuple[str, str]]]) -> dict:
    lines = [ln for _, hunk in hunks for ln in hunk]
    return {
        "path": path,
        "removed": [text for tag, text in lines if tag == "-"],
        "added": [text for tag, text in lines if tag == "+"],
        "hunks": [{"new_start": start, "lines": hunk} for start, hunk in hunks],
    }


def test_a_removed_opener_puts_only_the_old_side_inside_the_string(tmp_path: Path) -> None:
    f = _record(
        "core/x.py",
        (
            1,
            [
                ("-", "X = '''"),
                ("-", "def a(p):"),
                ("+", "X = 1"),
                ("+", "def a(p, q):"),
            ],
        ),
    )
    removed, added = _py_ignorable_lines(f, tmp_path)
    assert removed == {1}
    assert added == set()


def test_an_added_opener_puts_only_the_new_side_inside_the_string(tmp_path: Path) -> None:
    f = _record(
        "core/x.py",
        (
            1,
            [
                ("-", "X = 1"),
                ("-", "def a(p):"),
                ("+", "X = '''"),
                ("+", "def a(p, q):"),
            ],
        ),
    )
    removed, added = _py_ignorable_lines(f, tmp_path)
    assert removed == set()
    assert added == {1}


def test_indexes_stay_aligned_across_hunks(tmp_path: Path) -> None:
    """The first hunk has no def-shaped line and is skipped, but its removed and added lines
    still count: the second hunk's indexes are into the file's whole removed/added lists."""
    f = _record(
        "core/x.py",
        (1, [("-", "x = 1"), ("-", "y = 1"), ("+", "x = 2")]),
        (
            10,
            [
                (" ", "S = '''"),
                ("-", "def a(p):"),
                ("+", "def a(p, q):"),
            ],
        ),
    )
    removed, added = _py_ignorable_lines(f, tmp_path)
    assert removed == {2}
    assert added == {1}


def test_a_hunk_with_no_def_shaped_line_never_reads_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.gates.hanging_detectors as hd

    def boom(text):
        raise AssertionError("the file was read for a hunk with no candidate")

    monkeypatch.setattr(hd, "_py_start_states", boom)
    f = _record("core/x.py", (1, [("-", "x = 1"), ("+", "x = 2")]))
    assert _py_ignorable_lines(f, tmp_path) == (set(), set())
    # A def-shaped CONTEXT line is not a changed line: it needs no judging either.
    g = _record(
        "core/x.py",
        (1, [(" ", "def a(p):"), ("-", "x = 1"), ("+", "x = 2")]),
    )
    assert _py_ignorable_lines(g, tmp_path) == (set(), set())


def test_the_disk_state_is_read_at_the_hunks_first_line(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "x.py",
        "A = 1\nS = '''\nbody\ndef a(p, q):\n'''\ndef b(p, q):\n",
    )
    inside = _record("core/x.py", (4, [("-", "def a(p):"), ("+", "def a(p, q):")]))
    assert _py_ignorable_lines(inside, tmp_path) == ({0}, {0})
    before = _record("core/x.py", (3, [(" ", "body"), ("-", "def a(p):"), ("+", "def a(p, q):")]))
    assert _py_ignorable_lines(before, tmp_path) == ({0}, {0})
    after = _record("core/x.py", (6, [("-", "def b(p):"), ("+", "def b(p, q):")]))
    assert _py_ignorable_lines(after, tmp_path) == (set(), set())
    first = _record("core/x.py", (1, [("-", "def c(p):"), ("+", "def c(p, q):")]))
    assert _py_ignorable_lines(first, tmp_path) == (set(), set())


def test_a_hunk_beyond_the_end_of_the_file_starts_in_code(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "x.py", "A = 1\n")
    f = _record("core/x.py", (99, [("-", "def a(p):"), ("+", "def a(p, q):")]))
    assert _py_ignorable_lines(f, tmp_path) == (set(), set())


# --- the self-check over every tracked python file --------------------------

SHAPE = re.compile(r"\bdef\s+[A-Za-z_]\w*\s*\(")


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


def test_no_tracked_python_file_reads_a_non_def_as_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Over EVERY tracked .py file: for each def-SHAPED line that is not a real definition
    (inside a string, a comment, a docstring), simulate an edit that adds a required
    parameter to it. The detector must report nothing: it must never block a PR for
    editing text that merely looks like code.

    A real def is what `ast` says is one, so this also catches a mistake in the lexer's
    string tracking on real code. The file is on disk, so the hunk-start state comes from
    the file exactly as in CI."""
    offenders: list[str] = []
    candidates = 0
    # `_definition_modules` is reached only when the diff yielded a changed signature, so a
    # spy on it is a stricter check than "no findings": a def read from text that no other
    # file happens to call would produce no finding and still be a misread.
    reached: list[str] = []
    monkeypatch.setattr(hd, "_definition_modules", lambda root, name: reached.append(name) or 0)
    for path in _tracked_python_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not SHAPE.search(text):
            continue
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        real = {
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        rel = path.relative_to(REPO_ROOT).as_posix()
        hunks = []
        for number, line in enumerate(text.split("\n"), start=1):  # the diff's own line model
            if number in real or not SHAPE.search(line):
                continue
            edited = SHAPE.sub(lambda m: m.group(0) + "zz_extra, ", line, count=1)
            hunks.append(f"@@ -{number},1 +{number},1 @@\n-{line}\n+{edited}\n")
            candidates += 1
        if not hunks:
            continue
        diff = f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n" + "".join(hunks)
        before = len(reached)
        found = detect_changed_signature_callers(diff, repo_root=REPO_ROOT)
        if found or len(reached) != before:
            offenders.append(f"{rel}: read as a definition: {reached[before:][:3]}")
    assert candidates > 100, f"only {candidates} def-shaped non-def lines: the check proves little"
    assert not offenders, offenders[:10]
