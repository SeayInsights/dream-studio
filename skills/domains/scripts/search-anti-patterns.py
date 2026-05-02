#!/usr/bin/env python3
"""
Anti-Pattern Search Utility

Search UX anti-patterns by keyword (category, component, rule).
Usage: py search-anti-patterns.py "button"
"""

import sys
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class AntiPattern:
    """Represents a single anti-pattern entry"""
    number: int
    title: str
    severity: str
    platform: str
    issue: str
    do: str
    dont: str
    category: str

    def matches(self, keyword: str) -> Tuple[bool, int]:
        """
        Check if pattern matches keyword and return relevance score.
        Higher score = better match.

        Returns: (matches: bool, score: int)
        """
        keyword_lower = keyword.lower()

        # Exact match in title (highest priority)
        if keyword_lower in self.title.lower():
            return (True, 100)

        # Exact match in category
        if keyword_lower in self.category.lower():
            return (True, 90)

        # Exact match in issue description
        if keyword_lower in self.issue.lower():
            return (True, 80)

        # Partial match in do/don't
        if keyword_lower in self.do.lower() or keyword_lower in self.dont.lower():
            return (True, 70)

        # Partial match in platform
        if keyword_lower in self.platform.lower():
            return (True, 60)

        return (False, 0)


def parse_anti_patterns(file_path: Path) -> List[AntiPattern]:
    """Parse anti-patterns.md file into structured data"""
    content = file_path.read_text(encoding='utf-8')
    patterns = []
    current_category = ""

    # Split by horizontal rules to get individual patterns
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Track category headers
        if line.startswith('## ') and not line.startswith('## Summary'):
            current_category = line[3:].strip()
            i += 1
            continue

        # Pattern entry starts with ### followed by number
        if line.startswith('###'):
            # Extract number and title
            match = re.match(r'###\s+(\d+)\.\s+(.+?)\s+\((.+?)\s+Severity\)', line)
            if not match:
                i += 1
                continue

            number = int(match.group(1))
            title = match.group(2)
            severity = match.group(3).upper()

            # Parse subsequent lines
            platform = ""
            issue = ""
            do_text = ""
            dont_text = ""

            i += 1
            while i < len(lines) and not lines[i].strip().startswith('---'):
                current = lines[i].strip()

                if current.startswith('**Platform:**'):
                    platform = current.replace('**Platform:**', '').strip()
                elif current.startswith('**Issue:**'):
                    issue = current.replace('**Issue:**', '').strip()
                elif current.startswith('**Do:**'):
                    do_text = current.replace('**Do:**', '').strip()
                    # Continue reading until we hit Don't or code block ends
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith('**Don\'t:**'):
                        if lines[i].strip() and not lines[i].strip().startswith('```'):
                            do_text += ' ' + lines[i].strip()
                        i += 1
                    i -= 1  # Back up one line
                elif current.startswith('**Don\'t:**'):
                    dont_text = current.replace('**Don\'t:**', '').strip()
                    # Continue reading until we hit horizontal rule or next section
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith('---'):
                        if lines[i].strip() and not lines[i].strip().startswith('```') and not lines[i].strip().startswith('#'):
                            dont_text += ' ' + lines[i].strip()
                        i += 1
                    i -= 1  # Back up one line

                i += 1

            pattern = AntiPattern(
                number=number,
                title=title,
                severity=severity,
                platform=platform,
                issue=issue,
                do=do_text,
                dont=dont_text,
                category=current_category
            )
            patterns.append(pattern)

        i += 1

    return patterns


def search_patterns(patterns: List[AntiPattern], keyword: str) -> List[Tuple[AntiPattern, int]]:
    """Search patterns by keyword and return ranked results"""
    results = []

    for pattern in patterns:
        matches, score = pattern.matches(keyword)
        if matches:
            results.append((pattern, score))

    # Sort by score (highest first)
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def format_output(results: List[Tuple[AntiPattern, int]], keyword: str):
    """Format and print search results"""
    if not results:
        print(f"\nNo anti-patterns found matching '{keyword}'")
        return

    print(f"\nFound {len(results)} matching anti-pattern{'s' if len(results) != 1 else ''}:\n")

    for i, (pattern, _) in enumerate(results, 1):
        print(f"{i}. [{pattern.severity}] {pattern.title}")
        print(f"   Category: {pattern.category}")
        print(f"   Platform: {pattern.platform}")
        print(f"   Issue: {pattern.issue}")
        print(f"   Don't: {pattern.dont}")
        print(f"   Do: {pattern.do}")
        print()


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: py search-anti-patterns.py <keyword>")
        print("Example: py search-anti-patterns.py button")
        sys.exit(1)

    keyword = ' '.join(sys.argv[1:])

    # Find anti-patterns.md file
    script_dir = Path(__file__).parent
    anti_patterns_file = script_dir.parent / 'modes' / 'design' / 'references' / 'anti-patterns.md'

    if not anti_patterns_file.exists():
        print(f"Error: Could not find anti-patterns.md at {anti_patterns_file}")
        sys.exit(1)

    # Parse and search
    patterns = parse_anti_patterns(anti_patterns_file)
    results = search_patterns(patterns, keyword)

    # Display results
    format_output(results, keyword)


if __name__ == '__main__':
    main()
