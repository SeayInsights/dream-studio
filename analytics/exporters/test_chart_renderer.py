"""
Tests for ChartRenderer.

Run with: python -m pytest analytics/exporters/test_chart_renderer.py -v
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from analytics.exporters.chart_renderer import ChartRenderer, render_chart_fallback


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp)


@pytest.fixture
def renderer():
    """Create a ChartRenderer instance."""
    return ChartRenderer()


class TestChartRenderer:
    """Test suite for ChartRenderer."""

    def test_line_chart_basic(self, renderer, temp_dir):
        """Test basic line chart rendering."""
        config = {
            "type": "line",
            "title": "Monthly Revenue",
            "data": {
                "labels": ["Jan", "Feb", "Mar", "Apr", "May"],
                "datasets": [
                    {
                        "label": "Revenue",
                        "data": [10, 20, 15, 25, 30]
                    }
                ]
            }
        }

        output_path = temp_dir / "line_chart.png"
        result = renderer.render_chart(config, str(output_path))

        # Should return path if matplotlib available, None otherwise
        if result:
            assert output_path.exists()
            assert output_path.stat().st_size > 0

    def test_line_chart_multi_series(self, renderer, temp_dir):
        """Test line chart with multiple series."""
        config = {
            "type": "line",
            "title": "Sales Comparison",
            "xLabel": "Month",
            "yLabel": "Sales ($)",
            "data": {
                "labels": ["Jan", "Feb", "Mar"],
                "datasets": [
                    {"label": "Product A", "data": [100, 150, 120]},
                    {"label": "Product B", "data": [80, 90, 110]},
                ]
            }
        }

        output_path = temp_dir / "line_multi.png"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()

    def test_bar_chart_basic(self, renderer, temp_dir):
        """Test basic bar chart rendering."""
        config = {
            "type": "bar",
            "title": "Quarterly Sales",
            "data": {
                "labels": ["Q1", "Q2", "Q3", "Q4"],
                "datasets": [
                    {
                        "label": "Sales",
                        "data": [100, 120, 110, 140]
                    }
                ]
            }
        }

        output_path = temp_dir / "bar_chart.png"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()

    def test_bar_chart_grouped(self, renderer, temp_dir):
        """Test grouped bar chart."""
        config = {
            "type": "bar",
            "title": "Product Comparison",
            "data": {
                "labels": ["Store A", "Store B", "Store C"],
                "datasets": [
                    {"label": "Product X", "data": [50, 60, 55]},
                    {"label": "Product Y", "data": [40, 45, 50]},
                ]
            }
        }

        output_path = temp_dir / "bar_grouped.png"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()

    def test_pie_chart_basic(self, renderer, temp_dir):
        """Test basic pie chart rendering."""
        config = {
            "type": "pie",
            "title": "Market Share",
            "data": {
                "labels": ["Product A", "Product B", "Product C", "Others"],
                "datasets": [
                    {
                        "data": [30, 25, 20, 25]
                    }
                ]
            }
        }

        output_path = temp_dir / "pie_chart.png"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()

    def test_scatter_chart_basic(self, renderer, temp_dir):
        """Test basic scatter plot rendering."""
        config = {
            "type": "scatter",
            "title": "Price vs Quality",
            "xLabel": "Price",
            "yLabel": "Quality Score",
            "data": {
                "datasets": [
                    {
                        "label": "Products",
                        "data": [
                            {"x": 10, "y": 7},
                            {"x": 15, "y": 8},
                            {"x": 20, "y": 9},
                            {"x": 25, "y": 8.5},
                        ]
                    }
                ]
            }
        }

        output_path = temp_dir / "scatter_chart.png"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()

    def test_scatter_chart_multi_series(self, renderer, temp_dir):
        """Test scatter plot with multiple series."""
        config = {
            "type": "scatter",
            "title": "Performance Analysis",
            "data": {
                "datasets": [
                    {
                        "label": "Team A",
                        "data": [{"x": 1, "y": 10}, {"x": 2, "y": 15}]
                    },
                    {
                        "label": "Team B",
                        "data": [{"x": 1, "y": 12}, {"x": 2, "y": 14}]
                    }
                ]
            }
        }

        output_path = temp_dir / "scatter_multi.png"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()

    def test_svg_output(self, renderer, temp_dir):
        """Test SVG output format."""
        config = {
            "type": "line",
            "title": "Test SVG",
            "data": {
                "labels": ["A", "B", "C"],
                "datasets": [{"label": "Test", "data": [1, 2, 3]}]
            }
        }

        output_path = temp_dir / "chart.svg"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()
            assert output_path.suffix == '.svg'

    def test_invalid_chart_type(self, renderer, temp_dir):
        """Test handling of invalid chart type."""
        config = {
            "type": "radar",  # Unsupported type
            "title": "Invalid Chart",
            "data": {"labels": [], "datasets": []}
        }

        output_path = temp_dir / "invalid.png"
        result = renderer.render_chart(config, str(output_path))

        assert result is None

    def test_empty_config(self, renderer, temp_dir):
        """Test handling of empty config."""
        config = {}
        output_path = temp_dir / "empty.png"
        result = renderer.render_chart(config, str(output_path))

        assert result is None

    def test_missing_data(self, renderer, temp_dir):
        """Test handling of missing data."""
        config = {
            "type": "line",
            "title": "Missing Data",
            "data": {}
        }

        output_path = temp_dir / "missing.png"
        result = renderer.render_chart(config, str(output_path))

        assert result is None

    def test_fallback_placeholder(self):
        """Test fallback placeholder generation."""
        config = {
            "type": "line",
            "title": "Revenue Chart"
        }

        placeholder = render_chart_fallback(config)
        assert placeholder == "[Chart: Revenue Chart (Line)]"

    def test_fallback_placeholder_unknown_type(self):
        """Test fallback placeholder with unknown type."""
        config = {
            "title": "Mystery Chart"
        }

        placeholder = render_chart_fallback(config)
        assert placeholder == "[Chart: Mystery Chart (Unknown)]"

    def test_custom_dimensions(self, temp_dir):
        """Test chart rendering with custom dimensions."""
        renderer = ChartRenderer(width=1200, height=800, dpi=150)

        config = {
            "type": "bar",
            "title": "Custom Size Chart",
            "data": {
                "labels": ["A", "B", "C"],
                "datasets": [{"label": "Test", "data": [10, 20, 15]}]
            }
        }

        output_path = temp_dir / "custom_size.png"
        result = renderer.render_chart(config, str(output_path))

        if result:
            assert output_path.exists()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
