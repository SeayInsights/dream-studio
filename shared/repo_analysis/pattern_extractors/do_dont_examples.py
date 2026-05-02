"""
DO/DON'T Examples Pattern Extractor

Detects side-by-side DO/DON'T examples that show correct vs incorrect patterns.
These examples help LLMs learn from anti-patterns and understand what to avoid.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract DO/DON'T examples pattern from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'do_dont_count': int,
            'patterns': List[Dict]
        }
    """
    # Patterns for DO/DON'T markers
    patterns = [
        (r'❌\s*(DON\'?T|Bad|Wrong|Anti-pattern)', 'emoji_dont'),
        (r'✅\s*(DO|Good|Right|Pattern)', 'emoji_do'),
        (r'\*\*DON\'?T\*\*', 'bold_dont'),
        (r'\*\*DO\*\*', 'bold_do'),
        (r'##\s*DON\'?T', 'header_dont'),
        (r'##\s*DO\s', 'header_do')
    ]

    matches = []
    for pattern, label in patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            matches.append({
                'type': label,
                'position': match.start(),
                'text': match.group(0)
            })

    return {
        'detected': len(matches) > 0,
        'do_dont_count': len(matches),
        'patterns': matches
    }


def extract_example_pairs(content: str) -> List[Tuple[str, str]]:
    """
    Extract DO/DON'T example pairs from content

    Attempts to find matched pairs of DO and DON'T examples that appear close together.

    Args:
        content: Full content of SKILL.md file

    Returns:
        List of (dont_example, do_example) tuples
    """
    pairs = []

    # Pattern: Look for code blocks with DO/DON'T markers nearby
    code_block_pattern = r'```[\s\S]*?```'
    code_blocks = [(m.group(0), m.start()) for m in re.finditer(code_block_pattern, content)]

    dont_pattern = r'(❌|DON\'?T|Bad|Wrong|Anti-pattern)'
    do_pattern = r'(✅|DO(?!\s*N\'?T)|Good|Right|Pattern)'

    for i, (block, pos) in enumerate(code_blocks):
        # Look for DON'T marker before this block
        context_before = content[max(0, pos - 200):pos]

        if re.search(dont_pattern, context_before, re.IGNORECASE):
            # This is a DON'T example, look for corresponding DO example
            if i + 1 < len(code_blocks):
                next_block, next_pos = code_blocks[i + 1]
                context_between = content[pos + len(block):next_pos]

                if re.search(do_pattern, context_between, re.IGNORECASE):
                    pairs.append((block, next_block))

    return pairs
