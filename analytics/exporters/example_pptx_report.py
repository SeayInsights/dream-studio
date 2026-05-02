"""Example PowerPoint Report Generator

Demonstrates how to use PPTXExporter to create professional analytics presentations.
Includes examples of:
- Title and metadata formatting
- Multiple sections with metrics
- Chart integration (with ChartRenderer)
- Table slides
- Text/bullet point slides
- Custom slide creation

Run this script to generate a sample PowerPoint presentation.
"""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os
import sys
import io

# Ensure UTF-8 output for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from analytics.exporters import PPTXExporter, ChartRenderer


def create_executive_summary_report():
    """Create a comprehensive executive summary presentation"""

    print("Creating Executive Summary PowerPoint Report...")
    print("=" * 70)

    # Initialize exporters
    exporter = PPTXExporter()
    chart_renderer = ChartRenderer()

    # Check library availability
    print(f"python-pptx available: {exporter.has_python_pptx}")
    print(f"Chart rendering available: {chart_renderer.width > 0}")
    print()

    # Generate sample charts
    print("Rendering charts...")

    # Chart 1: Monthly Revenue
    revenue_chart_config = {
        "type": "bar",
        "title": "Monthly Revenue (USD)",
        "xLabel": "Month",
        "yLabel": "Revenue",
        "data": {
            "labels": ["January", "February", "March", "April"],
            "datasets": [{
                "label": "Revenue",
                "data": [95000, 110000, 105000, 125430.50]
            }]
        }
    }

    revenue_chart_path = None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        revenue_chart_path = chart_renderer.render_chart(revenue_chart_config, tmp.name)

    # Chart 2: User Growth
    user_growth_config = {
        "type": "line",
        "title": "User Growth Trend",
        "xLabel": "Month",
        "yLabel": "Active Users",
        "data": {
            "labels": ["January", "February", "March", "April"],
            "datasets": [{
                "label": "Active Users",
                "data": [10500, 11200, 11800, 12458]
            }]
        }
    }

    user_growth_path = None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        user_growth_path = chart_renderer.render_chart(user_growth_config, tmp.name)

    # Chart 3: Regional Distribution
    region_chart_config = {
        "type": "pie",
        "title": "Revenue by Region",
        "data": {
            "labels": ["North America", "Europe", "Asia Pacific", "Latin America"],
            "datasets": [{
                "data": [45000, 38000, 28000, 14430.50]
            }]
        }
    }

    region_chart_path = None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        region_chart_path = chart_renderer.render_chart(region_chart_config, tmp.name)

    print(f"  Revenue chart: {'✓' if revenue_chart_path else 'Placeholder'}")
    print(f"  User growth chart: {'✓' if user_growth_path else 'Placeholder'}")
    print(f"  Region chart: {'✓' if region_chart_path else 'Placeholder'}")
    print()

    # Prepare report data
    report_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "Executive Summary",
            "date_range": {
                "start": (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d"),
                "end": datetime.now().strftime("%Y-%m-%d")
            }
        },
        "sections": [
            # Section 1: Key Performance Indicators
            {
                "title": "Key Performance Indicators",
                "metrics": {
                    "Total Users": 15234,
                    "Active Users": 12458,
                    "New Users (MTD)": 234,
                    "Conversion Rate": 0.0823,
                    "Total Revenue (USD)": 125430.50,
                    "Revenue Growth": 0.1954,
                    "Customer Retention": 0.94,
                    "Churn Rate": 0.0234,
                    "Average Order Value": 81.35,
                    "Customer Satisfaction": 4.7
                },
                "charts": []
            },

            # Section 2: Revenue Analysis
            {
                "title": "Revenue Analysis",
                "metrics": {
                    "Q1 Revenue": 310000.00,
                    "Q2 Revenue (Projected)": 390000.00,
                    "Monthly Average": 103333.33,
                    "Growth vs Last Quarter": 0.15,
                    "Target Achievement": 0.95
                },
                "charts": [{
                    "title": "Monthly Revenue Trend",
                    "type": "bar",
                    "image_path": revenue_chart_path
                }]
            },

            # Section 3: User Growth
            {
                "title": "User Growth & Engagement",
                "metrics": {
                    "Total Registered Users": 15234,
                    "Daily Active Users": 4127,
                    "Weekly Active Users": 8945,
                    "Monthly Active Users": 12458,
                    "DAU/MAU Ratio": 0.331,
                    "Average Session Duration (min)": 12.5
                },
                "charts": [{
                    "title": "Active User Trends",
                    "type": "line",
                    "image_path": user_growth_path
                }]
            },

            # Section 4: Regional Performance
            {
                "title": "Regional Performance",
                "metrics": {
                    "North America": 45000.00,
                    "Europe": 38000.00,
                    "Asia Pacific": 28000.00,
                    "Latin America": 14430.50
                },
                "charts": [{
                    "title": "Revenue Distribution by Region",
                    "type": "pie",
                    "image_path": region_chart_path
                }]
            },

            # Section 5: Product Performance
            {
                "title": "Product Performance",
                "metrics": {
                    "Total Products": 127,
                    "Active Products": 98,
                    "New Products (This Quarter)": 12,
                    "Top Product Revenue": 23450.00,
                    "Average Products per Order": 2.3
                },
                "charts": []
            },

            # Section 6: Customer Insights
            {
                "title": "Customer Insights",
                "metrics": {
                    "Total Customers": 5234,
                    "Premium Customers": 892,
                    "Lifetime Value (Avg)": 412.50,
                    "Support Tickets": 234,
                    "Avg Resolution Time (hours)": 4.2,
                    "NPS Score": 67
                },
                "charts": []
            }
        ]
    }

    # Generate PowerPoint presentation
    print("Generating PowerPoint presentation...")

    output_path = "C:/Users/Dannis Seay/Downloads/executive_summary_report.pptx"

    success, result = exporter.export_to_pptx(report_data, output_path)

    print()
    if success:
        print("✓ Presentation generated successfully!")
        print(f"  Path: {result}")

        if os.path.exists(result):
            file_size = os.path.getsize(result)
            print(f"  Size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")

        # Count slides
        num_sections = len(report_data["sections"])
        # Title + TOC + sections (some with charts) + closing
        chart_slides = sum(1 for s in report_data["sections"] if s.get("charts"))
        estimated_slides = 1 + 1 + num_sections + chart_slides + 1
        print(f"  Estimated slides: ~{estimated_slides}")

        print()
        print("You can now open the presentation in PowerPoint!")
    else:
        print(f"✗ Export failed: {result}")

    # Cleanup temporary chart files
    if revenue_chart_path and os.path.exists(revenue_chart_path):
        os.unlink(revenue_chart_path)
    if user_growth_path and os.path.exists(user_growth_path):
        os.unlink(user_growth_path)
    if region_chart_path and os.path.exists(region_chart_path):
        os.unlink(region_chart_path)

    print()
    print("=" * 70)


def create_custom_presentation():
    """Create a custom presentation using individual slide methods"""

    print("\nCreating Custom PowerPoint Presentation...")
    print("=" * 70)

    exporter = PPTXExporter()

    if not exporter.has_python_pptx:
        print("python-pptx not available - skipping custom presentation example")
        return

    # Create presentation
    prs = exporter.create_presentation()

    # Slide 1: Title
    exporter.add_title_slide(
        prs,
        "Q1 2026 Analytics Review",
        "Performance Highlights\nApril 2026"
    )

    # Slide 2: Table of Contents
    exporter.add_text_slide(
        prs,
        "Agenda",
        [
            "Executive Summary",
            "Financial Performance",
            "User Analytics",
            "Product Insights",
            "Strategic Recommendations"
        ]
    )

    # Slide 3: Metrics Table
    exporter.add_table_slide(
        prs,
        {
            "title": "Executive Summary - Q1 Results",
            "data": {
                "Total Revenue": 125430.50,
                "User Growth": 0.1954,
                "Customer Retention": 0.94,
                "Net Promoter Score": 67,
                "Target Achievement": 0.95
            }
        }
    )

    # Slide 4: Key Findings
    exporter.add_text_slide(
        prs,
        "Key Findings",
        [
            "Revenue exceeded target by 5% - strongest quarter on record",
            "User growth accelerated 19.5% quarter-over-quarter",
            "Customer retention improved to 94%, up from 89%",
            "North America remains largest market at 36% of revenue",
            "Mobile engagement increased 25% with new app features"
        ]
    )

    # Slide 5: Recommendations
    exporter.add_text_slide(
        prs,
        "Strategic Recommendations",
        [
            "Increase marketing spend in Q2 to capitalize on growth momentum",
            "Expand product line in Europe and Asia Pacific regions",
            "Implement retention campaign for at-risk customer segment",
            "Launch premium tier to increase average order value",
            "Invest in customer support to maintain high satisfaction"
        ]
    )

    # Slide 6: Next Steps
    exporter.add_text_slide(
        prs,
        "Next Steps",
        [
            "Schedule follow-up meeting for Q2 planning",
            "Assign owners for each strategic initiative",
            "Set monthly checkpoints for progress tracking",
            "Prepare detailed financial model for Q2-Q4"
        ]
    )

    # Slide 7: Closing
    exporter.add_text_slide(
        prs,
        "Questions?",
        [
            "Thank you for your attention",
            "",
            "Analytics Team",
            "dream-studio Platform"
        ]
    )

    # Save presentation
    output_path = "C:/Users/Dannis Seay/Downloads/custom_presentation.pptx"
    prs.save(output_path)

    print(f"✓ Custom presentation saved to: {output_path}")

    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"  Size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")
        print(f"  Slides: 7")

    print("=" * 70)


def main():
    """Run all examples"""

    print("\n" + "=" * 70)
    print("PowerPoint Exporter - Example Report Generator")
    print("=" * 70)
    print()

    # Example 1: Full executive summary report
    create_executive_summary_report()

    # Example 2: Custom presentation with manual slide creation
    create_custom_presentation()

    print("\nAll examples completed!")
    print("Check your Downloads folder for the generated presentations.")
    print()


if __name__ == "__main__":
    main()
