"""
Markdown Report Formatter

Formats repository analysis results as readable Markdown documentation.
"""

from typing import Dict, List


def format_report(report: Dict) -> str:
    """
    Format analysis report as comprehensive Markdown document

    Args:
        report: Analysis report dictionary with:
            - summary: aggregate metrics
            - repo_structures: repository organization
            - skill_analyses: individual SKILL.md analyses
            - patterns: detected patterns
            - statistics: comparative statistics

    Returns:
        Markdown-formatted string
    """
    sections = []

    # Header
    sections.append(_format_header())

    # Summary
    sections.append(_format_summary(report.get('summary', {})))

    # Repository Structures
    if 'repo_structures' in report:
        sections.append(_format_repo_structures(report['repo_structures']))

    # Pattern Adoption Rates
    if 'statistics' in report and 'pattern_adoption_rate' in report['statistics']:
        sections.append(_format_adoption_rates(report['statistics']['pattern_adoption_rate']))

    # Patterns Detected
    if 'patterns' in report:
        sections.append(_format_patterns(report['patterns']))

    # Statistics
    if 'statistics' in report:
        sections.append(_format_statistics(report['statistics']))

    return '\n\n'.join(sections)


def format_summary_only(report: Dict) -> str:
    """
    Format only summary section as Markdown

    Args:
        report: Analysis report dictionary

    Returns:
        Markdown-formatted summary
    """
    sections = [
        _format_header(),
        _format_summary(report.get('summary', {}))
    ]
    return '\n\n'.join(sections)


def format_patterns_only(report: Dict) -> str:
    """
    Format only patterns section as Markdown

    Args:
        report: Analysis report dictionary

    Returns:
        Markdown-formatted patterns
    """
    sections = [
        "# Pattern Analysis\n",
        _format_patterns(report.get('patterns', {}))
    ]
    return '\n\n'.join(sections)


def _format_header() -> str:
    """Generate report header"""
    return "# Repository Analysis Report"


def _format_summary(summary: Dict) -> str:
    """Format summary section"""
    lines = ["## Summary\n"]

    total_skills = summary.get('total_skills_analyzed', 0)
    repos = summary.get('repos_analyzed', [])
    patterns = summary.get('patterns_found', [])

    lines.append(f"- **Total SKILL.md files analyzed**: {total_skills}")
    lines.append(f"- **Repositories analyzed**: {', '.join(repos)}")
    lines.append(f"- **Patterns found**: {', '.join(patterns)}")

    return '\n'.join(lines)


def _format_repo_structures(repo_structures: Dict) -> str:
    """Format repository structures section"""
    lines = ["## Repository Structures\n"]

    for repo_name, repo_data in repo_structures.items():
        lines.append(f"### {repo_name}\n")
        lines.append(f"- **Total skills**: {repo_data.get('total_skills', 0)}")
        lines.append(f"- **Skills with references**: {repo_data.get('skills_with_references', 0)}")
        lines.append(f"- **Has CLAUDE.md**: {repo_data.get('has_claude_md', False)}")
        lines.append(f"- **Has AGENTS.md**: {repo_data.get('has_agents_md', False)}")
        lines.append(f"- **Has skill standards**: {repo_data.get('has_skill_standards', False)}")
        lines.append(f"- **Has PR template**: {repo_data.get('has_pr_template', False)}")
        lines.append(f"- **Has validation CI**: {repo_data.get('has_validation_ci', False)}")

        # Reference files
        ref_files = repo_data.get('reference_files', [])
        if ref_files:
            lines.append(f"\n**Reference files** ({len(ref_files)}):")
            for ref in ref_files[:10]:  # Show first 10
                lines.append(f"  - `{ref}`")
            if len(ref_files) > 10:
                lines.append(f"  - _(and {len(ref_files) - 10} more)_")

        lines.append("")  # Blank line between repos

    return '\n'.join(lines)


def _format_adoption_rates(adoption_rates: Dict) -> str:
    """Format pattern adoption rates section"""
    lines = ["## Pattern Adoption Rates\n"]

    for repo_name, rates in adoption_rates.items():
        lines.append(f"### {repo_name}\n")

        # Create table
        lines.append("| Pattern | Adoption Rate |")
        lines.append("|---------|---------------|")

        for pattern_name, rate in rates.items():
            display_name = pattern_name.replace('_', ' ').title()
            lines.append(f"| {display_name} | {rate} |")

        lines.append("")  # Blank line between repos

    return '\n'.join(lines)


def _format_patterns(patterns: Dict) -> str:
    """Format patterns detected section"""
    lines = ["## Patterns Detected\n"]

    for pattern_name, instances in patterns.items():
        display_name = pattern_name.replace('_', ' ').title()
        lines.append(f"### {display_name}\n")
        lines.append(f"**Found {len(instances)} instances**\n")

        # Show first 10 instances
        for instance in instances[:10]:
            repo = instance.get('repo', 'unknown')
            file = instance.get('file', 'unknown')
            lines.append(f"- **{repo}**: `{file}`")

            # Include count if available
            if 'count' in instance:
                lines.append(f" ({instance['count']} occurrences)")

        if len(instances) > 10:
            lines.append(f"\n_(and {len(instances) - 10} more instances)_")

        lines.append("")  # Blank line between patterns

    return '\n'.join(lines)


def _format_statistics(statistics: Dict) -> str:
    """Format statistics section"""
    lines = ["## Statistics\n"]

    # By-repo statistics
    if 'by_repo' in statistics:
        lines.append("### By Repository\n")

        for repo_name, stats in statistics['by_repo'].items():
            lines.append(f"#### {repo_name}\n")

            for stat_name, value in stats.items():
                display_name = stat_name.replace('_', ' ').title()
                lines.append(f"- **{display_name}**: {value}")

            lines.append("")

    # Averages
    if 'averages' in statistics:
        lines.append("### Averages\n")

        for repo_name, averages in statistics['averages'].items():
            lines.append(f"#### {repo_name}\n")

            for avg_name, value in averages.items():
                display_name = avg_name.replace('_', ' ').title()
                # Format floating point values
                if isinstance(value, float):
                    lines.append(f"- **{display_name}**: {value:.2f}")
                else:
                    lines.append(f"- **{display_name}**: {value}")

            lines.append("")

    return '\n'.join(lines)


def format_comparison_table(reports: List[Dict], repo_names: List[str]) -> str:
    """
    Format side-by-side comparison table for multiple repositories

    Args:
        reports: List of analysis report dictionaries
        repo_names: List of repository names

    Returns:
        Markdown table comparing repositories
    """
    if not reports or not repo_names or len(reports) != len(repo_names):
        return "## Comparison\n\n_Invalid comparison data_"

    lines = ["## Repository Comparison\n"]

    # Extract metrics for each repo
    metrics = []
    for report in reports:
        summary = report.get('summary', {})
        metrics.append({
            'total_skills': summary.get('total_skills_analyzed', 0),
            'patterns_found': len(summary.get('patterns_found', []))
        })

    # Create table
    lines.append("| Metric | " + " | ".join(repo_names) + " |")
    lines.append("|--------|" + "|".join(["--------"] * len(repo_names)) + "|")

    # Total skills row
    skills_row = "| Total Skills | " + " | ".join(str(m['total_skills']) for m in metrics) + " |"
    lines.append(skills_row)

    # Patterns found row
    patterns_row = "| Patterns Found | " + " | ".join(str(m['patterns_found']) for m in metrics) + " |"
    lines.append(patterns_row)

    return '\n'.join(lines)
