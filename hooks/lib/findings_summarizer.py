"""Compress audit/review findings from markdown prose into structured JSON.

CLI usage:
    py hooks/lib/findings_summarizer.py <findings-file> [--format json|compact]

Module usage:
    from lib.findings_summarizer import summarize_findings
    result = summarize_findings(text)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = ["critical", "high", "medium", "low"]
_SEVERITY_ALIASES: dict[str, str] = {
    "critical": "critical",
    "crit": "critical",
    "high": "high",
    "medium": "medium",
    "med": "medium",
    "moderate": "medium",
    "low": "low",
    "info": "low",
    "informational": "low",
}


def _normalise_severity(raw: str) -> str | None:
    return _SEVERITY_ALIASES.get(raw.strip().lower())


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------
# Each pattern must yield named groups: severity, and optionally file, title, fix.

_PATTERNS: list[re.Pattern[str]] = [
    # 1. Bracket format: [CRITICAL] src/auth.ts:42 — SQL injection in login query
    re.compile(
        r"^\s*\[(?P<severity>[A-Za-z]+)\]\s+"
        r"(?P<file>\S+?)\s*[—\-–]+\s*(?P<title>.+?)(?:\s*\(fix:\s*(?P<fix>.+?)\))?\s*$",
        re.IGNORECASE,
    ),
    # 2. Bold format: **High**: Unvalidated user input in src/api/routes.ts
    re.compile(
        r"^\s*\*\*(?P<severity>[A-Za-z]+)\*\*\s*:\s*(?P<title>.+?)"
        r"(?:\s+in\s+(?P<file>\S+?))?\s*$",
        re.IGNORECASE,
    ),
    # 3. Table row: | High | src/auth.ts | SQL injection | Use parameterized query |
    re.compile(
        r"^\s*\|(?P<severity>[^|]+)\|(?P<file>[^|]+)\|(?P<title>[^|]+)\|(?P<fix>[^|]+)\|?\s*$",
        re.IGNORECASE,
    ),
    # 3b. Table row with only 3 columns (no fix): | High | src/auth.ts | SQL injection |
    re.compile(
        r"^\s*\|(?P<severity>[^|]+)\|(?P<file>[^|]+)\|(?P<title>[^|]+)\|\s*$",
        re.IGNORECASE,
    ),
    # 4. Heading format: ### Critical: Missing CSRF protection
    re.compile(
        r"^\s*#{1,6}\s+(?P<severity>[A-Za-z]+)\s*:\s*(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    # 5. Dash-list format: - **Medium** — src/utils.ts: unused import
    re.compile(
        r"^\s*[-*]\s+\*\*(?P<severity>[A-Za-z]+)\*\*\s*[—\-–]+\s*"
        r"(?P<file>\S+?):\s*(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    # 5b. Dash-list without file: - **Medium** — some finding text
    re.compile(
        r"^\s*[-*]\s+\*\*(?P<severity>[A-Za-z]+)\*\*\s*[—\-–]+\s*(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
]

# Table separator rows to skip (e.g. |---|---|---|)
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s|:\-]+\|\s*$")

def _looks_like_file(token: str) -> bool:
    t = token.strip()
    if not t or t.lower() in _SEVERITY_ALIASES:
        return False
    # Must contain a slash, dot, or colon to be considered a path
    return bool(re.search(r"[./\\:]", t))


def _parse_line(line: str) -> dict | None:
    """Attempt to extract a finding from a single line. Returns None if no match."""
    if _TABLE_SEP_RE.match(line):
        return None

    for pattern in _PATTERNS:
        m = pattern.match(line)
        if not m:
            continue

        severity_raw = m.group("severity")
        severity = _normalise_severity(severity_raw)
        if severity is None:
            continue

        title = (m.groupdict().get("title") or "").strip()
        file_val = (m.groupdict().get("file") or "").strip()
        fix_val = (m.groupdict().get("fix") or "").strip()

        # Skip obviously non-finding table separators or header rows
        if not title:
            continue

        finding: dict = {
            "severity": severity,
            "file": file_val if _looks_like_file(file_val) else "unknown",
            "title": title,
        }
        if fix_val:
            finding["fix"] = fix_val

        return finding

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_findings(text: str) -> dict:
    """Parse markdown findings text and return structured summary dict.

    Args:
        text: Raw markdown content from an audit/review/scan output file.

    Returns:
        Dict with keys: total, critical, high, medium, low, findings.
    """
    findings: list[dict] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            result = _parse_line(line)
        except Exception:
            # Malformed line — skip silently
            continue
        if result is not None:
            findings.append(result)

    # Sort by severity order: critical → high → medium → low
    findings.sort(key=lambda f: _SEVERITY_ORDER.index(f["severity"]))

    counts: dict[str, int] = {sev: 0 for sev in _SEVERITY_ORDER}
    for f in findings:
        counts[f["severity"]] += 1

    return {
        "total": len(findings),
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "findings": findings,
    }


def _format_compact(summary: dict) -> str:
    """Render findings as one line per finding."""
    lines: list[str] = []
    for f in summary["findings"]:
        sev = f["severity"].upper()
        file_ = f.get("file", "unknown")
        title = f.get("title", "")
        fix = f.get("fix", "")
        if fix:
            line = f"[{sev}] {file_} — {title} (fix: {fix})"
        else:
            line = f"[{sev}] {file_} — {title}"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="findings_summarizer",
        description="Compress markdown findings into structured JSON or compact text.",
    )
    parser.add_argument(
        "findings_file",
        help="Path to a markdown findings file produced by audit/review/scan workflow nodes.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "compact"],
        default="json",
        help="Output format: 'json' (default) or 'compact' (one line per finding).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    findings_path = Path(args.findings_file)

    if not findings_path.exists():
        if args.format == "compact":
            # Nothing to print for compact when file missing
            return
        print(json.dumps({"total": 0, "findings": []}, indent=2))
        return

    try:
        text = findings_path.read_text(encoding="utf-8")
    except Exception:
        if args.format == "compact":
            return
        print(json.dumps({"total": 0, "findings": []}, indent=2))
        return

    if not text.strip():
        if args.format == "compact":
            return
        print(json.dumps({"total": 0, "findings": []}, indent=2))
        return

    summary = summarize_findings(text)

    if args.format == "compact":
        output = _format_compact(summary)
        if output:
            print(output)
    else:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
