"""
Chart renderer for converting Chart.js configs to static images for PDF embedding.

Supports multiple rendering backends with graceful fallback:
1. matplotlib (preferred - widely available, good defaults)
2. plotly (alternative - interactive→static conversion)
3. Graceful fallback - returns None for placeholder rendering
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Try matplotlib (preferred)
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend for server use
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available - chart rendering will be limited")

# Try plotly (alternative)
try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    logger.debug("plotly not available - falling back to matplotlib only")

# Consistent color palette for professional charts
CHART_COLORS = [
    '#2c3e50',  # Dark blue-gray
    '#3498db',  # Blue
    '#e74c3c',  # Red
    '#2ecc71',  # Green
    '#f39c12',  # Orange
    '#9b59b6',  # Purple
    '#1abc9c',  # Turquoise
    '#34495e',  # Dark gray
]

# Default chart dimensions
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
DEFAULT_DPI = 100


class ChartRenderer:
    """Render Chart.js configs as static images for PDF embedding."""

    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, dpi: int = DEFAULT_DPI):
        """
        Initialize chart renderer.

        Args:
            width: Chart width in pixels
            height: Chart height in pixels
            dpi: Dots per inch for rendering
        """
        self.width = width
        self.height = height
        self.dpi = dpi

        if not HAS_MATPLOTLIB and not HAS_PLOTLY:
            logger.warning("No chart rendering libraries available - charts will use placeholders")

    def render_chart(self, chart_config: Dict[str, Any], output_path: str) -> Optional[str]:
        """
        Render a chart from Chart.js config and save as image.

        Args:
            chart_config: Chart configuration dict with type, title, data
            output_path: Path to save rendered image

        Returns:
            Path to saved image, or None if rendering failed
        """
        if not chart_config:
            logger.error("Empty chart config provided")
            return None

        chart_type = chart_config.get('type', '').lower()
        if not chart_type:
            logger.error("Chart type not specified in config")
            return None

        # Validate output path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine format from extension
        format_ext = output_path.suffix.lower()
        if format_ext not in ['.png', '.svg']:
            logger.warning(f"Unsupported format {format_ext}, defaulting to PNG")
            output_path = output_path.with_suffix('.png')

        try:
            # Route to appropriate renderer
            if chart_type == 'line':
                success = self.render_line_chart(chart_config, output_path)
            elif chart_type == 'bar':
                success = self.render_bar_chart(chart_config, output_path)
            elif chart_type == 'pie':
                success = self.render_pie_chart(chart_config, output_path)
            elif chart_type == 'scatter':
                success = self.render_scatter_chart(chart_config, output_path)
            else:
                logger.error(f"Unsupported chart type: {chart_type}")
                return None

            if success:
                logger.info(f"Chart rendered successfully: {output_path}")
                return str(output_path)
            else:
                logger.error(f"Failed to render {chart_type} chart")
                return None

        except Exception as e:
            logger.error(f"Error rendering chart: {e}", exc_info=True)
            return None

    def render_line_chart(self, config: Dict[str, Any], output_path: Path) -> bool:
        """Render a line chart."""
        if not HAS_MATPLOTLIB:
            return False

        try:
            data = config.get('data', {})
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not datasets:
                logger.error("No datasets found in line chart config")
                return False

            fig, ax = plt.subplots(figsize=(self.width/self.dpi, self.height/self.dpi), dpi=self.dpi)

            # Plot each dataset
            for i, dataset in enumerate(datasets):
                label = dataset.get('label', f'Series {i+1}')
                values = dataset.get('data', [])
                color = CHART_COLORS[i % len(CHART_COLORS)]

                ax.plot(labels, values, marker='o', label=label, color=color, linewidth=2)

            # Styling
            ax.set_title(config.get('title', 'Line Chart'), fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel(config.get('xLabel', ''), fontsize=11)
            ax.set_ylabel(config.get('yLabel', ''), fontsize=11)
            ax.legend(loc='best', frameon=True, shadow=True)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            plt.tight_layout()
            plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig)

            return True

        except Exception as e:
            logger.error(f"Error rendering line chart: {e}", exc_info=True)
            return False

    def render_bar_chart(self, config: Dict[str, Any], output_path: Path) -> bool:
        """Render a bar chart."""
        if not HAS_MATPLOTLIB:
            return False

        try:
            data = config.get('data', {})
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not datasets:
                logger.error("No datasets found in bar chart config")
                return False

            fig, ax = plt.subplots(figsize=(self.width/self.dpi, self.height/self.dpi), dpi=self.dpi)

            # Calculate bar positions
            x = range(len(labels))
            bar_width = 0.8 / len(datasets)

            # Plot each dataset
            for i, dataset in enumerate(datasets):
                label = dataset.get('label', f'Series {i+1}')
                values = dataset.get('data', [])
                color = CHART_COLORS[i % len(CHART_COLORS)]

                offset = (i - len(datasets)/2 + 0.5) * bar_width
                positions = [pos + offset for pos in x]

                ax.bar(positions, values, bar_width, label=label, color=color, alpha=0.8)

            # Styling
            ax.set_title(config.get('title', 'Bar Chart'), fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel(config.get('xLabel', ''), fontsize=11)
            ax.set_ylabel(config.get('yLabel', ''), fontsize=11)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha='right')
            ax.legend(loc='best', frameon=True, shadow=True)
            ax.grid(True, alpha=0.3, linestyle='--', axis='y')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            plt.tight_layout()
            plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig)

            return True

        except Exception as e:
            logger.error(f"Error rendering bar chart: {e}", exc_info=True)
            return False

    def render_pie_chart(self, config: Dict[str, Any], output_path: Path) -> bool:
        """Render a pie chart."""
        if not HAS_MATPLOTLIB:
            return False

        try:
            data = config.get('data', {})
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not datasets or not datasets[0].get('data'):
                logger.error("No data found in pie chart config")
                return False

            # Pie charts typically use the first dataset
            values = datasets[0].get('data', [])

            fig, ax = plt.subplots(figsize=(self.width/self.dpi, self.height/self.dpi), dpi=self.dpi)

            # Create pie chart
            colors = CHART_COLORS[:len(values)]
            wedges, texts, autotexts = ax.pie(
                values,
                labels=labels,
                colors=colors,
                autopct='%1.1f%%',
                startangle=90,
                pctdistance=0.85,
                explode=[0.05] * len(values)  # Slight separation for clarity
            )

            # Style percentage text
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(10)
                autotext.set_fontweight('bold')

            # Style labels
            for text in texts:
                text.set_fontsize(10)

            ax.set_title(config.get('title', 'Pie Chart'), fontsize=14, fontweight='bold', pad=20)

            plt.tight_layout()
            plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig)

            return True

        except Exception as e:
            logger.error(f"Error rendering pie chart: {e}", exc_info=True)
            return False

    def render_scatter_chart(self, config: Dict[str, Any], output_path: Path) -> bool:
        """Render a scatter plot."""
        if not HAS_MATPLOTLIB:
            return False

        try:
            data = config.get('data', {})
            datasets = data.get('datasets', [])

            if not datasets:
                logger.error("No datasets found in scatter chart config")
                return False

            fig, ax = plt.subplots(figsize=(self.width/self.dpi, self.height/self.dpi), dpi=self.dpi)

            # Plot each dataset
            for i, dataset in enumerate(datasets):
                label = dataset.get('label', f'Series {i+1}')
                points = dataset.get('data', [])
                color = CHART_COLORS[i % len(CHART_COLORS)]

                # Extract x and y coordinates
                x_values = [p.get('x', 0) for p in points]
                y_values = [p.get('y', 0) for p in points]

                ax.scatter(x_values, y_values, label=label, color=color, s=50, alpha=0.7, edgecolors='white', linewidth=1)

            # Styling
            ax.set_title(config.get('title', 'Scatter Plot'), fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel(config.get('xLabel', 'X'), fontsize=11)
            ax.set_ylabel(config.get('yLabel', 'Y'), fontsize=11)
            ax.legend(loc='best', frameon=True, shadow=True)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            plt.tight_layout()
            plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig)

            return True

        except Exception as e:
            logger.error(f"Error rendering scatter chart: {e}", exc_info=True)
            return False


def render_chart_fallback(chart_config: Dict[str, Any]) -> str:
    """
    Generate a placeholder string for charts that can't be rendered.

    Args:
        chart_config: Chart configuration dict

    Returns:
        Placeholder text for PDF
    """
    title = chart_config.get('title', 'Chart')
    chart_type = chart_config.get('type', 'unknown').title()
    return f"[Chart: {title} ({chart_type})]"
