"""ReportGenerator - Generate analytics reports from collector data"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from analytics.core.collectors import (
    SkillCollector,
    TokenCollector,
    SessionCollector,
    ModelCollector,
    LessonCollector,
    WorkflowCollector
)


class ReportGenerator:
    """
    Generate analytics reports by aggregating data from collectors.

    Supports multiple report types with configurable templates and date ranges.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize ReportGenerator

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            # Expand ~ if present
            self.db_path = os.path.expanduser(db_path)

        # Initialize collectors
        self.skill_collector = SkillCollector(self.db_path)
        self.token_collector = TokenCollector(self.db_path)
        self.session_collector = SessionCollector(self.db_path)
        self.model_collector = ModelCollector(self.db_path)
        self.lesson_collector = LessonCollector(self.db_path)
        self.workflow_collector = WorkflowCollector(self.db_path)

    def generate_report(
        self,
        report_type: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a report of the specified type

        Args:
            report_type: Type of report ('summary', 'detailed', 'custom')
            config: Report configuration dict with optional keys:
                - date_range: Tuple of (start_date, end_date) as strings (YYYY-MM-DD)
                - template: Dict defining report structure for 'custom' type
                - sections: List of section names to include

        Returns:
            Dict containing:
                - metadata: Dict with generated_at, report_type, date_range
                - sections: List of section dicts with title, metrics, charts

        Raises:
            ValueError: If report_type is invalid or required config is missing
        """
        config = config or {}

        # Validate report type
        valid_types = ['summary', 'detailed', 'custom']
        if report_type not in valid_types:
            raise ValueError(
                f"Invalid report_type '{report_type}'. Must be one of: {valid_types}"
            )

        # Validate custom report template early
        if report_type == 'custom':
            template = config.get('template')
            if not template:
                raise ValueError("Custom report requires 'template' in config")
            if not isinstance(template, dict):
                raise ValueError("Custom report 'template' must be a dict")
            if 'sections' not in template:
                raise ValueError("Custom report template must include 'sections' key")

        # Parse date range
        try:
            date_range = self._parse_date_range(config.get('date_range'))
            days = self._calculate_days(date_range)
        except Exception as e:
            raise ValueError(f"Invalid date_range in config: {e}")

        # Compile metrics for the date range
        try:
            metrics = self.compile_metrics(date_range)
        except Exception as e:
            raise ValueError(f"Failed to compile metrics: {e}")

        # Build report based on type
        if report_type == 'summary':
            sections = self._build_summary_sections(metrics)
        elif report_type == 'detailed':
            sections = self._build_detailed_sections(metrics)
        elif report_type == 'custom':
            template = config.get('template')  # Already validated above
            sections = self.render_template(template, metrics)

        # Build metadata
        metadata = {
            'generated_at': datetime.now().isoformat(),
            'report_type': report_type,
            'date_range': {
                'start': date_range[0],
                'end': date_range[1],
                'days': days
            }
        }

        return {
            'metadata': metadata,
            'sections': sections
        }

    def compile_metrics(self, date_range: Tuple[str, str]) -> Dict[str, Any]:
        """
        Gather metrics from all collectors for the given date range

        Args:
            date_range: Tuple of (start_date, end_date) as strings (YYYY-MM-DD)

        Returns:
            Dict with keys for each collector type containing their metrics
        """
        days = self._calculate_days(date_range)

        # Collect from all sources
        metrics = {
            'skills': self.skill_collector.collect(days=days),
            'tokens': self.token_collector.collect(days=days),
            'sessions': self.session_collector.collect(days=days),
            'models': self.model_collector.collect(days=days),
            'lessons': self.lesson_collector.collect(days=days),
            'workflows': self.workflow_collector.collect(days=days),
            'date_range': {
                'start': date_range[0],
                'end': date_range[1],
                'days': days
            }
        }

        return metrics

    def render_template(
        self,
        template: Dict[str, Any],
        data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Apply a template to data to generate custom report sections

        Args:
            template: Dict defining report structure with keys:
                - sections: List of section dicts with:
                    - title: Section title
                    - metrics: List of metric paths (e.g., 'skills.total_invocations')
                    - charts: Optional list of chart configs
            data: Metrics data from compile_metrics()

        Returns:
            List of section dicts ready for report output
        """
        sections = []

        for section_template in template.get('sections', []):
            section = {
                'title': section_template.get('title', 'Untitled Section'),
                'metrics': {},
                'charts': section_template.get('charts', [])
            }

            # Extract requested metrics
            for metric_path in section_template.get('metrics', []):
                try:
                    value = self._get_nested_value(data, metric_path)
                    section['metrics'][metric_path] = value
                except KeyError:
                    section['metrics'][metric_path] = None  # Missing data

            sections.append(section)

        return sections

    def _parse_date_range(
        self,
        date_range: Optional[Any]
    ) -> Tuple[str, str]:
        """
        Parse and validate date range from config

        Args:
            date_range: Either None (default to last 30 days) or tuple of (start, end)

        Returns:
            Tuple of (start_date, end_date) as ISO strings (YYYY-MM-DD)
        """
        if date_range is None:
            # Default: last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            return (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

        if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
            raise ValueError("date_range must be a tuple of (start_date, end_date)")

        start_str, end_str = date_range

        # Validate date formats
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_str, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Dates must be in YYYY-MM-DD format: {e}")

        # Validate range
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        if end_date > datetime.now():
            raise ValueError("end_date cannot be in the future")

        return (start_str, end_str)

    def _calculate_days(self, date_range: Tuple[str, str]) -> int:
        """Calculate number of days in date range"""
        start_date = datetime.strptime(date_range[0], "%Y-%m-%d")
        end_date = datetime.strptime(date_range[1], "%Y-%m-%d")
        return (end_date - start_date).days + 1  # Inclusive

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        Get nested value from dict using dot-notation path

        Args:
            data: Source data dict
            path: Dot-separated path (e.g., 'skills.total_invocations')

        Returns:
            Value at path

        Raises:
            KeyError: If path not found
        """
        keys = path.split('.')
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value[key]
            else:
                raise KeyError(f"Cannot navigate to '{key}' in path '{path}'")

        return value

    def _build_summary_sections(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build sections for summary report type"""
        sections = []

        # Overview section
        sections.append({
            'title': 'Overview',
            'metrics': {
                'total_sessions': metrics['sessions'].get('total_sessions', 0),
                'total_skill_invocations': metrics['skills'].get('total_invocations', 0),
                'total_tokens': metrics['tokens'].get('total_tokens', 0),
                'total_cost_usd': metrics['tokens'].get('total_cost_usd', 0.0),
                'date_range_days': metrics['date_range']['days']
            },
            'charts': []
        })

        # Top skills section
        top_skills = metrics['skills'].get('top_skills', [])
        sections.append({
            'title': 'Top Skills',
            'metrics': {
                'top_skills': top_skills[:5],  # Top 5
                'success_rate_overall': metrics['skills'].get('success_rate_overall', 0.0)
            },
            'charts': [
                {
                    'type': 'bar',
                    'data': top_skills[:5],
                    'x_label': 'Skill',
                    'y_label': 'Invocations'
                }
            ]
        })

        # Token usage section
        sections.append({
            'title': 'Token Usage',
            'metrics': {
                'by_model': metrics['tokens'].get('by_model', {}),
                'daily_average': metrics['tokens'].get('daily_average', 0)
            },
            'charts': [
                {
                    'type': 'pie',
                    'data': metrics['tokens'].get('by_model', {}),
                    'label': 'Token distribution by model'
                }
            ]
        })

        return sections

    def _build_detailed_sections(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build sections for detailed report type"""
        sections = []

        # Include all summary sections
        sections.extend(self._build_summary_sections(metrics))

        # Add detailed skill breakdown
        sections.append({
            'title': 'Detailed Skill Metrics',
            'metrics': {
                'by_skill': metrics['skills'].get('by_skill', {}),
                'failures': metrics['skills'].get('failures', [])[:10]  # Last 10 failures
            },
            'charts': []
        })

        # Add token breakdown by project
        sections.append({
            'title': 'Token Usage by Project',
            'metrics': {
                'by_project': metrics['tokens'].get('by_project', {}),
                'by_skill': metrics['tokens'].get('by_skill', {})
            },
            'charts': []
        })

        # Add session metrics
        sections.append({
            'title': 'Session Analytics',
            'metrics': {
                'by_project': metrics['sessions'].get('by_project', {}),
                'day_of_week': metrics['sessions'].get('day_of_week', {}),
                'outcomes': metrics['sessions'].get('outcomes', {}),
                'avg_duration_minutes': metrics['sessions'].get('avg_duration_minutes', 0.0)
            },
            'charts': [
                {
                    'type': 'bar',
                    'data': metrics['sessions'].get('day_of_week', {}),
                    'x_label': 'Day of Week',
                    'y_label': 'Sessions'
                }
            ]
        })

        # Add model usage
        sections.append({
            'title': 'Model Usage',
            'metrics': {
                'by_model': metrics['models'].get('by_model', {}),
                'model_switches': metrics['models'].get('model_switches', [])
            },
            'charts': []
        })

        # Add lessons learned
        sections.append({
            'title': 'Lessons Learned',
            'metrics': {
                'total_lessons': metrics['lessons'].get('total_lessons', 0),
                'by_source': metrics['lessons'].get('by_source', {}),
                'by_status': metrics['lessons'].get('by_status', {}),
                'recent_lessons': metrics['lessons'].get('recent_lessons', [])[:5]
            },
            'charts': []
        })

        # Add workflow metrics
        sections.append({
            'title': 'Workflow Analytics',
            'metrics': {
                'total_runs': metrics['workflows'].get('total_runs', 0),
                'by_workflow': metrics['workflows'].get('by_workflow', {}),
                'by_status': metrics['workflows'].get('by_status', {}),
                'success_rate': metrics['workflows'].get('success_rate', 0.0),
                'avg_completion_time': metrics['workflows'].get('avg_completion_time', 0.0)
            },
            'charts': []
        })

        return sections
