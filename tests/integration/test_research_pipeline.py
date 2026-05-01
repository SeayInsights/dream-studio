"""Tests for the research persistence pipeline.

Covers:
- research_store: save/retrieve, staleness, list, delete, search
- source_ranker: rank_sources confidence levels
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — make hooks/lib and scripts importable
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from lib.research_store import (
    delete_research,
    get_research,
    is_stale,
    list_topics,
    save_research,
    search_research,
)
from source_ranker import rank_sources


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_research_dir(tmp_path, monkeypatch):
    """Redirect user_data_dir() to a temp directory for every test."""
    from lib import paths

    monkeypatch.setattr(paths, "user_data_dir", lambda: tmp_path / ".dream-studio")
    return tmp_path


# ---------------------------------------------------------------------------
# research_store tests
# ---------------------------------------------------------------------------

def test_save_and_get_research():
    """Round-trip: saved data must come back verbatim."""
    data = {
        "topic": "python async patterns",
        "sources": [
            {
                "url": "https://docs.python.org/3/library/asyncio.html",
                "tier": 1,
                "date": "2026-04-01",
                "key_findings": "asyncio provides cooperative multitasking",
            }
        ],
        "confidence": "MEDIUM",
        "triangulated": False,
        "refresh_due": "2026-08-01",
        "saved_date": "2026-05-01",
    }

    save_research("python async patterns", data)
    retrieved = get_research("python async patterns")

    assert retrieved is not None
    assert retrieved["topic"] == "python async patterns"
    assert len(retrieved["sources"]) == 1
    assert retrieved["sources"][0]["url"] == "https://docs.python.org/3/library/asyncio.html"
    assert retrieved["confidence"] == "MEDIUM"
    assert retrieved["triangulated"] is False
    assert retrieved["refresh_due"] == "2026-08-01"
    assert retrieved["saved_date"] == "2026-05-01"


def test_is_stale_with_past_date():
    """A refresh_due date in the past should be considered stale."""
    data = {
        "topic": "stale topic",
        "sources": [],
        "refresh_due": "2020-01-01",
    }
    save_research("stale topic", data)

    assert is_stale("stale topic") is True


def test_is_stale_with_future_date():
    """A refresh_due date far in the future should not be stale."""
    data = {
        "topic": "fresh topic",
        "sources": [],
        "refresh_due": "2099-12-31",
    }
    save_research("fresh topic", data)

    assert is_stale("fresh topic") is False


def test_list_topics():
    """list_topics() must return all saved topics with correct metadata."""
    topics = [
        ("rust ownership", "2099-06-01", "HIGH", True),
        ("wasm compilation", "2020-01-01", "LOW", False),
        ("css container queries", "2099-09-15", "MEDIUM", True),
    ]

    for topic, refresh_due, confidence, triangulated in topics:
        save_research(
            topic,
            {
                "topic": topic,
                "sources": [],
                "confidence": confidence,
                "triangulated": triangulated,
                "refresh_due": refresh_due,
            },
        )

    result = list_topics()

    assert len(result) == 3

    topic_names = {r["topic"] for r in result}
    assert topic_names == {"rust ownership", "wasm compilation", "css container queries"}

    by_topic = {r["topic"]: r for r in result}

    assert by_topic["rust ownership"]["confidence"] == "HIGH"
    assert by_topic["rust ownership"]["triangulated"] is True
    assert by_topic["rust ownership"]["stale"] is False

    assert by_topic["wasm compilation"]["stale"] is True

    assert by_topic["css container queries"]["confidence"] == "MEDIUM"
    assert by_topic["css container queries"]["triangulated"] is True


def test_delete_research():
    """After deletion, get_research should return None."""
    data = {"topic": "disposable topic", "sources": [], "refresh_due": "2099-01-01"}
    save_research("disposable topic", data)

    assert get_research("disposable topic") is not None

    deleted = delete_research("disposable topic")
    assert deleted is True

    assert get_research("disposable topic") is None


def test_search_research():
    """search_research should return the correct topic matched by keyword."""
    save_research(
        "database indexing",
        {
            "topic": "database indexing",
            "sources": [
                {
                    "url": "https://example.com/db",
                    "tier": 1,
                    "date": "2026-04-01",
                    "key_findings": "B-tree indexes speed up read queries significantly",
                }
            ],
            "refresh_due": "2099-01-01",
        },
    )
    save_research(
        "css grid layout",
        {
            "topic": "css grid layout",
            "sources": [
                {
                    "url": "https://example.com/css",
                    "tier": 2,
                    "date": "2026-04-01",
                    "key_findings": "CSS Grid simplifies two-dimensional layouts",
                }
            ],
            "refresh_due": "2099-01-01",
        },
    )
    save_research(
        "python packaging",
        {
            "topic": "python packaging",
            "sources": [
                {
                    "url": "https://example.com/pypi",
                    "tier": 1,
                    "date": "2026-04-01",
                    "key_findings": "pyproject.toml is the modern packaging standard",
                }
            ],
            "refresh_due": "2099-01-01",
        },
    )

    results = search_research("B-tree")

    assert len(results) == 1
    assert results[0]["topic"] == "database indexing"


# ---------------------------------------------------------------------------
# source_ranker tests
# ---------------------------------------------------------------------------

def test_source_ranker_low_confidence():
    """A single source with no counter-argument should score LOW confidence."""
    sources = [
        {
            "url": "https://blog.example.com/article",
            "name": "Example Blog Post",
            "tier": 2,
            "findings": "This approach works well for most use cases.",
        }
    ]

    result = rank_sources(sources)

    assert result["confidence"] == "LOW"
    assert result["source_count"] == 1
    assert result["triangulation_score"] == pytest.approx(0.2)


def test_source_ranker_medium_confidence():
    """Two sources should yield MEDIUM confidence."""
    sources = [
        {
            "url": "https://docs.example.com/guide",
            "name": "Official Guide",
            "tier": 1,
            "findings": "The recommended pattern is dependency injection.",
        },
        {
            "url": "https://research.example.org/paper",
            "name": "Research Paper",
            "tier": 1,
            "findings": "Empirical study confirms dependency injection reduces coupling.",
        },
    ]

    result = rank_sources(sources)

    assert result["confidence"] == "MEDIUM"
    assert result["source_count"] == 2
    assert result["triangulation_score"] == pytest.approx(0.5)


def test_source_ranker_high_confidence():
    """Three sources including a Tier 1 source and a counter-argument should yield HIGH confidence."""
    sources = [
        {
            "url": "https://spec.example.org/rfc",
            "name": "RFC Document",
            "tier": 1,
            "findings": "The specification defines strict ordering requirements.",
        },
        {
            "url": "https://journal.example.edu/study",
            "name": "Academic Study",
            "tier": 1,
            "findings": "Empirical data supports the specification's approach in 87% of cases.",
        },
        {
            "url": "https://blog.practitioner.io/deep-dive",
            "name": "Practitioner Analysis",
            "tier": 2,
            "findings": (
                "However, the counter-argument is that strict ordering adds overhead "
                "that may not be warranted in low-throughput systems."
            ),
        },
    ]

    result = rank_sources(sources)

    assert result["confidence"] == "HIGH"
    assert result["source_count"] == 3
    assert result["triangulation_score"] == pytest.approx(1.0)
    assert result["tier1_count"] == 2
    assert result["counter_argument"] == "PRESENT"
