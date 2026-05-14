# Research Flag System - Technical Reference

## Overview

The `--research` flag enables web-based research and source quality assessment in think mode. This system helps explore emerging topics, validate assumptions, and discover best practices beyond model knowledge.

## How It Works

The flag triggers a research → triangulation → quality assessment workflow:

1. **Topics extracted** from user input and spec context (e.g., "NetworkX vs igraph", "authentication best practices")
2. **WebSearch queries** run with cached results (30-day TTL)
3. **Source triangulation** validates findings across multiple independent sources
4. **Confidence scoring** combines source quality, recency, and consensus
5. **Tier assessment** filters results to Tier 1 (official) and Tier 2 (reputable) sources only

## Source Tier Definitions

Research results are categorized by source authority:

### Tier 1 (Official) — High-authority primary sources
- GitHub repositories and discussions
- Official documentation (python.org, docs.djangoproject.com, etc.)
- Academic papers and technical standards
- Official blog posts from project maintainers
- RFCs and published specifications

### Tier 2 (Reputable) — Established technical media
- Real Python, CSS-Tricks, Dev.to (verified technical blogs)
- O'Reilly and published technical articles
- Medium posts from recognized experts
- Official conference talks and recorded sessions
- Technical journals and established industry publications

### Tier 3 (Community) — Community-driven sources
**Note: Excluded from research output**
- Stack Overflow answers and discussions
- Reddit threads and comments
- Forum discussions
- Unverified user blogs

Tier 3 sources are collected but not included in the Research Findings section to maintain quality.

## Research Extraction

Topics are automatically extracted from:
- User input keywords (e.g., "should we use X or Y?")
- Spec context and clarification notes
- Decision points and trade-offs being explored

Focus areas are also identified (e.g., "performance", "security", "ease of use", "community support") to guide source collection.

## WebSearch with Caching

The research API calls WebSearch with cached results:

- **Cache key**: Normalized topic query
- **Cache TTL**: 30 days
- **Max sources per query**: 10 (configurable)
- **Duplicate removal**: URLs already collected are skipped to avoid redundancy

## Source Triangulation

Triangulation validates findings across multiple independent sources:

- **Minimum threshold**: 3 independent sources recommended
- **Score calculation**: `min(source_count / 3, 1.0)`
  - 1-2 sources: triangulation score < 0.5 (low confidence)
  - 3-5 sources: triangulation score 0.5-0.9 (medium confidence)
  - 6+ sources: triangulation score 1.0 (high confidence)

- **Independence check**: Sources from different domains (e.g., docs.python.org + realpython.com + github.com discussion) count as independent; multiple articles from the same blog count as one source for triangulation

## Confidence Scoring

Final confidence score (0-1 scale) combines:
- **Source quality**: Tier 1 sources weighted 100%, Tier 2 sources weighted 70%
- **Recency**: Articles updated in last 12 months receive full weight; older articles penalized
- **Consensus**: Agreement across sources increases confidence; conflicting advice lowers it

### Sample scoring:
- 3 Tier 1 sources (recent, agreeing): confidence 0.90+ (High)
- 2 Tier 1 + 2 Tier 2 sources (mixed): confidence 0.70-0.80 (Medium-High)
- 1 Tier 1 + 3 Tier 2 sources (conflicting): confidence 0.50-0.65 (Medium)
- 1 Tier 1 source only: confidence < 0.50 (Low)

## When to Use Research vs Model Knowledge

### Use `--research` when:
- **New/emerging technologies** (frameworks <2 years old, recent standards)
- **Comparison questions** (library A vs B, approach X vs Y)
- **Best practices** you want validated across current sources
- **Breaking changes** in popular libraries (versions that changed significantly)
- **Niche domains** where your knowledge may be outdated

### Do NOT use research when:
- **Fundamental computer science** (algorithms, data structures, complexity theory)
- **Core language features** (Python basics, standard library well-known functions)
- **Project-specific patterns** already documented in CONSTITUTION.md
- **Time-sensitive answers are not required** (e.g., "what's the best pattern for X" where your training data is sufficient)

Research adds 2-5 minutes to think mode execution. Use it strategically for questions where web sources provide real value.

## Research Output Format

When `--research` flag is present, the "Research Findings" section is appended to spec.md:

```markdown
## Research Findings

**Topic:** NetworkX vs igraph for graph analysis
**Confidence:** 0.85 (High) | **Triangulation:** 1.0 (6+ sources)

**Sources:**
- [NetworkX vs igraph benchmark](https://github.com/networkx/networkx/discussions/5234) (Tier 1: GitHub)
- [Python graph library comparison](https://realpython.com/python-graph-libraries/) (Tier 2: Blog)
- [NetworkX performance guide](https://networkx.org/documentation/stable/reference/algorithms/performance.html) (Tier 1: Docs)
- [igraph Python documentation](https://igraph.org/python/) (Tier 1: Docs)
- [Graph library benchmarks](https://medium.com/@user/graph-benchmarks) (Tier 2: Article)
- [Community discussion on NetworkX scalability](https://github.com/networkx/networkx/issues/5234) (Tier 1: GitHub)

**Summary:**
NetworkX is more Pythonic and easier to use with better documentation, but igraph is 2-10x faster for large graphs (>10k nodes). NetworkX has better community support; igraph requires C dependencies but offers parallel processing. For prototype/analysis work, NetworkX is recommended; for production pipelines with large graphs (>100k nodes), igraph is preferred.
```

### Output fields:
- **Topic** — The research question being explored
- **Confidence** — Score (0-1) with label: Low (<0.5), Medium (0.5-0.75), High (>0.75)
- **Triangulation** — Source count and score: low (<3 sources), medium (3-5), high (6+)
- **Sources** — List of top sources with tier labels
- **Summary** — 3-5 sentence conclusion with actionable guidance

## Caching and Performance

Research results are cached to improve performance:

- **Cache location**: advisory SQLite `research_cache` table for API/dashboard research, plus the local file-backed cache managed by `py interfaces/cli/research_cache.py`
- **Authority**: research cache entries are advisory/local-only by default, not canonical truth or redacted exports
- **Cache duration**: 30 days (reset on request)
- **Cache hits**: Identical queries within 30 days return cached results immediately
- **Cache misses**: New queries trigger fresh WebSearch and are stored for future use

### Clear cache for a topic:
```python
from control.research.web import invalidate_cache
invalidate_cache("NetworkX vs igraph")  # Clears single topic
invalidate_cache()  # Clears all research cache
```

### Check cache status:
```python
from control.research.tools import get_cache_stats
stats = get_cache_stats()
print(f"Cached topics: {stats['total_topics']}")
print(f"Cache size: {stats['size_mb']} MB")
```

## Example Research Workflow

1. **User input**: `think: --research Should we use Celery or RQ for task queuing?`
2. **System extracts**: Topics: ["Celery vs RQ", "task queue comparison"], Focus areas: ["performance", "scalability", "ease of use"]
3. **WebSearch runs**: Collects articles, docs, GitHub discussions (checks 30-day cache first)
4. **Triangulation**: 5 sources found (2 Tier 1, 3 Tier 2), triangulation score 0.83
5. **Confidence**: 0.78 (Medium-High) — consistent advice across sources, recent articles, minor conflicts on scalability
6. **Output appended** to spec.md with research findings section
7. **Director decision**: "Thanks — use Celery; this confirms our architecture choice"

## Troubleshooting

### Research returns too few sources
- **Check**: Is the topic too niche or too new? Try broader keywords (e.g., "async task queue" instead of "my-specific-library")
- **Check**: Are you asking about a tool <1 year old? Limited web coverage is expected
- **Fix**: Combine with `--recommend-tools` to surface tools, or proceed with caution + note uncertainty in spec

### Confidence score is unexpectedly low
- **Check**: Are sources conflicting? (e.g., some recommend approach A, others recommend B)
- **Check**: Are most sources Tier 2 or older than 12 months?
- **Fix**: Add more Tier 1 sources by rephrasing query (e.g., search official docs directly)
- **Action**: Flag confidence < 0.5 to Director: "Research confidence is LOW — consider collecting more sources or proceeding with caution"

### Cached results feel stale
- **Check**: Is the topic fast-moving (e.g., new major library release)?
- **Fix**: Clear cache and re-run: `invalidate_cache("topic-name")`
- **Best practice**: For topics that change frequently, clear cache before research phase
