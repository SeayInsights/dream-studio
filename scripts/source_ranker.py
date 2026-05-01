"""
source_ranker.py — Automated triangulation scoring for research sources.

Scores a list of sources against research methodology rules from
skills/domains/research/analysis.yml.

Usage:
    python source_ranker.py --sources sources.json
    cat sources.json | python source_ranker.py --stdin
    python source_ranker.py --sources sources.json --json
"""

import argparse
import json
import re
import sys
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Core scoring logic — testable, no CLI dependencies
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Return the registered domain (e.g. 'example.com') from a URL."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path  # handle bare domains
        # Strip port and leading 'www.'
        host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return url.lower()


def rank_sources(sources: list[dict]) -> dict:
    """
    Score a list of research sources against the methodology rules from
    skills/domains/research/analysis.yml.

    Args:
        sources: list of dicts with keys: url, name, tier, findings

    Returns:
        dict with keys:
            triangulation_score   float  0–1
            source_count          int
            tier1_count           int
            tier1_pct             float  0–100
            tier2_count           int
            domains               list[str]
            shared_domains        list[str]
            independence          str  "OK" | "SUSPECT"
            bias_flag             str  "PASS" | "FLAG"
            counter_argument      str  "PRESENT" | "MISSING"
            confidence            str  "LOW" | "MEDIUM" | "HIGH"
            gaps                  list[str]
    """
    n = len(sources)

    # -----------------------------------------------------------------------
    # 1. Triangulation score
    # -----------------------------------------------------------------------
    if n >= 3:
        triangulation_score = 1.0
    elif n == 2:
        triangulation_score = 0.5
    elif n == 1:
        triangulation_score = 0.2
    else:
        triangulation_score = 0.0

    # -----------------------------------------------------------------------
    # 2. Source tier distribution
    # -----------------------------------------------------------------------
    tier1_count = sum(1 for s in sources if s.get("tier") == 1)
    tier2_count = sum(1 for s in sources if s.get("tier") == 2)
    tier1_pct = (tier1_count / n * 100) if n > 0 else 0.0

    # -----------------------------------------------------------------------
    # 3. Independence check — flag if multiple sources share the same domain
    # -----------------------------------------------------------------------
    domains = [_extract_domain(s.get("url", "")) for s in sources]
    domain_counts: dict[str, int] = {}
    for d in domains:
        if d:
            domain_counts[d] = domain_counts.get(d, 0) + 1
    shared_domains = [d for d, count in domain_counts.items() if count > 1]
    independence = "SUSPECT" if shared_domains else "OK"

    # -----------------------------------------------------------------------
    # 4. Confirmation bias flag
    # -----------------------------------------------------------------------
    # Flag as "suspiciously unanimous" when all sources appear to agree
    # (no dissenting language detected in any findings).
    DISSENT_PATTERNS = re.compile(
        r"\b(however|but|counter|opposing|against|dispute|disagree|"
        r"controversial|debate|contested|unlike|alternatively|"
        r"on the other hand|nevertheless|though|except)\b",
        re.IGNORECASE,
    )
    has_dissent = any(
        DISSENT_PATTERNS.search(s.get("findings", "")) for s in sources
    )
    bias_flag = "PASS" if has_dissent else "FLAG"

    # -----------------------------------------------------------------------
    # 5. Counter-argument present
    # -----------------------------------------------------------------------
    COUNTER_PATTERNS = re.compile(
        r"\b(counter|opposing|however|steel.?man|on the other hand|"
        r"alternatively|objection|refute|rebut|contrary)\b",
        re.IGNORECASE,
    )
    counter_present = any(
        COUNTER_PATTERNS.search(s.get("findings", "")) for s in sources
    )
    counter_argument = "PRESENT" if counter_present else "MISSING"

    # -----------------------------------------------------------------------
    # Confidence thresholds
    # HIGH:   triangulation >= 1.0 AND tier1 >= 33% AND counter present
    # MEDIUM: triangulation >= 0.5 OR (tier1 >= 50% AND sources >= 2)
    # LOW:    everything else
    # -----------------------------------------------------------------------
    if triangulation_score >= 1.0 and tier1_pct >= 33.0 and counter_present:
        confidence = "HIGH"
    elif triangulation_score >= 0.5 or (tier1_pct >= 50.0 and n >= 2):
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # -----------------------------------------------------------------------
    # Gap analysis
    # -----------------------------------------------------------------------
    gaps: list[str] = []

    if n < 3:
        needed = 3 - n
        gaps.append(
            f"Need {needed} more independent source{'s' if needed > 1 else ''} for triangulation"
        )

    if counter_argument == "MISSING":
        gaps.append("Need counter-argument or steel-man")

    if tier1_count == 0:
        gaps.append("All sources are Tier 2 — seek a primary source")
    elif tier1_pct < 33.0:
        gaps.append("Low Tier 1 coverage — add more primary sources")

    if independence == "SUSPECT":
        gaps.append(
            f"Sources share domains ({', '.join(shared_domains)}) — independence unverified"
        )

    if bias_flag == "FLAG":
        gaps.append("All sources appear to agree — actively search for disconfirming evidence")

    return {
        "triangulation_score": triangulation_score,
        "source_count": n,
        "tier1_count": tier1_count,
        "tier1_pct": tier1_pct,
        "tier2_count": tier2_count,
        "domains": domains,
        "shared_domains": shared_domains,
        "independence": independence,
        "bias_flag": bias_flag,
        "counter_argument": counter_argument,
        "confidence": confidence,
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_text(sources: list[dict], result: dict) -> str:
    """Render result as human-readable text matching the spec."""
    n = result["source_count"]
    tri = result["triangulation_score"]
    tier1_count = result["tier1_count"]
    tier1_pct = result["tier1_pct"]
    independence = result["independence"]
    shared = result["shared_domains"]
    bias_flag = result["bias_flag"]
    counter = result["counter_argument"]
    confidence = result["confidence"]
    gaps = result["gaps"]

    lines: list[str] = []

    lines.append(f"Confidence: {confidence}")
    lines.append(
        f"Triangulation: {tri:.1f} ({n} of 3 needed)"
    )
    lines.append(
        f"Tier 1 sources: {tier1_count} of {n} ({tier1_pct:.0f}%)"
    )

    if independence == "SUSPECT":
        lines.append(f"Independence: SUSPECT (shared domains: {', '.join(shared)})")
    else:
        lines.append("Independence: OK")

    if bias_flag == "FLAG":
        lines.append("Bias check: FLAG (all sources agree — seek counter-arguments)")
    else:
        lines.append("Bias check: PASS")

    lines.append(f"Counter-argument: {counter}")

    if gaps:
        lines.append("")
        lines.append("Gaps to fill:")
        for gap in gaps:
            lines.append(f"  - {gap}")

    gap_count = len(gaps)
    if gap_count == 0:
        summary_detail = "no gaps identified"
    elif gap_count == 1:
        summary_detail = "address 1 gap before finalizing"
    else:
        summary_detail = f"address {gap_count} gaps before finalizing"

    lines.append("")
    lines.append(f"Overall: {confidence} confidence — {summary_detail}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score research sources against triangulation methodology rules."
    )

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--sources",
        metavar="JSON_FILE",
        help="Path to JSON file containing the source list.",
    )
    source_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read JSON source list from stdin.",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted text.",
    )

    args = parser.parse_args()

    # Load input
    try:
        if args.stdin:
            raw = sys.stdin.read()
        else:
            with open(args.sources, "r", encoding="utf-8") as fh:
                raw = fh.read()
        sources = json.loads(raw)
    except FileNotFoundError:
        print(f"ERROR: File not found: {args.sources}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON — {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(sources, list):
        print("ERROR: JSON input must be an array of source objects.", file=sys.stderr)
        sys.exit(1)

    result = rank_sources(sources)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_text(sources, result))


if __name__ == "__main__":
    main()
