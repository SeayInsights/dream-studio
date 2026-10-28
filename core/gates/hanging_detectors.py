"""Nothing-left-hanging detectors (WO-BLAST-RADIUS-GATE T2).

When a fix's blast radius is bigger than the fix itself, the change set leaves
something dangling that the pr-smoke subset doesn't run — and main goes red
post-merge. These detectors scan a unified git diff for the three classes that
broke main 11 times this milestone:

  (a) detect_stale_removed_symbol_tests — a test still asserts a symbol/string
      that the diff REMOVED and did not re-add (e.g. #347: dashboard HTML ids /
      JS functions deleted, but tests/unit/test_frontend_dashboard_telemetry_surface.py
      still asserted them).

  (b) detect_changed_signature_callers — a function/method SIGNATURE changed in
      the diff, and a file outside the change set still references it (e.g. #353:
      _write_handoff_packet_to_db gained a parameter; the handoff authority test
      still asserted the old call shape).

  (c) detect_unowned_table_writes — the diff adds an INSERT/UPDATE to a table
      that another, unchanged module also writes — an ownership/authority-boundary
      conflict (e.g. #354: TokenConsumptionProjection claimed token_usage_records
      while execution_spine.py still wrote it).

  (d) detect_migration_file_db_duplication — a numbered migration adds a table/
      column while leaving a duplicate definition behind (file+DB drift).

Each detector returns a list of finding dicts:
    {"detector": str, "severity": "block", "path": str, "symbol": str, "message": str}

Detectors are conservative-by-over-inclusion: a signature change can break ANY
reference, so a flagged finding means "review this before merge", not "proven
broken". The merge gate (blast_radius.main) treats findings as blocking.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.gates.sql_comments import strip_sql_comments

REPO_ROOT = Path(__file__).resolve().parents[2]

Finding = dict[str, Any]

# --- diff parsing -----------------------------------------------------------


def _strip_rust_cfg_test(lines: list[str]) -> list[str]:
    """Drop everything from a `#[cfg(test)]` line onward, in `lines` itself.

    The FALLBACK strip: it only sees what's IN `lines` (a diff's flat added-
    or removed-line list), so it only catches the marker when the marker
    itself was added or removed in this same diff -- true whenever a `.rs`
    file is wholly new (every line is "added", including its own
    `#[cfg(test)]`), which is why this was enough when it was written. Used
    directly for `removed` (no on-disk copy of the OLD file is available to
    do better) and as the fallback for `added` when `_rust_cfg_test_boundary`
    has nothing to read (see `_strip_rust_added_lines`).
    """
    for i, line in enumerate(lines):
        if "#[cfg(test)]" in line:
            return lines[:i]
    return lines


def _rust_cfg_test_boundary(repo_root: Path, path: str) -> int | None:
    """1-indexed line number of the first `#[cfg(test)]` in `path`'s CURRENT
    on-disk text under `repo_root`, or `None` if it can't be read.

    An INCREMENTAL edit to an already-existing `.rs` file can add a new test
    fixture whose diff hunk carries the file's `#[cfg(test)]`/`mod tests {`
    lines as UNCHANGED CONTEXT, not as `+` lines -- invisible to
    `_strip_rust_cfg_test`'s diff-only view, which then never truncates and
    lets the fixture's own INSERT/UPDATE read as a new production write
    again (the exact false positive this module exists to prevent). This
    gate always runs against a real checkout of the diff's own head commit,
    so the on-disk file already IS the diff's new-file state and is
    authoritative for where the test module actually starts, regardless of
    which lines the diff happened to mark as context versus added.
    """
    try:
        text = (repo_root / path).read_text(encoding="utf-8")
    except OSError:
        return None
    for i, line in enumerate(text.splitlines(), start=1):
        if "#[cfg(test)]" in line:
            return i
    return None


def _strip_rust_added_lines(
    added: list[str], added_lineno: list[int], repo_root: Path, path: str
) -> list[str]:
    """Drop `added` lines at or after the file's `#[cfg(test)]` boundary.

    Position-based when the on-disk file is available (real gate runs): a
    line's OWN new-file line number decides whether it's inside the test
    module, so an addition deep inside an already-existing `mod tests {}`
    block is caught even though the marker itself is unchanged context. A
    negative `lineno` means "no hunk header was seen for this line" (a
    malformed diff) and is always `< boundary`, so it's kept -- unknown
    position fails toward over-inclusion (still flagged), the same safe
    direction as the plain fallback below.

    Falls back to `_strip_rust_cfg_test`'s diff-only scan when the file
    can't be read (e.g. deleted, or -- as in this module's own unit tests --
    a diff constructed without a matching on-disk fixture); that keeps this
    module's existing wholly-new-file behaviour unchanged.
    """
    boundary = _rust_cfg_test_boundary(repo_root, path)
    if boundary is None:
        return _strip_rust_cfg_test(added)
    return [line for line, lineno in zip(added, added_lineno) if lineno < boundary]


_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _parse_diff(diff_text: str, *, repo_root: Path | str = REPO_ROOT) -> list[dict[str, Any]]:
    """Parse a unified git diff into per-file {path, added[], removed[]} records."""
    root = Path(repo_root)
    files: list[dict[str, Any]] = []
    added_linenos: list[list[int]] = []
    cur: dict[str, Any] | None = None
    cur_added_lineno: list[int] = []
    new_lineno: int | None = None
    # SPLIT ON LF ONLY. `str.splitlines()` also breaks at CR, VT, FF, FS, GS, RS, NEL, U+2028
    # and U+2029: characters INSIDE a changed line (a docstring holding a form feed), whose
    # split miscounts a hunk and silently disables the trusted-copy check on it.
    diff_lines = diff_text.split("\n")
    if diff_lines and diff_lines[-1] == "":
        diff_lines.pop()
    for line in diff_lines:
        if line.startswith("diff --git"):
            if cur is not None:
                files.append(cur)
                added_linenos.append(cur_added_lineno)
            cur = {"path": None, "added": [], "removed": [], "hunks": []}
            cur_hunk = None
            cur_added_lineno = []
            new_lineno = None
            # Fallback path from the "diff --git a/x b/x" header.
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                cur["path"] = parts[1].strip()
        elif line.startswith("+++ b/"):
            if cur is not None:
                cur["path"] = line.removeprefix("+++ b/").strip()
        elif line.startswith("+++") or line.startswith("---"):
            continue
        else:
            hunk = _HUNK_HEADER_RE.match(line)
            if hunk is not None:
                new_lineno = int(hunk.group(1))
                cur_hunk = {"new_start": new_lineno, "lines": []}
                if cur is not None:
                    cur["hunks"].append(cur_hunk)
            elif line.startswith("+"):
                if cur_hunk is not None:
                    cur_hunk["lines"].append(("+", line[1:]))
                if cur is not None:
                    cur["added"].append(line[1:])
                    cur_added_lineno.append(new_lineno if new_lineno is not None else -1)
                if new_lineno is not None:
                    new_lineno += 1
            elif line.startswith("-"):
                if cur_hunk is not None:
                    cur_hunk["lines"].append(("-", line[1:]))
                if cur is not None:
                    cur["removed"].append(line[1:])
                # Old-file-only line -- the new-file counter does not advance.
            elif new_lineno is not None:
                # A context line, unchanged in both old and new file: it still
                # occupies a position in the NEW file, so the counter that
                # tracks new-file line numbers advances even though nothing is
                # recorded as added or removed. Lines before any hunk header
                # (index/mode/similarity headers) leave new_lineno at None and
                # are correctly ignored here.
                if cur_hunk is not None and not line.startswith("\\"):
                    cur_hunk["lines"].append((" ", line[1:]))
                new_lineno += 1
    if cur is not None:
        files.append(cur)
        added_linenos.append(cur_added_lineno)
    result = [f for f in files if f.get("path")]
    result_lineno = [ln for f, ln in zip(files, added_linenos) if f.get("path")]
    for f, added_lineno in zip(result, result_lineno):
        if _normalize(f["path"]).endswith(".rs"):
            f["added"] = _strip_rust_added_lines(
                f["added"], added_lineno, root, _normalize(f["path"])
            )
            f["removed"] = _strip_rust_cfg_test(f["removed"])
    return result


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _is_test_path(path: str) -> bool:
    p = _normalize(path)
    return p.startswith("tests/") and p.endswith(".py") and Path(p).name.startswith("test_")


def _is_non_runtime_writer(path: str) -> bool:
    """True for files that are NOT live-runtime table writers.

    Single-writer ownership (detect_unowned_table_writes) only governs *runtime*
    modules competing for a derived/projection table. The following are excluded
    because they are DDL or one-shot tooling, not the runtime owner — same
    convention as tests/unit/test_schema_keep_list.py::_source_files:
      - numbered migration DDL/seed (`core/event_store/migrations/*.sql`),
        which is governed by detect_migration_file_db_duplication instead;
      - one-time upgrade/migrate/reconcile/backfill CLI tooling, which writes
        the table once during an upgrade, not on the live path.
    """
    p = _normalize(path)
    if "core/event_store/migrations/" in p:
        return True
    if p.startswith("core/upgrade/"):
        return True
    for prefix in (
        "interfaces/cli/migrate_",
        "interfaces/cli/reconcile_",
        "interfaces/cli/backfill_",
    ):
        if p.startswith(prefix):
            return True
    return False


_CODE_SUFFIXES = (".py", ".html", ".js", ".ts", ".sql", ".yaml", ".yml")
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".dream-studio"}


def _iter_code_files(repo_root: Path) -> Iterable[tuple[str, str]]:
    """Yield (relative_path, text) for code files under repo_root."""
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in _CODE_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        yield _normalize(str(path.relative_to(repo_root))), text


# --- (a) stale removed-symbol tests -----------------------------------------

_ATTR_RE = re.compile(r'\b(?:id|class|name|data-[\w-]+)\s*=\s*["\']([\w\-]{3,})["\']')
_DEF_RE = re.compile(r"\b(?:def|class|function|const|let|var)\s+([A-Za-z_]\w{2,})")


_STR_LITERAL_RE = re.compile(r"\"[^\"]*\"|'[^']*'")


def _symbols_by_kind(lines: Iterable[str]) -> tuple[set[str], set[str]]:
    """Extract removed/added symbols, partitioned by origin.

    ``attrs`` = HTML/JS attribute ids (id=/class=/name=/data-) — the #347 target,
    genuinely stale even when a test references them as a quoted string.
    ``defs`` = real definitions (def/class/function/const/let/var).

    Arbitrary quoted-string literals are deliberately NOT symbols: deleting a dead
    file whose fixture-like literals (e.g. "token-1", "test_db") coincide with an
    unchanged test's fixtures would otherwise flood this gate with false positives
    on legitimate dead-code removal (WO d3221b4d, surfaced by the God File Cleanup).
    """
    attrs: set[str] = set()
    defs: set[str] = set()
    for ln in lines:
        attrs.update(m.group(1) for m in _ATTR_RE.finditer(ln))
        defs.update(m.group(1) for m in _DEF_RE.finditer(ln))
    return attrs, defs


def _symbols(lines: Iterable[str]) -> set[str]:
    attrs, defs = _symbols_by_kind(lines)
    return attrs | defs


def detect_stale_removed_symbol_tests(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT
) -> list[Finding]:
    root = Path(repo_root)
    files = _parse_diff(diff_text, repo_root=root)
    changed_paths = {_normalize(f["path"]) for f in files}
    removed_attr: set[str] = set()
    removed_def: set[str] = set()
    added: set[str] = set()
    for f in files:
        ra, rd = _symbols_by_kind(f["removed"])
        removed_attr |= ra
        removed_def |= rd
        added |= _symbols(f["added"])
    removed_attr -= added
    removed_def -= added
    truly_removed = removed_attr | removed_def
    if not truly_removed:
        return []

    # A BARE WORD BOUNDARY IS NOT A REFERENCE. Two classes of false positive this
    # detector produced on 2026-09-21, both against a generic name:
    #
    #   self._targets      an instance attribute, not the module-level `_targets`
    #                      the diff removed -- a different symbol that happens to
    #                      share a name
    #   "tests/unit/test_a.py::test_one"
    #                      a path inside a STRING, in a fixture of captured pytest
    #                      output; nothing references a symbol there at all
    #
    # So `self.`/`cls.` and a preceding `/` are excluded -- and ONLY those. A blanket
    # exclusion of `.` was the first attempt and it broke
    # test_stale_symbol_flags_dotted_patch_target, because `mock.patch("mod.removed")`
    # is a genuine reference that also sits behind a dot. The distinction is instance
    # attribute access versus a dotted import path, not the dot itself.
    #
    # This matters beyond tidiness: a detector whose findings are mostly noise gets
    # switched off, and then its true positives go with it.
    patterns = {
        s: re.compile(r"(?<![\w-])(?<!self\.)(?<!cls\.)(?<!/)" + re.escape(s) + r"(?![\w-])")
        for s in truly_removed
    }

    # A removed symbol is only stale-test-worthy if it is ABSENT from the current
    # NON-TEST source tree. A symbol removed from one diff line but still present
    # elsewhere in source (e.g. a common word like "failures"/"in_progress", or a
    # dict key still used) is NOT a genuinely-removed API symbol — flagging tests
    # that merely mention it produces a flood of false positives.
    present_in_source: set[str] = set()
    defined_in_other_tests: set[str] = set()
    test_files: list[tuple[str, str]] = []
    for rel, text in _iter_code_files(root):
        if _is_test_path(rel):
            if rel not in changed_paths:
                test_files.append((rel, text))
                # A symbol still DEFINED in another unchanged test file (e.g. a
                # shared test helper `def _seed` imported across test modules) is
                # not genuinely removed — the diff merely deleted a same-named
                # private helper elsewhere. Counting it as live prevents flagging
                # references to a symbol that still exists (name-collision FP).
                for sym in (m.group(1) for m in _DEF_RE.finditer(text)):
                    if sym in patterns:
                        defined_in_other_tests.add(sym)
            continue
        for sym, pat in patterns.items():
            if sym not in present_in_source and pat.search(text):
                present_in_source.add(sym)

    genuinely_removed = {
        s for s in truly_removed if s not in present_in_source and s not in defined_in_other_tests
    }
    if not genuinely_removed:
        return []

    findings: list[Finding] = []
    for rel, text in test_files:
        # Symbols the test DEFINES itself are its own helpers, not dangling
        # references to removed source (e.g. a test-local `def _seed_db`).
        test_defines = {m.group(1) for m in _DEF_RE.finditer(text)}
        code_text = _STR_LITERAL_RE.sub(" ", text)  # test source minus string literals
        for sym in genuinely_removed:
            if sym in test_defines or not patterns[sym].search(text):
                continue
            # A removed DEFINITION (function/class) is genuinely stale if the test
            # references it as CODE (call/import/attribute) OR as a DOTTED target in
            # a string (e.g. `mock.patch("mod.removed_func")`, `getattr(o,"x")` is not
            # dotted so excluded) — but NOT as a bare string-literal value (e.g. a
            # column/role data string "audit_report"). HTML/JS-id removals stay stale
            # even as plain quoted strings.
            if sym in removed_def and sym not in removed_attr:
                dotted_ref = re.search(
                    r"\." + re.escape(sym) + r"\b|\b" + re.escape(sym) + r"\s*\.", text
                )
                if not patterns[sym].search(code_text) and not dotted_ref:
                    continue
            findings.append(
                {
                    "detector": "stale_removed_symbol_test",
                    "severity": "block",
                    "path": rel,
                    "symbol": sym,
                    "message": (
                        f"{rel} still references {sym!r}, which the diff removed and which "
                        f"is now absent from non-test source. Update or delete the stale test."
                    ),
                }
            )
    return findings


# --- (b) changed-signature callers ------------------------------------------

_SIG_RE = re.compile(r"\b(?:def|function)\s+([A-Za-z_]\w*)\s*(?:<[^()]*?>)?\s*\(([^)]*)\)")
# A Python definition STARTS a statement: nothing but indentation (and `async`, and a byte
# order mark on the file's first line) may precede `def`. Anchoring is exact where lexing
# is a heuristic, which is why Python files use this and every other file type walks the
# line with `_lex` and `_SIG_RE`.
# The HEAD of a def: everything up to its opening paren, PEP 695 type parameters allowed
# (`def f[T](x)`, `def f[T: Seq[int]](x)`). The parameter list is read by `_balanced_close`,
# so a default holding a call (`b=g(1)`) is whole and the list may continue on later lines.
_PY_DEF_RE = re.compile(
    "[" + chr(0xFEFF) + r"]?\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*"
    r"(?:\[(?:[^\[\]]|\[[^\[\]]*\])*\])?\s*\("
)

_PY_SUFFIXES = (".py", ".pyi")
_HASH_COMMENT_SUFFIXES = (
    ".rb",
    ".sh",
    ".bash",
    ".zsh",
    ".yml",
    ".yaml",
    ".toml",
    ".pl",
    ".pm",
    ".mk",
)
_PS_SUFFIXES = (".ps1", ".psm1", ".psd1")
_DASH_COMMENT_SUFFIXES = (".sql", ".lua")
_LINE_COMMENT = {"c": "//", "hash": "#", "sql": "--", "ps": "#"}
# Block comments: `/* */` in C-like and sql files, `<# #>` in PowerShell.
_BLOCK_COMMENT = {"c": ("/*", "*/"), "sql": ("/*", "*/"), "ps": ("<#", "#>")}
_QUOTES = "'\"`"
# A `/` starts a regular expression, not a division, after one of these (or at the start of
# the line), after `=>`, and after one of the keywords below. `<` and `>` need a closer look
# (see `_slash_starts_regex`): `</p>` and `<br/>` are markup, `a < /x/` and `s => /x/` are not.
_REGEX_PRECEDERS = frozenset("=(,:[!&|?{};+-*%~^")
_REGEX_KEYWORDS = frozenset(
    {
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
    }
)
_WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")


def _slash_starts_regex(text: str, i: int, last: str, prev: str, last_idx: int) -> bool:
    """Does the `/` at ``text[i]`` open a regex literal? Decided by the previous significant
    token, the way a JS lexer does. ``last`` is the last code character before it, ``prev``
    the one before that, ``last_idx`` its index."""
    if last == "":
        return True
    if last in ("<", ">"):
        if last == ">" and prev == "=":
            return True  # `s => /x/.test(s)`
        # `</p>`, `<br/>` and `<a>/</a>` put the slash right against the bracket (markup); an
        # operator has space after it: `a < /x/`, `a > /x/.source`.
        return not (i > 0 and text[i - 1] == last)
    if last in _REGEX_PRECEDERS:
        return True
    if last in _WORD_CHARS:
        start = last_idx
        while start > 0 and text[start - 1] in _WORD_CHARS:
            start -= 1
        word_end = last_idx + 1
        return text[start:word_end] in _REGEX_KEYWORDS  # `return /x/`, not `a / b`
    return False


def _is_python_path(path: str) -> bool:
    """A `.py` module or a `.pyi` stub: a statement-start `def` is a definition there."""
    return path.lower().endswith(_PY_SUFFIXES)


def _comment_style(path: str) -> str:
    """How a file marks comments, which decides what a `def` match may sit inside.

    ``py`` (anchored, see `_PY_DEF_RE`), ``hash`` (`#`: ruby, shell, yaml, toml), ``ps``
    (PowerShell: `#`, `<# #>`, a backtick escapes), ``sql`` (`--` and block comments) or ``c`` (`//`, block comments and regex literals:
    JS, TS, HTML, and the default for any type not listed).
    """
    low = path.lower()
    if low.endswith(_PY_SUFFIXES):
        return "py"
    if low.endswith(_PS_SUFFIXES):
        return "ps"
    if low.endswith(_HASH_COMMENT_SUFFIXES):
        return "hash"
    if low.endswith(_DASH_COMMENT_SUFFIXES):
        return "sql"
    return "c"


def _regex_end(text: str, start: int) -> int:
    """The index just after the regex literal that opens at ``text[start] == "/"``, or -1
    when no closing slash follows on this line (so it was a division after all)."""
    i, n, in_class = start + 1, len(text), False
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "/":
            i += 1
            while i < n and text[i].isalpha():
                i += 1  # flags
            return i
        i += 1
    return -1


def _lex(text: str, style: str = "c", probe=None):
    """Walk ``text`` ONCE, carrying lexer state; return ``(probe_result, ends_inside)``.

    LINEAR BY CONSTRUCTION. The previous reader rescanned the whole prefix for every
    `function` match inside a literal: a 100 KB line of ``"`` + `function f(a) ` x 7,142 +
    ``"`` took 43 s. Here the walk visits each character once; the optional ``probe`` is
    called only at positions where the lexer is in CODE and the character can start a
    definition (`d` or `f`), and a truthy result ends the walk. A definition can therefore
    never be found inside a string or a comment, and an unclosed `function foo(` in one
    cannot swallow a real `function bar(a)` after it.

    What it understands: ``'``, ``"`` and backtick strings (a backslash skips the next
    character; ``'''`` and ``\"\"\"`` triples where the text shows them), the style's line
    comment (``//``, ``#`` or ``--``), ``/* ... */`` for ``c`` and ``sql``, and for ``c`` a
    regex literal, told from a division by the previous token (`_slash_starts_regex`),
    closed on the same line, honouring ``[...]`` classes and escapes. A ``#`` comment starts
    at a TOKEN (the line start or after whitespace), so ``$#``, ``${#x}`` and ``a#b`` are
    not comments. In ``hash`` files a backslash outside a string escapes the next
    character. In ``ps`` (PowerShell) files ``<# ... #>`` is a block comment, a backtick
    escapes and a backslash is just a path separator.

    A slash after ``<`` or ``>`` is a division when it touches the bracket (``</p>``,
    ``<br/>``, ``<a>/``) and a regex when a space follows it (``a < /x/``, ``a > /x/.source``);
    after ``=>`` it is a regex either way.

    NOT understood, so a def after one of these on the same line can be missed: a template
    literal's ``${...}``; anything spanning lines; a regex after ``)`` (``if (a) /x'/``);
    JSX text holding an apostrophe (``<p>it's</p>``). OVER-REPORTED: a slash after ``await``
    or ``yield`` is always a regex, even where ``yield`` is an identifier.
    """
    line_comment = _LINE_COMMENT.get(style)
    block = _BLOCK_COMMENT.get(style)
    # PowerShell: a backtick escapes, a backslash is a path separator, a backtick opens nothing.
    quotes = "'\"" if style == "ps" else _QUOTES
    escape = "`" if style == "ps" else "\\"
    regex_ok = style == "c"
    last_paren = text.rfind(")") if probe is not None else -1
    n, i = len(text), 0
    quote: str | None = None
    last, prev, last_idx = "", "", -1  # the last significant code characters
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == escape:
                i += 2
            elif text.startswith(quote, i):
                prev, last, last_idx = last, ch, i
                i += len(quote)
                quote = None
            else:
                i += 1
            continue
        if probe is not None and ch in "df" and i < last_paren:
            found = probe(i)
            if found is not None:
                return found, False
        if (
            line_comment is not None
            and text.startswith(line_comment, i)
            and (line_comment != "#" or i == 0 or text[i - 1].isspace())
        ):
            return None, True
        if block is not None and text.startswith(block[0], i):
            end = text.find(block[1], i + len(block[0]))
            if end < 0:
                return None, True
            i = end + len(block[1])
            continue
        if ch in quotes:
            triple = ch * 3
            if ch != "`" and text.startswith(triple, i):
                quote, i = triple, i + 3
            else:
                quote, i = ch, i + 1
            continue
        if ch == escape and style in ("hash", "ps"):
            i += 2
            continue
        if regex_ok and ch == "/" and _slash_starts_regex(text, i, last, prev, last_idx):
            end = _regex_end(text, i)
            if end >= 0:
                prev, last, last_idx = last, ")", end - 1
                i = end
                continue
            regex_ok = False  # no closing slash anywhere after this: stop trying (linear)
        if not ch.isspace():
            prev, last, last_idx = last, ch, i
        i += 1
    return None, quote is not None


def _in_literal_or_comment(prefix: str, style: str = "c") -> bool:
    """Is the position just after ``prefix`` inside a string literal or a comment?"""
    return _lex(prefix, style)[1]


def _signature_on_line(line: str, *, is_py: bool, style: str = "c") -> tuple[str, str, bool] | None:
    """The ``(name, parameter text, is_python_def)`` a changed diff line defines, or None.

    A `def` INSIDE A STRING IS NOT A DEFINITION. tests/unit/test_hanging_detectors.py builds
    synthetic diffs in string literals, and `_SIG_RE.search` read ``"+def f(a=None):\\n"`` as
    a real definition: PR #923, which refined this detector, failed its own gate on an edit
    to such a line. Python files take only a statement-start `def`; other files take the
    first `def`/`function` the single-pass lexer reaches in CODE (`_lex`).
    """
    if is_py:
        m = _PY_DEF_RE.match(line)
        if m is None:
            return None
        begin = m.end()
        close = _balanced_close(line, begin)
        return (m.group(1), line[begin:close], True) if close >= 0 else None

    def probe(i: int):
        m = _SIG_RE.match(line, i)
        return (m.group(1), m.group(2), False) if m else None

    return _lex(line, style, probe)[0]


def _code_part(line: str) -> str:
    """``line`` up to a trailing ``#`` comment (a ``#`` inside a string is not one)."""
    quote: str | None = None
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#":
            return line[:i]
        i += 1
    return line


def _scan_parens(text: str, start: int, depth: int) -> tuple[int, int]:
    """Walk ``text`` from ``start`` with ``depth`` parens open, skipping quoted strings.

    Returns ``(index of the paren that closes the list, depth)``: the index is -1 while the
    list is still open at the end of ``text``, and ``depth`` then says how deep."""
    quote: str | None = None
    i, n = start, len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i, 0
        i += 1
    return -1, depth


def _balanced_close(text: str, start: int) -> int:
    """The index of the ``)`` that closes the parameter list whose first character is at
    ``text[start]``, or -1 if it does not close within ``text``."""
    return _scan_parens(text, start, 1)[0]


# A multi-line parameter list is joined across at most this many lines / characters.
_MAX_JOINED_LINES = 300
_MAX_JOINED_CHARS = 20_000


def _python_signatures(
    lines: list[str], skip: set[int] | frozenset[int] = frozenset()
) -> list[tuple[str, str, bool]]:
    """Every ``(name, parameter text, True)`` a stream of changed Python lines defines.

    A def whose parameter list closes on its own line is read as ``_signature_on_line``
    reads it. One that does not (the list continues on the next lines, one parameter each)
    is JOINED: the following lines are appended, comments removed, until the parens
    balance, bounded by `_MAX_JOINED_LINES`, `_MAX_JOINED_CHARS` and a work budget linear in
    the number of lines (a file of unclosed ``def f(`` lines must not be quadratic).
    ``skip`` holds indexes of lines that start inside a multi-line string. Only the lines of
    the stream itself are joined: a def whose header is unchanged context and whose
    parameters changed is not seen (documented limit).
    """
    found: list[tuple[str, str, bool]] = []
    budget = 2000 + 5 * len(lines)
    count = len(lines)
    for i, line in enumerate(lines):
        if i in skip:
            continue
        m = _PY_DEF_RE.match(line)
        if m is None:
            continue
        begin = m.end()
        close = _balanced_close(line, begin)
        if close >= 0:
            found.append((m.group(1), line[begin:close], True))
            continue
        parts = [_code_part(line[begin:])]
        depth = _scan_parens(parts[0], 0, 1)[1]
        size = len(parts[0])
        j = i + 1
        while j < count and j - i <= _MAX_JOINED_LINES and size <= _MAX_JOINED_CHARS and budget > 0:
            budget -= 1
            nxt = _code_part(lines[j])
            end, depth = _scan_parens(nxt, 0, depth)
            if end >= 0:
                parts.append(nxt[:end])
                found.append((m.group(1), "\n".join(parts), True))
                break
            parts.append(nxt)
            size += len(nxt)
            j += 1
    return found


# --- python: is a line inside a multi-line string? ---------------------------


def _py_line_end_state(line: str, state: str | None) -> str | None:
    """The open string delimiter (or None) after ``line``, given ``state`` at its start.

    ``state`` and the result are None (in code), ``'''`` or ``\"\"\"`` (a triple-quoted
    string that stays open across lines) or a single ``'`` / ``"`` (a single-quoted string
    continued over a line break by a trailing backslash). Handles single-line strings (a
    backslash skips a character) and ``#`` comments. An unterminated single-quoted string
    ends with its line unless the line ends in a backslash.
    """
    triple = state if state is not None and len(state) == 3 else None
    quote = state if state is not None and len(state) == 1 else None
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if triple is not None:
            if ch == "\\":
                i += 2
            elif line.startswith(triple, i):
                i += 3
                triple = None
            else:
                i += 1
            continue
        if quote is not None:
            if ch == "\\":
                after = i + 1
                if after >= n or line[after:] == "\r":
                    return quote  # a backslash-newline continues the string
                i += 2
            else:
                i += 1
                if ch == quote:
                    quote = None
            continue
        if ch == "#":
            break
        if ch in "'\"":
            if line.startswith(ch * 3, i):
                triple, i = ch * 3, i + 3
            else:
                quote, i = ch, i + 1
            continue
        i += 1
    return triple


def _split_source_lines(text: str) -> list[str]:
    """Lines as git and `ast` count them: by newline only. A lone CR is a character."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _py_start_states_lexer(text: str) -> list[str | None]:
    """The hand-lexer's reading of `_py_start_states`: used only when `tokenize` cannot."""
    states: list[str | None] = []
    state: str | None = None
    for line in _split_source_lines(text):
        states.append(state)
        state = _py_line_end_state(line, state)
    return states


def _quote_of(token_text: str) -> str:
    """The delimiter a STRING or FSTRING_START token opens with, prefix letters removed."""
    body = token_text.lstrip("rRbBuUfFtT")
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def _tokenize_string_rows(text: str) -> dict[int, str] | None:
    """Rows that START inside a multi-line string, by `tokenize`: or None if it cannot say.

    `tokenize` is the source of truth for a file that tokenizes: it knows PEP 701 nested
    f-strings (``f"{\"\"\"x\"\"\"}"``) and backslash-continued strings that the hand lexer
    does not. Rows are counted by the lines `readline` hands it, which the caller splits on
    newline only, as git does (a lone CR is a character, not a line break).
    """
    import io  # function-local: see _parse_params
    import tokenize

    rows: dict[int, str] = {}
    open_fstrings: list[tuple[int, str]] = []
    # f-strings (3.12) and template strings (3.14) are token SPANS, not STRING tokens.
    fstring_start = (getattr(tokenize, "FSTRING_START", -1), getattr(tokenize, "TSTRING_START", -1))
    fstring_end = (getattr(tokenize, "FSTRING_END", -1), getattr(tokenize, "TSTRING_END", -1))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING:
                delim = _quote_of(tok.string)
                for row in range(tok.start[0] + 1, tok.end[0] + 1):
                    rows.setdefault(row, delim)
            elif tok.type in fstring_start:
                open_fstrings.append((tok.start[0], _quote_of(tok.string)))
            elif tok.type in fstring_end and open_fstrings:
                start_row, delim = open_fstrings.pop()
                for row in range(start_row + 1, tok.end[0] + 1):
                    rows.setdefault(row, delim)
    except Exception:  # noqa: BLE001 - tokenize raises SystemError on a NUL after an
        # indented line (CPython 3.12.10), IndentationError, TokenError, ...: anything means
        # it cannot say, and the hand lexer answers instead.
        rows = None  # type: ignore[assignment]
    return rows


def _py_start_states(text: str) -> list[str | None]:
    """For each line of a Python file, the string delimiter open at its START (or None)."""
    rows = _tokenize_string_rows(text)
    if rows is None:
        return _py_start_states_lexer(text)
    return [rows.get(number) for number in range(1, len(_split_source_lines(text)) + 1)]


def _read_disk_text(path: Path) -> str:
    """A file's text with its line breaks untouched (no universal-newline translation: a lone
    CR is not a line break to git) and undecodable bytes replaced."""
    try:
        data = path.read_bytes()
    except OSError:
        data = b""
    return data.decode("utf-8", errors="replace")


def _py_ignorable_lines(
    f: dict[str, Any], root: Path, file_reader=None
) -> tuple[set[int], set[int]]:
    """Indexes into ``f["removed"]`` / ``f["added"]`` of lines that START inside a
    multi-line string, and so are text, not definitions.

    A diff shows the changed lines and three of context, never the string's opener, so the
    state is rebuilt per hunk from the NEW file (`_py_start_states` at the hunk's first line)
    and then by scanning the hunk's lines in order. The old side starts each hunk in the
    state the new side does (they share everything before the first change).

    WHERE THE NEW FILE COMES FROM matters: the working tree can carry an uncommitted edit.
    ``file_reader(path)`` supplies the text (the blast-radius gate passes
    ``git show HEAD:path``); with none, the working tree is read. Either way a copy is
    trusted for a hunk only if it CARRIES the hunk's own lines at the hunk's position; one
    that does not (shifted by an edit, shorter, absent, or a deleted or new file) says
    nothing about the hunk, and the hunk starts in code. RESIDUALS: a working-tree edit
    above a hunk that keeps the line count and the hunk's lines (use a reader), and a PR
    that changes a quote's balance in one hunk and edits a def inside the affected string
    in a later hunk of the same file. Only hunks holding a def-shaped changed line are scanned.
    """
    removed_skip: set[int] = set()
    added_skip: set[int] = set()
    source_lines: list[str] = []
    starts: list[str | None] | None = None
    r_i = a_i = 0
    for hunk in f.get("hunks") or []:
        lines = hunk["lines"]
        if not any(tag != " " and _PY_DEF_RE.match(text) for tag, text in lines):
            r_i += sum(1 for tag, _ in lines if tag == "-")
            a_i += sum(1 for tag, _ in lines if tag == "+")
            continue
        if starts is None:
            path = _normalize(f["path"])
            source = (
                file_reader(path) if file_reader is not None else _read_disk_text(root / path)
            ) or ""
            source_lines = _split_source_lines(source)
            starts = _py_start_states(source)
        new_side = [text.rstrip("\r") for tag, text in lines if tag != "-"]
        k = hunk["new_start"] - 1
        stop = k + len(new_side)
        carries = bool(new_side) and [x.rstrip("\r") for x in source_lines[k:stop]] == new_side
        old_state = new_state = starts[k] if carries else None
        for tag, text in lines:
            if tag == "-":
                if old_state is not None:
                    removed_skip.add(r_i)
                old_state = _py_line_end_state(text, old_state)
                r_i += 1
            elif tag == "+":
                if new_state is not None:
                    added_skip.add(a_i)
                new_state = _py_line_end_state(text, new_state)
                a_i += 1
            else:
                old_state = _py_line_end_state(text, old_state)
                new_state = _py_line_end_state(text, new_state)
    return removed_skip, added_skip


def _split_top_level_commas(param_str: str) -> list[str]:
    """Split on commas at bracket depth 0 only.

    A naive ``param_str.split(",")`` fabricates phantom params from commas inside
    bracketed annotations (``Union[A, B]``, ``Dict[K, V]``, ``tuple[A, B]``). That
    made an annotation-only change like ``Union[A, B]`` -> ``A | B`` look like a
    signature change and blocked PEP 604 modernization (WO-BLAST-PARAM-SPLIT).
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in param_str:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _param_names(param_str: str) -> tuple[str, ...]:
    names: list[str] = []
    for raw in _split_top_level_commas(param_str):
        tok = raw.strip()
        if not tok or tok in ("self", "cls", "*", "/"):
            continue
        tok = tok.lstrip("*")
        tok = tok.split(":", 1)[0].split("=", 1)[0].strip()
        if tok:
            names.append(tok)
    return tuple(names)


# --- call-compatibility of a signature change -------------------------------

_POSITIONAL_KINDS = ("posonly", "pos")

# A parameter as the compatibility check sees it: (name, kind, has_default). Annotations
# and the VALUE of a default are deliberately absent -- neither changes whether a call
# binds -- while kind and "has a default" are exactly what decides it.
_Param = tuple[str, str, bool]


def _parse_params(param_str: str) -> list[_Param]:
    """The parameters of ``param_str`` in declaration order.

    Raises ValueError when it is not valid Python (a JS ``...rest``, a default `_SIG_RE`
    truncated at its first ``)``, and so on): "cannot tell" is an answer the caller must
    handle, never a silent "compatible"."""
    # Imported here, not at module top: runtime/config/release-gates/fail-open-baseline.txt
    # keys a tracked site by LINE NUMBER, and a module-level import would move the handler
    # in _rust_cfg_test_boundary one line and force a baseline rewrite for no real change.
    import ast

    try:
        tree = ast.parse("def _f(" + param_str + "):\n    pass\n")
    except Exception as exc:  # noqa: BLE001 - any parser failure is 'not a parameter list'
        # MemoryError is real: ast.parse raises it ("Parser stack overflowed") for a
        # pathologically nested line, 50,000 `not` operators for instance, rather than
        # the RecursionError one would expect.
        raise ValueError(f"not a Python parameter list: {param_str!r}") from exc
    a = tree.body[0].args  # type: ignore[attr-defined]
    positional = [*a.posonlyargs, *a.args]
    n_defaults = len(a.defaults)
    first_default = len(positional) - n_defaults
    out: list[_Param] = []
    for i, arg in enumerate(positional):
        kind = "posonly" if i < len(a.posonlyargs) else "pos"
        out.append((arg.arg, kind, i >= first_default))
    if a.vararg:
        out.append((a.vararg.arg, "vararg", False))
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        out.append((arg.arg, "kwonly", default is not None))
    if a.kwarg:
        out.append((a.kwarg.arg, "kwarg", False))
    return out


def _call_compatible(old: list[_Param], new: list[_Param]) -> bool:
    """True only if every call that bound before still binds to the same parameters."""
    new_pos = {name: (i, kind, has_default) for i, (name, kind, has_default) in enumerate(new)}
    if len(new_pos) != len(new):
        return False
    last = -1
    for name, kind, has_default in old:
        if name not in new_pos:
            return False  # removed or renamed
        i, new_kind, new_has_default = new_pos[name]
        if new_kind != kind:
            return False  # positional-only / pos-or-kw / keyword-only / *args / **kwargs
        if has_default and not new_has_default:
            return False  # a call that omitted it now fails
        if i <= last:
            return False  # reordered: positional calls bind differently
        last = i

    old_names = {name for name, _, _ in old}
    old_has_vararg = any(kind == "vararg" for _, kind, _ in old)
    last_old_positional = max(
        (
            i
            for i, (name, kind, _) in enumerate(new)
            if name in old_names and kind in _POSITIONAL_KINDS
        ),
        default=-1,
    )
    for i, (name, kind, has_default) in enumerate(new):
        if name in old_names or kind in ("vararg", "kwarg"):
            continue  # added *args / **kwargs accept what was previously an error
        if kind == "kwonly":
            if not has_default:
                return False  # every existing call now misses a required argument
            continue
        # A NEW POSITIONAL parameter: needs a default, must follow every old positional
        # one (else it takes an argument an old call passed to something else), and
        # cannot sit in front of an old *args (it would take the first extra argument).
        if not has_default or old_has_vararg or i < last_old_positional:
            return False
    return True


def _signature_compatibility(old_params: str, new_params: str) -> str:
    """Classify a signature change from the text of its old and new parameter lists.

    ``"unchanged"``     same parameters, kinds and default-ness (annotations and default
                        values may differ)
    ``"compatible"``    changed, but every call valid before binds identically after
    ``"incompatible"``  some previously valid call now fails or binds differently
    ``"unparseable"``   a parameter list is not valid Python: the caller falls back to the
                        old name-tuple comparison, which reports a changed name list
    """
    try:
        old = _parse_params(old_params)
        new = _parse_params(new_params)
    except ValueError:
        return "unparseable"
    if old == new:
        return "unchanged"
    return "compatible" if _call_compatible(old, new) else "incompatible"


_MOCK_ASSERTION_RE = re.compile(
    r"\.(?:assert_called\w*|assert_any_call|assert_has_calls|assert_not_called"
    r"|call_args\w*|call_count|mock_calls|method_calls|called)\b"
)


def _SETATTR_TARGET_RE(name: str):
    """Matcher for ``monkeypatch.setattr(mod, "name", ...)`` / ``patch.object(mod, "name")``:
    the function named as a string argument, which `_code_only` blanks."""
    pattern = r"(?:setattr|delattr|patch\.object)\s*\([^)]*['\"]" + re.escape(name) + r"['\"]"
    return re.compile(pattern)


# A cheap textual pre-filter: only a file naming one of these is worth an AST parse.
_INTROSPECTION_HINT_RE = re.compile(
    r"signature|getfullargspec|getargspec|getcallargs|from_callable|get_type_hints"
    r"|get_annotations|getmembers|__code__|__defaults__|__kwdefaults__|__annotations__"
    r"|__wrapped__"
    r"|\bdir\b|wraps|update_wrapper"
)
# Calls that read (or copy) a callable's parameters, and attributes that expose them.
_INTROSPECTION_CALLS = frozenset(
    {
        "signature",
        "getfullargspec",
        "getargspec",
        "getcallargs",
        "from_callable",
        "get_type_hints",
        "get_annotations",
        "getmembers",
        "getmembers_static",
        "dir",
        "wraps",
        "update_wrapper",
    }
)
_INTROSPECTION_ATTRS = frozenset(
    {
        "__code__",
        "__signature__",
        "__defaults__",
        "__kwdefaults__",
        "__annotations__",
        "__wrapped__",
    }
)
# `from <one of these> import signature as sig` makes `sig(fn)` an introspection call too.
_INTROSPECTION_MODULES = frozenset({"inspect", "typing", "functools", "typing_extensions"})


class _Memo:
    """Per-run memo for the detector's loop, which asks about the SAME file once per
    changed name. Identity-keyed (the loop hands over one string object per file) and only
    live while ``detect_changed_signature_callers`` runs, so a direct call never sees a
    stale entry. Cost: a 20-name scan parsed and tokenized each file 20 times."""

    active = False
    tree_of: str | None = None
    tree: Any = None
    code_of: str | None = None
    code: str = ""
    facts_of: str | None = None
    facts: Any = None

    @classmethod
    def reset(cls, active: bool) -> None:
        cls.active = active
        cls.tree_of = cls.code_of = cls.facts_of = None
        cls.tree, cls.code, cls.facts = None, "", None


def _parsed_tree(text: str):
    """The AST of ``text``, or None when it is not parseable Python."""
    import ast  # function-local: see _parse_params

    if _Memo.tree_of is text:  # only ever set while a run is live (see the store below)
        return _Memo.tree
    try:
        tree = ast.parse(text)
    except Exception:  # noqa: BLE001 - not parseable Python, whatever the parser raises
        tree = None
    if _Memo.active:
        _Memo.tree_of, _Memo.tree = text, tree
    return tree


def _code_only_of(text: str) -> str:
    """`_code_only`, memoised for the detector's loop (see `_Memo`)."""
    if _Memo.code_of is text:
        return _Memo.code
    code = _code_only(text)
    if _Memo.active:
        _Memo.code_of, _Memo.code = text, code
    return code


def _introspection_text_re(name: str):
    """Textual stand-in for `_inspects_symbol` when the file is not parseable Python: an
    introspection call whose arguments name the function, or an introspection attribute
    read off it. The name may be nested in the arguments to any depth, within 200 characters."""
    n = re.escape(name)
    calls = "|".join(sorted(_INTROSPECTION_CALLS))
    attrs = "|".join(sorted(_INTROSPECTION_ATTRS))
    # The name may sit at any depth of the call's arguments (`signature(getattr(m, "name"))`):
    # up to 200 characters on the same line, a bound that keeps it linear and its false
    # positives (`signature(x); f(name)`) to a file that does not even parse.
    arg = r"[^\n]{0,200}?"
    return re.compile(rf"(?:{calls})\s*\({arg}(?<!\w){n}\b|(?<!\w){n}\s*\.\s*(?:{attrs})\b")


def _ast_idents(node: Any) -> set[str]:
    """Every identifier-like thing a subtree mentions: Name ids, Attribute attrs, and string
    constants (whole, and the last segment of a dotted path: ``"pkg.mod.fn"`` names ``fn``)."""
    import ast  # function-local: see _parse_params

    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            found.add(n.id)
        elif isinstance(n, ast.Attribute):
            found.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            found.add(n.value.rsplit(".", 1)[-1])
    return found


def _ast_store_names(node: Any) -> list[str]:
    import ast  # function-local: see _parse_params

    return [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]


def _callee_ids(func: Any) -> set[str]:
    """What a call is calling: ``f`` for ``f(...)``, ``fn`` for ``mod.fn(...)`` (the attribute,
    not the receiver: ``REG.items()`` calls ``items``, so a loop over it still binds from
    ``REG``), and everything the expression mentions for any other callee (``REG["k"]()``)."""
    import ast  # function-local: see _parse_params

    if isinstance(func, ast.Name):
        return {func.id}
    if isinstance(func, ast.Attribute):
        return {func.attr}
    return _ast_idents(func)


def _ast_bindings(nodes: list[Any]) -> list[tuple[set[str], set[str] | None, list[str]]]:
    """Every plain binding in a module as ``(names mentioned by the source, names mentioned
    by the callee when the source is a call, names bound)``: assignments (plain, annotated,
    walrus), loop and comprehension targets, ``with ... as``, and ``match`` captures."""
    import ast  # function-local: see _parse_params

    found: list[tuple[Any, list[str]]] = []
    for node in nodes:
        if isinstance(node, ast.Assign):
            found.append((node.value, [t for tgt in node.targets for t in _ast_store_names(tgt)]))
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            found.append((node.value, _ast_store_names(node.target)))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            found.append((node.iter, _ast_store_names(node.target)))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    found.append((item.context_expr, _ast_store_names(item.optional_vars)))
        elif isinstance(node, getattr(ast, "Match", ())):
            captured: list[str] = []
            for pattern in (case.pattern for case in node.cases):
                for sub in ast.walk(pattern):
                    captured.extend(
                        x for x in (getattr(sub, "name", None), getattr(sub, "rest", None)) if x
                    )
            found.append((node.subject, captured))
    return [
        (
            _ast_idents(source),
            _callee_ids(source.func) if isinstance(source, ast.Call) else None,
            targets,
        )
        for source, targets in found
    ]


def _introspection_callables(tree: Any, nodes: list[Any]) -> set[str]:
    """Names that ARE an introspection call: `signature` and friends, ``from inspect import
    signature as sig``, ``sig = inspect.signature`` (and ``b = sig``), and helper defs or
    lambdas whose body introspects one of their own parameters (to a fixed point, so a helper
    of a helper counts)."""
    import ast  # function-local: see _parse_params

    def callee(func: Any) -> str | None:
        return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)

    names = set(_INTROSPECTION_CALLS)
    assigns: list[tuple[list[str], str | None]] = []
    helpers: list[tuple[str, set[str], list[tuple[str | None, set[str]]]]] = []
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in (
            _INTROSPECTION_MODULES
        ):
            names.update(a.asname for a in node.names if a.asname and a.name in names)
        elif isinstance(node, ast.Assign):
            targets = [t for tgt in node.targets for t in _ast_store_names(tgt)]
            if isinstance(node.value, ast.Lambda):
                params = {a.arg for a in node.value.args.args + node.value.args.kwonlyargs}
                calls = [
                    (callee(c.func), set().union(*(_ast_idents(a) for a in c.args), set()))
                    for c in ast.walk(node.value.body)
                    if isinstance(c, ast.Call)
                ]
                helpers.extend((t, params, calls) for t in targets)
            elif isinstance(node.value, (ast.Name, ast.Attribute)):
                assigns.append((targets, callee(node.value)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = {a.arg for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs}
            calls = [
                (callee(c.func), set().union(*(_ast_idents(a) for a in c.args), set()))
                for stmt in node.body
                for c in ast.walk(stmt)
                if isinstance(c, ast.Call)
            ]
            helpers.append((node.name, params, calls))
    changed = True
    while changed:
        changed = False
        for targets, source in assigns:
            if source in names:
                for t in targets:
                    if t not in names:
                        names.add(t)
                        changed = True
        for hname, params, calls in helpers:
            if hname not in names and any(c in names and ids & params for c, ids in calls):
                names.add(hname)
                changed = True
    return names


class _Introspection:
    """Everything a caller file says about introspection, independent of any one name.

    ``sites`` is the union of the identifiers mentioned by every introspection site (an
    introspection call's arguments, the owner of an introspection attribute, the owner of a
    ``getattr(x, "<dunder>")``). ``index`` maps an identifier to the bindings that mention it
    and ``aliases`` an imported name to its ``as`` names, so a changed name asks only "what is
    reachable from me, and does it meet a site", never "walk the file again"."""

    def __init__(self, tree: Any) -> None:
        import ast  # function-local: see _parse_params

        self.unparseable = tree is None
        self.sites: set[str] = set()
        self.index: dict[str, list[int]] = {}
        self.bindings: list[tuple[set[str], set[str] | None, list[str]]] = []
        self.aliases: dict[str, set[str]] = {}
        if tree is None:
            return
        nodes = list(ast.walk(tree))
        call_names = _introspection_callables(tree, nodes)
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if a.asname:
                        self.aliases.setdefault(a.name.split(".")[-1], set()).add(a.asname)
        self.bindings = _ast_bindings(nodes)
        for position, (mentioned, _, _) in enumerate(self.bindings):
            for word in mentioned:
                self.index.setdefault(word, []).append(position)
        for node in nodes:
            if isinstance(node, ast.Call):
                func = node.func
                called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if called in call_names:
                    for a in [*node.args, *(k.value for k in node.keywords)]:
                        self.sites |= _ast_idents(a)
                if (
                    called == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in _INTROSPECTION_ATTRS
                ):
                    self.sites |= _ast_idents(node.args[0])
            elif isinstance(node, ast.Attribute) and node.attr in _INTROSPECTION_ATTRS:
                self.sites |= _ast_idents(node.value)

    def reaches_a_site(self, name: str) -> bool:
        """Is ``name``, or a variable bound from it (to a fixed point), at an introspection
        site? A worklist over the binding index: linear in what is reachable."""
        names = {name} | self.aliases.get(name, set())
        queue = list(names)
        while queue:
            word = queue.pop()
            for position in self.index.get(word, ()):
                _, callee_mentions, targets = self.bindings[position]
                if callee_mentions is not None and callee_mentions & names:
                    continue  # `result = do_work(1)` binds what the function RETURNS
                for target in targets:
                    if target not in names:
                        names.add(target)
                        queue.append(target)
        return bool(names & self.sites)


_PATCH_STRING_RE = re.compile(r"""patch[\w.]*\(\s*['"]([\w.]*)""")
_SETATTR_CALL_RE = re.compile(r"(?:setattr|delattr|patch\.object)\s*\(([^)]*)")
_QUOTED_RE = re.compile(r"""['"]([^'"]*)['"]""")
_ALIAS_RE = re.compile(r"\b(\w+)\s+as\s+(\w+)\b")


class _FileFacts:
    """Name-independent facts about ONE caller file, each computed at most once.

    The detector asks the same file about every changed name. Each answer used to cost a
    scan of the whole file per name (a regex for the call site, one for a patch target, one
    for `setattr`, an alias search, an AST walk): 2000 changed names against a 20,000-line
    test file took 71 s. The facts are indexed once, so a name costs a set lookup and, for
    introspection, the part of the file reachable from it."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._cache: dict[str, Any] = {}

    def _once(self, key: str, make):
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    @property
    def raw_idents(self) -> set[str]:
        """Every identifier-shaped token anywhere in the file (strings and comments too)."""
        return self._once("raw", lambda: set(_IDENT_RE.findall(self.text)))

    @property
    def code_idents(self) -> set[str]:
        """The same, with comments and string contents blanked: a CALL SITE."""
        return self._once("code", lambda: set(_IDENT_RE.findall(_code_only_of(self.text))))

    @property
    def patch_segments(self) -> set[str]:
        """Dotted-path segments of every ``patch("a.b.c")`` target: `c` is a patched name."""
        return self._once(
            "patch",
            lambda: {
                seg
                for m in _PATCH_STRING_RE.finditer(self.text)
                for seg in m.group(1).split(".")
                if seg
            },
        )

    @property
    def setattr_strings(self) -> set[str]:
        """Every string handed to ``setattr`` / ``delattr`` / ``patch.object``."""
        return self._once(
            "setattr",
            lambda: {
                s
                for m in _SETATTR_CALL_RE.finditer(self.text)
                for s in _QUOTED_RE.findall(m.group(1))
            },
        )

    @property
    def alias_first(self) -> dict[str, str]:
        """``X as Y`` imports in code: Y -> the first X it was bound from."""

        def build() -> dict[str, str]:
            first: dict[str, str] = {}
            for m in _ALIAS_RE.finditer(_code_only_of(self.text)):
                first.setdefault(m.group(2), m.group(1))
            return first

        return self._once("alias", build)

    @property
    def has_mock_assertion(self) -> bool:
        return self._once("mock", lambda: bool(_MOCK_ASSERTION_RE.search(_code_only_of(self.text))))

    @property
    def introspection(self) -> _Introspection | None:
        """None when the file holds no introspection token at all (nothing to parse)."""

        def build() -> _Introspection | None:
            if not _INTROSPECTION_HINT_RE.search(self.text):
                return None
            return _Introspection(_parsed_tree(self.text))

        return self._once("introspection", build)

    def inspects(self, name: str) -> bool:
        if name not in self.raw_idents:
            return False
        intro = self.introspection
        if intro is None:
            return False
        if intro.unparseable:
            return bool(_introspection_text_re(name).search(self.text))
        return intro.reaches_a_site(name)


def _facts_of(text: str) -> _FileFacts:
    """The facts of ``text``, built once per file during a detector run (see `_Memo`)."""
    if _Memo.facts_of is text:
        return _Memo.facts
    facts = _FileFacts(text)
    if _Memo.active:
        _Memo.facts_of, _Memo.facts = text, facts
    return facts


def _inspects_symbol(text: str, name: str) -> bool:
    """Does this file READ THE PARAMETERS of ``name``?

    ``inspect.signature(fn).parameters``, ``getfullargspec(fn).args``, ``inspect.getmembers``,
    ``fn.__code__.co_argcount`` / ``co_varnames``, ``fn.__signature__``, ``fn.__defaults__``,
    ``fn.__annotations__``, ``getattr(fn, "__defaults__")`` (any introspection dunder named
    as a string), ``typing.get_type_hints(fn)``, ``dir(fn)``, ``functools.wraps(fn)``: a
    consumer of the OLD SHAPE. A call-compatible change keeps every call valid and still
    changes every one of these answers, so such a file breaks exactly as a mock does.
    tests/unit/test_workflow_runner.py asserts ``list(sig.parameters) == ["self", "node_id",
    "ynode"]``.

    The introspection must be OF THIS FUNCTION. "The file contains ``inspect.signature``
    anywhere" would report every test that ever inspected anything, so the AST is asked
    whether the call's arguments (or the attribute's owner) mention the name -- as a name,
    an attribute (``Cls.name``), a string (``getattr(mod, "name")``), or a variable bound
    from one of those by an assignment, annotated assignment, walrus, loop, comprehension,
    ``with ... as`` or ``match`` capture, followed to a fixed point however many hops and in
    whatever textual order (a worklist: linear, where a rescan per link was quadratic), or by
    ``from mod import name as alias``. The introspection CALL may itself be aliased:
    ``from inspect import signature as sig``, ``sig = inspect.signature``, or a helper
    ``def get(fn): return inspect.signature(fn)``. A file that is not parseable Python gets
    the textual equivalent (one level of nested parentheses in the arguments; no alias
    following, no getattr form).

    THE FILE IS INDEXED ONCE (`_FileFacts`, `_Introspection`): the sites and the bindings
    are collected in one walk and a changed name only follows its own reachable bindings,
    so the cost is O(file + names), not O(file x names).

    NOT DETECTED, because no static reading can tie them to the function: a computed name
    (``getattr(Cls, method)``), a computed attribute (``getattr(fn, attr)``,
    ``operator.attrgetter``), ``vars()`` / ``__dict__`` access, and a stub or fake handed in
    without the name appearing in the file at all.
    """
    return _facts_of(text).inspects(name)


def _string_reference(text: str, name: str) -> bool:
    """A reference to ``name`` that `_code_only` blanks because it lives in a string: a
    ``setattr`` / ``delattr`` / ``patch.object`` target, or introspection by a string name.
    Reported for ANY signature change, compatible or not: a string patch target is a
    dependency whichever way the signature moved."""
    facts = _facts_of(text)
    return name in facts.setattr_strings or facts.inspects(name)


def _mocks_symbol(
    text: str, name: str, *, referenced_in_code: bool, string_ref: bool | None = None
) -> bool:
    """Does this file MOCK or INTROSPECT ``name`` -- the ways a call-compatible change
    still breaks it?

    #353 was a compatible widening: ``_write_handoff_packet_to_db(session_id, cwd)``
    gained ``handoff_path=None``, and what broke was a test asserting the OLD CALL SHAPE
    through a mock. A default parameter protects a real call and nothing that records
    one or reads the parameters. So a compatible change is reported for a file that names
    the function as a patch target, hands its name to ``setattr`` / ``patch.object``,
    introspects its signature (`_inspects_symbol`), or references it in code alongside mock
    call assertions -- and for no other file. ``string_ref`` hands over an answer the caller
    already computed for `_string_reference`. A patch target names the function as a WHOLE
    dotted segment (``"pkg.mod.name"``).
    """
    facts = _facts_of(text)
    if name in facts.patch_segments:
        return True
    if _string_reference(text, name) if string_ref is None else string_ref:
        return True
    return referenced_in_code and facts.has_mock_assertion


def _slice(lines: list[str], start: tuple[int, int], end: tuple[int, int]) -> str:
    """The text between two ``(row, col)`` positions, rows 1-indexed as tokenize reports."""
    start_row, start_col = start
    end_row, end_col = end
    if start_row == end_row:
        row = lines[start_row - 1] if start_row - 1 < len(lines) else ""
        return row[start_col:end_col]
    out = [lines[start_row - 1][start_col:]] if start_row - 1 < len(lines) else []
    # Bound named rather than inlined: black formats `lines[start_row : end_row - 1]` with
    # a space before the colon and flake8 then flags E203, so the two tools only agree
    # when the slice expression is simple.
    last_full_row = end_row - 1
    out.extend(lines[start_row:last_full_row])
    if end_row - 1 < len(lines):
        out.append(lines[end_row - 1][:end_col])
    return "".join(out)


def _code_only(text: str) -> str:
    """``text`` with comments and string literals blanked out.

    A MENTION IS NOT A CALLER. ``detect_changed_signature_callers`` searched raw file
    text, so a comment naming a symbol counted as a reference to it. That blocked PR #691
    on two files whose only "reference" was the prose
    ``conftest.guard_real_homedir checks ...`` -- for a pytest FIXTURE whose added
    ``request`` parameter pytest injects and no caller ever passes.

    The SQL detector further down already carries this lesson ("Match real SQL writes, not
    prose ... a false positive this gate caught on its own source"). One detector in this
    file learned it and the other did not.

    Blanked rather than removed so line and column offsets survive. Falls back to the
    original text when the file will not tokenize: a syntax error means this cannot tell
    code from prose, and under-reporting a real dangling caller is worse than tolerating
    the false positive it would avoid.
    """
    import io
    import token as _token
    import tokenize as _tokenize

    try:
        lines = io.StringIO(text).readlines()  # by LF only, like the readline below
        pieces: list[str] = []
        previous_end = (1, 0)
        for tok in _tokenize.generate_tokens(io.StringIO(text).readline):
            pieces.append(_slice(lines, previous_end, tok.start))
            raw = _slice(lines, tok.start, tok.end)
            if tok.type in (_token.COMMENT, _token.STRING):
                pieces.append("".join("\n" if ch == "\n" else " " for ch in raw))
            else:
                pieces.append(raw)
            previous_end = tok.end
        return "".join(pieces)
    except Exception:  # noqa: BLE001 - tokenize can raise SystemError (a NUL), not only
        # TokenError and SyntaxError: any failure means it cannot tell code from prose.
        return text


def _PATCH_TARGET_RE(name: str):
    """Compiled matcher for a quoted mock.patch target naming *name*.

    A named function rather than an inline expression so it is unit-testable on its own:
    an inline regex inside the loop could only be exercised through the whole detector,
    which is how the previous attempt became unexplainable -- it behaved one way in
    isolation and another in place, with no way to interrogate the difference.
    """
    return re.compile(r"patch[\w.]*\(\s*['\"][\w.]*(?<![\w])" + re.escape(name) + r"[^'\"]*['\"]")


_DEF_NAME_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*[(\[]", re.M)
_IDENT_RE = re.compile(r"\w+")


def _definition_counts(files: Iterable[tuple[str, str]], names: set[str]) -> dict[str, int]:
    """How many files define each of ``names``: ONE pass over the files, indexed by name.

    A NAME DEFINED ONCE IDENTIFIES ITS SYMBOL; A NAME DEFINED EVERYWHERE DOES NOT. `main`
    and `run` are defined in dozens of modules here, so a bare-name match against them
    finds every unrelated mention in the tree -- measured at 720 findings on one PR, 682 of
    them for those two names alone. (This walked the whole tree once per changed name, so a
    PR changing 100k names never finished.)
    """
    counts = dict.fromkeys(names, 0)
    for _rel, text in files:
        for name in names.intersection(_DEF_NAME_RE.findall(text)):
            counts[name] += 1
    return counts


def _qualified_reference(text: str, module_hint: str, name: str) -> bool:
    """Does ``text`` reference ``name`` in a way that names its module?

    Used only for AMBIGUOUS names. A dotted path (`monitor.thing`, or a quoted patch
    target) or an import of the defining module ties the reference to this symbol; a bare
    `main()` in a YAML file does not.
    """
    stem = module_hint.rsplit("/", 1)[-1].removesuffix(".py")
    if not stem:
        return False
    # A DOTTED PATH NAMING THE MODULE, and nothing weaker. An earlier version also
    # accepted "this file imports the changed module", which is FILE-level and so
    # counted a same-named reference to an UNRELATED module:
    # tests/unit/test_review_lane_registry.py imports the changed detectors and
    # separately calls `review_lane_registry.run()`, and that bare `run` was
    # attributed to the changed one. The dotted path ties the reference itself to the
    # module, which is the actual question.
    return bool(
        re.search(
            r"(?<!\w)" + re.escape(stem) + r"\s*\.\s*" + re.escape(name) + r"\b",
            text,
        )
    )


def _aliased_to_a_different_name(text: str, name: str) -> bool:
    """Does *text* import some OTHER symbol and rebind it locally to *name*,
    via ``import X as name`` / ``from mod import X as name`` with ``X != name``?

    ``_definition_modules`` catches ambiguity from multiple ``def``s of the
    same name, but an import alias creates a second, unrelated binding to that
    name with no ``def`` at all: scripts/dashboard_smoke_harness.py imports
    the real ``core.analytics.duckdb_store.connect_analytics`` and renames it
    to the local ``_connect_analytics`` — a bare-name match then wrongly
    attributed that call to the unrelated ``_connect_analytics`` wrapper
    defined (and changed) in projections/api/routes/analytics.py, since both
    happen to share that local name. A file that locally aliases a DIFFERENT
    origin symbol to this name is not calling the changed one, whichever
    module actually changed.
    """
    first = _facts_of(text).alias_first.get(name)
    return first is not None and first != name


def _classify_pair(old_item: tuple[str, bool], new_item: tuple[str, bool]):
    """One removed/added def pair -> (old names, new names, mock_only), or None."""
    (old_text, old_py), (new_text, new_py) = old_item, new_item
    old_names, new_names = _param_names(old_text), _param_names(new_text)
    verdict = _signature_compatibility(old_text, new_text) if old_py and new_py else "unparseable"
    if verdict == "unchanged":
        return None
    if verdict == "unparseable" and old_names == new_names:
        return None  # cannot tell, and the names did not change: as before
    return old_names, new_names, verdict == "compatible"


def _normalized_params(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _classify_changes(old_items: list[tuple[str, bool]], new_items: list[tuple[str, bool]]):
    """Every same-named def of one file, not just the last.

    Two classes can each define ``render``; keeping only the last pair let an incompatible
    change followed by a compatible one pass. The removed and added defs are paired in
    order and the file is reported if ANY pair is incompatible; it is compatible-only if
    every changed pair is.

    When the counts differ no pairing is trustworthy, so the full parameter text (whitespace
    removed) is compared as a MULTISET, and the file is reported, without a compatibility
    verdict, if EITHER (a) a parameter list occurs more often on the added side than on the
    removed side (a new or changed definition: comparing sets of name lists hid one that
    reused an old shape, issue #926: ``-(a)`` ``-(a, b)`` / ``+(a, b)`` ``+(a, b)`` ``+(a)``,
    and a kind-only change such as ``(a, b)`` -> ``(a, *, b)``), or (b) a parameter list that
    was removed no longer exists at all (a definition whose shape disappeared is a signature
    change: ``-(a)`` ``-(a, b)`` / ``+(a, b)``). The only silent count change is fewer
    definitions of a shape that still exists, a dropped DUPLICATE (``-(a)`` ``-(a)`` /
    ``+(a)``).
    """
    if len(old_items) != len(new_items):
        old_counts: dict[str, int] = {}
        new_counts: dict[str, int] = {}
        for text, _ in old_items:
            key = _normalized_params(text)
            old_counts[key] = old_counts.get(key, 0) + 1
        for text, _ in new_items:
            key = _normalized_params(text)
            new_counts[key] = new_counts.get(key, 0) + 1
        added = any(count > old_counts.get(key, 0) for key, count in new_counts.items())
        vanished = any(key not in new_counts for key in old_counts)
        if not (added or vanished):
            return None
        return _param_names(old_items[-1][0]), _param_names(new_items[-1][0]), False
    changes = [
        c for c in (_classify_pair(o, n) for o, n in zip(old_items, new_items)) if c is not None
    ]
    if not changes:
        return None
    strict = [c for c in changes if not c[2]]
    return strict[0] if strict else changes[0]


def detect_changed_signature_callers(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT, file_reader=None
) -> list[Finding]:
    """Flag files outside the diff that reference a function whose signature changed.

    A CHANGE NO CALL CAN NOTICE IS NOT A BREAKING CHANGE (2026-10-21, PR #918). The
    detector compared only the tuple of parameter names, so
    ``record_execution_event(conn, **values)`` gaining ``*, spool=True`` blocked a PR on
    five emitters and two tests whose calls all still bind. The old and new parameter
    lists of a Python ``def`` are now parsed with ``ast`` and classified by
    ``_signature_compatibility``. A change is COMPATIBLE only if both hold:

    * every old parameter survives with the same name, kind (positional-only /
      positional-or-keyword / ``*args`` / keyword-only / ``**kwargs``) and relative
      order, and none lost its default (an old required parameter may GAIN one);
    * every new parameter is one of: keyword-only WITH a default; ``*args`` or
      ``**kwargs``; or a positional parameter WITH a default placed after every old
      positional parameter, when the old signature has no ``*args`` to be taken from.

    Anything else -- a removed, renamed or reordered parameter, a lost default, a kind
    change, a new required parameter of any kind -- is INCOMPATIBLE and reported as
    before. A parameter list that does not parse is never silenced: it falls back to the
    previous name-tuple comparison. Non-Python signatures (``function`` in JS) are not
    analysed and keep that comparison too.

    COMPATIBLE IS NOT "SAFE FOR A MOCK". #353 was a compatible widening whose break was a
    test asserting the old call shape through ``mock.patch``. A compatible change is
    therefore still reported for a file that names the function as a patch target, passes
    its name to ``setattr`` / ``patch.object``, introspects its signature
    (``inspect.signature``, ``getfullargspec``, ``__code__``, ``__signature__``,
    ``__defaults__``: ``_inspects_symbol``), or references it next to mock call assertions
    (``_mocks_symbol``). A string patch target or string-named introspection is reported
    for an incompatible change as well (``_string_reference``): it is a dependency whichever
    way the signature moved.

    EVERY same-named def of a file is classified, not the last (``_classify_changes``):
    two classes may each define ``render``. Removed and added defs are paired in order and
    the file is reported if any pair is incompatible; with unequal counts the full
    parameter text is compared as a multiset: a shape added more often than it was removed,
    or a removed shape that no longer exists at all, is reported; only a dropped DUPLICATE of
    a shape that survives is silent (issue #926).

    NOT DETECTED, by design or for want of a signal: a fake or stub handed in without the
    function's name appearing in the file; introspection through a computed name or attribute
    (``getattr(Cls, method)``, ``getattr(fn, attr)``, ``vars()``, ``__dict__``,
    ``operator.attrgetter``); and a gate ``main()`` whose parameters
    ``core/gates/registry.py`` counts to decide whether to pass argv (``main`` is ambiguous,
    so it is matched only by its module). That last assumption is enforced by
    tests/unit/gates/test_gate_registry.py instead. A registry or dispatch table that CALLS
    with the old arity needs no detector: a compatible change keeps every old call valid.

    DECIDED EDGE: a caller that today passes a key named like the new parameter through
    ``**values`` (``spool=...``) now binds it to the parameter instead. That is a semantic
    shift for exactly one key, chosen by the diff that adds the parameter, so the change
    stays COMPATIBLE; reporting every caller of every ``**kwargs`` function that gains a
    named keyword is what this refinement removes.

    A `def` INSIDE A STRING OR COMMENT IS NOT A DEFINITION (``_signature_on_line``). PR #923
    failed its own gate because tests/unit/test_hanging_detectors.py builds synthetic diffs
    in strings, and an edit to ``"+def f(a=None):\\n"`` was read as a real signature change.
    A ``.py`` or ``.pyi`` file contributes only a statement-start ``def``
    (``^\\s*(?:async\\s+)?def``, a leading byte order mark allowed: exact, because Python
    cannot put a `def` anywhere else) that does not START INSIDE A MULTI-LINE STRING
    (``_py_ignorable_lines``: the state is rebuilt per hunk from the NEW file, by
    ``tokenize`` when the file tokenizes and by a hand lexer otherwise, then by scanning the
    hunk's lines in order). The new file is what ``file_reader(path)`` returns -- the
    blast-radius gate hands it ``git show HEAD:path`` -- or, with no reader, the working
    tree; a copy is trusted for a hunk only if it carries the hunk's own lines at the
    hunk's position, otherwise (shifted, shorter, absent, a new or deleted file) the hunk
    starts in code. RESIDUALS: a working-tree edit above a hunk that keeps the line count
    and the hunk's lines (hence the reader), and a PR that changes a quote's balance in one
    hunk and edits a def inside the affected string in a later hunk. Every other file type
    contributes the first match the single-pass lexer ``_lex`` reaches IN CODE: quotes,
    backticks, triple quotes, the file type's line comment (``//``; ``#``, starting a token
    only, for ruby/shell/yaml/toml/powershell; ``--`` for sql), ``/* */`` and, for C-like
    files, a regex literal told from a division by the previous token (``return /x/``,
    ``s => /x/`` and ``a < /x/`` are regexes; ``a / b``, ``</p>`` and ``<br/>`` are not).
    NOT understood: a template literal's ``${...}``, anything spanning lines. The walk is
    linear in the line length.
    tests/unit/test_blast_radius_py_strings.py runs the whole check over every tracked
    ``.py`` file.

    PYTHON PARAMETER LISTS are read whole (`_python_signatures`): the closing paren is found by
    a balanced scan that skips strings, so ``b=g(1)`` is one default; PEP 695 type parameters
    (``def f[T](x)``) are allowed; and a list that continues on later lines is JOINED, comments
    removed, across at most 300 lines / 20,000 characters and a work budget linear in the stream
    (a re-wrapped def, ``def f(`` / ``a,`` / ``b,`` / ``):``, is read). LIMITS: only the
    stream's own lines are joined, so a def whose header is unchanged context and whose
    parameter lines changed is not seen, and a JS ``function`` is read from one line
    (``_SIG_RE`` stops at the first ``)``).

    THE DIFF IS SPLIT ON LF ONLY (`_parse_diff`) and the gate reads git's output as bytes
    (`blast_radius._git`): CR, VT, FF, FS, GS, RS, NEL, U+2028 and U+2029 are CHARACTERS of a
    changed line, and splitting at them miscounts a hunk and disables the trusted-copy check
    on it. Paths are listed with ``core.quotepath=off`` so a non-ASCII name is not quoted
    out of the diff.

    COST: every per-file answer is indexed once (`_FileFacts`): call sites, patch targets,
    ``setattr`` strings, aliases, mock assertions and introspection sites. A changed name is a
    set lookup (and, for introspection, the part of the file reachable from it), so N names
    against an M-line file cost O(M + N), not O(M x N). A patch target names the function as a
    whole dotted segment.
    """
    root = Path(repo_root)
    files = _parse_diff(diff_text, repo_root=root)
    changed_paths = {_normalize(f["path"]) for f in files}

    # name -> (old names, new names, mock_only). mock_only marks a CALL-COMPATIBLE change:
    # no real call can break, so only a file that mocks the function is still reported.
    changed_sigs: dict[str, tuple[tuple[str, ...], tuple[str, ...], bool]] = {}
    sig_origin: dict[str, str] = {}
    for f in files:
        # name -> every (parameter text, is a Python `def`) in the file, in order. Only
        # Python parameter lists get the compatibility analysis: a default in JS is not a
        # keyword-only contract.
        old: dict[str, list[tuple[str, bool]]] = {}
        new: dict[str, list[tuple[str, bool]]] = {}
        path = _normalize(f["path"])
        is_py, style = _is_python_path(path), _comment_style(path)
        # Lines that START inside a multi-line string of a Python file are text.
        removed_skip, added_skip = (
            _py_ignorable_lines(f, root, file_reader) if is_py else (set(), set())
        )
        for side, lines, skip in ((old, f["removed"], removed_skip), (new, f["added"], added_skip)):
            if is_py:
                sigs = _python_signatures(lines, skip)
            else:
                sigs = [
                    sig
                    for idx, ln in enumerate(lines)
                    if idx not in skip and (sig := _signature_on_line(ln, is_py=False, style=style))
                ]
            for sig in sigs:
                side.setdefault(sig[0], []).append((sig[1], sig[2]))
        for name in set(old) & set(new):
            change = _classify_changes(old[name], new[name])
            if change is None:
                continue
            old_names, new_names, mock_only = change
            # The stricter verdict wins when two files change a function of this name.
            if name in changed_sigs and not changed_sigs[name][2]:
                continue
            if name in changed_sigs and mock_only:
                continue
            changed_sigs[name] = (old_names, new_names, mock_only)
            sig_origin[name] = _normalize(f["path"])
    if not changed_sigs:
        return []

    # ONE walk of the tree serves both the definition count and the scan below (it used to
    # walk once per changed name, and again for the scan).
    files_in_tree = list(_iter_code_files(root))
    definitions = _definition_counts(files_in_tree, set(changed_sigs))
    _ambiguous = {name: count > 1 for name, count in definitions.items()}

    wanted = set(changed_sigs)
    findings: list[Finding] = []
    _Memo.reset(True)
    try:
        for rel, text in files_in_tree:
            if rel in changed_paths:
                continue
            # EVERY REFERENCE CONTAINS THE NAME AS AN IDENTIFIER: a call, an attribute, a
            # dotted path inside a patch string, a setattr string, an introspection
            # argument. One pass over the file finds the changed names it holds; a file
            # holding none is skipped before anything is tokenized or parsed (the old
            # per-name substring test was files x names: 100k names timed out).
            facts = _facts_of(text)
            held = wanted.intersection(facts.raw_idents)
            for name in sorted(held):
                # AN AMBIGUOUS NAME NEEDS ITS MODULE NAMED. `main` and `run` are defined in
                # dozens of modules here, so matching them bare finds every unrelated mention
                # -- 720 findings on one PR, 682 for those two names. A name defined ONCE (the
                # #353 symbol, and most real cases) keeps bare matching, so nothing this
                # detector was built to catch is weakened.
                if _ambiguous.get(name) and not _qualified_reference(
                    text, sig_origin.get(name, ""), name
                ):
                    continue
                # A LOCAL ALIAS TO A DIFFERENT ORIGIN SYMBOL IS NOT A CALLER OF THIS ONE,
                # whether or not `name` has more than one `def` in the tree — the ambiguity
                # here comes from an import, which _definition_modules never sees.
                if _aliased_to_a_different_name(text, name):
                    continue
                # A PATCH TARGET IS A REAL DEPENDENCY, AND IT LIVES IN A STRING.
                #
                # _code_only blanks comment and string contents so prose cannot raise false
                # positives -- but mock.patch names its target as a STRING literal,
                # patch('control.context.monitor._write_handoff_packet_to_db'), so the
                # de-noising erased exactly the reference this detector exists to find. The
                # #353 regression it was built for stopped being caught, and
                # tests/integration/test_session_regressions.py has failed on main since.
                #
                # Code first (cheap, no false positives), then the raw text restricted to
                # quoted patch targets. A quoted dotted path ending in the changed symbol is
                # a dependency by any reading; prose does not contain one by accident.
                # A call site: the name as a whole identifier in the code with comments and
                # string contents blanked. A leading `.` is allowed (`mod.name`, the #353
                # shape): the identifier is `name` there too.
                in_code = name in facts.code_idents
                old_p, new_p, mock_only = changed_sigs[name]
                string_ref: bool | None = None
                if mock_only or not in_code:
                    # A call site already decides an incompatible change: nothing below can
                    # change that verdict, so it is not computed. Everything else asks
                    # whether the file patches, mocks or introspects the function, once.
                    in_patch_target = name in facts.patch_segments
                    # A string target or string-named introspection is a reference for ANY
                    # change.
                    string_ref = _string_reference(text, name)
                    if not (in_code or in_patch_target or string_ref):
                        continue
                if mock_only:
                    # A CALL-COMPATIBLE CHANGE BREAKS NO REAL CALL. It can still break a
                    # file that mocks the function and asserts the old call shape (#353).
                    if not _mocks_symbol(
                        text, name, referenced_in_code=in_code, string_ref=string_ref
                    ):
                        continue
                    message = (
                        f"{rel} mocks or introspects {name}(), whose signature changed in this "
                        f"diff ({list(old_p)} -> {list(new_p)}). The change is call-compatible, "
                        f"but a mock, assertion or signature read written against the old shape "
                        f"can still break and this file was not updated."
                    )
                else:
                    shape = " (same names: a parameter kind or default changed)"
                    message = (
                        f"{rel} references {name}(), whose signature changed in this diff "
                        f"({list(old_p)} -> {list(new_p)}"
                        f"{shape if old_p == new_p else ''}) but this file was not updated."
                    )
                findings.append(
                    {
                        "detector": "changed_signature_caller",
                        "severity": "block",
                        "path": rel,
                        "symbol": name,
                        "message": message,
                    }
                )
    finally:
        _Memo.reset(False)
    return findings


# --- (c) unowned / duplicate table writes -----------------------------------

# Match real SQL writes, not prose. INSERT must be followed by a column list,
# VALUES, SELECT, or DEFAULT VALUES; UPDATE must be followed by SET. This keeps
# docstrings like "INSERT/UPDATE to a table" from being read as writes to tables
# named "to"/"or" (a false positive this gate caught on its own source).
_INSERT_RE = re.compile(
    r"\bINSERT\s+INTO\s+([A-Za-z_]\w*)\s*(?:\(|VALUES\b|SELECT\b|DEFAULT\b)",
    re.IGNORECASE,
)
_UPDATE_RE = re.compile(r"\bUPDATE\s+([A-Za-z_]\w*)\s+SET\b", re.IGNORECASE)


def _write_targets(text: str) -> set[str]:
    """Return lower-cased table names written by INSERT/UPDATE statements in text."""
    targets: set[str] = set()
    for rx in (_INSERT_RE, _UPDATE_RE):
        targets.update(m.group(1).lower() for m in rx.finditer(text))
    return targets


def _table_writers(table: str, repo_root: Path, *, exclude: str) -> list[str]:
    writers: list[str] = []
    table_l = table.lower()
    for rel, text in _iter_code_files(repo_root):
        if rel == exclude or _is_test_path(rel) or _is_non_runtime_writer(rel):
            continue
        if table_l in _write_targets(text):
            writers.append(rel)
    return writers


# Authority tables are multi-writer BY DESIGN — the work-order/mutation layer has
# many legitimate writers (close, start, block, unblock, reopen, …). Single-writer
# ownership only applies to derived/projection tables (e.g. token_usage_records),
# which are what this detector targets (#354). Skip the authority prefixes so a new
# business_* mutation is not flagged against every other mutation that writes it.
_AUTHORITY_TABLE_PREFIXES = ("business_", "raw_", "reg_")
_AUTHORITY_TABLE_EXACT = {"canonical_events"}


def _is_authority_table(table: str) -> bool:
    t = table.lower()
    return t in _AUTHORITY_TABLE_EXACT or t.startswith(_AUTHORITY_TABLE_PREFIXES)


def detect_unowned_table_writes(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT
) -> list[Finding]:
    root = Path(repo_root)
    files = _parse_diff(diff_text, repo_root=root)

    # A facade-split / refactor RELOCATES a write from one file to another within
    # the same diff: the table's write is removed from file A and added to a new
    # sibling B. The repo-wide writer set does not grow — the write existed at base
    # (evidenced by its removal here), so any multi-writer condition is pre-existing,
    # not introduced by this change set. Collecting every table whose write is
    # removed ANYWHERE in the diff and skipping it below keeps the God File Cleanup
    # (which moves whole DB-writing command groups into new modules) from tripping
    # this gate — the same false-positive class the stale-symbol detector already
    # guards against for dead-code removal (see _symbols_by_kind, WO d3221b4d).
    relocated: set[str] = set()
    for f in files:
        if _is_test_path(_normalize(f["path"])) or _is_non_runtime_writer(_normalize(f["path"])):
            continue
        relocated |= _write_targets("\n".join(f["removed"]))

    findings: list[Finding] = []
    for f in files:
        path = _normalize(f["path"])
        if _is_test_path(path) or _is_non_runtime_writer(path):
            continue
        added_targets = _write_targets("\n".join(f["added"]))
        removed_targets = _write_targets("\n".join(f["removed"]))
        for table in sorted(added_targets - removed_targets):
            if _is_authority_table(table):
                continue
            if table in relocated:
                # Write moved from another runtime file in this same diff; net
                # writer set unchanged (relocation, not a new competing owner).
                continue
            other = _table_writers(table, root, exclude=path)
            if other:
                findings.append(
                    {
                        "detector": "unowned_table_write",
                        "severity": "block",
                        "path": path,
                        "symbol": table,
                        "message": (
                            f"{path} adds a write to {table!r}, which is ALSO written by "
                            f"{', '.join(other)}. Resolve table ownership (a derived/projection "
                            f"table must have a single writer) before merge."
                        ),
                    }
                )
    return findings


# --- (d) migration file+DB duplication --------------------------------------

_CREATE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)", re.IGNORECASE)


def detect_migration_file_db_duplication(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT
) -> list[Finding]:
    """A migration CREATE TABLE for a table an unchanged migration already creates."""
    root = Path(repo_root)
    files = _parse_diff(diff_text, repo_root=root)
    findings: list[Finding] = []
    migrations_dir = root / "core" / "event_store" / "migrations"
    for f in files:
        path = _normalize(f["path"])
        if "migrations/" not in path or not path.endswith(".sql"):
            continue
        created = {
            m.group(1).lower()
            for ln in f["added"]
            for m in _CREATE_RE.finditer(strip_sql_comments(ln))
        }
        for table in sorted(created):
            if not migrations_dir.is_dir():
                continue
            for mig in migrations_dir.glob("*.sql"):
                rel = _normalize(str(mig.relative_to(root)))
                if rel == path:
                    continue
                try:
                    sql = strip_sql_comments(mig.read_text(encoding="utf-8"))
                except OSError:
                    continue
                if any(m.group(1).lower() == table for m in _CREATE_RE.finditer(sql)):
                    findings.append(
                        {
                            "detector": "migration_file_db_duplication",
                            "severity": "block",
                            "path": path,
                            "symbol": table,
                            "message": (
                                f"{path} creates table {table!r}, which {rel} already creates. "
                                f"Duplicate DDL leaves file+DB drift."
                            ),
                        }
                    )
    return findings


def run_all_detectors(
    diff_text: str, *, repo_root: Path | str = REPO_ROOT, file_reader=None
) -> list[Finding]:
    """Run every detector. ``file_reader(path)`` supplies the NEW text of a file for the one
    detector that needs it (the changed-signature detector's Python string state); the
    blast-radius gate passes ``git show HEAD:path``."""
    findings: list[Finding] = []
    for detector in (
        detect_stale_removed_symbol_tests,
        detect_changed_signature_callers,
        detect_unowned_table_writes,
        detect_migration_file_db_duplication,
    ):
        if detector is detect_changed_signature_callers:
            findings.extend(detector(diff_text, repo_root=repo_root, file_reader=file_reader))
        else:
            findings.extend(detector(diff_text, repo_root=repo_root))
    return findings
