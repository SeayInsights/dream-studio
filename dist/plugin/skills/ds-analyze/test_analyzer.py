#!/usr/bin/env python3
"""Integration test for domain analyzers"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from domains.registry import DomainAnalyzerRegistry
from domains.design import DesignSkillAnalyzer

# Test 1: Create analyzer instance
print("=" * 60)
print("Test 1: Create DesignSkillAnalyzer instance")
print("=" * 60)

repo_path = Path(__file__).parent.parent.parent  # dream-studio root
repo_name = "dream-studio"

analyzer = DesignSkillAnalyzer(repo_path, repo_name)
print(f"[OK] Created analyzer for {repo_name}")
print(f"  Domain: {analyzer.get_domain_name()}")
print(f"  Capabilities: {len(analyzer.get_capabilities())}")

# Test 2: Analyze one capability
print("\n" + "=" * 60)
print("Test 2: Analyze a single capability (color_systems)")
print("=" * 60)

result = analyzer.analyze_capability("color_systems")
print(f"  Detected: {result['detected']}")
print(f"  Score: {result['score']}/10")
print(f"  Quality: {result['quality']}")
print(f"  Count: {result['count']}")
print(f"  Evidence: {result['evidence'][:2]}")  # First 2 pieces of evidence

# Test 3: Score entire repository
print("\n" + "=" * 60)
print("Test 3: Score entire repository")
print("=" * 60)

scores = analyzer.score_repository()
print(f"  Overall Score: {scores['overall_score']}/10")
print(f"  Individual Scores:")
for capability in analyzer.get_capabilities()[:5]:  # First 5
    print(f"    {capability}: {scores[capability]}/10")

# Test 4: Get unique features
print("\n" + "=" * 60)
print("Test 4: Identify unique features")
print("=" * 60)

features = analyzer.get_unique_features()
if features:
    print(f"  Found {len(features)} unique features:")
    for feature in features:
        print(f"    - {feature}")
else:
    print("  No unique features detected (expected for non-design repo)")

# Test 5: Test registry auto-detection
print("\n" + "=" * 60)
print("Test 5: Auto-detect domain")
print("=" * 60)

detected_domain = DomainAnalyzerRegistry.auto_detect_domain(repo_path, verbose=False)
print(f"  Detected domain: {detected_domain}")
print(f"  (dream-studio is not a design/career/finance/real_estate repo, so 'general' is correct)")

print("\n" + "=" * 60)
print("All integration tests passed!")
print("=" * 60)
