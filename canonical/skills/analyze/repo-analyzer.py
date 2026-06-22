#!/usr/bin/env python3
"""
Repository Analysis Integration for Analyze Pack

Integrates shared/repo-analysis utility with dream-studio analyze pack.
Enables multi-perspective analysis of repository patterns and organizational structures.

Supports domain-specific analysis (design, career, finance, real estate) and
general SKILL.md pattern analysis.

Usage:
    from skills.analyze.repo_analyzer import analyze_repositories

    # Domain-specific analysis
    result = analyze_repositories(['/path/to/repo1'], domain='design')

    # General SKILL.md pattern analysis (backward compatible)
    result = analyze_repositories(['/path/to/repo1'])
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Union

# Add parent directory to path to import shared modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.repo_analysis.analyzer import RepoAnalyzer
from shared.repo_analysis.formatters import json_formatter, markdown_formatter

# Import domain registry
try:
    from skills.analyze.domains import DomainAnalyzerRegistry

    DOMAIN_SUPPORT = True
except ImportError:
    DOMAIN_SUPPORT = False
    print(
        "[WARN] Domain analyzers not available. Install domain analyzers or use general analysis only."
    )


def analyze_repositories(
    repo_paths: List[str],
    output_format: str = "dict",
    patterns_filter: Optional[List[str]] = None,
    domain: Optional[str] = None,
    verbose: bool = False,
) -> Union[Dict, str]:
    """
    Analyze repositories for SKILL.md patterns or domain-specific capabilities

    Args:
        repo_paths: List of repository directory paths to analyze
        output_format: Output format ('dict', 'json', 'markdown')
        patterns_filter: Optional list of pattern names to include (None = all)
        domain: Optional domain name ('design', 'career', 'finance', 'real_estate')
                If None, uses general SKILL.md pattern analysis or auto-detects
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

    valid_formats = {"dict", "json", "markdown"}
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

    # Choose analysis method based on domain
    if domain and domain != "general" and DOMAIN_SUPPORT:
        # Domain-specific analysis
        return _analyze_domain_specific(
            validated_repos, domain, output_format, patterns_filter, verbose
        )
    # General SKILL.md pattern analysis (backward compatible)
    return _analyze_general_patterns(validated_repos, output_format, patterns_filter, verbose)


def analyze_single_repo(
    repo_path: str, output_format: str = "dict", verbose: bool = False
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
    repo_paths: List[str], focus_patterns: Optional[List[str]] = None, verbose: bool = False
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
        repo_paths, output_format="dict", patterns_filter=focus_patterns, verbose=verbose
    )

    # Build comparison matrix
    comparison = {
        "repositories": report["summary"]["repos_analyzed"],
        "comparison_matrix": {},
        "recommendations": [],
    }

    # Extract pattern adoption rates
    if "statistics" in report and "pattern_adoption_rate" in report["statistics"]:
        comparison["comparison_matrix"] = report["statistics"]["pattern_adoption_rate"]

    # Generate recommendations
    comparison["recommendations"] = _generate_recommendations(report)

    return comparison


def extract_patterns_for_enhancement(
    source_repos: List[str],
    target_repo: str,
    min_adoption_threshold: float = 0.5,
    verbose: bool = False,
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

    if "statistics" in report and "pattern_adoption_rate" in report["statistics"]:
        adoption_rates = report["statistics"]["pattern_adoption_rate"]
        target_rates = adoption_rates.get(target_name, {})

        # Calculate average adoption in source repos
        for pattern_name in adoption_rates.get(list(adoption_rates.keys())[0], {}).keys():
            source_adoption_rates = []

            for source_repo in source_repos:
                source_name = Path(source_repo).name
                if source_name in adoption_rates:
                    rate_str = adoption_rates[source_name].get(pattern_name, "0%")
                    rate = float(rate_str.rstrip("%")) / 100
                    source_adoption_rates.append(rate)

            if source_adoption_rates:
                avg_source_adoption = sum(source_adoption_rates) / len(source_adoption_rates)
                target_rate_str = target_rates.get(pattern_name, "0%")
                target_adoption = float(target_rate_str.rstrip("%")) / 100

                # Recommend if well-adopted in sources but low in target
                if (
                    avg_source_adoption >= min_adoption_threshold
                    and target_adoption < min_adoption_threshold
                ):
                    recommended_patterns.append(
                        {
                            "pattern": pattern_name,
                            "source_adoption": f"{avg_source_adoption * 100:.1f}%",
                            "target_adoption": f"{target_adoption * 100:.1f}%",
                            "gap": f"{(avg_source_adoption - target_adoption) * 100:.1f}%",
                        }
                    )

    return {
        "target_repo": target_name,
        "source_repos": [Path(r).name for r in source_repos],
        "recommended_patterns": recommended_patterns,
        "estimated_effort": _estimate_effort(recommended_patterns),
    }


def _filter_patterns(report: Dict, pattern_filter: List[str]) -> Dict:
    """Filter report to include only specified patterns"""
    filtered_patterns = {k: v for k, v in report.get("patterns", {}).items() if k in pattern_filter}

    report["patterns"] = filtered_patterns
    report["summary"]["patterns_found"] = list(filtered_patterns.keys())

    return report


def _generate_recommendations(report: Dict) -> List[str]:
    """Generate actionable recommendations from analysis report"""
    recommendations = []

    # Check for missing progressive disclosure
    for repo_name, repo_data in report.get("repo_structures", {}).items():
        skills_with_refs = repo_data.get("skills_with_references", 0)
        total_skills = repo_data.get("total_skills", 0)

        if total_skills > 0 and skills_with_refs == 0:
            recommendations.append(
                f"{repo_name}: Consider adding references/ directories for progressive disclosure"
            )

    # Check for missing CI validation
    for repo_name, repo_data in report.get("repo_structures", {}).items():
        if not repo_data.get("has_validation_ci", False):
            recommendations.append(f"{repo_name}: Add CI validation workflow for quality gates")

    # Check for low pattern adoption
    if "statistics" in report and "pattern_adoption_rate" in report["statistics"]:
        for repo_name, rates in report["statistics"]["pattern_adoption_rate"].items():
            low_patterns = [
                pattern for pattern, rate in rates.items() if float(rate.rstrip("%")) < 30
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
    if pattern_count <= 2:
        return f"{pattern_count * 4}-{pattern_count * 6} hours (small)"
    if pattern_count <= 5:
        return f"{pattern_count * 6}-{pattern_count * 10} hours (medium)"
    return f"{pattern_count * 8}-{pattern_count * 15} hours (large)"


def _analyze_general_patterns(
    validated_repos: List[tuple],
    output_format: str,
    patterns_filter: Optional[List[str]],
    verbose: bool,
) -> Union[Dict, str]:
    """
    Run general SKILL.md pattern analysis (backward compatible)

    Args:
        validated_repos: List of (repo_path, repo_name) tuples
        output_format: Output format
        patterns_filter: Optional pattern filter
        verbose: Verbose output

    Returns:
        Analysis report
    """
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
    if output_format == "json":
        return json_formatter.format_report(report)
    if output_format == "markdown":
        return markdown_formatter.format_report(report)
    # dict
    return report


def _analyze_domain_specific(
    validated_repos: List[tuple],
    domain: str,
    output_format: str,
    capabilities_filter: Optional[List[str]],
    verbose: bool,
) -> Union[Dict, str]:
    """
    Run domain-specific capability analysis

    Args:
        validated_repos: List of (repo_path, repo_name) tuples
        domain: Domain name
        output_format: Output format
        capabilities_filter: Optional capability filter
        verbose: Verbose output

    Returns:
        Analysis report
    """
    results = {
        "domain": domain,
        "repositories": [],
        "capability_matrix": {},
        "unique_features": {},
        "overall_scores": {},
        "best_in_class": {},
    }

    # Analyze each repository
    for repo_path, repo_name in validated_repos:
        if verbose:
            print(f"\n[{domain.upper()}] Analyzing {repo_name}...")

        # Get domain analyzer
        analyzer = DomainAnalyzerRegistry.get_analyzer(domain, repo_path, repo_name)

        # Get capabilities
        capabilities = analyzer.get_capabilities()
        if capabilities_filter:
            capabilities = [c for c in capabilities if c in capabilities_filter]

        # Analyze each capability
        capability_scores = {}
        for cap in capabilities:
            if verbose:
                print(f"  - Analyzing {cap}...")
            result = analyzer.analyze_capability(cap)
            capability_scores[cap] = result["score"]

        # Get overall scores
        scores = analyzer.score_repository()

        # Get unique features
        unique_features = analyzer.get_unique_features()

        # Store results
        results["repositories"].append(repo_name)
        results["capability_matrix"][repo_name] = capability_scores
        results["overall_scores"][repo_name] = scores.get("overall_score", 0.0)
        if unique_features:
            results["unique_features"][repo_name] = unique_features

    # Calculate best-in-class for each capability
    if results["capability_matrix"]:
        all_capabilities = set()
        for repo_scores in results["capability_matrix"].values():
            all_capabilities.update(repo_scores.keys())

        for cap in all_capabilities:
            best_repo = None
            best_score = 0
            for repo_name, scores in results["capability_matrix"].items():
                if cap in scores and scores[cap] > best_score:
                    best_score = scores[cap]
                    best_repo = repo_name

            if best_repo:
                results["best_in_class"][cap] = {"repository": best_repo, "score": best_score}

    # Format output
    if output_format == "json":
        import json

        return json.dumps(results, indent=2)
    if output_format == "markdown":
        return _format_domain_results_markdown(results)
    # dict
    return results


def _format_domain_results_markdown(results: Dict) -> str:
    """Format domain-specific results as markdown"""
    lines = [
        f"# {results['domain'].title()} Skill Analysis",
        "",
        "## Summary",
        f"- Analyzed repositories: {', '.join(results['repositories'])}",
        f"- Domain: {results['domain']}",
        "",
        "## Overall Scores",
        "",
    ]

    # Overall scores table
    lines.append("| Repository | Overall Score |")
    lines.append("|------------|---------------|")
    for repo in results["repositories"]:
        score = results["overall_scores"].get(repo, 0.0)
        lines.append(f"| {repo} | {score:.1f}/10 |")

    lines.append("")
    lines.append("## Capability Matrix")
    lines.append("")

    # Capability matrix table
    if results["capability_matrix"]:
        # Get all capabilities
        all_caps = set()
        for scores in results["capability_matrix"].values():
            all_caps.update(scores.keys())
        all_caps = sorted(all_caps)

        # Header
        header = "| Capability | " + " | ".join(results["repositories"]) + " | Best |"
        lines.append(header)
        lines.append("|" + "|".join(["-" * 12] * (len(results["repositories"]) + 2)) + "|")

        # Rows
        for cap in all_caps:
            row = [cap]
            for repo in results["repositories"]:
                score = results["capability_matrix"][repo].get(cap, 0.0)
                row.append(f"{score:.1f}")

            best = results["best_in_class"].get(cap, {})
            best_repo = best.get("repository", "")
            row.append(best_repo)

            lines.append("| " + " | ".join(row) + " |")

    # Unique features
    if results["unique_features"]:
        lines.append("")
        lines.append("## Unique Features")
        lines.append("")
        for repo, features in results["unique_features"].items():
            lines.append(f"### {repo}")
            lines.append("")
            for feature in features:
                lines.append(f"- {feature}")
            lines.append("")

    return "\n".join(lines)


# CLI interface for standalone usage
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze repositories for dream-studio analyze pack"
    )
    parser.add_argument("repos", nargs="+", help="Repository paths to analyze")
    parser.add_argument("--format", choices=["dict", "json", "markdown"], default="markdown")
    parser.add_argument("--patterns", nargs="*", help="Filter specific patterns or capabilities")
    parser.add_argument(
        "--domain",
        type=str,
        help="Domain for analysis (design, career, finance, real_estate, general)",
    )
    parser.add_argument("--list-domains", action="store_true", help="List available domains")
    parser.add_argument(
        "--auto-detect", action="store_true", help="Auto-detect domain from repository contents"
    )
    parser.add_argument("--compare", action="store_true", help="Generate comparison report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.list_domains:
        if DOMAIN_SUPPORT:
            domains = DomainAnalyzerRegistry.list_domains()
            info = DomainAnalyzerRegistry.get_domain_info()
            print("\nAvailable Domains:")
            for domain in domains:
                domain_info = info[domain]
                print(f"\n  {domain}:")
                print(f"    Class: {domain_info['class']}")
                print(f"    Capabilities: {domain_info['capabilities_count']}")
                print(f"    Markers: {', '.join(domain_info['markers'][:3])}...")
        else:
            print("\nDomain support not available. Install domain analyzers.")
        exit(0)

    # Auto-detect domain if requested
    domain = args.domain
    if args.auto_detect and len(args.repos) == 1:
        if DOMAIN_SUPPORT:
            domain = DomainAnalyzerRegistry.auto_detect_domain(
                Path(args.repos[0]), verbose=args.verbose
            )
            print(f"[AUTO-DETECT] Domain: {domain}\n")
        else:
            print("[WARN] Auto-detect not available without domain support")

    if args.compare:
        result = compare_repositories(
            args.repos, focus_patterns=args.patterns, verbose=args.verbose
        )
        print(json_formatter.format_report(result))
    else:
        result = analyze_repositories(
            args.repos,
            output_format=args.format,
            patterns_filter=args.patterns,
            domain=domain,
            verbose=args.verbose,
        )
        print(result)
