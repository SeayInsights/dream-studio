"""Test suite for PPTXExporter

Tests PowerPoint export functionality with various data structures and scenarios.
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 output for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from analytics.exporters.pptx_exporter import PPTXExporter


def test_basic_export():
    """Test basic PowerPoint export with minimal data"""
    print("Test 1: Basic export with minimal data")

    exporter = PPTXExporter()

    # Minimal report data
    report_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "test",
            "date_range": {"start": "2026-04-01", "end": "2026-04-30"}
        },
        "sections": [
            {
                "title": "Test Section",
                "metrics": {"Test Metric": 123},
                "charts": []
            }
        ]
    }

    # Export to temp file
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        output_path = tmp.name

    try:
        success, result = exporter.export_to_pptx(report_data, output_path)

        if success:
            print(f"  ✓ Export successful: {result}")
            print(f"  ✓ File exists: {os.path.exists(result)}")
            print(f"  ✓ File size: {os.path.getsize(result)} bytes")
        else:
            print(f"  ✗ Export failed: {result}")

    finally:
        # Cleanup
        if os.path.exists(output_path):
            os.unlink(output_path)

    print()


def test_full_featured_export():
    """Test PowerPoint export with comprehensive data"""
    print("Test 2: Full-featured export with multiple sections")

    exporter = PPTXExporter()

    # Comprehensive report data
    report_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "executive",
            "date_range": {"start": "2026-04-01", "end": "2026-04-30"}
        },
        "sections": [
            {
                "title": "Key Performance Indicators",
                "metrics": {
                    "Total Users": 15234,
                    "Active Users": 12458,
                    "Conversion Rate": 0.0823,
                    "Revenue (USD)": 125430.50,
                    "Churn Rate": 0.0234,
                    "Customer Satisfaction": 4.7
                },
                "charts": []
            },
            {
                "title": "User Growth Trends",
                "metrics": {},
                "charts": [
                    {
                        "title": "Monthly Active Users",
                        "type": "line",
                        "image_path": None  # Would be path to chart image
                    }
                ]
            },
            {
                "title": "Revenue Analysis",
                "metrics": {
                    "Q1 Revenue": 125430.50,
                    "Q2 Target": 150000.00,
                    "Growth Rate": 0.15,
                    "Target Achievement": 0.95
                },
                "charts": []
            },
            {
                "title": "Regional Performance",
                "metrics": {
                    "North America": 45000,
                    "Europe": 38000,
                    "Asia Pacific": 28000,
                    "Latin America": 14430.50
                },
                "charts": []
            }
        ]
    }

    # Export to temp file
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        output_path = tmp.name

    try:
        success, result = exporter.export_to_pptx(report_data, output_path)

        if success:
            print(f"  ✓ Export successful: {result}")
            print(f"  ✓ File exists: {os.path.exists(result)}")
            print(f"  ✓ File size: {os.path.getsize(result)} bytes")

            # Count expected slides
            num_sections = len(report_data["sections"])
            # Title + TOC + sections + closing = expected slides
            expected_slides = 1 + 1 + num_sections + 1
            print(f"  ✓ Expected slides: ~{expected_slides}")
        else:
            print(f"  ✗ Export failed: {result}")

    finally:
        # Cleanup
        if os.path.exists(output_path):
            os.unlink(output_path)

    print()


def test_validation():
    """Test input validation"""
    print("Test 3: Input validation")

    exporter = PPTXExporter()

    # Test invalid data structures
    test_cases = [
        ("Empty dict", {}),
        ("Missing metadata", {"sections": []}),
        ("Missing sections", {"metadata": {}}),
        ("Invalid sections type", {"metadata": {}, "sections": "not a list"}),
    ]

    for test_name, invalid_data in test_cases:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
            output_path = tmp.name

        try:
            success, result = exporter.export_to_pptx(invalid_data, output_path)

            if not success:
                print(f"  ✓ {test_name}: Correctly rejected - {result}")
            else:
                print(f"  ✗ {test_name}: Should have failed but succeeded")

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    print()


def test_empty_sections():
    """Test export with empty sections"""
    print("Test 4: Export with empty sections")

    exporter = PPTXExporter()

    # Report with no metrics or charts
    report_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "test",
        },
        "sections": []
    }

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        output_path = tmp.name

    try:
        success, result = exporter.export_to_pptx(report_data, output_path)

        if success:
            print(f"  ✓ Export with no sections successful: {result}")
            print(f"  ✓ File size: {os.path.getsize(result)} bytes")
        else:
            print(f"  ✗ Export failed: {result}")

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)

    print()


def test_chart_integration():
    """Test chart rendering integration"""
    print("Test 5: Chart rendering integration")

    from analytics.exporters.chart_renderer import ChartRenderer

    exporter = PPTXExporter()
    chart_renderer = ChartRenderer()

    # Create a sample chart
    chart_config = {
        "type": "bar",
        "title": "Monthly Revenue",
        "data": {
            "labels": ["Jan", "Feb", "Mar", "Apr"],
            "datasets": [
                {
                    "label": "Revenue",
                    "data": [25000, 30000, 28000, 35000]
                }
            ]
        }
    }

    # Render chart to temp file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_chart:
        chart_path = tmp_chart.name

    # Render chart
    rendered_chart = chart_renderer.render_chart(chart_config, chart_path)

    # Create report with chart
    report_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "test",
        },
        "sections": [
            {
                "title": "Revenue Analysis",
                "metrics": {},
                "charts": [
                    {
                        "title": "Monthly Revenue",
                        "type": "bar",
                        "image_path": rendered_chart if rendered_chart else None
                    }
                ]
            }
        ]
    }

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        output_path = tmp.name

    try:
        success, result = exporter.export_to_pptx(report_data, output_path)

        if success:
            print(f"  ✓ Export with chart successful: {result}")
            if rendered_chart:
                print(f"  ✓ Chart was rendered and embedded")
            else:
                print(f"  ✓ Chart placeholder used (matplotlib not available)")
        else:
            print(f"  ✗ Export failed: {result}")

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)
        if rendered_chart and os.path.exists(chart_path):
            os.unlink(chart_path)

    print()


def test_library_availability():
    """Test library availability and installation instructions"""
    print("Test 6: Library availability check")

    exporter = PPTXExporter()

    print(f"  python-pptx available: {exporter.has_python_pptx}")
    print(f"  Pillow available: {exporter.has_pillow}")
    print()
    print("  Installation instructions:")
    print(f"  {exporter.get_installation_instructions()}")
    print()


def test_real_world_export():
    """Test export to Downloads folder (real-world scenario)"""
    print("Test 7: Real-world export to Downloads folder")

    exporter = PPTXExporter()

    # Realistic report data
    report_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "executive",
            "date_range": {"start": "2026-04-01", "end": "2026-04-30"}
        },
        "sections": [
            {
                "title": "Executive Summary",
                "metrics": {
                    "Total Revenue": 125430.50,
                    "Active Customers": 1542,
                    "New Customers": 234,
                    "Customer Retention": 0.94,
                    "Average Order Value": 81.35
                },
                "charts": []
            },
            {
                "title": "Sales Performance",
                "metrics": {
                    "Online Sales": 75000,
                    "Retail Sales": 50430.50,
                    "Growth vs Last Month": 0.15
                },
                "charts": []
            }
        ]
    }

    # Export to Downloads
    output_path = "C:/Users/Dannis Seay/Downloads/test_analytics_report.pptx"

    success, result = exporter.export_to_pptx(report_data, output_path)

    if success:
        print(f"  ✓ Export successful: {result}")
        print(f"  ✓ File size: {os.path.getsize(result)} bytes")
        print(f"  ✓ You can open the file to verify the presentation")
    else:
        print(f"  ✗ Export failed: {result}")

    print()


def main():
    """Run all tests"""
    print("=" * 70)
    print("PPTXExporter Test Suite")
    print("=" * 70)
    print()

    test_library_availability()
    test_validation()
    test_basic_export()
    test_empty_sections()
    test_full_featured_export()
    test_chart_integration()
    test_real_world_export()

    print("=" * 70)
    print("All tests completed")
    print("=" * 70)


if __name__ == "__main__":
    main()
