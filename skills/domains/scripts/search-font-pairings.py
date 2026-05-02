#!/usr/bin/env python3
"""
Font Pairing Search Utility

Search the font pairings database by keyword (mood, industry, style, font name).
Results are ranked by relevance.

Usage:
    py search-font-pairings.py "elegant wellness"
    py search-font-pairings.py "tech startup"
    py search-font-pairings.py "Playfair"
"""

import re
import sys
from pathlib import Path


def parse_font_pairings(md_content):
    """Parse font-pairings.md and extract structured pairing data."""
    pairings = []
    current_pairing = None

    lines = md_content.split('\n')

    for line in lines:
        # Match pairing headers like "### 1. Classic Elegant"
        header_match = re.match(r'^###\s+\d+\.\s+(.+)$', line)
        if header_match:
            if current_pairing:
                pairings.append(current_pairing)
            current_pairing = {
                'name': header_match.group(1),
                'fonts': '',
                'mood': '',
                'industry': '',
                'notes': ''
            }
            continue

        if current_pairing:
            # Extract Pairing line
            if line.startswith('- **Pairing:**'):
                fonts_text = line.replace('- **Pairing:**', '').strip()
                current_pairing['fonts'] = fonts_text

            # Extract Mood line
            elif line.startswith('- **Mood:**'):
                mood_text = line.replace('- **Mood:**', '').strip()
                current_pairing['mood'] = mood_text

            # Extract Best For line (industry/use case)
            elif line.startswith('- **Best For:**'):
                industry_text = line.replace('- **Best For:**', '').strip()
                current_pairing['industry'] = industry_text

            # Extract Notes line
            elif line.startswith('- **Notes:**'):
                notes_text = line.replace('- **Notes:**', '').strip()
                current_pairing['notes'] = notes_text

    # Don't forget the last pairing
    if current_pairing:
        pairings.append(current_pairing)

    return pairings


def calculate_relevance(pairing, search_terms):
    """Calculate relevance score for a pairing based on search terms."""
    score = 0

    # Combine all searchable text
    searchable_text = ' '.join([
        pairing['name'].lower(),
        pairing['fonts'].lower(),
        pairing['mood'].lower(),
        pairing['industry'].lower(),
        pairing['notes'].lower()
    ])

    for term in search_terms:
        term_lower = term.lower()

        # Exact match in name (highest weight)
        if term_lower in pairing['name'].lower():
            score += 10

        # Exact match in fonts
        if term_lower in pairing['fonts'].lower():
            score += 8

        # Exact match in mood tags (high weight)
        if term_lower in pairing['mood'].lower():
            score += 7

        # Exact match in industry tags
        if term_lower in pairing['industry'].lower():
            score += 6

        # Partial match in notes
        if term_lower in pairing['notes'].lower():
            score += 2

        # Word boundary matches (more precise)
        word_pattern = r'\b' + re.escape(term_lower) + r'\b'
        if re.search(word_pattern, searchable_text):
            score += 3

    return score


def search_pairings(pairings, query):
    """Search pairings and return ranked results."""
    # Split query into search terms
    search_terms = query.split()

    # Calculate scores for all pairings
    scored_pairings = []
    for pairing in pairings:
        score = calculate_relevance(pairing, search_terms)
        if score > 0:
            scored_pairings.append((score, pairing))

    # Sort by score (descending)
    scored_pairings.sort(key=lambda x: x[0], reverse=True)

    return [pairing for _, pairing in scored_pairings]


def format_pairing(index, pairing):
    """Format a pairing for display."""
    output = []
    output.append(f"\n{index}. {pairing['name']}")
    output.append(f"   Fonts: {pairing['fonts']}")

    if pairing['mood']:
        output.append(f"   Mood: {pairing['mood']}")

    if pairing['industry']:
        output.append(f"   Industry: {pairing['industry']}")

    if pairing['notes']:
        output.append(f"   Notes: {pairing['notes']}")

    return '\n'.join(output)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: py search-font-pairings.py \"search terms\"")
        print("\nExamples:")
        print("  py search-font-pairings.py \"elegant wellness\"")
        print("  py search-font-pairings.py \"tech startup\"")
        print("  py search-font-pairings.py \"Playfair\"")
        print("  py search-font-pairings.py \"mobile minimalist\"")
        sys.exit(1)

    # Get search query
    query = ' '.join(sys.argv[1:])

    # Locate the font-pairings.md file
    script_dir = Path(__file__).parent
    md_path = script_dir.parent / 'modes' / 'design' / 'references' / 'font-pairings.md'

    if not md_path.exists():
        print(f"Error: Font pairings file not found at {md_path}")
        sys.exit(1)

    # Read and parse the markdown file
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    pairings = parse_font_pairings(md_content)

    if not pairings:
        print("Error: No pairings found in font-pairings.md")
        sys.exit(1)

    # Search
    results = search_pairings(pairings, query)

    # Display results
    if not results:
        print(f"No matching font pairings found for: {query}")
        print("\nTry searching by:")
        print("  - Mood (elegant, professional, playful, bold, minimal, etc.)")
        print("  - Industry (wellness, tech, fashion, finance, etc.)")
        print("  - Font name (Playfair, Inter, Poppins, etc.)")
        sys.exit(0)

    print(f"Found {len(results)} matching font pairing{'s' if len(results) != 1 else ''} for: {query}")

    # Show top 10 results
    for i, pairing in enumerate(results[:10], 1):
        print(format_pairing(i, pairing))

    if len(results) > 10:
        print(f"\n... and {len(results) - 10} more results. Refine your search for more specific results.")


if __name__ == '__main__':
    main()
