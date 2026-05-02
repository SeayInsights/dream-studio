"""
Demo script for ChartRenderer.

Shows how to use the chart renderer with various chart types.

To install matplotlib for full functionality:
    pip install matplotlib

Usage:
    python analytics/exporters/demo_chart_renderer.py
"""

from pathlib import Path
import tempfile
from analytics.exporters import ChartRenderer, render_chart_fallback


def demo_line_chart(renderer, output_dir):
    """Demonstrate line chart rendering."""
    print("\n=== Line Chart Demo ===")

    config = {
        "type": "line",
        "title": "Monthly Sales Trend",
        "xLabel": "Month",
        "yLabel": "Sales ($1000s)",
        "data": {
            "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "datasets": [
                {
                    "label": "Product A",
                    "data": [45, 52, 48, 65, 70, 68]
                },
                {
                    "label": "Product B",
                    "data": [30, 38, 42, 45, 50, 55]
                }
            ]
        }
    }

    output_path = output_dir / "line_chart.png"
    result = renderer.render_chart(config, str(output_path))

    if result:
        print(f"[OK] Line chart rendered: {result}")
    else:
        print(f"[SKIP] Chart rendering unavailable - placeholder: {render_chart_fallback(config)}")


def demo_bar_chart(renderer, output_dir):
    """Demonstrate bar chart rendering."""
    print("\n=== Bar Chart Demo ===")

    config = {
        "type": "bar",
        "title": "Quarterly Performance",
        "xLabel": "Quarter",
        "yLabel": "Revenue ($M)",
        "data": {
            "labels": ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025"],
            "datasets": [
                {
                    "label": "Revenue",
                    "data": [2.3, 2.8, 3.1, 3.5]
                },
                {
                    "label": "Target",
                    "data": [2.5, 2.7, 3.0, 3.2]
                }
            ]
        }
    }

    output_path = output_dir / "bar_chart.png"
    result = renderer.render_chart(config, str(output_path))

    if result:
        print(f"[OK] Bar chart rendered: {result}")
    else:
        print(f"[SKIP] Chart rendering unavailable - placeholder: {render_chart_fallback(config)}")


def demo_pie_chart(renderer, output_dir):
    """Demonstrate pie chart rendering."""
    print("\n=== Pie Chart Demo ===")

    config = {
        "type": "pie",
        "title": "Market Share by Region",
        "data": {
            "labels": ["North America", "Europe", "Asia Pacific", "Latin America", "Other"],
            "datasets": [
                {
                    "data": [35, 28, 22, 10, 5]
                }
            ]
        }
    }

    output_path = output_dir / "pie_chart.png"
    result = renderer.render_chart(config, str(output_path))

    if result:
        print(f"[OK] Pie chart rendered: {result}")
    else:
        print(f"[SKIP] Chart rendering unavailable - placeholder: {render_chart_fallback(config)}")


def demo_scatter_chart(renderer, output_dir):
    """Demonstrate scatter plot rendering."""
    print("\n=== Scatter Chart Demo ===")

    config = {
        "type": "scatter",
        "title": "Customer Satisfaction vs. Price",
        "xLabel": "Price ($)",
        "yLabel": "Satisfaction Score (1-10)",
        "data": {
            "datasets": [
                {
                    "label": "Premium Products",
                    "data": [
                        {"x": 100, "y": 9.2},
                        {"x": 120, "y": 9.5},
                        {"x": 150, "y": 9.0},
                        {"x": 180, "y": 8.8}
                    ]
                },
                {
                    "label": "Standard Products",
                    "data": [
                        {"x": 40, "y": 7.5},
                        {"x": 50, "y": 8.0},
                        {"x": 60, "y": 7.8},
                        {"x": 70, "y": 8.2}
                    ]
                }
            ]
        }
    }

    output_path = output_dir / "scatter_chart.png"
    result = renderer.render_chart(config, str(output_path))

    if result:
        print(f"[OK] Scatter chart rendered: {result}")
    else:
        print(f"[SKIP] Chart rendering unavailable - placeholder: {render_chart_fallback(config)}")


def main():
    """Run all chart rendering demos."""
    print("===========================================")
    print("ChartRenderer Demo")
    print("===========================================")

    # Create temporary output directory
    output_dir = Path(tempfile.mkdtemp())
    print(f"\nOutput directory: {output_dir}")

    # Initialize renderer
    renderer = ChartRenderer(width=800, height=600, dpi=100)
    print(f"Renderer initialized: {renderer.width}x{renderer.height} @ {renderer.dpi}dpi")

    # Run demos
    demo_line_chart(renderer, output_dir)
    demo_bar_chart(renderer, output_dir)
    demo_pie_chart(renderer, output_dir)
    demo_scatter_chart(renderer, output_dir)

    # Summary
    print("\n===========================================")
    print("Demo Complete")
    print("===========================================")

    rendered_files = list(output_dir.glob("*.png"))
    if rendered_files:
        print(f"\n[OK] {len(rendered_files)} chart(s) rendered successfully:")
        for file in rendered_files:
            print(f"  - {file.name} ({file.stat().st_size / 1024:.1f} KB)")
        print(f"\nView charts at: {output_dir}")
    else:
        print("\n[WARN] No charts rendered - matplotlib not available")
        print("Install with: pip install matplotlib")
        print("\nPlaceholder mode is active - charts will show as text in PDFs")


if __name__ == "__main__":
    main()
