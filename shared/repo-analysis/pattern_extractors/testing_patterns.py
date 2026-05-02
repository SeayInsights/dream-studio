"""
Testing Patterns Extractor

Detects test organization patterns, test types, and test coverage indicators.
Helps identify testing maturity and test strategy across repositories.
"""

import re
from pathlib import Path
from typing import Dict, List


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract testing pattern references from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'test_mentions': int,
            'test_types': List[str],
            'test_frameworks': List[str]
        }
    """
    content_lower = content.lower()

    # Test type keywords
    test_types = []
    test_type_patterns = {
        'unit': r'\bunit\s+test',
        'integration': r'\bintegration\s+test',
        'e2e': r'\b(e2e|end-to-end)\s+test',
        'smoke': r'\bsmoke\s+test',
        'regression': r'\bregression\s+test',
        'acceptance': r'\bacceptance\s+test',
        'snapshot': r'\bsnapshot\s+test'
    }

    for test_type, pattern in test_type_patterns.items():
        if re.search(pattern, content_lower):
            test_types.append(test_type)

    # Test framework detection
    frameworks = []
    framework_patterns = [
        'pytest', 'unittest', 'jest', 'mocha', 'jasmine', 'vitest',
        'playwright', 'cypress', 'selenium', 'testify', 'ginkgo',
        'rspec', 'minitest', 'xunit', 'nunit'
    ]

    for framework in framework_patterns:
        if framework in content_lower:
            frameworks.append(framework)

    # Count test-related mentions
    test_keywords = ['test', 'testing', 'spec', 'coverage', 'assertion']
    test_mentions = sum(content_lower.count(kw) for kw in test_keywords)

    return {
        'detected': len(test_types) > 0 or len(frameworks) > 0,
        'test_mentions': test_mentions,
        'test_types': test_types,
        'test_frameworks': frameworks
    }


def analyze_test_files(repo_path: Path) -> Dict:
    """
    Analyze test file organization in repository

    Args:
        repo_path: Path to repository root

    Returns:
        Dictionary with test file analysis:
        {
            'has_test_directory': bool,
            'test_file_count': int,
            'test_directories': List[str],
            'test_file_patterns': Dict[str, int]
        }
    """
    # Common test directory names
    test_dir_names = ['test', 'tests', '__tests__', 'spec', 'specs', 'e2e']

    test_directories = []
    for dir_name in test_dir_names:
        test_dir = repo_path / dir_name
        if test_dir.exists() and test_dir.is_dir():
            test_directories.append(dir_name)

    # Common test file patterns
    test_patterns = {
        'test_*.py': len(list(repo_path.rglob('test_*.py'))),
        '*_test.py': len(list(repo_path.rglob('*_test.py'))),
        '*.test.js': len(list(repo_path.rglob('*.test.js'))),
        '*.test.ts': len(list(repo_path.rglob('*.test.ts'))),
        '*.spec.js': len(list(repo_path.rglob('*.spec.js'))),
        '*.spec.ts': len(list(repo_path.rglob('*.spec.ts'))),
        '*_test.go': len(list(repo_path.rglob('*_test.go')))
    }

    total_test_files = sum(test_patterns.values())

    return {
        'has_test_directory': len(test_directories) > 0,
        'test_file_count': total_test_files,
        'test_directories': test_directories,
        'test_file_patterns': {k: v for k, v in test_patterns.items() if v > 0}
    }


def extract_coverage_indicators(content: str) -> Dict:
    """
    Extract test coverage indicators and requirements

    Args:
        content: Full content of SKILL.md file

    Returns:
        Dictionary with coverage analysis:
        {
            'has_coverage_requirement': bool,
            'coverage_threshold': str or None,
            'coverage_tools': List[str]
        }
    """
    content_lower = content.lower()

    # Coverage threshold patterns (e.g., "80% coverage", "coverage > 90%")
    threshold_pattern = r'(\d+)%?\s*(?:coverage|test coverage)'
    threshold_match = re.search(threshold_pattern, content_lower)
    coverage_threshold = threshold_match.group(1) if threshold_match else None

    # Coverage tools
    coverage_tools = []
    tool_patterns = ['coverage', 'codecov', 'coveralls', 'istanbul', 'nyc', 'jacoco']

    for tool in tool_patterns:
        if tool in content_lower:
            coverage_tools.append(tool)

    return {
        'has_coverage_requirement': coverage_threshold is not None,
        'coverage_threshold': coverage_threshold,
        'coverage_tools': coverage_tools
    }
