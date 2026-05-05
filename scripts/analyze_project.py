#!/usr/bin/env python3
"""
Project Intelligence CLI

Comprehensive codebase analysis with stack detection, PRD generation,
and health scoring. Wrapper around analyze.engine.analyze_project().

Usage:
    py scripts/analyze_project.py <path> [--quick] [--incremental] [--verbose]

Examples:
    py scripts/analyze_project.py .
    py scripts/analyze_project.py ~/builds/my-app --quick
    py scripts/analyze_project.py . --incremental --verbose
"""

import argparse
import sys
from pathlib import Path
from typing import Optional


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a project with the dream-studio intelligence engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze current directory:
    py scripts/analyze_project.py .

  Quick analysis (skip research):
    py scripts/analyze_project.py ~/builds/my-app --quick

  Incremental analysis (changed files only):
    py scripts/analyze_project.py . --incremental

  Verbose output:
    py scripts/analyze_project.py . --verbose
        """
    )

    parser.add_argument(
        "path",
        type=str,
        help="Path to project directory to analyze (default: current directory)",
        nargs="?",
        default="."
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip research phase for faster analysis"
    )

    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Analyze only files changed since last analysis (requires git)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress during analysis"
    )

    args = parser.parse_args()

    # Validate path
    project_path = Path(args.path).resolve()
    if not project_path.exists():
        print(f"❌ Error: Path does not exist: {project_path}", file=sys.stderr)
        sys.exit(1)

    if not project_path.is_dir():
        print(f"❌ Error: Path is not a directory: {project_path}", file=sys.stderr)
        sys.exit(1)

    # Check for analyze.engine
    try:
        from analyze.engine import analyze_project
    except ImportError as e:
        print(f"❌ Error: Project intelligence engine not installed", file=sys.stderr)
        print(f"The intelligence mode requires Waves 0-4 of project-intelligence to be complete.", file=sys.stderr)
        print(f"Missing module: analyze.engine", file=sys.stderr)
        print(f"\nImport error: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine analysis mode
    run_type = "full"
    skip_phases = []

    if args.quick:
        run_type = "quick"
        skip_phases = ["research"]

    if args.incremental:
        run_type = "incremental"

    # Run analysis
    if args.verbose:
        print(f"🔍 Analyzing project: {project_path}")
        print(f"   Mode: {run_type}")
        if skip_phases:
            print(f"   Skipping phases: {', '.join(skip_phases)}")
        print()

    try:
        result = analyze_project(
            path=project_path,
            run_type=run_type,
            skip_phases=skip_phases
        )
    except Exception as e:
        print(f"❌ Analysis failed: {e}", file=sys.stderr)
        print(f"\nPartial results may be available in the database.", file=sys.stderr)
        print(f"Check logs for details: cat ~/.dream-studio/logs/analysis-errors.log", file=sys.stderr)
        sys.exit(1)

    # Display results
    display_results(result, project_path, args.verbose)


def display_results(result: dict, project_path: Path, verbose: bool = False):
    """Pretty-print analysis results to stdout."""

    status = result.get("status", "unknown")

    if status == "failed":
        error_msg = result.get("error_message", "Unknown error")
        print(f"❌ Analysis failed: {error_msg}", file=sys.stderr)
        return

    print("✅ Project Intelligence Analysis Complete\n")

    # Health score
    health_score = result.get("health_score", 0)
    health_interpretation = get_health_interpretation(health_score)
    print(f"📊 Health Score: {health_score}/10")
    print(f"   {health_interpretation}\n")

    # Stack detection
    stack_name = result.get("stack", {}).get("name", "Unknown")
    stack_confidence = result.get("stack", {}).get("confidence", 0) * 100
    print(f"🔍 Stack Detected: {stack_name} (confidence: {stack_confidence:.0f}%)\n")

    # Findings
    violations = result.get("violations_found", 0)
    bugs = result.get("bugs_found", 0)
    improvements = result.get("improvements_suggested", 0)

    print(f"📈 Findings:")
    print(f"   • {violations} architecture violations")
    print(f"   • {bugs} bugs detected")
    print(f"   • {improvements} improvement opportunities\n")

    # PRD
    prd_path = result.get("prd_path")
    if prd_path:
        print(f"📄 PRD Generated: {prd_path}\n")

    # Dashboard link
    print(f"🔗 View in Dashboard:")
    print(f"   Launch dashboard: py scripts/ds_dashboard.py")
    print(f"   Navigate to Projects tab → {project_path.name}\n")

    # Next steps (top recommendations from improvements)
    recommendations = result.get("top_recommendations", [])
    if recommendations:
        print(f"📋 Next Steps:")
        for i, rec in enumerate(recommendations[:3], 1):
            print(f"   {i}. {rec}")
        print()

    # Verbose output
    if verbose:
        print("🔧 Detailed Results:")
        print(f"   Run ID: {result.get('run_id', 'N/A')}")
        print(f"   Project ID: {result.get('project_id', 'N/A')}")

        duration = result.get("duration_seconds", 0)
        print(f"   Duration: {duration:.1f}s")

        phases = result.get("phases_completed", [])
        if phases:
            print(f"   Phases: {' → '.join(phases)}")


def get_health_interpretation(score: float) -> str:
    """Convert numeric health score to interpretation."""
    if score >= 9:
        return "Excellent — well-architected, minimal issues"
    elif score >= 7:
        return "Good — some minor issues, generally healthy"
    elif score >= 5:
        return "Fair — multiple issues requiring attention"
    elif score >= 3:
        return "Poor — significant technical debt, refactoring recommended"
    else:
        return "Critical — major issues blocking maintainability"


if __name__ == "__main__":
    main()
