"""
Frontmatter Pattern Extractor

Detects and parses YAML frontmatter in SKILL.md files.
Frontmatter provides structured metadata for skill routing, categorization, and discovery.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Tuple


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract frontmatter pattern from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'frontmatter': Dict,
            'keys': List[str],
            'triggers': List[str]
        }
    """
    has_fm, fm_data = parse_frontmatter(content)

    if not has_fm:
        return {
            'detected': False,
            'frontmatter': {},
            'keys': [],
            'triggers': []
        }

    # Extract trigger keywords from frontmatter
    triggers = extract_trigger_keywords(fm_data)

    return {
        'detected': True,
        'frontmatter': fm_data,
        'keys': list(fm_data.keys()),
        'triggers': triggers
    }


def parse_frontmatter(content: str) -> Tuple[bool, Dict]:
    """
    Parse YAML frontmatter from markdown content

    Args:
        content: Full markdown content

    Returns:
        Tuple of (has_frontmatter: bool, frontmatter_data: Dict)
    """
    if not content.startswith('---'):
        return False, {}

    # Split on --- delimiters
    parts = content.split('---', 2)

    if len(parts) < 3:
        return False, {}

    try:
        fm_data = yaml.safe_load(parts[1])
        return True, fm_data or {}
    except yaml.YAMLError:
        return False, {}


def extract_trigger_keywords(frontmatter: Dict) -> List[str]:
    """
    Extract trigger keywords from frontmatter

    Common frontmatter keys for triggers:
    - triggers
    - keywords
    - tags
    - aliases

    Args:
        frontmatter: Parsed frontmatter dictionary

    Returns:
        List of trigger keywords
    """
    triggers = []

    # Check multiple possible keys
    trigger_keys = ['triggers', 'keywords', 'tags', 'aliases']

    for key in trigger_keys:
        if key in frontmatter:
            value = frontmatter[key]

            # Handle both string and list values
            if isinstance(value, list):
                triggers.extend(value)
            elif isinstance(value, str):
                triggers.append(value)

    return triggers


def extract_metadata_schema(frontmatter: Dict) -> Dict:
    """
    Analyze frontmatter schema structure

    Args:
        frontmatter: Parsed frontmatter dictionary

    Returns:
        Schema analysis:
        {
            'fields': List[str],
            'field_types': Dict[str, str],
            'required_fields': List[str]
        }
    """
    fields = list(frontmatter.keys())

    # Infer field types
    field_types = {}
    for key, value in frontmatter.items():
        field_types[key] = type(value).__name__

    # Common required fields in SKILL.md frontmatter
    common_required = ['name', 'description', 'version']
    required_fields = [f for f in common_required if f in fields]

    return {
        'fields': fields,
        'field_types': field_types,
        'required_fields': required_fields
    }
