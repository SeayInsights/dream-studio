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
import io
import json
import logging
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import cachetools
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.event_store import studio_db
from core.config.database import transaction, get_connection

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
    def normalize_query(query: str, category: Optional[str] = None) -> str:
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

    def get(self, key: str) -> Optional[List]:
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

    def set(self, key: str, value: List) -> None:
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


def build_embedding_index() -> "SentenceTransformer":
    """Build sentence-transformers embedding index with SQLite caching.

    Uses all-MiniLM-L6-v2 model (lightweight, 384-dim vectors).
    Embeds tool descriptions and caches to SQLite as BLOB to avoid re-embedding.

    Performance:
        - First run: ~10-15s (model download + embedding all tools)
        - Subsequent runs: ~50-100ms (load cached embeddings from SQLite)
        - Search: <20ms per query (after model loaded)

    Returns:
        SentenceTransformer: Loaded model ready for encoding queries.

    Raises:
        RuntimeError: If database is empty or connection fails.
        ImportError: If sentence-transformers is not installed.
    """
    global _sentence_model, _embeddings_matrix, _embedding_tool_ids, _tool_data

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed. Run: pip install sentence-transformers"
        )

    try:
        # Load model (cached by HuggingFace)
        if _sentence_model is None:
            logger.info(f"Loading sentence-transformers model: {EMBEDDING_MODEL}")
            _sentence_model = SentenceTransformer(EMBEDDING_MODEL)

        # Load tool data if not already loaded
        if _tool_data is None:
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
                _embeddings_matrix = None
                _embedding_tool_ids = []
                return _sentence_model

            _tool_data = [dict(row) for row in rows]

        # Check if embeddings are cached in database
        conn = studio_db._connect()
        cached = conn.execute(
            """
            SELECT tool_id, embedding
            FROM tool_embeddings_cache
            WHERE model_name = ?
            ORDER BY tool_id
        """,
            (EMBEDDING_MODEL,),
        ).fetchall()

        cached_dict = {row["tool_id"]: row["embedding"] for row in cached}

        # Determine which tools need embedding
        tools_to_embed = []
        embeddings_list = []
        tool_ids = []

        for tool in _tool_data:
            tool_id = tool["tool_id"]
            tool_ids.append(tool_id)

            if tool_id in cached_dict:
                # Load from cache
                embedding_bytes = cached_dict[tool_id]
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                embeddings_list.append(embedding)
            else:
                # Mark for embedding
                tools_to_embed.append(tool)

        # Embed any new tools
        if tools_to_embed:
            logger.info(f"Embedding {len(tools_to_embed)} new tools...")

            # Build corpus
            corpus = []
            for tool in tools_to_embed:
                desc = tool.get("description") or ""
                name = tool.get("name") or ""
                tags = tool.get("tags") or ""

                # Parse tags if JSON
                try:
                    tags_list = json.loads(tags) if tags else []
                    tags_text = " ".join(tags_list)
                except (json.JSONDecodeError, TypeError):
                    tags_text = tags

                # Combine description, name, and tags
                text = f"{desc} {name} {tags_text}".strip()
                corpus.append(text if text else name)

            # Encode
            new_embeddings = _sentence_model.encode(corpus, show_progress_bar=False)

            # Save to the same registry database that supplied the tools.
            for tool, embedding in zip(tools_to_embed, new_embeddings):
                tool_id = tool["tool_id"]

                # Serialize embedding as bytes
                embedding_bytes = embedding.astype(np.float32).tobytes()

                # Insert into cache
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tool_embeddings_cache
                    (tool_id, embedding, model_name)
                    VALUES (?, ?, ?)
                """,
                    (tool_id, embedding_bytes, EMBEDDING_MODEL),
                )

                # Find position in tool_ids and insert
                idx = tool_ids.index(tool_id)
                embeddings_list.insert(idx, embedding)
            conn.commit()

            logger.info(f"Cached {len(tools_to_embed)} new embeddings to database")

        conn.close()

        # Convert to numpy matrix for fast similarity search
        _embeddings_matrix = np.array(embeddings_list)
        _embedding_tool_ids = tool_ids

        logger.info(f"Built embedding index for {len(tool_ids)} tools")
        return _sentence_model

    except Exception as e:
        logger.error(f"Failed to build embedding index: {e}")
        raise RuntimeError(f"Failed to build embedding index: {e}") from e


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
    query: str, top_k: int = 5, category: Optional[str] = None, use_embeddings: bool = False
) -> List[ToolMatch]:
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

    # Route to appropriate search method
    if use_embeddings:
        results = _search_with_embeddings(query, top_k, category)
    else:
        results = _search_with_tfidf(query, top_k, category)

    # Cache the results
    _query_cache.set(cache_key, results)

    logger.debug(
        f"Found {len(results)} matches for query: {query} (category: {category or 'any'}, method: {method})"
    )
    return results


def _search_with_tfidf(query: str, top_k: int, category: Optional[str] = None) -> List[ToolMatch]:
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


def _search_with_embeddings(
    query: str, top_k: int, category: Optional[str] = None
) -> List[ToolMatch]:
    """Internal semantic search implementation using sentence-transformers."""
    global _sentence_model, _embeddings_matrix, _embedding_tool_ids, _tool_data

    try:
        # Build embedding index if not already built
        if _sentence_model is None or _embeddings_matrix is None:
            try:
                build_embedding_index()
            except (RuntimeError, ImportError) as e:
                logger.warning(f"Failed to build embedding index, falling back to TF-IDF: {e}")
                return _search_with_tfidf(query, top_k, category)

        # Handle empty database
        if _embeddings_matrix is None or len(_embeddings_matrix) == 0:
            logger.debug("No embeddings in database")
            return []

        # Encode query
        query_embedding = _sentence_model.encode([query], show_progress_bar=False)[0]

        # Calculate cosine similarity
        # Normalize vectors for cosine similarity
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        embeddings_norm = _embeddings_matrix / np.linalg.norm(
            _embeddings_matrix, axis=1, keepdims=True
        )

        similarities = np.dot(embeddings_norm, query_norm)

        # Get top-k indices sorted by similarity (descending)
        top_indices = similarities.argsort()[::-1][: top_k * 2]  # Get extra to filter

        # Build results
        results = []
        for idx in top_indices:
            sim_score = float(similarities[idx])
            tool_id = _embedding_tool_ids[idx]

            # Find tool data
            tool = next((t for t in _tool_data if t["tool_id"] == tool_id), None)
            if not tool:
                continue

            # Calculate combined confidence
            registry_score = tool.get("confidence_score", 0.5) or 0.5
            confidence = calculate_confidence(sim_score, registry_score)

            # Filter out low-confidence results (lower threshold than TF-IDF)
            # Semantic similarity scores tend to be lower, so we use a more lenient cutoff
            if confidence < 0.4:
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
        logger.error(f"Embedding search failed, falling back to TF-IDF: {e}")
        return _search_with_tfidf(query, top_k, category)


def hybrid_search(query: str, top_k: int = 5, category: Optional[str] = None) -> List[ToolMatch]:
    """Search and rank tools using hybrid scoring (TF-IDF + embeddings).

    Combines both TF-IDF (keyword-based) and semantic embedding scores using a
    weighted average: hybrid_score = 0.5 * tfidf_score + 0.5 * embedding_score.

    This approach leverages the strengths of both methods:
    - TF-IDF: Excellent for exact keyword matches (e.g., "ffmpeg", "video")
    - Embeddings: Excellent for semantic understanding (e.g., "I need to process videos" → ffmpeg)
    - Hybrid: Best of both worlds, more robust and comprehensive results

    Results are cached with a 1-hour TTL. Cache key format: {normalized_query}_{category}_hybrid

    Args:
        query: Search query string
        top_k: Maximum number of results to return (default: 5)
        category: Optional category filter ('mcp', 'python_package', 'api', 'saas')

    Returns:
        List[ToolMatch]: Top-k results ranked by hybrid score (weighted average of TF-IDF and embedding confidence)

    Examples:
        >>> # Hybrid search combining keyword and semantic matching
        >>> results = hybrid_search("video processing", top_k=5)
        >>> for match in results:
        ...     print(f"{match.name}: {match.confidence:.2f}")

        >>> # With category filter
        >>> results = hybrid_search("ffmpeg", top_k=3, category="python_package")
    """
    global _vectorizer, _tfidf_matrix, _tool_data, _query_cache
    global _sentence_model, _embeddings_matrix, _embedding_tool_ids

    # Handle empty query
    if not query or not query.strip():
        logger.debug("Empty query received for hybrid search")
        return []

    # Check cache first (include 'hybrid' in cache key)
    cache_key = f"{CachedToolSearch.normalize_query(query, category)}_hybrid"
    cached_result = _query_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    try:
        # Get results from both search methods (fetch extra to have good pool for merging)
        tfidf_results = _search_with_tfidf(
            query, top_k * 2, category=None
        )  # No category filter yet
        embedding_results = _search_with_embeddings(
            query, top_k * 2, category=None
        )  # No category filter yet

        # Build a map of tool_id -> ToolMatch with hybrid score
        hybrid_scores = {}

        # Process TF-IDF results
        for match in tfidf_results:
            if match.tool_id not in hybrid_scores:
                hybrid_scores[match.tool_id] = {
                    "match": match,
                    "tfidf_score": match.confidence,
                    "embedding_score": None,
                }
            else:
                hybrid_scores[match.tool_id]["tfidf_score"] = match.confidence

        # Process embedding results
        for match in embedding_results:
            if match.tool_id not in hybrid_scores:
                hybrid_scores[match.tool_id] = {
                    "match": match,
                    "tfidf_score": None,
                    "embedding_score": match.confidence,
                }
            else:
                hybrid_scores[match.tool_id]["embedding_score"] = match.confidence

        # Calculate hybrid scores (weighted average of both methods)
        # Tools that appear in both searches get full hybrid scoring
        # Tools in only one search use the available score with an implicit penalty
        results_with_scores = []
        for tool_id, score_data in hybrid_scores.items():
            tfidf_score = score_data["tfidf_score"] or 0.0
            embedding_score = score_data["embedding_score"] or 0.0

            # Weighted average: 0.5 * TF-IDF + 0.5 * Embeddings
            hybrid_score = (0.5 * tfidf_score) + (0.5 * embedding_score)

            # Update the match's confidence to reflect hybrid score
            match = score_data["match"]
            match.confidence = round(hybrid_score, 3)

            results_with_scores.append(match)

        # Sort by hybrid score (descending)
        results_with_scores.sort(key=lambda m: m.confidence, reverse=True)

        # Apply category filter if provided
        if category:
            results_with_scores = filter_by_category(results_with_scores, category)

        # Take top-k and filter by minimum confidence (0.3 for hybrid, lenient since both methods contribute)
        results = [m for m in results_with_scores if m.confidence >= 0.3][:top_k]

        # Cache the results
        _query_cache.set(cache_key, results)

        logger.debug(
            f"Hybrid search found {len(results)} matches for query: {query} (category: {category or 'any'})"
        )
        return results

    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        # Fall back to TF-IDF on error
        return _search_with_tfidf(query, top_k, category)


def filter_by_category(results: List[ToolMatch], category: str) -> List[ToolMatch]:
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

    # Optionally clear embeddings from database
    if clear_embeddings:
        try:
            # EXEMPTION: tool_embeddings_cache is a low-level performance cache.
            # - Data is reconstructible (can regenerate embeddings from tool definitions)
            # - Data is non-authoritative (cache only, not source of truth)
            # - Data has no audit requirements (no compliance need)
            # - Mutation has no workflow implications (performance optimization only)
            # Per Wave 1.5 exemption policy, this mutation does NOT require event emission.
            with transaction() as conn:
                conn.execute("DELETE FROM tool_embeddings_cache")
            logger.info("Cleared all embeddings from database cache")
        except Exception as e:
            logger.error(f"Failed to clear embeddings cache: {e}")

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

        # Hybrid search
        print("\n[Hybrid Search (TF-IDF + Embeddings)]")
        start = time.time()
        hybrid_results = hybrid_search(query, top_k=10)
        hybrid_time = (time.time() - start) * 1000
        print(f"Time: {hybrid_time:.1f}ms")
        print(f"Results: {len(hybrid_results)}")
        if hybrid_results:
            print(f"Top result: {hybrid_results[0].name} ({hybrid_results[0].confidence:.2f})")

        print("\n" + "=" * 60)
        print(f"Speed difference (embeddings vs TF-IDF): {emb_time / tfidf_time:.2f}x slower")
        print(f"Speed difference (hybrid vs TF-IDF): {hybrid_time / tfidf_time:.2f}x slower")
        sys.exit(0)

    if use_hybrid:
        method = "hybrid (TF-IDF + embeddings)"
        print(f"Searching for: {query} (method: {method})\n")
        start = time.time()
        results = hybrid_search(query, top_k=10)
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
