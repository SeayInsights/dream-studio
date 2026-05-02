#!/usr/bin/env python
"""
Generate Analytics Dashboard - One-command dashboard generation

Usage:
    python scripts/generate-dashboard.py [days] [output]

Examples:
    python scripts/generate-dashboard.py                    # Last 30 days, default output
    python scripts/generate-dashboard.py 90                 # Last 90 days
    python scripts/generate-dashboard.py 30 dashboard.html  # Custom output path
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.generators import generate_dashboard


def main():
    days = 30
    output = "analytics_dashboard.html"

    if len(sys.argv) > 1:
        days = int(sys.argv[1])

    if len(sys.argv) > 2:
        output = sys.argv[2]

    print("=" * 70)
    print("🚀 Dream-Studio Analytics Dashboard Generator")
    print("=" * 70)
    print()

    try:
        path = generate_dashboard(days=days, output=output)
        print()
        print("=" * 70)
        print(f"🎉 Success! Dashboard saved to: {os.path.abspath(path)}")
        print("=" * 70)
        print()
        print("📖 To view: Open the HTML file in your browser")
        print()

    except Exception as e:
        print()
        print("❌ Error generating dashboard:")
        print(f"   {str(e)}")
        print()
        print("💡 Tip: Make sure you have analytics data in ~/.dream-studio/studio.db")
        sys.exit(1)


if __name__ == "__main__":
    main()
