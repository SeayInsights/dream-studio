"""
cip-brief.py — BM25-style keyword search across the deliverables catalog.

Usage:
    py scripts/cip-brief.py "fintech startup B2B premium"
    py scripts/cip-brief.py "retail enterprise packaging" --top 10

Output: ranked JSON list to stdout.
"""

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOP_WORDS = frozenset({"the", "a", "an", "is", "are", "in", "of", "for", "to", "and", "or", "with"})
BM25_K1 = 1.5
BM25_B = 0.75
DEFAULT_TOP = 20

# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on whitespace/punctuation, drop stop words."""
    raw = _TOKEN_RE.split(text.lower())
    return [t for t in raw if t and t not in STOP_WORDS]


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

def build_corpus(rows: list[dict]) -> tuple[list[list[str]], list[dict]]:
    """Return (token_lists, original_rows) for all deliverables."""
    token_lists = []
    for row in rows:
        combined = " ".join([
            row.get("name", ""),
            row.get("category", ""),
            row.get("description", ""),
        ])
        token_lists.append(tokenize(combined))
    return token_lists, rows


def bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    df_map: dict[str, int],
    n_docs: int,
    avgdl: float,
) -> float:
    """Compute BM25 score for a single document."""
    dl = len(doc_tokens)
    if dl == 0:
        return 0.0

    # Term frequency map for this document
    tf_map: dict[str, int] = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1

    score = 0.0
    for term in query_tokens:
        tf = tf_map.get(term, 0)
        if tf == 0:
            continue
        df = df_map.get(term, 0)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
        numerator = tf * (BM25_K1 + 1)
        denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
        score += idf * numerator / denominator

    return score


def search(query: str, rows: list[dict], top_n: int) -> dict:
    """Run BM25 search and return structured result dict."""
    query_tokens = tokenize(query)

    if not query_tokens:
        return {
            "query": query,
            "results": [],
            "total_matches": 0,
            "returned": 0,
        }

    token_lists, _ = build_corpus(rows)
    n_docs = len(token_lists)

    # Compute document frequency per term
    df_map: dict[str, int] = {}
    for doc_tokens in token_lists:
        seen = set(doc_tokens)
        for term in seen:
            df_map[term] = df_map.get(term, 0) + 1

    # Average document length
    total_len = sum(len(tl) for tl in token_lists)
    avgdl = total_len / n_docs if n_docs > 0 else 1.0

    # Score all documents
    scored = []
    for idx, (doc_tokens, row) in enumerate(zip(token_lists, rows)):
        s = bm25_score(query_tokens, doc_tokens, df_map, n_docs, avgdl)
        if s > 0:
            scored.append((s, idx, row))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)

    total_matches = len(scored)
    top = scored[:top_n]

    results = []
    for rank, (score, _idx, row) in enumerate(top, start=1):
        results.append({
            "rank": rank,
            "score": round(score, 4),
            "id": row.get("id", ""),
            "name": row.get("name", ""),
            "category": row.get("category", ""),
            "description": row.get("description", ""),
            "specs": row.get("specs", ""),
            "effort_hours": row.get("effort_hours", ""),
            "budget_tier": row.get("budget_tier", ""),
            "dependencies": row.get("dependencies", ""),
        })

    return {
        "query": query,
        "results": results,
        "total_matches": total_matches,
        "returned": len(results),
    }


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_deliverables(csv_path: Path) -> list[dict]:
    """Load deliverables from CSV file."""
    if not csv_path.exists():
        print(
            f"Error: deliverables catalog not found at {csv_path}\n"
            f"Expected: {csv_path.resolve()}",
            file=sys.stderr,
        )
        sys.exit(1)

    rows = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)

    if not rows:
        print(f"Warning: deliverables catalog is empty: {csv_path}", file=sys.stderr)

    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BM25 keyword search across the deliverables catalog.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  py scripts/cip-brief.py "fintech startup B2B premium"
  py scripts/cip-brief.py "retail enterprise packaging" --top 10
""",
    )
    parser.add_argument("query", help="Search query string")
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        metavar="N",
        help=f"Number of results to return (default: {DEFAULT_TOP})",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Resolve data/ relative to this script's location
    script_dir = Path(__file__).resolve().parent
    csv_path = script_dir.parent / "data" / "deliverables.csv"

    rows = load_deliverables(csv_path)
    result = search(args.query, rows, args.top)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
