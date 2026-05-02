"""
Version Guards Pattern Extractor

Detects version-specific guards and compatibility notes (e.g., "Terraform 1.6+", "Python 3.10+").
These guards help LLMs provide version-appropriate recommendations.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract version guard pattern from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'version_guard_count': int,
            'version_guards': List[Dict]
        }
    """
    # Pattern: Tool/language name followed by version number with +
    version_patterns = [
        (r'Terraform\s+([\d.]+)\+', 'Terraform'),
        (r'OpenTofu\s+([\d.]+)\+', 'OpenTofu'),
        (r'Python\s+([\d.]+)\+', 'Python'),
        (r'Node(?:\.js)?\s+([\d.]+)\+', 'Node.js'),
        (r'npm\s+([\d.]+)\+', 'npm'),
        (r'pnpm\s+([\d.]+)\+', 'pnpm'),
        (r'React\s+([\d.]+)\+', 'React'),
        (r'Next\.js\s+([\d.]+)\+', 'Next.js'),
        (r'TypeScript\s+([\d.]+)\+', 'TypeScript'),
        (r'Go\s+([\d.]+)\+', 'Go'),
        (r'Rust\s+([\d.]+)\+', 'Rust'),
        (r'Docker\s+([\d.]+)\+', 'Docker'),
        (r'Kubernetes\s+([\d.]+)\+', 'Kubernetes')
    ]

    version_guards = []

    for pattern, tool_name in version_patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            version = match.group(1)
            version_guards.append({
                'tool': tool_name,
                'version': version,
                'raw_text': match.group(0),
                'position': match.start()
            })

    return {
        'detected': len(version_guards) > 0,
        'version_guard_count': len(version_guards),
        'version_guards': version_guards
    }


def extract_compatibility_notes(content: str) -> List[Dict]:
    """
    Extract compatibility notes and breaking changes

    Args:
        content: Full content of SKILL.md file

    Returns:
        List of compatibility notes with context
    """
    compatibility_keywords = [
        'breaking change',
        'compatibility',
        'deprecated',
        'removed in',
        'added in',
        'available since',
        'requires',
        'minimum version'
    ]

    notes = []

    for keyword in compatibility_keywords:
        pattern = rf'.*{re.escape(keyword)}.*'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            line = match.group(0).strip()
            notes.append({
                'keyword': keyword,
                'line': line,
                'position': match.start()
            })

    return notes
