"""
Progressive Disclosure Pattern Extractor

Detects progressive disclosure pattern: SKILL.md files with links to references/ subdirectory.
This pattern indicates documentation that provides overview in main file with deep-dive details
available through reference links.
"""

import re
from pathlib import Path
from typing import Dict, List


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract progressive disclosure pattern from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'reference_link_count': int,
            'reference_links': List[str],
            'anchor_link_count': int
        }
    """
    # Pattern: [link text](references/filename.md)
    reference_pattern = r'\[.*?\]\(references/.*?\.md.*?\)'
    reference_links = re.findall(reference_pattern, content)

    # Pattern: [link text](#anchor) or [link text](file.md#anchor)
    anchor_pattern = r'\[.*?\]\(.*?#.*?\)'
    anchor_links = re.findall(anchor_pattern, content)

    return {
        'detected': len(reference_links) > 0,
        'reference_link_count': len(reference_links),
        'reference_links': reference_links,
        'anchor_link_count': len(anchor_links)
    }


def analyze_references_directory(skill_file_path: Path) -> Dict:
    """
    Analyze collocated references/ directory structure

    Args:
        skill_file_path: Path to SKILL.md file

    Returns:
        Dictionary with reference directory analysis:
        {
            'has_references_dir': bool,
            'reference_files': List[str],
            'reference_file_count': int
        }
    """
    ref_dir = skill_file_path.parent / 'references'

    if not ref_dir.exists() or not ref_dir.is_dir():
        return {
            'has_references_dir': False,
            'reference_files': [],
            'reference_file_count': 0
        }

    # List all .md files in references/
    reference_files = list(ref_dir.glob('*.md'))

    return {
        'has_references_dir': True,
        'reference_files': [f.name for f in reference_files],
        'reference_file_count': len(reference_files)
    }
