"""lint-artifact.py — the anti-slop linter for delivered HTML artifacts.

WHY THIS FILE IS BEING WRITTEN IN SEPTEMBER FOR A RULE DATED MAY. It existed: a
`lint-artifact.cpython-312.pyc` dated 2026-05-23 sits beside this file. The source was
never once tracked, because `.gitignore` carried an unanchored `lint-*` under "Test /
diagnostic output captures" and it swallowed this path silently. So every clone, every
CI runner and the shipped plugin had fourteen instructions to run a file that was not
there -- including a `severity: critical` gotcha reading "Run py scripts/lint-artifact.py
<output.html> before every delivery." The spec survived in
`references/anti-slop-linter.md`; only the implementation was lost, and this is written
from that catalog rather than invented.

WHAT IT ENFORCES IS INTENTIONALITY, NOT TASTE. Every pattern here has a legitimate use.
The point is that it be a deliberate choice rather than an unexamined default, which is
why every rule can be bypassed on the line above it and why the bypass is recorded in the
artifact rather than in a config file somebody else has to go find.

Contract (from the catalog, which is the authority for all of it):

    py scripts/lint-artifact.py <file.html>
    py scripts/lint-artifact.py <file.html> --severity critical
    py scripts/lint-artifact.py <file.html> --fix-hints
    py scripts/lint-artifact.py <file.html> --json

    exit 0 = clean, 1 = warnings only, 2 = critical violations found

    <!-- lint-disable <rule-id> -->            silences the next line
    <!-- lint-disable <rule-id> -->  ...       silences until
    <!-- lint-enable <rule-id> -->             the matching enable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

CRITICAL, HIGH, MEDIUM = "critical", "high", "medium"
SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2}


@dataclass
class Violation:
    rule: str
    severity: str
    line: int
    excerpt: str
    fix_hint: str = ""


@dataclass
class Rule:
    rule_id: str
    severity: str
    summary: str
    fix_hint: str
    # Called with (line, whole_document) and returns True when the line violates.
    test: object = field(repr=False, default=None)


# ---------------------------------------------------------------------------
# Shared fragments. Defined once so two rules cannot drift apart on what
# "a purple" or "a gradient" means -- the same reason the citation registry
# keeps one spelling of each standard.
# ---------------------------------------------------------------------------

PURPLE_HEXES = ("#7c3aed", "#8b5cf6", "#a78bfa", "#6d28d9")
INDIGO_HEXES = ("#6366f1", "#4f46e5", "#818cf8", "#4338ca")
GRADIENT_CALL = re.compile(r"(linear|radial|conic)-gradient\s*\(", re.I)
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")

#: The three emoji blocks the catalog names, and no others. A wider sweep would
#: catch typographic marks that are not emoji (arrows, dingbat punctuation) and
#: make the rule something authors learn to ignore.
EMOJI = re.compile(
    "[\U0001f300-\U0001faff\u2600-\u26ff\u2700-\u27bf]",
)

UI_CONTAINER = re.compile(r"<\s*(button|a|li|td|th|h[1-4])\b", re.I)

PLACEHOLDER_COPY = re.compile(
    r"lorem\s+ipsum|dolor\s+sit\s+amet|consectetur\s+adipiscing|sed\s+do\s+eiusmod"
    r"|ut\s+labore\s+et\s+dolore|\[PLACEHOLDER\]|\[INSERT\s+TEXT\]|\[CONTENT\s+HERE\]"
    r"|\[COPY\s+TBD\]",
    re.I,
)

INVENTED_METRIC = re.compile(
    r"\d+[xX]\s*(faster|better|more|less|cheaper)"
    r"|\d+\.?\d*%\s*(uptime|accuracy|faster|reduction|increase|improvement|satisfaction)"
    r"|\d+[KkMmBb]?\s*\+?\s*(users|clients|customers|companies|teams|businesses"
    r"|downloads|installs)"
    r"|#1\s+(in|for|rated|ranked|trusted)"
    r"|trusted\s+by\s+\d+",
    re.I,
)
CITATION_NEARBY = re.compile(r"<cite\b|<sup\b|data-source\s*=|href\s*=\s*[\"']#fn", re.I)

AI_TESTIMONIAL = re.compile(
    r"(I\s+(really\s+|absolutely\s+)?love)\s+this\s+(product|tool|app|platform|service)"
    r"|best\s+(tool|product|app|software|platform)\s+I(\'ve|\s+have)\s+ever\s+used"
    r"|changed\s+my\s+(life|business|workflow|everything)"
    r"|game.?changer"
    r"|(5\s+stars|five\s+stars|\u2b50{4,5})",
    re.I,
)
TESTIMONIAL_CONTEXT = re.compile(
    r"<blockquote\b|class\s*=\s*[\"'][^\"']*(testimonial|quote|review)", re.I
)

FILLER_HEADING = re.compile(
    r">\s*(why\s+choose\s+us|our\s+features|key\s+features|core\s+features"
    r"|get\s+started(\s+today)?|meet\s+our\s+team|our\s+team|what\s+we\s+offer"
    r"|what\s+we\s+do|our\s+mission|our\s+vision|our\s+values)\s*<",
    re.I,
)

DISPLAY_FONT_FAMILIES = re.compile(r"Inter|system-ui|-apple-system|BlinkMacSystemFont", re.I)
DISPLAY_SELECTOR = re.compile(r"\b(h[1-3])\b|heading|display|title|hero", re.I)

STOCK_ALT = re.compile(
    r"\balt\s*=\s*[\"']\s*(image|photo|picture|img|icon|logo|banner|thumbnail|screenshot)?"
    r"\s*[\"']",
    re.I,
)

BLUR_ALLOWED = re.compile(
    r"dialog|alertdialog|modal|overlay|drawer|sheet|lightbox|position\s*:\s*fixed", re.I
)
DECORATIVE_BLOB = re.compile(r"blob|glow|orb|bg-blur|blur-shape", re.I)


def _hue(hex_color: str) -> float | None:
    """Hue in degrees for a 3- or 6-digit hex, or None when it will not parse."""
    s = hex_color.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        r, g, b = (int(s[i] + s[i + 1], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    hi, lo = max(r, g, b), min(r, g, b)
    if hi == lo:
        return None  # a grey has no hue, and must not count toward a spread
    d = hi - lo
    if hi == r:
        h = ((g - b) / d) % 6
    elif hi == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def _hue_spread(colors: list[str]) -> float:
    """Widest gap-free arc the hues occupy, in degrees.

    Measured on the circle rather than as max-minus-min, because #f00 and #f0f are 60
    degrees apart and a naive subtraction calls them 300.
    """
    hues = sorted(h for h in (_hue(c) for c in colors) if h is not None)
    if len(hues) < 3:
        return 0.0
    gaps = [(hues[i + 1] - hues[i]) for i in range(len(hues) - 1)]
    gaps.append(360 - hues[-1] + hues[0])
    return 360 - max(gaps)


# ---------------------------------------------------------------------------
# Rules. Each returns True when the LINE violates; the document is passed for
# the handful that need surrounding context.
# ---------------------------------------------------------------------------


def _purple_gradient(line: str, _doc: str) -> bool:
    if GRADIENT_CALL.search(line):
        low = line.lower()
        if any(h in low for h in PURPLE_HEXES) or re.search(r"\b(purple|violet)\b", low):
            return True
    return bool(re.search(r"\b(from|to|via)-(purple|violet)-\d", line, re.I))


def _indigo_default(line: str, _doc: str) -> bool:
    low = line.lower()
    if any(h in low for h in INDIGO_HEXES):
        return True
    if re.search(r"\b(bg|text|border)-indigo-\d", line, re.I):
        return True
    return bool(
        re.search(
            r"(color|background(-color)?|border-color|fill|stroke|--color-(primary|accent))"
            r"\s*:\s*[^;]*\bindigo\b",
            line,
            re.I,
        )
    )


def _emoji_as_icon(line: str, _doc: str) -> bool:
    return bool(EMOJI.search(line)) and bool(UI_CONTAINER.search(line))


def _inter_as_display(line: str, _doc: str) -> bool:
    if "font-family" not in line.lower() or not DISPLAY_FONT_FAMILIES.search(line):
        return False
    if DISPLAY_SELECTOR.search(line):
        return True
    size = re.search(r"font-size\s*:\s*([\d.]+)(px|rem|em)", line, re.I)
    if size:
        value, unit = float(size.group(1)), size.group(2).lower()
        return (value >= 24) if unit == "px" else (value >= 1.5)
    return False


def _lorem_ipsum(line: str, _doc: str) -> bool:
    return bool(PLACEHOLDER_COPY.search(line))


def _invented_metrics(line: str, _doc: str) -> bool:
    return bool(INVENTED_METRIC.search(line)) and not CITATION_NEARBY.search(line)


def _ai_testimonial(line: str, doc: str) -> bool:
    if not AI_TESTIMONIAL.search(line):
        return False
    # The catalog scopes this to quote containers. Checking the whole document rather
    # than the line, because a blockquote's open tag is usually a line above its text.
    return bool(TESTIMONIAL_CONTEXT.search(doc))


def _rainbow_gradient(line: str, _doc: str) -> bool:
    if not GRADIENT_CALL.search(line):
        return False
    return _hue_spread(HEX_COLOR.findall(line)) > 180


def _filler_section(line: str, _doc: str) -> bool:
    return bool(re.search(r"<h[1-4]\b", line, re.I)) and bool(FILLER_HEADING.search(line))


def _left_accent_card(line: str, _doc: str) -> bool:
    if re.search(r"border-left\s*:\s*(3px|4px|0\.25rem|0\.1875rem)\s+solid", line, re.I):
        return True
    return bool(re.search(r"border-l-(4|\[3px\])", line)) and bool(
        re.search(r"\bbg-\S+", line) and re.search(r"\bp-\d", line)
    )


def _stock_alt_text(line: str, _doc: str) -> bool:
    return bool(STOCK_ALT.search(line))


def _excessive_shadow(line: str, _doc: str) -> bool:
    m = re.search(r"box-shadow\s*:\s*([^;]+)", line, re.I)
    if m:
        # Split on the commas that separate LAYERS, not the ones inside rgba(...).
        value = re.sub(r"\([^)]*\)", "()", m.group(1))
        if len(value.split(",")) > 2:
            return True
    return bool(re.search(r"shadow-(2xl|3xl)", line)) and bool(
        re.search(r"shadow-(sm|md|lg|xl|inner)", line)
    )


def _gratuitous_blur(line: str, _doc: str) -> bool:
    if re.search(r"backdrop-filter\s*:\s*blur|(-webkit-)?backdrop-filter", line, re.I):
        return not BLUR_ALLOWED.search(line)
    if re.search(r"filter\s*:\s*blur", line, re.I):
        return bool(DECORATIVE_BLOB.search(line))
    return False


def _default_rounded(line: str, _doc: str) -> bool:
    if not re.search(r"border-radius\s*:\s*(9999px|50%)|rounded-full", line, re.I):
        return False
    if re.search(r"<\s*(button|img)\b|avatar|badge|tag|chip|aspect-ratio\s*:\s*1", line, re.I):
        return False
    return True


def _dark_mode_afterthought(line: str, doc: str) -> bool:
    """Flagged once, on the media query line, when its whole block only swaps colours."""
    if "prefers-color-scheme" not in line or "dark" not in line:
        return False
    start = doc.find(line)
    if start < 0:
        return False
    depth, i, body = 0, doc.find("{", start), []
    if i < 0:
        return False
    for ch in doc[i:]:
        body.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    block = "".join(body)
    declarations = re.findall(r"([-a-zA-Z]+)\s*:", block)
    if not declarations:
        return False
    colour_only = {"background", "background-color", "color", "border-color"}
    return all(d.lower() in colour_only for d in declarations)


RULES: tuple[Rule, ...] = (
    Rule(
        "purple-gradient",
        CRITICAL,
        "#7c3aed / #8b5cf6 / violet in gradients",
        "Source the gradient from the brief's brand colours. If no brief exists, pause and ask.",
        _purple_gradient,
    ),
    Rule(
        "indigo-default",
        CRITICAL,
        "#6366f1 / #4f46e5 / Tailwind indigo as primary",
        "Use a brand colour token, not Tailwind's default indigo.",
        _indigo_default,
    ),
    Rule(
        "lorem-ipsum",
        CRITICAL,
        "Placeholder copy, lorem ipsum text",
        "Write real copy. If copy is not ready, mark it clearly and block delivery.",
        _lorem_ipsum,
    ),
    Rule(
        "ai-testimonial",
        CRITICAL,
        "Fabricated or unattributed social proof quotes",
        "Use real quotes with full attribution, or omit the section entirely.",
        _ai_testimonial,
    ),
    Rule(
        "emoji-as-icon",
        HIGH,
        "Unicode emoji used as UI icons",
        "Use inline SVG or an icon component with an accessible label.",
        _emoji_as_icon,
    ),
    Rule(
        "inter-as-display",
        HIGH,
        "Inter/system-ui on display or heading type",
        "Display type needs personality. Inter is a UI workhorse, not a headline font.",
        _inter_as_display,
    ),
    Rule(
        "invented-metrics",
        HIGH,
        "Uncited performance claims and user counts",
        "Add a real citation, or replace with a verifiable specific claim.",
        _invented_metrics,
    ),
    Rule(
        "rainbow-gradient",
        HIGH,
        "3+ hue-spanning colour stops in gradients",
        "Keep gradients analogous (within ~60 degrees of hue) or neutral-to-colour.",
        _rainbow_gradient,
    ),
    Rule(
        "filler-section",
        HIGH,
        "Generic section headings without specific claims",
        "Make the heading specific to the actual claim or benefit.",
        _filler_section,
    ),
    Rule(
        "left-accent-card",
        MEDIUM,
        "3-4px left border on card containers",
        "Choose a card treatment that fits the brand; left border is an AI tell.",
        _left_accent_card,
    ),
    Rule(
        "stock-alt-text",
        MEDIUM,
        "Generic or empty alt attributes",
        "Describe what the image communicates, not what it is.",
        _stock_alt_text,
    ),
    Rule(
        "excessive-shadow",
        MEDIUM,
        "More than 2 box-shadow layers on one element",
        "Two layers maximum: a base shadow plus an ambient one is almost always enough.",
        _excessive_shadow,
    ),
    Rule(
        "gratuitous-blur",
        MEDIUM,
        "backdrop-filter / blob blur used decoratively",
        "Reserve blur for dialogs and overlays; use a background tint elsewhere.",
        _gratuitous_blur,
    ),
    Rule(
        "default-rounded",
        MEDIUM,
        "border-radius: 9999px on non-pill elements",
        "Use a purposeful radius. Cards typically want 8-16px.",
        _default_rounded,
    ),
    Rule(
        "dark-mode-afterthought",
        MEDIUM,
        "Dark mode that only swaps background and text colours",
        "Redefine semantic tokens in dark mode and let components inherit.",
        _dark_mode_afterthought,
    ),
)

RULES_BY_ID = {r.rule_id: r for r in RULES}

DISABLE = re.compile(r"<!--\s*lint-disable\s+([a-z-]+)", re.I)
ENABLE = re.compile(r"<!--\s*lint-enable\s+([a-z-]+)", re.I)


def _after(lines: list[str], index: int) -> list[str]:
    """Everything below `index`. A named helper because black spaces the slice
    `lines[index + 1 :]` and flake8 calls that E203."""
    return lines[index + 1 :]  # noqa: E203


def _suppressions(lines: list[str]) -> list[set[str]]:
    """Which rules are silenced on each line.

    Two forms, both from the catalog: a bare `lint-disable` silences the NEXT line, and a
    `lint-disable` later closed by `lint-enable` silences the block between them. The
    block form is detected by looking ahead for the matching enable, so the one-line form
    stays the default and nobody has to close a comment they did not open.
    """
    blocks = {
        rule
        for i, line in enumerate(lines)
        for rule in DISABLE.findall(line)
        if any(rule in ENABLE.findall(later) for later in _after(lines, i))
    }
    active: set[str] = set()
    out: list[set[str]] = []
    for line in lines:
        opened = {r for r in DISABLE.findall(line) if r in blocks}
        next_line_only = {r for r in DISABLE.findall(line) if r not in blocks}
        active |= opened
        out.append(set(active) | next_line_only)
        active -= set(ENABLE.findall(line))
    # A bare disable applies to the line BELOW it, so carry it forward one line.
    for i, line in enumerate(lines[:-1]):
        for rule in DISABLE.findall(line):
            if rule not in blocks:
                out[i + 1].add(rule)
    return out


def lint(html: str, *, min_severity: str | None = None) -> list[Violation]:
    """Every violation in `html`, in document order then severity order."""
    lines = html.splitlines()
    silenced = _suppressions(lines)
    ceiling = SEVERITY_ORDER.get(min_severity or MEDIUM, SEVERITY_ORDER[MEDIUM])

    found: list[Violation] = []
    for number, line in enumerate(lines, start=1):
        if DISABLE.search(line) or ENABLE.search(line):
            continue  # the bypass comment itself is not a violation
        for rule in RULES:
            if SEVERITY_ORDER[rule.severity] > ceiling:
                continue
            if rule.rule_id in silenced[number - 1]:
                continue
            if rule.test(line, html):
                found.append(
                    Violation(
                        rule=rule.rule_id,
                        severity=rule.severity,
                        line=number,
                        excerpt=line.strip()[:120],
                        fix_hint=rule.fix_hint,
                    )
                )
    return found


def exit_code(violations: list[Violation]) -> int:
    if any(v.severity == CRITICAL for v in violations):
        return 2
    return 1 if violations else 0


def _render(violations: list[Violation], *, fix_hints: bool) -> str:
    if not violations:
        return "clean - no anti-slop violations found"
    out = []
    for v in sorted(violations, key=lambda v: (SEVERITY_ORDER[v.severity], v.line)):
        out.append(f"{v.severity.upper():8s} line {v.line:4d}  {v.rule}")
        out.append(f"                       {v.excerpt}")
        if fix_hints:
            out.append(f"                       fix: {v.fix_hint}")
    counts = {s: sum(1 for v in violations if v.severity == s) for s in (CRITICAL, HIGH, MEDIUM)}
    out.append("")
    out.append(
        f"{len(violations)} violation(s): "
        f"{counts[CRITICAL]} critical, {counts[HIGH]} high, {counts[MEDIUM]} medium"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lint-artifact.py",
        description="Anti-slop linter for delivered HTML artifacts.",
    )
    parser.add_argument("file", help="The HTML artifact to lint")
    parser.add_argument(
        "--severity",
        choices=[CRITICAL, HIGH, MEDIUM],
        default=None,
        help="Only report rules at this severity or worse",
    )
    parser.add_argument("--fix-hints", action="store_true", help="Include inline fix suggestions")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2

    violations = lint(
        path.read_text(encoding="utf-8", errors="replace"), min_severity=args.severity
    )

    if args.json:
        print(
            json.dumps(
                {
                    "file": str(path),
                    "violations": [vars(v) for v in violations],
                    "counts": {
                        s: sum(1 for v in violations if v.severity == s)
                        for s in (CRITICAL, HIGH, MEDIUM)
                    },
                },
                indent=2,
            )
        )
    else:
        print(_render(violations, fix_hints=args.fix_hints))
    return exit_code(violations)


if __name__ == "__main__":
    raise SystemExit(main())
