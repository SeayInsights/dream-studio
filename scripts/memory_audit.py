#!/usr/bin/env python3
"""memory_audit.py — Scan Claude memory files for staleness, conflicts, and gaps.

Usage:
    py scripts/memory_audit.py
    py scripts/memory_audit.py --days 30 --verbose
    py scripts/memory_audit.py --memory-path ~/.claude/projects/my-project/memory/
    py scripts/memory_audit.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# YAML frontmatter parsing (stdlib only)
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-style frontmatter from a markdown file.

    Returns (metadata_dict, body_text). If no frontmatter is found,
    returns ({}, full_text).
    """
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    raw = text[3:end].strip()
    body = text[end + 4:].strip()

    meta: dict = {}
    for line in raw.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    return meta, body


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def discover_memory_dirs(base: Path | None = None) -> list[Path]:
    """Find all memory/ directories under ~/.claude/projects/*/memory/."""
    if base is not None:
        return [base] if base.is_dir() else []

    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.is_dir():
        return []

    dirs: list[Path] = []
    for project_dir in claude_dir.iterdir():
        mem_dir = project_dir / "memory"
        if mem_dir.is_dir():
            dirs.append(mem_dir)
    return dirs


def collect_memory_files(dirs: list[Path]) -> list[Path]:
    """Collect all .md files from the given memory directories."""
    files: list[Path] = []
    for d in dirs:
        for f in sorted(d.glob("*.md")):
            if f.name != "MEMORY.md":
                files.append(f)
    return files


def find_gotcha_files() -> list[Path]:
    """Locate gotchas.yml files in the dream-studio skills tree."""
    # Try relative to this script's location first, then CWD.
    candidates = [
        Path(__file__).resolve().parent.parent / "skills",
        Path.cwd() / "skills",
    ]
    found: list[Path] = []
    for base in candidates:
        if base.is_dir():
            found.extend(base.rglob("gotchas.yml"))
    return found


def find_session_files() -> list[Path]:
    """Find session handoff files from common locations."""
    locations = [
        Path.home() / ".dream-studio",
    ]
    # Also scan project .sessions/ dirs near CWD
    for p in [Path.cwd(), Path.cwd().parent]:
        sessions_dir = p / ".sessions"
        if sessions_dir.is_dir():
            locations.append(sessions_dir)

    files: list[Path] = []
    for loc in locations:
        if loc.is_dir():
            for ext in ("*.md", "*.yml", "*.yaml", "*.json", "*.txt"):
                files.extend(loc.rglob(ext))
    return files


# ---------------------------------------------------------------------------
# Check 1 — Stale entries
# ---------------------------------------------------------------------------

def check_stale(files: list[Path], threshold_days: int) -> list[dict]:
    """Return memory files whose mtime exceeds threshold_days."""
    now = datetime.now(tz=timezone.utc)
    results: list[dict] = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        age_days = (now - mtime).days
        if age_days > threshold_days:
            results.append({
                "file": f.name,
                "path": str(f),
                "age_days": age_days,
                "last_modified": mtime.strftime("%Y-%m-%d"),
            })
    return sorted(results, key=lambda x: x["age_days"], reverse=True)


# ---------------------------------------------------------------------------
# Check 2 — Potential duplicates vs gotchas.yml
# ---------------------------------------------------------------------------

def load_gotchas(gotcha_files: list[Path]) -> list[dict]:
    """Load all gotcha entries (title + context) from gotchas.yml files."""
    entries: list[dict] = []
    for gf in gotcha_files:
        try:
            text = gf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Simple YAML list parser — each entry starts with "- title:"
        current: dict | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- title:"):
                if current is not None:
                    entries.append(current)
                current = {
                    "title": stripped[len("- title:"):].strip().strip('"').strip("'"),
                    "context": "",
                    "source_file": str(gf),
                    "source_key": gf.parent.name + "/" + gf.name,
                }
            elif current is not None and stripped.startswith("context:"):
                current["context"] = stripped[len("context:"):].strip().strip('"').strip("'")
            elif current is not None and stripped.startswith("fix:"):
                # accumulate fix text into context for matching
                current["context"] += " " + stripped[len("fix:"):].strip()

        if current is not None:
            entries.append(current)

    return entries


def check_duplicates(files: list[Path], gotcha_files: list[Path]) -> list[dict]:
    """Detect memory files whose core content overlaps with a gotcha entry."""
    gotchas = load_gotchas(gotcha_files)
    if not gotchas:
        return []

    results: list[dict] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        _meta, body = parse_frontmatter(text)
        # Take the first meaningful paragraph as the "core content"
        core_lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        core = " ".join(core_lines[:3]).lower()

        if not core:
            continue

        # Extract significant words (5+ chars) for matching
        sig_words = [w for w in re.findall(r"\b\w{5,}\b", core) if w not in _STOPWORDS]
        if len(sig_words) < 2:
            continue

        for gotcha in gotchas:
            haystack = (gotcha["title"] + " " + gotcha["context"]).lower()
            matches = sum(1 for w in sig_words if w in haystack)
            # Require at least 2 significant word matches to flag
            if matches >= 2:
                # Build a short gotcha ref like "quality/modes/debug/gotchas.yml#real-db-tests"
                ref_path = gotcha["source_key"]
                slug = re.sub(r"[^a-z0-9]+", "-", gotcha["title"].lower()).strip("-")
                results.append({
                    "memory_file": f.name,
                    "gotcha_ref": f"{ref_path}#{slug}",
                    "gotcha_title": gotcha["title"],
                    "match_count": matches,
                })
                break  # one match per memory file is enough

    return results


_STOPWORDS = {
    "should", "never", "always", "after", "before", "every", "their",
    "there", "about", "which", "where", "these", "those", "other",
    "using", "files", "this", "that", "with", "from", "into",
}


# ---------------------------------------------------------------------------
# Check 3 — Missing coverage (session handoffs)
# ---------------------------------------------------------------------------

_CORRECTION_PATTERNS = [
    re.compile(r'director[\s_-]+correction["\s:]*([^\n"]+)', re.I),
    re.compile(r'lessons?_this_session["\s:]*([^\n"]+)', re.I),
    re.compile(r'"([^"]{10,80})".*?—\s*no memory', re.I),
    re.compile(r'lesson["\s:]+([^\n"]{10,80})', re.I),
]


def extract_corrections(session_files: list[Path]) -> list[dict]:
    """Pull Director corrections and lessons from session files."""
    found: list[dict] = []
    for sf in session_files:
        try:
            text = sf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for pat in _CORRECTION_PATTERNS:
            for m in pat.finditer(text):
                snippet = m.group(1).strip().strip('"').strip("'")
                if len(snippet) < 10:
                    continue
                # Try to extract a date from the filename
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", sf.name)
                date_str = date_match.group(0) if date_match else sf.name
                found.append({
                    "session": date_str,
                    "correction": snippet,
                    "source": str(sf),
                })

    return found


def check_missing_coverage(
    memory_files: list[Path], session_files: list[Path]
) -> list[dict]:
    """Find session corrections that don't have a corresponding memory file."""
    corrections = extract_corrections(session_files)
    if not corrections:
        return []

    # Build a search corpus from memory file names + bodies
    mem_corpus = ""
    for f in memory_files:
        try:
            mem_corpus += f.stem.replace("_", " ") + " "
            text = f.read_text(encoding="utf-8", errors="replace")
            _meta, body = parse_frontmatter(text)
            mem_corpus += body[:500] + " "
        except OSError:
            continue
    mem_corpus = mem_corpus.lower()

    gaps: list[dict] = []
    seen_corrections: set[str] = set()

    for item in corrections:
        correction = item["correction"]
        key = correction[:60].lower()
        if key in seen_corrections:
            continue
        seen_corrections.add(key)

        # Check if significant words from the correction appear in memory corpus
        words = [w for w in re.findall(r"\b\w{5,}\b", correction.lower()) if w not in _STOPWORDS]
        if not words:
            continue

        coverage = sum(1 for w in words if w in mem_corpus)
        coverage_ratio = coverage / len(words) if words else 1.0

        if coverage_ratio < 0.4:  # less than 40% of key terms found
            gaps.append({
                "session": item["session"],
                "correction": correction,
                "suggested_filename": "feedback_" + re.sub(r"[^a-z0-9]+", "_", correction[:40].lower()).strip("_") + ".md",
            })

    return gaps


# ---------------------------------------------------------------------------
# Check 4 — Type distribution
# ---------------------------------------------------------------------------

def check_type_distribution(files: list[Path]) -> dict[str, int]:
    """Count memory files by their frontmatter 'type' field."""
    counts: dict[str, int] = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta, _ = parse_frontmatter(text)
        mem_type = meta.get("type", "unknown")
        counts[mem_type] = counts.get(mem_type, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_report(
    *,
    stale: list[dict],
    duplicates: list[dict],
    gaps: list[dict],
    type_dist: dict[str, int],
    all_files: list[Path],
    verbose: bool,
    memory_dirs: list[Path],
) -> str:
    lines: list[str] = ["=== Memory Audit Report ===", ""]

    if verbose:
        lines.append(f"Scanned directories:")
        for d in memory_dirs:
            lines.append(f"  {d}")
        lines.append(f"  Total files scanned: {len(all_files)}")
        lines.append("")

    # Stale
    lines.append("Stale entries (>60 days):" if not verbose else f"Stale entries ({len(stale)} found):")
    if stale:
        for item in stale:
            lines.append(
                f"  ⚠ {item['file']} — {item['age_days']} days old"
                f" (last modified: {item['last_modified']})"
            )
    else:
        lines.append("  (none)")
    lines.append("")

    # Duplicates
    lines.append("Potential duplicates:")
    if duplicates:
        for item in duplicates:
            lines.append(f"  ⚠ {item['memory_file']} ↔ {item['gotcha_ref']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Missing coverage
    lines.append("Missing coverage:")
    if gaps:
        for item in gaps:
            lines.append(
                f"  ✗ Session {item['session']}: \"{item['correction']}\" "
                f"— no memory entry found"
            )
            if verbose:
                lines.append(f"      Suggested: {item['suggested_filename']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Type distribution
    lines.append("Type distribution:")
    if type_dist:
        dist_str = " | ".join(f"{k}: {v}" for k, v in sorted(type_dist.items()))
        lines.append(f"  {dist_str}")
    else:
        lines.append("  (no typed memory files found)")
    lines.append("")

    # Summary
    total_issues = len(stale) + len(duplicates) + len(gaps)
    summary_parts = []
    if stale:
        summary_parts.append(f"{len(stale)} stale")
    if duplicates:
        summary_parts.append(f"{len(duplicates)} duplicate")
    if gaps:
        summary_parts.append(f"{len(gaps)} gap")
    summary = ", ".join(summary_parts) if summary_parts else "0 issues"
    lines.append(
        f"Summary: {summary} — {total_issues} item{'s' if total_issues != 1 else ''} need attention"
        if total_issues > 0
        else "Summary: all clear — no issues found"
    )

    return "\n".join(lines)


def format_json(
    *,
    stale: list[dict],
    duplicates: list[dict],
    gaps: list[dict],
    type_dist: dict[str, int],
    all_files: list[Path],
) -> str:
    payload = {
        "stale": stale,
        "duplicates": duplicates,
        "gaps": gaps,
        "type_distribution": type_dist,
        "total_files_scanned": len(all_files),
        "summary": {
            "stale_count": len(stale),
            "duplicate_count": len(duplicates),
            "gap_count": len(gaps),
            "total_issues": len(stale) + len(duplicates) + len(gaps),
        },
    }
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _safe_print(text: str) -> None:
    """Print text, replacing unencodable characters for the current console."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii"))


def main() -> None:
    # Allow UTF-8 output on Windows if the terminal supports it
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Audit Claude memory files for staleness, conflicts, and gaps.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--memory-path",
        metavar="PATH",
        help="Scan a specific memory directory (default: auto-discover from ~/.claude/projects/)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        metavar="N",
        help="Staleness threshold in days (default: 60)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all files scanned, not just issues",
    )
    args = parser.parse_args()

    # Resolve memory directories
    explicit_path = Path(args.memory_path).expanduser() if args.memory_path else None
    memory_dirs = discover_memory_dirs(explicit_path)

    if not memory_dirs:
        if args.as_json:
            print(json.dumps({"error": "No memory directories found.", "dirs_checked": str(explicit_path or Path.home() / ".claude" / "projects")}))
        else:
            print("No memory directories found. Use --memory-path to specify one.")
        sys.exit(0)

    all_files = collect_memory_files(memory_dirs)

    if not all_files and not args.as_json:
        print(f"No memory files found in: {', '.join(str(d) for d in memory_dirs)}")
        sys.exit(0)

    # Run all checks
    gotcha_files = find_gotcha_files()
    session_files = find_session_files()

    stale = check_stale(all_files, args.days)
    duplicates = check_duplicates(all_files, gotcha_files)
    gaps = check_missing_coverage(all_files, session_files)
    type_dist = check_type_distribution(all_files)

    if args.as_json:
        output = format_json(
            stale=stale,
            duplicates=duplicates,
            gaps=gaps,
            type_dist=type_dist,
            all_files=all_files,
        )
    else:
        output = format_report(
            stale=stale,
            duplicates=duplicates,
            gaps=gaps,
            type_dist=type_dist,
            all_files=all_files,
            verbose=args.verbose,
            memory_dirs=memory_dirs,
        )

    _safe_print(output)


if __name__ == "__main__":
    main()
