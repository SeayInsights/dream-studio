"""Test script for PDFExporter

Run with: python -m analytics.exporters.test_pdf_exporter
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from analytics.exporters import PDFExporter


def create_sample_report_data():
    """Create sample report data for testing"""
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "security_summary",
            "date_range": {
                "start": "2026-04-01",
                "end": "2026-04-30"
            }
        },
        "sections": [
            {
                "title": "Executive Summary",
                "metrics": {
                    "Total Vulnerabilities": 142,
                    "Critical": 8,
                    "High": 23,
                    "Medium": 67,
                    "Low": 44,
                    "Scan Coverage": "94.2%",
                    "Remediation Rate": "78.5%"
                },
                "charts": [
                    {
                        "type": "bar",
                        "title": "Vulnerabilities by Severity",
                        "data": [8, 23, 67, 44]
                    }
                ]
            },
            {
                "title": "Trend Analysis",
                "metrics": {
                    "New Vulnerabilities (30 days)": 34,
                    "Resolved (30 days)": 56,
                    "Net Change": -22,
                    "Average Time to Remediate": "12.3 days"
                },
                "charts": [
                    {
                        "type": "line",
                        "title": "Monthly Vulnerability Trends",
                        "data": [[120, 135, 128, 142]]
                    }
                ]
            },
            {
                "title": "Repository Breakdown",
                "metrics": {
                    "Total Repositories Scanned": 47,
                    "Repositories with Critical": 5,
                    "Repositories with High": 12,
                    "Clean Repositories": 18
                },
                "charts": [
                    {
                        "type": "pie",
                        "title": "Repository Risk Distribution",
                        "data": [5, 12, 12, 18]
                    }
                ]
            }
        ]
    }


def test_pdf_export():
    """Test PDF export functionality"""
    print("=" * 60)
    print("Testing PDFExporter")
    print("=" * 60)

    # Initialize exporter
    exporter = PDFExporter()
    print(f"\nReportlab available: {exporter.has_reportlab}")
    print(f"Pillow available: {exporter.has_pillow}")

    # Create sample data
    print("\n1. Creating sample report data...")
    report_data = create_sample_report_data()
    print(f"   [OK] Created report with {len(report_data['sections'])} sections")

    # Test export
    print("\n2. Exporting to PDF...")
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "test_report.pdf"

    success, result = exporter.export_to_pdf(report_data, str(output_path))

    if success:
        print(f"   [OK] PDF exported successfully")
        print(f"   Location: {result}")

        # Check file size
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            print(f"   File size: {size:,} bytes")
    else:
        print(f"   [FAIL] Export failed: {result}")
        return False

    # Test validation
    print("\n3. Testing validation...")

    # Invalid data structure
    success, result = exporter.export_to_pdf({}, str(output_path))
    if not success:
        print(f"   [OK] Correctly rejected invalid data: {result}")
    else:
        print(f"   [FAIL] Should have rejected invalid data")

    # Missing metadata
    success, result = exporter.export_to_pdf({"sections": []}, str(output_path))
    if not success:
        print(f"   [OK] Correctly rejected missing metadata: {result}")
    else:
        print(f"   [FAIL] Should have rejected missing metadata")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

    if exporter.has_reportlab:
        print("\n[OK] Full PDF functionality available")
        print(f"  Open the PDF: {output_path}")
    else:
        print("\nWARNING: Running in text-only fallback mode")
        print("   Install reportlab for full PDF support:")
        print("   pip install reportlab Pillow")

    return True


if __name__ == "__main__":
    test_pdf_export()
