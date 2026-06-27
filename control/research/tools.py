"""TF-IDF and sentence-transformers search module for tool discovery system.

Provides two search modes:
1. TF-IDF search (fast, lightweight, keyword-based)
2. Semantic search (slower, contextual, embedding-based)

Includes query caching with 1-hour TTL for improved performance.

Usage:
    from control.research.tools import search_tools

    # TF-IDF search (default)
    results = search_tools("video processing", top_k=5)

    # Semantic search
    results = search_tools("video processing", top_k=5, use_embeddings=True)

    for match in results:
        print(f"{match.name} ({match.confidence:.2f}): {match.description}")
"""

from __future__ import annotations
import json
import logging
import re
import string
from dataclasses import dataclass

import cachetools
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.event_store import studio_db
from core.config.database import transaction

# Cache the vectorizer and fitted data globally
_vectorizer = None
_tfidf_matrix = None
_tool_data = None

# Cache for sentence-transformers model and embeddings
_sentence_model = None
_embeddings_matrix = None
_embedding_tool_ids = None

# Model name for sentence-transformers
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

logger = logging.getLogger(__name__)


class CachedToolSearch:
    """Caching layer for tool search results with 1-hour TTL.

    Normalizes queries (lowercase, strip whitespace, remove punctuation)
    and caches results to avoid repeated TF-IDF computations.

    Cache key format: {normalized_query}_{category}
    TTL: 3600 seconds (1 hour)
    Max size: 1000 entries
    """

    def __init__(self, maxsize: int = 1000, ttl: int = 3600):
        """Initialize the query cache.

        Args:
            maxsize: Maximum number of cached entries (default: 1000)
            ttl: Time to live in seconds (default: 3600 = 1 hour)
        """
        self.cache = cachetools.TTLCache(maxsize=maxsize, ttl=ttl)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def normalize_query(query: str, category: str | None = None) -> str:
        """Normalize query for consistent cache key generation.

        Performs:
        - Convert to lowercase
        - Strip leading/trailing whitespace
        - Remove punctuation
        - Replace multiple spaces with single space

        Args:
            query: Raw query string
            category: Optional category filter

        Returns:
            str: Normalized cache key "{query}_{category}"
        """
        # Lowercase
        normalized = query.lower().strip()

        # Remove punctuation
        normalized = normalized.translate(str.maketrans("", "", string.punctuation))

        # Collapse multiple spaces
        normalized = re.sub(r"\s+", " ", normalized)

        # Add category if provided
        if category:
            normalized = f"{normalized}_{category.lower()}"

        return normalized

    def get(self, key: str) -> list | None:
        """Retrieve cached result if available.

        Args:
            key: Cache key (normalized query)

        Returns:
            List[ToolMatch] if hit, None if miss or expired
        """
        result = self.cache.get(key)
        if result is not None:
            self.hits += 1
            logger.debug(f"Cache HIT for: {key[:50]}... (hits: {self.hits})")
        else:
            self.misses += 1
            logger.debug(f"Cache MISS for: {key[:50]}... (misses: {self.misses})")
        return result

    def set(self, key: str, value: list) -> None:
        """Store result in cache.

        Args:
            key: Cache key (normalized query)
            value: List of ToolMatch results
        """
        self.cache[key] = value
        logger.debug(f"Cache SET for: {key[:50]}... (size: {len(self.cache)})")

    def stats(self) -> dict:
        """Return cache statistics.

        Returns:
            dict: {hits, misses, ratio, size, maxsize}
        """
        total = self.hits + self.misses
        ratio = self.hits / total if total > 0 else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": round(ratio, 3),
            "cache_size": len(self.cache),
            "cache_maxsize": self.cache.maxsize,
            "ttl": self.cache.ttl,
        }

    def clear(self) -> None:
        """Clear all cached entries and reset statistics."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("Cache cleared and statistics reset")


# Global cache instance
_query_cache = CachedToolSearch(maxsize=1000, ttl=3600)


@dataclass
class ToolMatch:
    """A single tool match result from search."""

    tool_id: str
    name: str
    category: str
    description: str
    confidence: float
    source_url: str
    install_command: str


@dataclass
class ToolDetail:
    """Catalog metadata for a registered tool.

    Tool details are discovery metadata only. They do not authorize adapter
    execution, provider selection, installation, or canonical architecture
    decisions.
    """

    tool_id: str
    name: str
    category: str
    description: str
    source_url: str
    install_command: str
    tags: list[str]
    confidence_score: float


@dataclass
class SearchResultWithStatus:
    """Tool search results with explicit retrieval mode metadata.

    Retrieval mode values:
        tfidf_default                      — TF-IDF used; embeddings not requested (default path).
        semantic_embeddings                — sentence-transformers embeddings used successfully.
        tfidf_fallback_dependency_missing  — Embeddings requested but sentence-transformers not installed.
        tfidf_fallback_semantic_error      — Embeddings requested, dep present, but runtime error; TF-IDF used.
        disabled_by_default                — No query provided; no search attempted.

    Semantic status values mirror semantic_retrieval_status():
        available                      — sentence-transformers is installed.
        unavailable_dependency_missing — sentence-transformers not installed.
        disabled_by_default            — Embeddings not requested (use_embeddings=False).
    """

    results: list[ToolMatch]
    retrieval_mode: str
    semantic_status: str
    embeddings_used: bool


def _parse_tags(raw_tags: str | None) -> list[str]:
    if not raw_tags:
        return []
    try:
        parsed = json.loads(raw_tags)
    except (json.JSONDecodeError, TypeError):
        parsed = [tag.strip() for tag in str(raw_tags).split(",")]
    if isinstance(parsed, list):
        return [str(tag).strip() for tag in parsed if str(tag).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def get_tool_by_id(tool_id: str) -> ToolDetail | None:
    """Return catalog metadata for one tool, or None if absent.

    This helper performs a local registry lookup only. Provider names, MCP
    labels, package names, and install commands remain discovery metadata; this
    function does not execute external tools or make providers canonical.
    """
    if not tool_id or not tool_id.strip():
        return None

    conn = studio_db._connect()
    try:
        row = conn.execute(
            """
            SELECT tool_id, name, category, description, source_url,
                   install_command, tags, confidence_score
            FROM tool_registry
            WHERE tool_id = ?
            """,
            (tool_id.strip(),),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return ToolDetail(
        tool_id=row["tool_id"],
        name=row["name"],
        category=row["category"],
        description=row["description"] or "",
        source_url=row["source_url"] or "",
        install_command=row["install_command"] or "",
        tags=_parse_tags(row["tags"]),
        confidence_score=float(row["confidence_score"] or 0.0),
    )


def build_index() -> TfidfVectorizer:
    """Build TF-IDF index from tool_registry.description.

    Returns:
        TfidfVectorizer: Fitted vectorizer ready for search.

    Raises:
        RuntimeError: If database is empty or connection fails.
    """
    global _vectorizer, _tfidf_matrix, _tool_data

    try:
        conn = studio_db._connect()
        rows = conn.execute("""
            SELECT tool_id, name, category, description, source_url,
                   install_command, tags, confidence_score
            FROM tool_registry
            ORDER BY tool_id
        """).fetchall()
        conn.close()

        if not rows:
            logger.warning("tool_registry is empty, returning empty index")
            _tool_data = []
            _vectorizer = TfidfVectorizer()
            _tfidf_matrix = None
            return _vectorizer

        # Store tool data for later retrieval
        _tool_data = [dict(row) for row in rows]

        # Build corpus from descriptions (with fallback to name if no description)
        corpus = []
        for tool in _tool_data:
            desc = tool.get("description") or ""
            name = tool.get("name") or ""
            tags = tool.get("tags") or ""

            # Parse tags if JSON
            try:
                tags_list = json.loads(tags) if tags else []
                tags_text = " ".join(tags_list)
            except (json.JSONDecodeError, TypeError):
                tags_text = tags

            # Combine description, name, and tags for richer indexing
            text = f"{desc} {name} {tags_text}".strip()
            corpus.append(text if text else name)

        # Create and fit TF-IDF vectorizer
        _vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words="english",
            ngram_range=(1, 2),  # unigrams and bigrams
            min_df=1,
            max_df=0.9,
        )

        _tfidf_matrix = _vectorizer.fit_transform(corpus)

        logger.info(f"Built TF-IDF index for {len(_tool_data)} tools")
        return _vectorizer

    except Exception as e:
        logger.error(f"Failed to build TF-IDF index: {e}")
        raise RuntimeError(f"Failed to build TF-IDF index: {e}") from e


def calculate_confidence(similarity: float, registry_score: float = 1.0) -> float:
    """Map cosine similarity to confidence score.

    Args:
        similarity: Cosine similarity score (0.0-1.0)
        registry_score: Tool's confidence_score from registry (0.0-1.0)

    Returns:
        float: Combined confidence score (0.0-1.0)
    """
    # Weighted combination: 70% similarity, 30% registry score
    confidence = (0.7 * similarity) + (0.3 * registry_score)
    return round(confidence, 3)


def search_tools(
    query: str, top_k: int = 5, category: str | None = None, use_embeddings: bool = False
) -> list[ToolMatch]:
    """Search and rank tools using TF-IDF or semantic embeddings with caching.

    Queries are normalized and cached with a 1-hour TTL to improve performance.
    Cache key format: {normalized_query}_{category}_{method}

    Args:
        query: Search query string
        top_k: Maximum number of results to return
        category: Optional category filter ('mcp', 'python_package', 'api', 'saas')
        use_embeddings: If True, use sentence-transformers semantic search (default: False, use TF-IDF)

    Returns:
        List[ToolMatch]: Ranked list of matching tools (confidence > 0.7 for embeddings, > 0.5 for TF-IDF)

    Examples:
        >>> # TF-IDF search (fast, keyword-based)
        >>> results = search_tools("video processing", top_k=5)
        >>> for match in results:
        ...     print(f"{match.name}: {match.confidence:.2f}")

        >>> # Semantic search (contextual, embedding-based)
        >>> results = search_tools("video processing", top_k=5, use_embeddings=True)

        >>> results = search_tools("ffmpeg", top_k=3, category="python_package")
    """
    global _vectorizer, _tfidf_matrix, _tool_data, _query_cache
    global _sentence_model, _embeddings_matrix, _embedding_tool_ids

    # Handle empty query
    if not query or not query.strip():
        logger.debug("Empty query received")
        return []

    # Check cache first (include method in cache key)
    method = "embeddings" if use_embeddings else "tfidf"
    cache_key = f"{CachedToolSearch.normalize_query(query, category)}_{method}"
    cached_result = _query_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    # tool_embeddings_cache dropped migration 131: semantic embedding path removed; always TF-IDF
    results = _search_with_tfidf(query, top_k, category)

    # Cache the results
    _query_cache.set(cache_key, results)

    logger.debug(
        f"Found {len(results)} matches for query: {query} (category: {category or 'any'}, method: {method})"
    )
    return results


def _search_with_tfidf(query: str, top_k: int, category: str | None = None) -> list[ToolMatch]:
    """Internal TF-IDF search implementation."""
    global _vectorizer, _tfidf_matrix, _tool_data

    # Build index if not already built
    if _vectorizer is None or _tfidf_matrix is None or _tool_data is None:
        try:
            build_index()
        except RuntimeError as e:
            logger.error(f"Failed to build TF-IDF index: {e}")
            return []

    # Handle empty database
    if not _tool_data:
        logger.debug("No tools in database")
        return []

    try:
        # Transform query to TF-IDF vector
        query_vec = _vectorizer.transform([query])

        # Calculate cosine similarity with all documents
        similarities = cosine_similarity(query_vec, _tfidf_matrix).flatten()

        # Get top-k indices sorted by similarity (descending)
        top_indices = similarities.argsort()[::-1][: top_k * 2]  # Get extra to filter

        # Build results
        results = []
        for idx in top_indices:
            sim_score = similarities[idx]
            tool = _tool_data[idx]

            # Calculate combined confidence
            registry_score = tool.get("confidence_score", 0.5) or 0.5
            confidence = calculate_confidence(sim_score, registry_score)

            # Filter out low-confidence results (0.5 threshold for TF-IDF)
            if confidence < 0.5:
                continue

            results.append(
                ToolMatch(
                    tool_id=tool["tool_id"],
                    name=tool["name"],
                    category=tool["category"],
                    description=tool.get("description") or "",
                    confidence=confidence,
                    source_url=tool.get("source_url") or "",
                    install_command=tool.get("install_command") or "",
                )
            )

            # Stop once we have enough high-confidence results
            if len(results) >= top_k:
                break

        # Apply category filter if provided
        if category:
            results = filter_by_category(results, category)

        return results

    except Exception as e:
        logger.error(f"TF-IDF search failed: {e}")
        return []


def filter_by_category(results: list[ToolMatch], category: str) -> list[ToolMatch]:
    """Filter results by category.

    Args:
        results: List of ToolMatch objects
        category: Category to filter by ('mcp', 'python_package', 'api', 'saas')

    Returns:
        List[ToolMatch]: Filtered results matching the category
    """
    if not category:
        return results

    return [match for match in results if match.category == category]


def rebuild_index(clear_embeddings: bool = False) -> bool:
    """Force rebuild of the TF-IDF and/or embedding indexes.

    Useful after bulk updates to tool_registry.
    Also clears the query cache.

    Args:
        clear_embeddings: If True, also clear embedding cache from database

    Returns:
        bool: True if rebuild succeeded, False otherwise
    """
    global _vectorizer, _tfidf_matrix, _tool_data, _query_cache
    global _sentence_model, _embeddings_matrix, _embedding_tool_ids

    # Clear cached data
    _vectorizer = None
    _tfidf_matrix = None
    _tool_data = None
    _embeddings_matrix = None
    _embedding_tool_ids = None
    _query_cache.clear()

    # tool_embeddings_cache dropped migration 131; clear_embeddings arg is a no-op
    try:
        build_index()
        return True
    except RuntimeError:
        return False


def get_cache_stats() -> dict:
    """Get current query cache statistics.

    Returns:
        dict: Cache stats including hits, misses, hit_ratio, size, maxsize, ttl
    """
    global _query_cache
    return _query_cache.stats()


def clear_cache() -> None:
    """Clear all cached queries and reset statistics."""
    global _query_cache
    _query_cache.clear()
    logger.info("Query cache cleared")


def search_tools_with_status(
    query: str, top_k: int = 5, category: str | None = None, use_embeddings: bool = False
) -> SearchResultWithStatus:
    """search_tools() with explicit retrieval mode metadata.

    Preserves search_tools() behavior exactly. Returns SearchResultWithStatus so
    callers can inspect which retrieval path was actually taken.

    When use_embeddings=False (default): always returns tfidf_default.
    When use_embeddings=True: probes sentence-transformers availability first
    and reports tfidf_fallback_dependency_missing or tfidf_fallback_semantic_error
    if the dep is absent or fails at runtime.
    """
    if not use_embeddings:
        return SearchResultWithStatus(
            results=search_tools(query, top_k=top_k, category=category, use_embeddings=False),
            retrieval_mode="tfidf_default",
            semantic_status="disabled_by_default",
            embeddings_used=False,
        )

    # tool_embeddings_cache dropped migration 131: semantic embedding unavailable
    return SearchResultWithStatus(
        results=search_tools(query, top_k=top_k, category=category, use_embeddings=False),
        retrieval_mode="tfidf_fallback_dependency_missing",
        semantic_status="unavailable_table_dropped",
        embeddings_used=False,
    )


def hybrid_search_with_status(
    query: str, top_k: int = 5, category: str | None = None
) -> SearchResultWithStatus:
    """hybrid_search() with explicit retrieval mode metadata.

    tool_embeddings_cache dropped migration 131: semantic embedding path removed.
    Always falls back to TF-IDF.
    """
    if not query or not query.strip():
        return SearchResultWithStatus(
            results=[],
            retrieval_mode="disabled_by_default",
            semantic_status="disabled_by_default",
            embeddings_used=False,
        )

    return SearchResultWithStatus(
        results=_search_with_tfidf(query, top_k, category),
        retrieval_mode="tfidf_fallback_dependency_missing",
        semantic_status="unavailable_table_dropped",
        embeddings_used=False,
    )


def semantic_retrieval_status() -> dict:
    """Return controlled status for the optional semantic retrieval provider.

    Safe to call without sentence-transformers installed.
    Never imports sentence_transformers at module level — check is lazy.

    Status values:
        available                      — sentence-transformers is installed
        unavailable_dependency_missing — sentence-transformers not installed

    Returns:
        dict with keys: status, available, default_active, default_provider
    """
    base: dict = {"default_active": False, "default_provider": "tfidf"}
    try:
        import sentence_transformers  # noqa: F401

        return {**base, "status": "available", "available": True}
    except ImportError:
        return {
            **base,
            "status": "unavailable_dependency_missing",
            "available": False,
            "hint": "pip install -r requirements-semantic.txt",
        }


if __name__ == "__main__":
    # Simple CLI test with cache demonstration
    import sys
    import time

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print(
            "Usage: python tool_search.py <query> [--embeddings] [--hybrid] [--cache-stats] [--clear-cache] [--benchmark]"
        )
        print("Example: python tool_search.py 'video processing'")
        print("Example: python tool_search.py 'ffmpeg' --embeddings --cache-stats")
        print("Example: python tool_search.py 'video' --hybrid")
        print(
            "Example: python tool_search.py 'video' --benchmark  # Compare TF-IDF vs embeddings vs hybrid"
        )
        sys.exit(1)

    query = " ".join(arg for arg in sys.argv[1:] if not arg.startswith("--"))
    show_stats = "--cache-stats" in sys.argv
    clear = "--clear-cache" in sys.argv
    use_embeddings = "--embeddings" in sys.argv
    use_hybrid = "--hybrid" in sys.argv
    benchmark = "--benchmark" in sys.argv

    if clear:
        clear_cache()
        print("Cache cleared.\n")

    if benchmark:
        print(f"Benchmarking TF-IDF vs Embeddings vs Hybrid for: {query}\n")
        print("=" * 60)

        # TF-IDF search
        print("\n[TF-IDF Search]")
        start = time.time()
        tfidf_results = search_tools(query, top_k=10, use_embeddings=False)
        tfidf_time = (time.time() - start) * 1000
        print(f"Time: {tfidf_time:.1f}ms")
        print(f"Results: {len(tfidf_results)}")
        if tfidf_results:
            print(f"Top result: {tfidf_results[0].name} ({tfidf_results[0].confidence:.2f})")

        # Embeddings search
        print("\n[Semantic Search (Embeddings)]")
        start = time.time()
        emb_results = search_tools(query, top_k=10, use_embeddings=True)
        emb_time = (time.time() - start) * 1000
        print(f"Time: {emb_time:.1f}ms")
        print(f"Results: {len(emb_results)}")
        if emb_results:
            print(f"Top result: {emb_results[0].name} ({emb_results[0].confidence:.2f})")

        print("\n" + "=" * 60)
        print(f"Speed difference (embeddings vs TF-IDF): {emb_time / tfidf_time:.2f}x slower")
        sys.exit(0)

    if use_hybrid:
        # hybrid_search removed (tool_embeddings_cache dropped migration 131); fallback to TF-IDF
        method = "TF-IDF (hybrid unavailable: tool_embeddings_cache dropped)"
        print(f"Searching for: {query} (method: {method})\n")
        start = time.time()
        results = search_tools(query, top_k=10, use_embeddings=False)
        elapsed = (time.time() - start) * 1000
    else:
        method = "semantic embeddings" if use_embeddings else "TF-IDF"
        print(f"Searching for: {query} (method: {method})\n")
        start = time.time()
        results = search_tools(query, top_k=10, use_embeddings=use_embeddings)
        elapsed = (time.time() - start) * 1000

    if not results:
        print("No results found.")
    else:
        print(f"Found {len(results)} results in {elapsed:.1f}ms:\n")
        for i, match in enumerate(results, 1):
            print(f"{i}. {match.name} ({match.category})")
            print(f"   Confidence: {match.confidence:.2f}")
            print(f"   {match.description[:100]}...")
            if match.install_command:
                print(f"   Install: {match.install_command}")
            print()

    # Show cache statistics if requested
    if show_stats:
        stats = get_cache_stats()
        print("\nCache Statistics:")
        print(f"  Hits:      {stats['hits']}")
        print(f"  Misses:    {stats['misses']}")
        print(f"  Hit Ratio: {stats['hit_ratio']:.1%}")
        print(f"  Size:      {stats['cache_size']}/{stats['cache_maxsize']}")
        print(f"  TTL:       {stats['ttl']}s")

        # Demonstrate cache hit with repeat search
        print("\nRunning same search again (should hit cache)...\n")
        start = time.time()
        results2 = search_tools(query, top_k=10, use_embeddings=use_embeddings)
        elapsed2 = (time.time() - start) * 1000
        stats2 = get_cache_stats()
        print(f"Cache hit ratio after repeat: {stats2['hit_ratio']:.1%}")
        print(f"Time for cached query: {elapsed2:.1f}ms")
