# Tool Recommendations System - Technical Reference

## Overview

The `--recommend-tools` flag enables automatic discovery and recommendation of external tools (Python packages, MCPs, APIs, SaaS) based on problem keywords. This system helps think mode surface relevant tools early in design.

## How It Works

The flag triggers a keyword extraction → tool search → confidence scoring workflow:

1. **Keywords extracted** from user input and spec context (e.g., "video", "processing", "pipeline")
2. **TF-IDF search** runs over tool_registry table using extracted keywords
3. **Confidence scoring** combines TF-IDF similarity (70%) + tool registry confidence score (30%)
4. **Top 5 recommendations** with confidence > 0.7 are appended to spec.md

## TF-IDF Vectorization

The maintained tool discovery interface builds a TF-IDF index over the tool_registry:

- **Corpus**: Description + name + tags for each tool
- **Features**: Unigrams and bigrams (1-2 word sequences)
- **Max features**: 1,000 terms
- **Filtering**: Remove English stopwords, apply min_df=1 and max_df=0.9

```python
TfidfVectorizer(
    max_features=1000,
    stop_words='english',
    ngram_range=(1, 2),      # unigrams + bigrams
    min_df=1,
    max_df=0.9,
)
```

## Cosine Similarity Scoring

For each query (extracted keywords):

1. Transform query to TF-IDF vector
2. Calculate cosine similarity between query and all tool vectors
3. Rank tools by similarity score (0.0–1.0)
4. Return top-K candidates (K = 10 to account for filtering)

## Confidence Score Calculation

Final confidence = (0.7 × similarity_score) + (0.3 × registry_confidence_score)

- **Similarity score**: Cosine similarity from TF-IDF (0.0–1.0)
- **Registry confidence**: Tool's pre-scored confidence in database (0.0–1.0, default 0.5)
- **Filter threshold**: Only tools with confidence ≥ 0.5 are returned
- **Recommendation threshold**: Only tools with confidence ≥ 0.7 appear in spec output

## Query Caching

Results are cached with 1-hour TTL to avoid repeated TF-IDF computations:

- **Cache key**: Normalized query (lowercase, punctuation removed, spaces collapsed) + category
- **Max size**: 1,000 entries
- **TTL**: 3,600 seconds (1 hour)
- **Cache stats**: Available via `get_cache_stats()` in tool_search module

## Tool Registry Schema

Tools are stored in the `tool_registry` table:

| Column | Type | Description |
|---|---|---|
| **tool_id** | TEXT (PK) | Unique identifier (e.g., `pkg-ffmpeg-python`) |
| **name** | TEXT | Display name (e.g., `ffmpeg-python`) |
| **category** | TEXT | Category: `mcp`, `python_package`, `api`, `saas` |
| **description** | TEXT | One-line description used for TF-IDF indexing |
| **source_url** | TEXT | URL to documentation or repo |
| **install_command** | TEXT | Install instruction (e.g., `pip install ffmpeg-python`) |
| **tags** | TEXT | JSON array of keywords (e.g., `["video", "audio", "processing"]`) |
| **confidence_score** | REAL | Pre-rated confidence 0.0–1.0 (default 0.5) |
| **last_verified_at** | TEXT | ISO 8601 timestamp of last validation |
| **created_at** | TEXT | ISO 8601 creation timestamp |

## Customizing the Tool Registry

### Adding a Tool

Insert directly into tool_registry:

```python
conn.execute("""
    INSERT INTO tool_registry 
    (tool_id, name, category, description, source_url, install_command, tags, confidence_score)
    VALUES
    (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "pkg-celery",
    "Celery",
    "python_package",
    "Distributed task queue for Python applications",
    "https://docs.celeryproject.org",
    "pip install celery",
    '["async", "tasks", "queue", "distributed"]',
    0.85
))
conn.commit()
```

Or use the CLI:
```bash
py -m control.research.tools "celery" --add-tool
```

### Removing a Tool

```python
conn.execute("DELETE FROM tool_registry WHERE tool_id = ?", ("pkg-celery",))
conn.commit()
```

After bulk changes, rebuild the TF-IDF index:

```python
from control.research.tools import rebuild_index
success = rebuild_index()  # Returns True if successful
```

### Updating Tool Metadata

To fix description or tags for an existing tool:

```python
conn.execute("""
    UPDATE tool_registry 
    SET description = ?, tags = ?, confidence_score = ?
    WHERE tool_id = ?
""", (
    "New description",
    '["updated", "tags"]',
    0.9,
    "pkg-celery"
))
conn.commit()
rebuild_index()  # Clear cache and rebuild
```

## Troubleshooting

### No recommendations appear
- **Check**: Is the query sufficiently specific? Generic queries like "build" may not match any tools.
- **Check**: Does tool_registry have entries? Query `SELECT COUNT(*) FROM tool_registry`.
- **Fix**: Rephrase with domain keywords (e.g., "video processing" instead of "process").

### Wrong tools recommended
- **Check**: Are tool tags accurate? Tags heavily influence matching.
- **Check**: Is registry confidence_score set appropriately for the tool?
- **Fix**: Update tags or confidence_score via UPDATE statement and rebuild index.

### Cache hit/miss ratio too low
- **Debug**: Run `py -m control.research.tools "your-query" --cache-stats`
- **Fix**: If misses are high, your queries may vary in phrasing. Normalize queries to consistent keywords.

### Index out of sync after manual edits
- **Fix**: Always call `rebuild_index()` after INSERT/UPDATE/DELETE operations to clear cache and rebuild TF-IDF vectors.

## Example Spec Output

When `--recommend-tools` flag is used:

```markdown
# Video Processing Pipeline Spec

(... standard spec content ...)

## Recommended Tools

- **ffmpeg-python** (95% confidence) - Python bindings for FFmpeg video processing
  - Install: `pip install ffmpeg-python`
  - Why: High match for "video processing" keywords
  - Source: https://github.com/kkroening/ffmpeg-python

- **opencv-python** (88% confidence) - Computer vision and video analysis library
  - Install: `pip install opencv-python`
  - Why: Strong match for "video" and "processing" keywords
  - Source: https://opencv.org

- **moviepy** (82% confidence) - Video editing library for Python
  - Install: `pip install moviepy`
  - Why: Match for "video", "processing", and "pipeline" keywords
  - Source: https://zulko.github.io/moviepy/
```

## API Integration

The tool search system can be called programmatically:

```python
from control.research.tools import search_tools, get_cache_stats

# Search for tools
results = search_tools("video processing", top_k=5, category="python_package")

for match in results:
    print(f"{match.name} ({match.confidence:.2f}): {match.description}")
    print(f"  Install: {match.install_command}")

# Check cache performance
stats = get_cache_stats()
print(f"Cache hit ratio: {stats['hit_ratio']:.1%}")
```
