#!/usr/bin/env python3
"""Tests for the career, finance, and real-estate domain analyzers."""

import sys
from pathlib import Path

import pytest

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from domains.career import CareerSkillAnalyzer
from domains.finance import FinanceSkillAnalyzer
from domains.real_estate import RealEstateSkillAnalyzer

# Use the analyze skill's own directory as the test subject -- these analyzers
# only need a repo_path that exists and is a directory; a low/uninteresting
# score is expected and is not what's under test here.
TEST_PATH = Path(__file__).parent
TEST_NAME = "analyze-skill"

ANALYZER_CLASSES = [CareerSkillAnalyzer, FinanceSkillAnalyzer, RealEstateSkillAnalyzer]


@pytest.mark.parametrize("analyzer_class", ANALYZER_CLASSES)
def test_weights_sum_to_one(analyzer_class):
    total_weight = sum(analyzer_class.WEIGHTS.values())
    assert total_weight == pytest.approx(1.0)


@pytest.mark.parametrize("analyzer_class", ANALYZER_CLASSES)
def test_capability_count_matches_weight_count(analyzer_class):
    analyzer = analyzer_class(TEST_PATH, TEST_NAME)
    assert len(analyzer.get_capabilities()) == len(analyzer_class.WEIGHTS)


@pytest.mark.parametrize("analyzer_class", ANALYZER_CLASSES)
def test_score_repository_returns_bounded_scores(analyzer_class):
    analyzer = analyzer_class(TEST_PATH, TEST_NAME)
    scores = analyzer.score_repository()

    assert 0.0 <= scores["overall_score"] <= 10.0
    for capability in analyzer.get_capabilities():
        assert capability in scores
        assert 0.0 <= scores[capability] <= 10.0
