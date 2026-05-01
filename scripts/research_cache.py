"""CLI for managing the dream-studio research cache.

Usage examples
--------------
  python scripts/research_cache.py save "security-owasp" --sources '[{"url":"https://owasp.org","tier":"1","date":"2026-05-01","key_findings":"Top 10 list"}]'
  python scripts/research_cache.py get "security-owasp"
  python scripts/research_cache.py stale
  python scripts/research_cache.py refresh "security-owasp"
  python scripts/research_cache.py prune --days 180
  python scripts/research_cache.py list
  python scripts/research_cache.py stats
  python scripts/research_cache.py list --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap hook library path
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from lib.research_store import (
    delete_research,
    get_research,
    is_stale,
    list_topics,
    save_research,
    search_research,
)

# ---------------------------------------------------------------------------
# Domain refresh logic
# ---------------------------------------------------------------------------

_DOMAIN_DAYS: list[tuple[tuple[str, ...], int]] = [
    (("security-", "vuln-", "cve-"), 30),
    (("market-", "competitive-", "competitor-"), 90),
    (("tech-", "architecture-", "arch-"), 180),
]
_DEFAULT_DAYS = 90


def _refresh_days(topic: str) -> int:
    """Return the refresh interval in days based on the topic prefix."""
    lower = topic.lower()
    for prefixes, days in _DOMAIN_DAYS:
        if any(lower.startswith(p) for p in prefixes):
            return days
    return _DEFAULT_DAYS


def _refresh_due(topic: str) -> str:
    """Return the ISO refresh-due date string for a topic."""
    return (date.today() + timedelta(days=_refresh_days(topic))).isoformat()


# ---------------------------------------------------------------------------
# Confidence / triangulation helpers
# ---------------------------------------------------------------------------

def _calc_confidence(sources: list[dict]) -> str:
    """Calculate confidence level from source list."""
    count = len(sources)
    if count == 0:
        return "low"
    tier1_count = sum(
        1 for s in sources if str(s.get("tier", "")).strip() == "1"
    )
    if count >= 3 and tier1_count >= 1:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _calc_triangulated(sources: list[dict]) -> bool:
    return len(sources) >= 3


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------

def _load_sources(sources_arg: str) -> list[dict]:
    """Parse --sources value as inline JSON or a file path."""
    stripped = sources_arg.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        raw = json.loads(stripped)
    else:
        path = Path(stripped)
        if not path.is_file():
            raise FileNotFoundError(f"Sources file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("sources must be a JSON array of source objects")
    return raw


# ---------------------------------------------------------------------------
# Table output helpers
# ---------------------------------------------------------------------------

def _col_width(rows: list[list[str]], idx: int, header: str) -> int:
    """Return the max column width for column *idx* including the header."""
    return max(len(header), *(len(str(r[idx])) for r in rows)) if rows else len(header)


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a simple fixed-width text table."""
    widths = [_col_width(rows, i, h) for i, h in enumerate(headers)]
    sep = "  ".join("-" * w for w in widths)
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print(sep)
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_save(args: argparse.Namespace) -> int:
    sources = _load_sources(args.sources)
    confidence = _calc_confidence(sources)
    triangulated = _calc_triangulated(sources)
    today = date.today().isoformat()
    due = _refresh_due(args.topic)

    data = {
        "topic": args.topic,
        "sources": sources,
        "confidence": confidence,
        "triangulated": triangulated,
        "saved_date": today,
        "refresh_due": due,
    }
    path = save_research(args.topic, data)
    print(f"Saved: {args.topic}")
    print(f"  confidence={confidence}  triangulated={triangulated}  refresh_due={due}")
    print(f"  file={path}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    doc = get_research(args.topic)
    if doc is None:
        print(f"Not found: {args.topic}")
        return 1
    print(json.dumps(doc, indent=2))
    return 0


def cmd_stale(args: argparse.Namespace) -> int:
    topics = list_topics()
    stale_topics = [t for t in topics if t["stale"]]

    if args.json:
        print(json.dumps(stale_topics, indent=2))
        return 0

    if not stale_topics:
        print("No stale topics.")
        return 0

    headers = ["TOPIC", "CONFIDENCE", "TRIANGULATED", "REFRESH_DUE"]
    rows = [
        [
            t["topic"],
            str(t.get("confidence") or ""),
            str(t.get("triangulated", False)),
            str(t.get("refresh_due") or ""),
        ]
        for t in stale_topics
    ]
    _print_table(headers, rows)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    doc = get_research(args.topic)
    if doc is None:
        print(f"Not found: {args.topic}")
        return 1
    doc["refresh_due"] = date.today().isoformat()
    save_research(args.topic, doc)
    print(f"Marked for re-research: {args.topic}  (refresh_due={doc['refresh_due']})")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    cutoff = date.today() - timedelta(days=args.days)
    topics = list_topics()
    pruned = 0
    for t in topics:
        doc = get_research(t["topic"])
        if doc is None:
            continue
        saved_raw = doc.get("saved_date")
        if not saved_raw:
            continue
        try:
            saved = date.fromisoformat(str(saved_raw))
        except ValueError:
            continue
        if saved < cutoff:
            deleted = delete_research(t["topic"])
            if deleted:
                print(f"Pruned: {t['topic']}  (saved={saved_raw})")
                pruned += 1
    print(f"\nTotal pruned: {pruned}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    topics = list_topics()

    if args.json:
        print(json.dumps(topics, indent=2))
        return 0

    if not topics:
        print("No research topics cached.")
        return 0

    headers = ["TOPIC", "CONFIDENCE", "TRIANGULATED", "REFRESH_DUE", "STALE"]
    rows = [
        [
            t["topic"],
            str(t.get("confidence") or ""),
            str(t.get("triangulated", False)),
            str(t.get("refresh_due") or ""),
            "YES" if t["stale"] else "no",
        ]
        for t in topics
    ]
    _print_table(headers, rows)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    topics = list_topics()
    total = len(topics)
    stale_count = sum(1 for t in topics if t["stale"])

    # source counts and domain breakdown
    source_counts: list[int] = []
    domain_counts: dict[str, int] = {}
    for t in topics:
        doc = get_research(t["topic"])
        if doc is None:
            continue
        srcs = doc.get("sources", [])
        source_counts.append(len(srcs))

        # parse domain prefix
        topic_lower = t["topic"].lower()
        domain = "other"
        for prefixes, _ in _DOMAIN_DAYS:
            if any(topic_lower.startswith(p) for p in prefixes):
                domain = prefixes[0].rstrip("-")
                break
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    avg_sources = (sum(source_counts) / len(source_counts)) if source_counts else 0.0

    stats = {
        "total_topics": total,
        "stale_count": stale_count,
        "avg_sources_per_topic": round(avg_sources, 2),
        "coverage_by_domain": domain_counts,
    }

    if args.json:
        print(json.dumps(stats, indent=2))
        return 0

    print(f"Total topics      : {total}")
    print(f"Stale             : {stale_count}")
    print(f"Avg sources/topic : {avg_sources:.2f}")
    print("Coverage by domain:")
    if domain_counts:
        for domain, count in sorted(domain_counts.items()):
            print(f"  {domain:<20} {count}")
    else:
        print("  (none)")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research_cache",
        description="Manage the dream-studio research cache.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # save
    p_save = sub.add_parser("save", help="Save research results for a topic.")
    p_save.add_argument("topic", help="Topic name (e.g. security-owasp)")
    p_save.add_argument(
        "--sources",
        required=True,
        help="JSON array of source objects (inline) or path to a JSON file.",
    )

    # get
    p_get = sub.add_parser("get", help="Retrieve cached research for a topic.")
    p_get.add_argument("topic", help="Topic name")

    # stale
    p_stale = sub.add_parser("stale", help="List topics past their refresh_due date.")
    p_stale.add_argument(
        "--json", action="store_true", help="Output as JSON array."
    )

    # refresh
    p_refresh = sub.add_parser(
        "refresh", help="Mark a topic for re-research (set refresh_due to today)."
    )
    p_refresh.add_argument("topic", help="Topic name")

    # prune
    p_prune = sub.add_parser(
        "prune", help="Remove entries older than N days (by saved_date)."
    )
    p_prune.add_argument(
        "--days",
        type=int,
        default=180,
        metavar="N",
        help="Age threshold in days (default: 180).",
    )

    # list
    p_list = sub.add_parser("list", help="List all cached topics with metadata.")
    p_list.add_argument(
        "--json", action="store_true", help="Output as JSON array."
    )

    # stats
    p_stats = sub.add_parser("stats", help="Show aggregate statistics.")
    p_stats.add_argument(
        "--json", action="store_true", help="Output as JSON object."
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_COMMAND_MAP = {
    "save": cmd_save,
    "get": cmd_get,
    "stale": cmd_stale,
    "refresh": cmd_refresh,
    "prune": cmd_prune,
    "list": cmd_list,
    "stats": cmd_stats,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = _COMMAND_MAP.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    try:
        code = handler(args)
    except (json.JSONDecodeError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
