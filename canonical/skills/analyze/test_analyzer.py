#!/usr/bin/env python3
"""Integration tests for DesignSkillAnalyzer and domain auto-detection.

Exercises the analyzer against the dream-studio repo itself (not a design
repo), so the useful assertion is that the general-purpose plumbing
(instantiate, analyze one capability, score the whole repo) works end to end
without crashing -- not that any particular score comes back high.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from domains.design import DesignSkillAnalyzer

# dream-studio repo root: this file lives at canonical/skills/analyze/, three
# directories under the root, so reaching it takes FOUR .parent hops, not
# three. An earlier version of this file used three and silently pointed at
# canonical/ instead of the repo root (see modes/repo/gotchas.yml's
# repo-root-parent-hop-off-by-one entry for the same bug class in
# repo-analyzer.py and analyze-repos.py).
REPO_PATH = Path(__file__).parent.parent.parent.parent
REPO_NAME = "dream-studio"


def test_design_analyzer_instantiates_with_all_capabilities():
    analyzer = DesignSkillAnalyzer(REPO_PATH, REPO_NAME)
    assert analyzer.get_domain_name() == "design"
    assert len(analyzer.get_capabilities()) == len(DesignSkillAnalyzer.WEIGHTS)


def test_analyze_single_capability_returns_full_result_shape():
    analyzer = DesignSkillAnalyzer(REPO_PATH, REPO_NAME)
    result = analyzer.analyze_capability("color_systems")

    assert {"detected", "score", "evidence", "count", "quality"} <= result.keys()
    assert 0.0 <= result["score"] <= 10.0
    assert result["quality"] in {"excellent", "good", "adequate", "weak"}


def test_score_repository_covers_every_capability():
    analyzer = DesignSkillAnalyzer(REPO_PATH, REPO_NAME)
    scores = analyzer.score_repository()

    assert 0.0 <= scores["overall_score"] <= 10.0
    for capability in analyzer.get_capabilities():
        assert capability in scores
        assert 0.0 <= scores[capability] <= 10.0


def test_get_unique_features_returns_a_list():
    analyzer = DesignSkillAnalyzer(REPO_PATH, REPO_NAME)
    assert isinstance(analyzer.get_unique_features(), list)


def test_auto_detect_domain_defaults_to_general_with_no_markers(tmp_path):
    # Deliberately uses an isolated tmp_path rather than the real dream-studio
    # checkout: auto_detect_domain() matches markers via a recursive filename
    # SUBSTRING search (see repo/gotchas.yml's
    # broad-substring-marker-matching-on-large-repos entry), so pointing it
    # at a large, general-purpose monorepo can trip an unrelated domain's
    # markers by coincidence. A directory with no domain-marker filenames at
    # all is what actually isolates the "no signal -> general" behavior.
    from domains.registry import DomainAnalyzerRegistry

    (tmp_path / "README.md").write_text("Just a plain project readme.\n", encoding="utf-8")

    detected_domain = DomainAnalyzerRegistry.auto_detect_domain(tmp_path, verbose=False)
    assert detected_domain == "general"
