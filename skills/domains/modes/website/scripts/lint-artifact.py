#!/usr/bin/env py
"""
Anti-Slop Linter — scans an HTML artifact for AI-default design patterns.

Usage:
    py scripts/lint-artifact.py path/to/output.html

Exit codes:
    0 = no violations
    1 = violations found
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    rule: str
    severity: str
    line: int
    column: int
    message: str
    context: str
    fix: str


@dataclass
class RuleDef:
    id: str
    severity: str
    check: Callable  # fn(lines: list[str], disabled_lines: set[int]) -> list[Violation]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_inline(text: str) -> str:
    """Remove HTML tags for plain-text searches."""
    return re.sub(r"<[^>]+>", " ", text)


def _make_violation(rule_id: str, severity: str, line_no: int, col: int,
                    message: str, context_line: str, fix: str) -> Violation:
    return Violation(
        rule=rule_id,
        severity=severity,
        line=line_no,
        column=col,
        message=message,
        context=context_line.strip(),
        fix=fix,
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def check_purple_gradient(lines, disabled):
    """Rule: purple-gradient (critical)"""
    rule_id = "purple-gradient"
    severity = "critical"
    fix = "Replace with brand-specific colors from locked direction palette"

    hex_colors = r"#(?:7c3aed|8b5cf6|a78bfa|6d28d9|7e22ce)"
    color_names = r"\b(?:purple|violet)\b"
    # Match these colors inside gradient() function calls
    grad_pat = re.compile(
        r"gradient\([^)]*(?:" + hex_colors + r"|" + color_names + r")[^)]*\)",
        re.IGNORECASE,
    )
    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        m = grad_pat.search(line)
        if m:
            matched_val = m.group(0)[:60]
            violations.append(_make_violation(
                rule_id, severity, i, m.start() + 1,
                f"AI-default purple gradient detected: {matched_val}",
                line,
                fix,
            ))
    return violations


def check_indigo_default(lines, disabled):
    """Rule: indigo-default (critical)"""
    rule_id = "indigo-default"
    severity = "critical"
    fix = "Replace Tailwind indigo/indigo-* utilities and hex values with brand palette tokens"

    hex_pat = re.compile(r"#(?:6366f1|4f46e5|818cf8|4338ca)", re.IGNORECASE)
    class_pat = re.compile(r"\bindigo-(?:400|500|600|700)\b", re.IGNORECASE)
    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        for pat in (hex_pat, class_pat):
            m = pat.search(line)
            if m:
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    f"AI-default indigo color detected: {m.group(0)}",
                    line,
                    fix,
                ))
                break  # one violation per line per rule
    return violations


def check_emoji_as_icon(lines, disabled):
    """Rule: emoji-as-icon (high) — emoji in buttons, nav, or headings."""
    rule_id = "emoji-as-icon"
    severity = "high"
    fix = "Replace emoji with an SVG icon or icon font; keep emoji only in prose/body copy"

    # Common emoji Unicode ranges
    emoji_ranges = [
        (0x1F300, 0x1F9FF),
        (0x2600, 0x26FF),
        (0x2700, 0x27BF),
        (0x1F000, 0x1F02F),
        (0x1F0A0, 0x1F0FF),
        (0x1FA00, 0x1FA6F),
        (0x1FA70, 0x1FAFF),
    ]

    def has_emoji(text: str) -> tuple[bool, str]:
        for ch in text:
            cp = ord(ch)
            for lo, hi in emoji_ranges:
                if lo <= cp <= hi:
                    return True, ch
        return False, ""

    # Tags that indicate non-content contexts
    ui_tag_pat = re.compile(
        r"<(?:button|nav|a|h[1-6]|header|li|span|div)[^>]*>([^<]*)",
        re.IGNORECASE,
    )

    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        for m in ui_tag_pat.finditer(line):
            content = m.group(1)
            found, emoji_char = has_emoji(content)
            if found:
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    f"Emoji used as UI icon: {emoji_char!r}",
                    line,
                    fix,
                ))
                break
    return violations


def check_inter_as_display(lines, disabled):
    """Rule: inter-as-display (high)"""
    rule_id = "inter-as-display"
    severity = "high"
    fix = "Use a distinct display/heading typeface; reserve Inter/system-ui for body copy"

    # font-family line containing Inter or system-ui
    font_pat = re.compile(
        r"font-family\s*:[^;]*(?:Inter|system-ui|-apple-system)[^;]*;",
        re.IGNORECASE,
    )
    # selector context: h1-h6, .display, .heading, .title, .hero
    selector_pat = re.compile(
        r"(?:h[1-6]|\.(?:display|heading|title|hero))\b",
        re.IGNORECASE,
    )

    violations = []
    # We track the last seen selector to judge context
    last_selector = ""
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        if selector_pat.search(line):
            last_selector = line
        m = font_pat.search(line)
        if m:
            # Check if we're inside a heading/display selector block
            # Simple heuristic: last selector within 10 lines was a heading selector
            if selector_pat.search(last_selector):
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    "Inter/system-ui used as display/heading font",
                    line,
                    fix,
                ))
    return violations


def check_lorem_ipsum(lines, disabled):
    """Rule: lorem-ipsum (critical)"""
    rule_id = "lorem-ipsum"
    severity = "critical"
    fix = "Replace placeholder text with real copy before delivery"

    lorem_pat = re.compile(
        r"(?:Lorem\s+ipsum|dolor\s+sit\s+amet|consectetur\s+adipiscing)",
        re.IGNORECASE,
    )
    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        m = lorem_pat.search(line)
        if m:
            violations.append(_make_violation(
                rule_id, severity, i, m.start() + 1,
                "Lorem ipsum placeholder text found",
                line,
                fix,
            ))
    return violations


def check_invented_metrics(lines, disabled):
    """Rule: invented-metrics (high)"""
    rule_id = "invented-metrics"
    severity = "high"
    fix = "Use only real, verifiable metrics; remove or replace fabricated statistics"

    patterns = [
        re.compile(r"\d+[xX]\s*faster", re.IGNORECASE),
        re.compile(r"\d+\.?\d*%\s*uptime", re.IGNORECASE),
        re.compile(r"\d+[MmKk]\+?\s+(?:users|clients|customers|downloads)", re.IGNORECASE),
    ]
    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        plain = _strip_inline(line)
        for pat in patterns:
            m = pat.search(plain)
            if m:
                violations.append(_make_violation(
                    rule_id, severity, i, 1,
                    f"Invented metric detected: {m.group(0)!r}",
                    line,
                    fix,
                ))
                break
    return violations


def check_left_accent_card(lines, disabled):
    """Rule: left-accent-card (medium)"""
    rule_id = "left-accent-card"
    severity = "medium"
    fix = "Replace left-border accent cards with a distinct brand pattern (e.g., filled header, tinted bg)"

    # border-left: Npx solid … inside a card/container context
    border_pat = re.compile(
        r"border-left\s*:\s*[2-6]px\s+solid",
        re.IGNORECASE,
    )
    card_context = re.compile(
        r"\b(?:card|container|panel|box|widget|item)\b",
        re.IGNORECASE,
    )

    violations = []
    window: list[str] = []
    for i, line in enumerate(lines, 1):
        window.append(line)
        if len(window) > 20:
            window.pop(0)
        if i - 1 in disabled:
            continue
        m = border_pat.search(line)
        if m:
            context_block = " ".join(window)
            if card_context.search(context_block):
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    "Left-accent border on card/container element detected",
                    line,
                    fix,
                ))
    return violations


def check_stock_alt_text(lines, disabled):
    """Rule: stock-alt-text (medium)"""
    rule_id = "stock-alt-text"
    severity = "medium"
    fix = "Write descriptive alt text that conveys meaning; do not leave alt empty on informational images"

    # alt="" or alt="image|photo|icon|picture|placeholder|screenshot"
    alt_pat = re.compile(
        r'alt\s*=\s*"(?:|image|photo|icon|picture|placeholder|screenshot)"',
        re.IGNORECASE,
    )
    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        m = alt_pat.search(line)
        if m:
            violations.append(_make_violation(
                rule_id, severity, i, m.start() + 1,
                f"Generic or empty alt text: {m.group(0)}",
                line,
                fix,
            ))
    return violations


def check_excessive_shadow(lines, disabled):
    """Rule: excessive-shadow (medium) — 3+ shadow values on one element."""
    rule_id = "excessive-shadow"
    severity = "medium"
    fix = "Limit to one or two shadow layers; heavy stacking is a visual cliché"

    box_shadow_pat = re.compile(r"box-shadow\s*:\s*([^;]+);", re.IGNORECASE)

    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        m = box_shadow_pat.search(line)
        if m:
            value = m.group(1)
            # Count comma-separated shadow values (rough heuristic)
            # Shadows are separated by commas NOT inside parentheses
            depth = 0
            count = 1
            for ch in value:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif ch == "," and depth == 0:
                    count += 1
            if count >= 3:
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    f"Excessive box-shadow: {count} shadow layers",
                    line,
                    fix,
                ))
    return violations


def check_gratuitous_blur(lines, disabled):
    """Rule: gratuitous-blur (medium) — backdrop-filter blur outside modal/dialog/overlay."""
    rule_id = "gratuitous-blur"
    severity = "medium"
    fix = "Use backdrop-filter:blur only inside modals, drawers, or toast overlays"

    blur_pat = re.compile(r"backdrop-filter\s*:[^;]*blur\s*\(", re.IGNORECASE)
    modal_context = re.compile(
        r"\b(?:modal|dialog|overlay|drawer|toast|popup|sheet)\b",
        re.IGNORECASE,
    )

    violations = []
    window: list[str] = []
    for i, line in enumerate(lines, 1):
        window.append(line)
        if len(window) > 30:
            window.pop(0)
        if i - 1 in disabled:
            continue
        m = blur_pat.search(line)
        if m:
            ctx = " ".join(window)
            if not modal_context.search(ctx):
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    "backdrop-filter:blur used outside a modal/overlay context",
                    line,
                    fix,
                ))
    return violations


def check_rainbow_gradient(lines, disabled):
    """Rule: rainbow-gradient (high) — linear/radial gradient with 3+ distinct color stops."""
    rule_id = "rainbow-gradient"
    severity = "high"
    fix = "Limit gradients to 2 colors from the brand palette; avoid spectrum/rainbow effects"

    grad_pat = re.compile(
        r"(?:linear|radial)-gradient\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    # Match individual color stops (hex, rgb, hsl, named color)
    color_stop_pat = re.compile(
        r"(?:#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)|hsla?\([^)]+\)|(?:red|blue|green|yellow|orange|purple|pink|cyan|magenta|lime|teal|indigo|violet)\b)",
        re.IGNORECASE,
    )

    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        for m in grad_pat.finditer(line):
            stops = color_stop_pat.findall(m.group(1))
            if len(stops) >= 3:
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    f"Rainbow/multi-stop gradient with {len(stops)} color stops",
                    line,
                    fix,
                ))
                break
    return violations


def check_default_rounded(lines, disabled):
    """Rule: default-rounded (medium) — border-radius:9999px or rounded-full on non-pill elements."""
    rule_id = "default-rounded"
    severity = "medium"
    fix = "Only use 9999px/rounded-full on true pill buttons or avatar circles; use explicit radii elsewhere"

    radius_pat = re.compile(
        r"(?:border-radius\s*:\s*9999px|\brounded-full\b)",
        re.IGNORECASE,
    )
    # Known legitimate pill/avatar contexts
    pill_ctx = re.compile(
        r"\b(?:pill|badge|tag|avatar|chip|label)\b",
        re.IGNORECASE,
    )

    violations = []
    window: list[str] = []
    for i, line in enumerate(lines, 1):
        window.append(line)
        if len(window) > 15:
            window.pop(0)
        if i - 1 in disabled:
            continue
        m = radius_pat.search(line)
        if m:
            ctx = " ".join(window)
            if not pill_ctx.search(ctx):
                violations.append(_make_violation(
                    rule_id, severity, i, m.start() + 1,
                    "Full-round border-radius on non-pill/non-avatar element",
                    line,
                    fix,
                ))
    return violations


def check_ai_testimonial(lines, disabled):
    """Rule: ai-testimonial (critical) — known AI-generated testimonial phrases."""
    rule_id = "ai-testimonial"
    severity = "critical"
    fix = "Replace with real, attributed testimonials or remove the section entirely"

    phrases = [
        r"game[\s-]changer",
        r"transformed\s+(?:my|our)\s+(?:business|workflow|life|team)",
        r"couldn'?t\s+imagine\s+(?:my|our)\s+(?:business|life|work)\s+without",
        r"increased\s+(?:our\s+)?(?:revenue|productivity|efficiency)\s+by\s+\d+",
        r"5\s*(?:out\s+of\s+5|/\s*5)\s+stars",
        r"highly\s+recommend(?:ed)?",
        r"best\s+(?:decision|investment)\s+(?:I|we)\s+(?:ever\s+)?made",
        r"saved\s+(?:us|me)\s+(?:hours|time|money)",
        r"absolutely\s+(?:love|amazing|fantastic|incredible)\s+this",
    ]
    combined = re.compile("|".join(phrases), re.IGNORECASE)

    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        plain = _strip_inline(line)
        m = combined.search(plain)
        if m:
            violations.append(_make_violation(
                rule_id, severity, i, 1,
                f"AI-generated testimonial phrase detected: {m.group(0)!r}",
                line,
                fix,
            ))
    return violations


def check_filler_section(lines, disabled):
    """Rule: filler-section (high) — generic heading text patterns."""
    rule_id = "filler-section"
    severity = "high"
    fix = "Replace generic headings with specific, brand-relevant copy"

    # Headings that are pure filler
    generic_headings = re.compile(
        r"<h[1-6][^>]*>\s*(?:"
        r"(?:Our\s+)?(?:Features?|Benefits?|Services?|Solutions?|Pricing|Testimonials?|FAQ|About\s+Us|Contact\s+Us|Get\s+Started|Why\s+Choose\s+Us|How\s+It\s+Works|What\s+(?:We\s+Do|Our\s+Clients\s+Say)|Meet\s+(?:the\s+)?Team|Our\s+(?:Story|Mission|Vision|Values)|Call\s+to\s+Action|Sign\s+Up\s+(?:Today|Now|Free)|Ready\s+to\s+Get\s+Started)"
        r")\s*</h[1-6]>",
        re.IGNORECASE,
    )

    violations = []
    for i, line in enumerate(lines, 1):
        if i - 1 in disabled:
            continue
        m = generic_headings.search(line)
        if m:
            heading_text = re.sub(r"<[^>]+>", "", m.group(0)).strip()
            violations.append(_make_violation(
                rule_id, severity, i, m.start() + 1,
                f"Generic filler heading: {heading_text!r}",
                line,
                fix,
            ))
    return violations


def check_dark_mode_afterthought(lines, _disabled):
    """Rule: dark-mode-afterthought (medium) — prefers-color-scheme:dark only changes bg/text."""
    rule_id = "dark-mode-afterthought"
    severity = "medium"
    fix = "Expand dark mode to cover borders, shadows, illustrations, and interactive states"

    # Find all @media (prefers-color-scheme: dark) blocks
    full_text = "\n".join(lines)
    dark_block_pat = re.compile(
        r"@media\s*\([^)]*prefers-color-scheme\s*:\s*dark[^)]*\)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        re.IGNORECASE | re.DOTALL,
    )

    # Properties that suggest a superficial dark mode
    shallow_props = re.compile(
        r"\b(?:background(?:-color)?|color|bg)\b",
        re.IGNORECASE,
    )
    # Properties that suggest a thorough dark mode
    deep_props = re.compile(
        r"\b(?:border(?:-color)?|box-shadow|outline|fill|stroke|opacity|filter|backdrop-filter)\b",
        re.IGNORECASE,
    )

    violations = []
    for m in dark_block_pat.finditer(full_text):
        block = m.group(1)
        has_shallow = bool(shallow_props.search(block))
        has_deep = bool(deep_props.search(block))
        if has_shallow and not has_deep:
            # Find line number of match start
            line_no = full_text[: m.start()].count("\n") + 1
            violations.append(_make_violation(
                rule_id, severity, line_no, 1,
                "Dark mode block only adjusts background/text colors",
                lines[line_no - 1] if line_no <= len(lines) else "",
                fix,
            ))
    return violations


# ---------------------------------------------------------------------------
# Rule registry — add new rules here
# ---------------------------------------------------------------------------

RULES: list[RuleDef] = [
    RuleDef("purple-gradient",        "critical", check_purple_gradient),
    RuleDef("indigo-default",         "critical", check_indigo_default),
    RuleDef("lorem-ipsum",            "critical", check_lorem_ipsum),
    RuleDef("ai-testimonial",         "critical", check_ai_testimonial),
    RuleDef("emoji-as-icon",          "high",     check_emoji_as_icon),
    RuleDef("inter-as-display",       "high",     check_inter_as_display),
    RuleDef("invented-metrics",       "high",     check_invented_metrics),
    RuleDef("rainbow-gradient",       "high",     check_rainbow_gradient),
    RuleDef("filler-section",         "high",     check_filler_section),
    RuleDef("left-accent-card",       "medium",   check_left_accent_card),
    RuleDef("stock-alt-text",         "medium",   check_stock_alt_text),
    RuleDef("excessive-shadow",       "medium",   check_excessive_shadow),
    RuleDef("gratuitous-blur",        "medium",   check_gratuitous_blur),
    RuleDef("default-rounded",        "medium",   check_default_rounded),
    RuleDef("dark-mode-afterthought", "medium",   check_dark_mode_afterthought),
]


# ---------------------------------------------------------------------------
# Bypass / disable comment parsing
# ---------------------------------------------------------------------------

def _build_disabled_set(lines: list[str]) -> dict[str, set[int]]:
    """
    Returns a mapping of rule_id -> set of 0-based line indices that are disabled.
    A line is disabled if the PREVIOUS line contains:
        <!-- lint-disable <rule-id> -->
    If rule-id is "all", every rule is disabled for that line.
    """
    disable_pat = re.compile(r"<!--\s*lint-disable\s+([\w-]+)\s*-->")
    disabled: dict[str, set[int]] = {r.id: set() for r in RULES}

    for i, line in enumerate(lines):
        m = disable_pat.search(line)
        if m:
            rule_id = m.group(1)
            target_line = i + 1  # 0-based index of the NEXT line
            if rule_id == "all":
                for s in disabled.values():
                    s.add(target_line)
            elif rule_id in disabled:
                disabled[rule_id].add(target_line)
    return disabled


# ---------------------------------------------------------------------------
# Main lint runner
# ---------------------------------------------------------------------------

def lint_file(html_path: str) -> dict:
    path = Path(html_path)
    if not path.exists():
        print(f"Error: file not found: {html_path}", file=sys.stderr)
        sys.exit(2)

    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()

    disabled_by_rule = _build_disabled_set(lines)

    all_violations: list[Violation] = []
    for rule in RULES:
        rule_disabled = disabled_by_rule.get(rule.id, set())
        found = rule.check(lines, rule_disabled)
        all_violations.extend(found)

    # Sort by line number
    all_violations.sort(key=lambda v: (v.line, v.column))

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for v in all_violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1

    total = len(all_violations)
    passed = total == 0

    result = {
        "file": str(path),
        "violations": [
            {
                "rule": v.rule,
                "severity": v.severity,
                "line": v.line,
                "column": v.column,
                "message": v.message,
                "context": v.context,
                "fix": v.fix,
            }
            for v in all_violations
        ],
        "summary": {
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "total": total,
            "passed": passed,
        },
    }
    return result


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def print_human_summary(result: dict) -> None:
    summary = result["summary"]
    total = summary["total"]

    parts = []
    if summary["critical"]:
        parts.append(f"{summary['critical']} critical")
    if summary["high"]:
        parts.append(f"{summary['high']} high")
    if summary["medium"]:
        parts.append(f"{summary['medium']} medium")

    detail = ", ".join(parts) if parts else "none"
    header = f"\nAnti-Slop Lint: {total} violation{'s' if total != 1 else ''} ({detail})"
    print(header.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
        sys.stdout.encoding or "utf-8", errors="replace"
    ))

    for v in result["violations"]:
        msg = v["message"].encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        )
        print(f"  L{v['line']}: [{v['severity']}] {v['rule']} -- {msg}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lint-artifact",
        description="Anti-Slop Linter: scan an HTML artifact for AI-default design patterns.",
    )
    parser.add_argument(
        "file",
        metavar="HTML_FILE",
        help="Path to the HTML file to lint",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Suppress human-readable summary; output only JSON",
    )
    parser.add_argument(
        "--rule",
        metavar="RULE_ID",
        action="append",
        dest="rules",
        help="Run only this rule (repeatable). Default: run all rules.",
    )
    args = parser.parse_args()

    # Filter rules if requested
    if args.rules:
        known = {r.id for r in RULES}
        for rid in args.rules:
            if rid not in known:
                print(f"Error: unknown rule '{rid}'. Known rules: {', '.join(sorted(known))}", file=sys.stderr)
                sys.exit(2)
        # Temporarily replace global RULES list
        active = [r for r in RULES if r.id in set(args.rules)]
        RULES[:] = active

    result = lint_file(args.file)

    # JSON output
    print(json.dumps(result, indent=2))

    # Human-readable summary
    if not args.json_only:
        print_human_summary(result)

    sys.exit(0 if result["summary"]["passed"] else 1)


if __name__ == "__main__":
    main()
