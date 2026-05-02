#!/usr/bin/env python3
"""
Repository Analysis Integration for Analyze Pack

Integrates shared/repo-analysis utility with dream-studio analyze pack.
Enables multi-perspective analysis of repository patterns and organizational structures.

Usage:
    from skills.analyze.repo_analyzer import analyze_repositories

    result = analyze_repositories(['/path/to/repo1', '/path/to/repo2'])
    # Returns analysis report ready for multi-perspective analysis
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Union

# Add parent directory to path to import shared modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.repo_analysis.analyzer import RepoAnalyzer
from shared.repo_analysis.formatters import json_formatter, markdown_formatter


def analyze_repositories(
    repo_paths: List[str],
    output_format: str = 'dict',
    patterns_filter: Optional[List[str]] = None,
    verbose: bool = False
) -> Union[Dict, str]:
    """
    Analyze repositories for SKILL.md patterns and structures

    Args:
        repo_paths: List of repository directory paths to analyze
        output_format: Output format ('dict', 'json', 'markdown')
        patterns_filter: Optional list of pattern names to include (None = all)
        verbose: Print progress messages

    Returns:
        Analysis report in requested format:
        - 'dict': Python dictionary (default)
        - 'json': JSON-formatted string
        - 'markdown': Markdown-formatted string

    Raises:
        ValueError: If repo_paths is empty or format is invalid
        FileNotFoundError: If any repository path doesn't exist
    """
    if not repo_paths:
        raise ValueError("repo_paths cannot be empty")

    valid_formats = {'dict', 'json', 'markdown'}
    if output_format not in valid_formats:
        raise ValueError(f"Invalid format '{output_format}'. Must be one of: {valid_formats}")

    # Validate repository paths
    validated_repos = []
    for repo_str in repo_paths:
        repo_path = Path(repo_str).resolve()

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {repo_path}")

        if not repo_path.is_dir():
            raise ValueError(f"Not a directory: {repo_path}")

        repo_name = repo_path.name
        validated_repos.append((repo_path, repo_name))

    # Create analyzer
    analyzer = RepoAnalyzer()

    # Add repositories
    for repo_path, repo_name in validated_repos:
        if verbose:
            print(f"[ANALYZE] Queuing: {repo_name}")
        analyzer.add_repo(repo_path, repo_name)

    # Run analysis
    analyzer.analyze_all(verbose=verbose)

    # Generate report
    report = analyzer.generate_report()

    # Filter patterns if specified
    if patterns_filter:
        report = _filter_patterns(report, patterns_filter)

    # Format output
    if output_format == 'json':
        return json_formatter.format_report(report)
    elif output_format == 'markdown':
        return markdown_formatter.format_report(report)
    else:  # dict
        return report


def analyze_single_repo(
    repo_path: str,
    output_format: str = 'dict',
    verbose: bool = False
) -> Union[Dict, str]:
    """
    Analyze a single repository (convenience wrapper)

    Args:
        repo_path: Path to repository directory
        output_format: Output format ('dict', 'json', 'markdown')
        verbose: Print progress messages

    Returns:
        Analysis report in requested format
    """
    return analyze_repositories([repo_path], output_format, verbose=verbose)


def compare_repositories(
    repo_paths: List[str],
    focus_patterns: Optional[List[str]] = None,
    verbose: bool = False
) -> Dict:
    """
    Compare multiple repositories side-by-side

    Args:
        repo_paths: List of repository directory paths
        focus_patterns: Optional list of patterns to focus comparison on
        verbose: Print progress messages

    Returns:
        Comparison report with:
        {
            'repositories': List[str],
            'comparison_matrix': Dict,
            'recommendations': List[str]
        }
    """
    # Run analysis
    report = analyze_repositories(
        repo_paths,
        output_format='dict',
        patterns_filter=focus_patterns,
        verbose=verbose
    )

    # Build comparison matrix
    comparison = {
        'repositories': report['summary']['repos_analyzed'],
        'comparison_matrix': {},
        'recommendations': []
    }

    # Extract pattern adoption rates
    if 'statistics' in report and 'pattern_adoption_rate' in report['statistics']:
        comparison['comparison_matrix'] = report['statistics']['pattern_adoption_rate']

    # Generate recommendations
    comparison['recommendations'] = _generate_recommendations(report)

    return comparison


def extract_patterns_for_enhancement(
    source_repos: List[str],
    target_repo: str,
    min_adoption_threshold: float = 0.5,
    verbose: bool = False
) -> Dict:
    """
    Identify patterns from source repos that could enhance target repo

    Args:
        source_repos: List of repository paths to extract patterns from
        target_repo: Repository path to analyze for enhancement opportunities
        min_adoption_threshold: Minimum adoption rate (0.0-1.0) in source repos
        verbose: Print progress messages

    Returns:
        Enhancement recommendations:
        {
            'target_repo': str,
            'source_repos': List[str],
            'recommended_patterns': List[Dict],
            'estimated_effort': str
        }
    """
    # Analyze all repos together
    all_repos = source_repos + [target_repo]
    report = analyze_repositories(all_repos, verbose=verbose)

    target_name = Path(target_repo).name

    # Find patterns well-adopted in sources but missing in target
    recommended_patterns = []

    if 'statistics' in report and 'pattern_adoption_rate' in report['statistics']:
        adoption_rates = report['statistics']['pattern_adoption_rate']
        target_rates = adoption_rates.get(target_name, {})

        # Calculate average adoption in source repos
        for pattern_name in adoption_rates.get(list(adoption_rates.keys())[0], {}).keys():
            source_adoption_rates = []

            for source_repo in source_repos:
                source_name = Path(source_repo).name
                if source_name in adoption_rates:
                    rate_str = adoption_rates[source_name].get(pattern_name, '0%')
                    rate = float(rate_str.rstrip('%')) / 100
                    source_adoption_rates.append(rate)

            if source_adoption_rates:
                avg_source_adoption = sum(source_adoption_rates) / len(source_adoption_rates)
                target_rate_str = target_rates.get(pattern_name, '0%')
                target_adoption = float(target_rate_str.rstrip('%')) / 100

                # Recommend if well-adopted in sources but low in target
                if avg_source_adoption >= min_adoption_threshold and target_adoption < min_adoption_threshold:
                    recommended_patterns.append({
                        'pattern': pattern_name,
                        'source_adoption': f"{avg_source_adoption * 100:.1f}%",
                        'target_adoption': f"{target_adoption * 100:.1f}%",
                        'gap': f"{(avg_source_adoption - target_adoption) * 100:.1f}%"
                    })

    return {
        'target_repo': target_name,
        'source_repos': [Path(r).name for r in source_repos],
        'recommended_patterns': recommended_patterns,
        'estimated_effort': _estimate_effort(recommended_patterns)
    }


def _filter_patterns(report: Dict, pattern_filter: List[str]) -> Dict:
    """Filter report to include only specified patterns"""
    filtered_patterns = {
        k: v for k, v in report.get('patterns', {}).items()
        if k in pattern_filter
    }

    report['patterns'] = filtered_patterns
    report['summary']['patterns_found'] = list(filtered_patterns.keys())

    return report


def _generate_recommendations(report: Dict) -> List[str]:
    """Generate actionable recommendations from analysis report"""
    recommendations = []

    # Check for missing progressive disclosure
    for repo_name, repo_data in report.get('repo_structures', {}).items():
        skills_with_refs = repo_data.get('skills_with_references', 0)
        total_skills = repo_data.get('total_skills', 0)

        if total_skills > 0 and skills_with_refs == 0:
            recommendations.append(
                f"{repo_name}: Consider adding references/ directories for progressive disclosure"
            )

    # Check for missing CI validation
    for repo_name, repo_data in report.get('repo_structures', {}).items():
        if not repo_data.get('has_validation_ci', False):
            recommendations.append(
                f"{repo_name}: Add CI validation workflow for quality gates"
            )

    # Check for low pattern adoption
    if 'statistics' in report and 'pattern_adoption_rate' in report['statistics']:
        for repo_name, rates in report['statistics']['pattern_adoption_rate'].items():
            low_patterns = [
                pattern for pattern, rate in rates.items()
                if float(rate.rstrip('%')) < 30
            ]

            if len(low_patterns) > 3:
                recommendations.append(
                    f"{repo_name}: Low pattern adoption detected. Consider implementing: {', '.join(low_patterns[:3])}"
                )

    return recommendations


def _estimate_effort(recommended_patterns: List[Dict]) -> str:
    """Estimate effort required to implement recommended patterns"""
    pattern_count = len(recommended_patterns)

    if pattern_count == 0:
        return "0 hours (no patterns recommended)"
    elif pattern_count <= 2:
        return f"{pattern_count * 4}-{pattern_count * 6} hours (small)"
    elif pattern_count <= 5:
        return f"{pattern_count * 6}-{pattern_count * 10} hours (medium)"
    else:
        return f"{pattern_count * 8}-{pattern_count * 15} hours (large)"


# CLI interface for standalone usage
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Analyze repositories for dream-studio analyze pack')
    parser.add_argument('repos', nargs='+', help='Repository paths to analyze')
    parser.add_argument('--format', choices=['dict', 'json', 'markdown'], default='markdown')
    parser.add_argument('--patterns', nargs='*', help='Filter specific patterns')
    parser.add_argument('--compare', action='store_true', help='Generate comparison report')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.compare:
        result = compare_repositories(args.repos, focus_patterns=args.patterns, verbose=args.verbose)
        print(json_formatter.format_report(result))
    else:
        result = analyze_repositories(
            args.repos,
            output_format=args.format,
            patterns_filter=args.patterns,
            verbose=args.verbose
        )
        print(result)
