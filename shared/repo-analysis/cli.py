#!/usr/bin/env python3
"""
CLI interface for Repository Analysis Utility

Usage:
    python -m shared.repo-analysis.cli --repos /path/to/repo1 /path/to/repo2 --output report.json
    python -m shared.repo-analysis.cli --repos /path/to/repo --output report.md --format markdown
"""

import argparse
import sys
import json
from pathlib import Path
from typing import List

from .analyzer import RepoAnalyzer


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze repositories for SKILL.md patterns and organizational structures',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze single repo, output JSON
  %(prog)s --repos /path/to/repo --output report.json

  # Analyze multiple repos, output Markdown
  %(prog)s --repos /path/to/repo1 /path/to/repo2 --output report.md --format markdown

  # Filter specific patterns
  %(prog)s --repos /path/to/repo --output report.json --patterns progressive_disclosure decision_tables
        """
    )

    parser.add_argument(
        '--repos',
        nargs='+',
        required=True,
        help='Path(s) to repository directories to analyze (space-separated)'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Output file path for analysis report'
    )

    parser.add_argument(
        '--patterns',
        nargs='*',
        default=None,
        help='Specific patterns to extract (default: all patterns). Available: progressive_disclosure, decision_tables, do_dont_examples, response_contracts, version_guards, frontmatter_patterns, testing_patterns, cicd_patterns, docs_patterns, code_quality_patterns'
    )

    parser.add_argument(
        '--format',
        choices=['json', 'markdown'],
        default='json',
        help='Output format (default: json)'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Print progress messages during analysis'
    )

    return parser.parse_args()


def validate_repos(repo_paths: List[str]) -> List[tuple[Path, str]]:
    """
    Validate repository paths and return list of (Path, repo_name) tuples

    Args:
        repo_paths: List of repository path strings

    Returns:
        List of (Path object, repo name) tuples

    Raises:
        SystemExit: If any repository path is invalid
    """
    validated = []
    errors = []

    for repo_str in repo_paths:
        repo_path = Path(repo_str).resolve()

        if not repo_path.exists():
            errors.append(f"Repository not found: {repo_path}")
            continue

        if not repo_path.is_dir():
            errors.append(f"Not a directory: {repo_path}")
            continue

        # Use directory name as repo name
        repo_name = repo_path.name
        validated.append((repo_path, repo_name))

    if errors:
        print("[ERROR] Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    return validated


def validate_output_path(output_str: str) -> Path:
    """
    Validate output file path

    Args:
        output_str: Output file path string

    Returns:
        Path object

    Raises:
        SystemExit: If output path is invalid
    """
    output_path = Path(output_str).resolve()

    # Check parent directory exists
    if not output_path.parent.exists():
        print(f"[ERROR] Output directory does not exist: {output_path.parent}", file=sys.stderr)
        sys.exit(1)

    return output_path


def filter_patterns(report: dict, pattern_filter: List[str]) -> dict:
    """
    Filter report to include only specified patterns

    Args:
        report: Full analysis report
        pattern_filter: List of pattern names to include

    Returns:
        Filtered report
    """
    if pattern_filter is None:
        return report

    # Filter patterns dict
    filtered_patterns = {
        k: v for k, v in report['patterns'].items()
        if k in pattern_filter
    }

    # Update summary
    report['patterns'] = filtered_patterns
    report['summary']['patterns_found'] = list(filtered_patterns.keys())

    return report


def format_markdown_report(report: dict) -> str:
    """
    Convert JSON report to Markdown format

    Args:
        report: Analysis report dictionary

    Returns:
        Markdown-formatted string
    """
    lines = []
    lines.append("# Repository Analysis Report\n")

    # Summary
    lines.append("## Summary\n")
    lines.append(f"- **Total SKILL.md files analyzed**: {report['summary']['total_skills_analyzed']}")
    lines.append(f"- **Repositories analyzed**: {', '.join(report['summary']['repos_analyzed'])}")
    lines.append(f"- **Patterns found**: {', '.join(report['summary']['patterns_found'])}\n")

    # Repository Structures
    lines.append("## Repository Structures\n")
    for repo_name, repo_data in report['repo_structures'].items():
        lines.append(f"### {repo_name}\n")
        lines.append(f"- Total skills: {repo_data['total_skills']}")
        lines.append(f"- Skills with references: {repo_data['skills_with_references']}")
        lines.append(f"- Has CLAUDE.md: {repo_data['has_claude_md']}")
        lines.append(f"- Has AGENTS.md: {repo_data['has_agents_md']}")
        lines.append(f"- Has skill standards: {repo_data['has_skill_standards']}")
        lines.append(f"- Has PR template: {repo_data['has_pr_template']}")
        lines.append(f"- Has validation CI: {repo_data['has_validation_ci']}\n")

    # Pattern Adoption Rates
    lines.append("## Pattern Adoption Rates\n")
    if 'pattern_adoption_rate' in report['statistics']:
        for repo_name, rates in report['statistics']['pattern_adoption_rate'].items():
            lines.append(f"### {repo_name}\n")
            for pattern, rate in rates.items():
                lines.append(f"- {pattern}: {rate}")
            lines.append("")

    # Patterns Found
    lines.append("## Patterns Detected\n")
    for pattern_name, instances in report['patterns'].items():
        lines.append(f"### {pattern_name.replace('_', ' ').title()}\n")
        lines.append(f"Found {len(instances)} instances:\n")
        for instance in instances[:5]:  # Show first 5 instances
            lines.append(f"- **{instance['repo']}**: {instance['file']}")
        if len(instances) > 5:
            lines.append(f"- _(and {len(instances) - 5} more)_")
        lines.append("")

    return "\n".join(lines)


def main():
    """Main CLI entry point"""
    args = parse_args()

    # Validate inputs
    repos = validate_repos(args.repos)
    output_path = validate_output_path(args.output)

    if args.verbose:
        print(f"[CLI] Starting analysis of {len(repos)} repositories")
        print(f"[CLI] Output format: {args.format}")
        print(f"[CLI] Output file: {output_path}")

    # Create analyzer
    analyzer = RepoAnalyzer()

    # Add repositories
    for repo_path, repo_name in repos:
        if args.verbose:
            print(f"[CLI] Queued: {repo_name} ({repo_path})")
        analyzer.add_repo(repo_path, repo_name)

    # Run analysis
    analyzer.analyze_all(verbose=args.verbose)

    # Generate report
    report = analyzer.generate_report()

    # Filter patterns if specified
    if args.patterns:
        report = filter_patterns(report, args.patterns)

    # Write output
    if args.format == 'json':
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
    else:  # markdown
        markdown_content = format_markdown_report(report)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

    if args.verbose:
        print(f"\n[CLI] Analysis complete! Report written to: {output_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
