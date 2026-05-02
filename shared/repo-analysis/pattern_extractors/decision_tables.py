"""
Decision Tables Pattern Extractor

Detects decision tables/matrices used for routing, classification, or tool selection.
These tables help LLMs make structured decisions based on scenarios, conditions, or goals.
"""

import re
from pathlib import Path
from typing import Dict, List


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract decision table pattern from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'decision_table_count': int,
            'tables': List[str]
        }
    """
    # Pattern: Markdown table with decision-oriented headers
    table_pattern = r'\|[^\n]+\|[^\n]+\|\s*\n\s*\|[-:\s|]+\|\s*\n(\s*\|[^\n]+\|\s*\n)+'

    # Keywords that indicate decision/routing tables
    decision_keywords = [
        'scenario', 'when', 'use', 'why', 'tradeoff', 'approach',
        'situation', 'tool', 'method', 'strategy', 'goal', 'condition',
        'if', 'then', 'choose', 'select', 'route'
    ]

    decision_tables = []

    for table_match in re.finditer(table_pattern, content):
        table = table_match.group(0)
        header = table.split('\n')[0].lower()

        # Check if header contains decision-oriented keywords
        if any(kw in header for kw in decision_keywords):
            decision_tables.append(table)

    return {
        'detected': len(decision_tables) > 0,
        'decision_table_count': len(decision_tables),
        'tables': decision_tables
    }


def analyze_table_structure(table_content: str) -> Dict:
    """
    Analyze the structure of a decision table

    Args:
        table_content: Markdown table content

    Returns:
        Dictionary with table structure analysis:
        {
            'column_count': int,
            'row_count': int,
            'headers': List[str]
        }
    """
    lines = [line.strip() for line in table_content.split('\n') if line.strip()]

    if not lines:
        return {'column_count': 0, 'row_count': 0, 'headers': []}

    # Parse header row
    header_row = lines[0]
    headers = [cell.strip() for cell in header_row.split('|') if cell.strip()]

    # Count data rows (skip header and separator)
    row_count = len(lines) - 2 if len(lines) > 2 else 0

    return {
        'column_count': len(headers),
        'row_count': row_count,
        'headers': headers
    }
