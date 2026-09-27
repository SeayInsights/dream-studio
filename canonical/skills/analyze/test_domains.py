#!/usr/bin/env python3
"""Verify all domain analyzers are registered with DomainAnalyzerRegistry."""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from domains.registry import DomainAnalyzerRegistry

EXPECTED_DOMAINS = {"career", "design", "finance", "real_estate"}


def test_all_domain_analyzers_are_registered():
    domains = DomainAnalyzerRegistry.list_domains()
    assert set(domains) == EXPECTED_DOMAINS


def test_domain_info_reports_capabilities_for_every_domain():
    domains = DomainAnalyzerRegistry.list_domains()
    info = DomainAnalyzerRegistry.get_domain_info()

    assert set(info.keys()) == set(domains)

    for domain in domains:
        domain_info = info[domain]
        assert domain_info["class"].endswith("SkillAnalyzer")
        assert domain_info["capabilities_count"] > 0
        assert len(domain_info["capabilities"]) == domain_info["capabilities_count"]
        assert len(domain_info["markers"]) > 0
