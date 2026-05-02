"""Integration test: CSVExporter with ReportGenerator

This test verifies that the CSV exporter correctly handles
real report data from ReportGenerator.
"""
import sys
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from analytics.exporters import CSVExporter


def create_realistic_report():
    """Create realistic report data (mimics ReportGenerator output)"""
    return {
        "metadata": {
            "generated_at": "2026-05-01T23:20:00",
            "report_type": "detailed",
            "date_range": {
                "start": "2026-04-01",
                "end": "2026-04-30",
                "days": 30
            }
        },
        "sections": [
            {
                "title": "Overview",
                "metrics": {
                    "total_sessions": 156,
                    "total_skill_invocations": 1234,
                    "total_tokens": 5678901,
                    "total_cost_usd": 123.45,
                    "date_range_days": 30
                },
                "charts": []
            },
            {
                "title": "Top Skills",
                "metrics": {
                    "top_skills": [
                        {"skill": "core:build", "count": 567, "success_rate": 92.5},
                        {"skill": "quality:debug", "count": 234, "success_rate": 88.3},
                        {"skill": "domains:saas-build", "count": 123, "success_rate": 95.1},
                        {"skill": "core:think", "count": 89, "success_rate": 100.0},
                        {"skill": "quality:polish", "count": 67, "success_rate": 91.0}
                    ],
                    "success_rate_overall": 91.8
                },
                "charts": []
            },
            {
                "title": "Token Usage",
                "metrics": {
                    "by_model": {
                        "claude-sonnet-4-5": 3456789,
                        "claude-haiku-4-0": 2222112
                    },
                    "daily_average": 189296.7
                },
                "charts": []
            },
            {
                "title": "Session Analytics",
                "metrics": {
                    "by_project": {
                        "dream-studio": 89,
                        "dreamysuite": 45,
                        "career-studio": 22
                    },
                    "day_of_week": {
                        "Monday": 25,
                        "Tuesday": 30,
                        "Wednesday": 28,
                        "Thursday": 22,
                        "Friday": 20,
                        "Saturday": 18,
                        "Sunday": 13
                    },
                    "outcomes": {
                        "success": 140,
                        "partial": 12,
                        "failed": 4
                    },
                    "avg_duration_minutes": 42.5
                },
                "charts": []
            }
        ]
    }


def test_integration():
    """Test CSVExporter with realistic report data"""

    print("Integration Test: CSVExporter with Report Data")
    print("=" * 60)

    # Create report data
    print("\n1. Creating realistic report data...")
    report = create_realistic_report()
    print(f"   ✓ Report data created")
    print(f"     Type: {report['metadata']['report_type']}")
    print(f"     Sections: {len(report['sections'])}")

    # Initialize exporter
    exporter = CSVExporter()

    # Create output directory
    output_dir = Path("test_output/integration")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n2. Testing CSV exports...")

    # Test 1: Single CSV
    print("   a) Single CSV export")
    success, result = exporter.export_to_csv(
        report,
        output_dir / "integration_single.csv"
    )

    if success:
        print(f"      ✓ Created: {Path(result).name}")
        print(f"        Size: {Path(result).stat().st_size:,} bytes")
    else:
        print(f"      ✗ Failed: {result}")
        return False

    # Test 2: Multiple CSVs
    print("   b) Multiple CSV files")
    success, result = exporter.export_multiple(
        report,
        output_dir / "multiple"
    )

    if success:
        print(f"      ✓ Created {len(result)} files")
    else:
        print(f"      ✗ Failed: {result}")
        return False

    # Test 3: ZIP archive
    print("   c) ZIP archive")
    success, result = exporter.export_as_zip(
        report,
        output_dir / "integration_archive.zip"
    )

    if success:
        print(f"      ✓ Created: {Path(result).name}")
        print(f"        Size: {Path(result).stat().st_size:,} bytes")
    else:
        print(f"      ✗ Failed: {result}")
        return False

    print("\n" + "=" * 60)
    print("✓ Integration test passed!")
    print(f"\nView results in: {output_dir.absolute()}")

    return True


if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)
