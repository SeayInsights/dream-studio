"""
JSON Report Formatter

Formats repository analysis results as structured JSON.
"""

import json
from typing import Dict


def format_report(report: Dict) -> str:
    """
    Format analysis report as JSON

    Args:
        report: Analysis report dictionary with:
            - summary: aggregate metrics
            - repo_structures: repository organization
            - skill_analyses: individual SKILL.md analyses
            - patterns: detected patterns
            - statistics: comparative statistics

    Returns:
        JSON-formatted string
    """
    return json.dumps(report, indent=2, ensure_ascii=False)


def format_compact(report: Dict) -> str:
    """
    Format analysis report as compact JSON (no indentation)

    Args:
        report: Analysis report dictionary

    Returns:
        Compact JSON-formatted string
    """
    return json.dumps(report, separators=(',', ':'), ensure_ascii=False)


def format_summary_only(report: Dict) -> str:
    """
    Format only the summary section as JSON

    Args:
        report: Analysis report dictionary

    Returns:
        JSON-formatted summary string
    """
    summary_report = {
        'summary': report.get('summary', {}),
        'statistics': report.get('statistics', {})
    }
    return json.dumps(summary_report, indent=2, ensure_ascii=False)


def format_patterns_only(report: Dict) -> str:
    """
    Format only the patterns section as JSON

    Args:
        report: Analysis report dictionary

    Returns:
        JSON-formatted patterns string
    """
    patterns_report = {
        'patterns': report.get('patterns', {}),
        'pattern_count': {
            pattern_name: len(instances)
            for pattern_name, instances in report.get('patterns', {}).items()
        }
    }
    return json.dumps(patterns_report, indent=2, ensure_ascii=False)
