"""Content-level enforcement detectors — pure text functions.

Domain-isolated from `guardrails/evaluator.py`. The evaluator queries the
activity_log to enforce structural/policy rules; this module inspects response
text for content-level violations the operator has set as project norms.

Each detector is a pure function over a string. No DB, no IO, no logging.
Callers (test suites, pre-send hooks, gate checks) decide how to react.

Add new content-level checks here. Keep them pure: input text in, structured
finding out.
"""

from __future__ import annotations

import re

_BRACKET_PATTERN = re.compile(r"\[([^\[\]]+)\]")

_BRACKET_PLACEHOLDER_TRIGGERS = re.compile(
    r"^\s*(tbd|todo|fixme|xxx|placeholder|insert\b|fill\b|your\s|add\s)",
    re.IGNORECASE,
)

_BARE_PLACEHOLDER_WORDS = re.compile(r"\b(TBD|TODO|FIXME|XXX|PLACEHOLDER)\b")

_PLACEHOLDER_PHRASES = re.compile(
    r"\b("
    r"define later"
    r"|as needed"
    r"|to be determined"
    r"|to be defined"
    r"|fill (?:this |it )?in(?: later)?"
    r")\b",
    re.IGNORECASE,
)

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]+`")
_URL_PATTERN = re.compile(r"https?://\S+")


def detect_placeholders(text: str) -> list[str]:
    """Return placeholder substrings found in ``text``, in document order.

    Catches three shapes the operator has flagged as "no placeholders":
      * bracket-wrapped placeholders such as ``[TBD]`` or ``[your name]``
      * bare placeholder words ``TBD`` / ``TODO`` / ``FIXME`` / ``XXX`` / ``PLACEHOLDER``
      * common placeholder phrases such as ``define later`` or ``as needed``

    Bracket spans whose content is not placeholder-like (e.g. citations
    like ``[1]`` or link labels like ``[docs]``) are ignored. Bare words or
    phrases that sit inside a bracket finding are not reported twice.
    """
    if not text:
        return []

    spans: list[tuple[int, int, str]] = []
    bracket_ranges: list[tuple[int, int]] = []

    for match in _BRACKET_PATTERN.finditer(text):
        if _BRACKET_PLACEHOLDER_TRIGGERS.match(match.group(1)):
            spans.append((match.start(), match.end(), match.group(0)))
            bracket_ranges.append((match.start(), match.end()))

    def _inside_bracket(m: re.Match) -> bool:
        return any(start <= m.start() and m.end() <= end for start, end in bracket_ranges)

    for match in _BARE_PLACEHOLDER_WORDS.finditer(text):
        if not _inside_bracket(match):
            spans.append((match.start(), match.end(), match.group(0)))

    for match in _PLACEHOLDER_PHRASES.finditer(text):
        if not _inside_bracket(match):
            spans.append((match.start(), match.end(), match.group(0)))

    spans.sort(key=lambda s: s[0])
    return [text_part for _, _, text_part in spans]


def detect_multi_question(text: str) -> bool:
    """Return True when ``text`` poses more than one question to the user.

    Strips fenced code, inline code, and URLs before counting ``?`` marks so
    that documentation samples and query strings do not falsely trigger.
    """
    if not text:
        return False

    stripped = _CODE_FENCE.sub("", text)
    stripped = _INLINE_CODE.sub("", stripped)
    stripped = _URL_PATTERN.sub("", stripped)

    return stripped.count("?") > 1
