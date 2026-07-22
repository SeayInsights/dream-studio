"""Source tier scoring, extraction, confidence, and summarization for web research.

WO-GF-CONTROL-INSTALL-split: see web.py facade docstring.
"""

from __future__ import annotations

from .web_shared import Source


def _get_source_tier(url: str) -> int:
    """Determine source quality tier based on domain.

    Args:
        url: Source URL

    Returns:
        Tier level (1-3, lower is higher quality)
    """
    url_lower = url.lower()

    # Tier 1: Official documentation and primary sources
    tier1_domains = [
        "github.com",
        "readthedocs.io",
        "readthedocs.org",
        "python.org",
        "nodejs.org",
        "docs.microsoft.com",
        "developer.mozilla.org",
        "w3.org",
        "ietf.org",
        "npmjs.com",
        "pypi.org",
        "crates.io",
        "golang.org",
        "rust-lang.org",
        "kotlinlang.org",
        "swift.org",
        "apache.org",
        "eclipse.org",
        "kubernetes.io",
    ]

    # Tier 2: Technical blogs and curated content
    tier2_domains = [
        "medium.com",
        "dev.to",
        "hashnode.dev",
        "blog.",
        "engineering.",
        "tech.",
        "martinfowler.com",
        "overreacted.io",
        "smashingmagazine.com",
        "css-tricks.com",
        "freecodecamp.org",
        "digitalocean.com/community",
    ]

    # Tier 3: Forums and Q&A sites
    tier3_domains = [
        "stackoverflow.com",
        "stackexchange.com",
        "reddit.com",
        "discord.com",
        "discourse.org",
        "discuss.",
        "community.",
        "forum.",
    ]

    for domain in tier1_domains:
        if domain in url_lower:
            return 1

    for domain in tier2_domains:
        if domain in url_lower:
            return 2

    for domain in tier3_domains:
        if domain in url_lower:
            return 3

    # Default to tier 2 for unknown domains
    return 2


def extract_sources(search_results: list[dict]) -> list[Source]:
    """Parse search results into Source objects with tier classification.

    Args:
        search_results: List of dicts with 'url', 'title', 'snippet' keys

    Returns:
        List of Source objects with tier assignments
    """
    sources = []

    for result in search_results:
        url = result.get("url", "")
        title = result.get("title", "")
        snippet = result.get("snippet", "")

        if not url or not title:
            continue

        tier = _get_source_tier(url)
        sources.append(
            Source(
                url=url,
                title=title,
                snippet=snippet,
                tier=tier,
                extraction_notes=snippet or "unavailable",
            )
        )

    return sources


def calculate_confidence(sources: list[Source]) -> float:
    """Calculate confidence score based on source quality and count.

    Formula: (tier1_weight * count1 + tier2_weight * count2 + tier3_weight * count3) / max_possible

    Args:
        sources: List of Source objects

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not sources:
        return 0.0

    # Weights by tier (tier 1 = highest weight)
    tier_weights = {1: 1.0, 2: 0.6, 3: 0.3}

    # Count sources by tier
    tier_counts = {1: 0, 2: 0, 3: 0}
    for source in sources:
        tier_counts[source.tier] = tier_counts.get(source.tier, 0) + 1

    # Calculate weighted score
    weighted_sum = sum(tier_counts[tier] * tier_weights[tier] for tier in tier_counts)

    # Max possible score for this many sources (all tier 1)
    max_score = len(sources) * tier_weights[1]

    # Normalize to 0-1
    confidence = min(weighted_sum / max_score, 1.0) if max_score > 0 else 0.0

    return round(confidence, 2)


def calculate_triangulation(sources: list[Source]) -> float:
    """Calculate source triangulation score based on independent agreement.

    Triangulation improves with more sources (need 3+ for full confidence).

    Args:
        sources: List of Source objects

    Returns:
        Triangulation score between 0.0 and 1.0
    """
    if not sources:
        return 0.0

    # Need at least 3 sources for 1.0 triangulation
    triangulation = min(len(sources) / 3.0, 1.0)

    return round(triangulation, 2)


def summarize_findings(sources: list[Source]) -> str:
    """Generate markdown summary of research findings.

    Args:
        sources: List of Source objects

    Returns:
        Markdown formatted summary string
    """
    if not sources:
        return "No sources found."

    # Group sources by tier
    by_tier = {1: [], 2: [], 3: []}
    for source in sources:
        by_tier[source.tier].append(source)

    lines = ["## Research Findings\n"]

    tier_labels = {
        1: "Primary Sources (Tier 1)",
        2: "Technical Content (Tier 2)",
        3: "Community Discussion (Tier 3)",
    }

    for tier in [1, 2, 3]:
        tier_sources = by_tier[tier]
        if not tier_sources:
            continue

        lines.append(f"\n### {tier_labels[tier]}\n")

        for source in tier_sources:
            lines.append(f"- **[{source.title}]({source.url})**")
            if source.snippet:
                # Clean and truncate snippet
                snippet = source.snippet.replace("\n", " ").strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                lines.append(f"  {snippet}\n")

    return "\n".join(lines)
