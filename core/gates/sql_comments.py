"""Shared comment-stripper for gate DDL-keyword heuristics (WO-GATE-SQL-PARSERS).

Several gate parsers regex SQL DDL (CREATE TABLE / DROP TABLE / ALTER … RENAME
TO) out of file and diff text. They repeatedly matched keywords inside comments
and prose — e.g. a comment ``# CREATE TABLE if needed`` extracted the table name
``if`` (the ``IF NOT EXISTS`` optional group missed, so ``(\\w+)`` captured ``if``),
tripping blast-radius migration_file_db_duplication and the test-fixture
resurrection guard, and polluting the tombstone ledger with junk names
(if/is/on/removed).

``strip_sql_comments`` removes SQL (``--``, ``/* */``) and Python (``#``) comments
before those regexes run. It is intentionally approximate — it does not honor
quotes — because the callers only need DDL keywords that appear *inside a comment*
to stop matching; real DDL (including DDL inside a Python string literal, which
has no comment marker) is preserved.
"""

from __future__ import annotations

import re

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_MARKERS = ("--", "#")


def strip_sql_comments(text: str) -> str:
    """Return *text* with SQL/Python comments blanked out.

    Block comments (``/* … */``) are removed first, then each line is truncated at
    the earliest ``--`` or ``#`` line-comment marker. Line structure is preserved
    (comments become empty tails) so diff/line-oriented callers keep their offsets.
    """
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    out: list[str] = []
    for line in text.splitlines():
        cut_positions = [line.find(m) for m in _LINE_COMMENT_MARKERS]
        cut_positions = [i for i in cut_positions if i != -1]
        if cut_positions:
            line = line[: min(cut_positions)]
        out.append(line)
    return "\n".join(out)
