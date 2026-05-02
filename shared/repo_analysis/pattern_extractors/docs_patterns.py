"""
Documentation Patterns Extractor

Detects documentation quality indicators, inline documentation, and doc structure.
Helps identify documentation maturity and coverage across repositories.
"""

import re
from pathlib import Path
from typing import Dict, List


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract documentation pattern indicators from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'doc_sections': List[str],
            'has_examples': bool,
            'has_api_docs': bool
        }
    """
    content_lower = content.lower()

    # Documentation section headers
    doc_sections = []
    section_patterns = {
        'usage': r'##\s+usage',
        'examples': r'##\s+examples?',
        'api': r'##\s+(api|reference)',
        'installation': r'##\s+(installation|setup|getting started)',
        'configuration': r'##\s+configuration',
        'troubleshooting': r'##\s+troubleshooting',
        'contributing': r'##\s+contributing',
        'changelog': r'##\s+(changelog|history|releases)',
        'faq': r'##\s+(faq|frequently asked questions)'
    }

    for section_name, pattern in section_patterns.items():
        if re.search(pattern, content_lower):
            doc_sections.append(section_name)

    # Check for examples
    has_examples = 'example' in content_lower or '```' in content

    # Check for API documentation indicators
    api_keywords = ['endpoint', 'parameter', 'returns', 'response', 'request']
    has_api_docs = any(kw in content_lower for kw in api_keywords)

    return {
        'detected': len(doc_sections) > 0,
        'doc_sections': doc_sections,
        'has_examples': has_examples,
        'has_api_docs': has_api_docs
    }


def analyze_readme_quality(repo_path: Path) -> Dict:
    """
    Analyze README.md quality and completeness

    Args:
        repo_path: Path to repository root

    Returns:
        Dictionary with README analysis:
        {
            'has_readme': bool,
            'readme_length': int,
            'has_badges': bool,
            'has_toc': bool,
            'sections': List[str]
        }
    """
    readme_path = repo_path / 'README.md'

    if not readme_path.exists():
        return {
            'has_readme': False,
            'readme_length': 0,
            'has_badges': False,
            'has_toc': False,
            'sections': []
        }

    try:
        content = readme_path.read_text(encoding='utf-8', errors='ignore')
    except (IOError, OSError):
        return {
            'has_readme': True,
            'readme_length': 0,
            'has_badges': False,
            'has_toc': False,
            'sections': []
        }

    # Check for badges (shields.io, etc.)
    badge_pattern = r'!\[.*?\]\(https://img\.shields\.io'
    has_badges = bool(re.search(badge_pattern, content))

    # Check for table of contents
    toc_patterns = [
        r'##\s+table of contents',
        r'\[.*?\]\(#.*?\).*\[.*?\]\(#.*?\)',  # Multiple anchor links
    ]
    has_toc = any(re.search(p, content, re.IGNORECASE) for p in toc_patterns)

    # Extract sections
    sections = re.findall(r'^#{2,3}\s+(.+)$', content, re.MULTILINE)

    return {
        'has_readme': True,
        'readme_length': len(content),
        'has_badges': has_badges,
        'has_toc': has_toc,
        'sections': sections[:20]  # Limit to first 20 sections
    }


def analyze_inline_docs(repo_path: Path, extensions: List[str] = []) -> Dict:
    """
    Analyze inline code documentation (docstrings, JSDoc, etc.)

    Args:
        repo_path: Path to repository root
        extensions: File extensions to check (e.g., ['.py', '.js', '.ts'])

    Returns:
        Dictionary with inline doc analysis:
        {
            'files_with_docstrings': int,
            'total_docstrings': int,
            'doc_style': str
        }
    """
    if not extensions:
        extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs']

    files_with_docstrings = 0
    total_docstrings = 0
    doc_styles = []

    # Sample up to 50 files (performance limit)
    sample_files = []
    for ext in extensions:
        sample_files.extend(list(repo_path.rglob(f'*{ext}'))[:50])

    for file_path in sample_files[:50]:
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')

            # Python docstrings
            py_docstrings = re.findall(r'"""[\s\S]*?"""', content)
            if py_docstrings:
                doc_styles.append('python-docstring')
                total_docstrings += len(py_docstrings)

            # JSDoc comments
            jsdoc_pattern = r'/\*\*[\s\S]*?\*/'
            jsdoc_comments = re.findall(jsdoc_pattern, content)
            if jsdoc_comments:
                doc_styles.append('jsdoc')
                total_docstrings += len(jsdoc_comments)

            # Go doc comments
            go_doc_pattern = r'//\s+\w+\s+.*\n(?://.*\n)*func'
            go_docs = re.findall(go_doc_pattern, content)
            if go_docs:
                doc_styles.append('go-doc')
                total_docstrings += len(go_docs)

            if py_docstrings or jsdoc_comments or go_docs:
                files_with_docstrings += 1

        except (IOError, OSError):
            continue

    # Determine primary doc style
    primary_style = max(set(doc_styles), key=doc_styles.count) if doc_styles else None

    return {
        'files_with_docstrings': files_with_docstrings,
        'total_docstrings': total_docstrings,
        'doc_style': primary_style
    }
