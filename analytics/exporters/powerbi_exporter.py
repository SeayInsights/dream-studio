"""PowerBIExporter - Export analytics reports to Power BI-compatible format"""
import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Tuple, Union, Optional
from datetime import datetime


class PowerBIExporter:
    """
    Export analytics reports to Power BI-compatible dataset format.

    Creates a directory structure with:
    - CSV files for each table (data/)
    - schema.json with table definitions, relationships, measures
    - dataset.pbids connection file for Power BI Desktop

    Usage:
        >>> from analytics.exporters import PowerBIExporter
        >>> from analytics.core.reports import ReportGenerator
        >>>
        >>> generator = ReportGenerator()
        >>> report = generator.generate_report("detailed")
        >>>
        >>> exporter = PowerBIExporter()
        >>> success, path = exporter.export_dataset(report, "powerbi_export/")
        >>> # User can now open dataset.pbids file in Power BI Desktop
    """

    def __init__(self):
        """Initialize PowerBIExporter"""
        pass

    def export_dataset(
        self,
        report_data: Dict[str, Any],
        output_path: Union[str, Path]
    ) -> Tuple[bool, str]:
        """
        Export report data as Power BI dataset

        Creates directory structure:
            output_path/
            ├── data/
            │   ├── skills.csv
            │   ├── tokens.csv
            │   ├── sessions.csv
            │   ├── models.csv
            │   ├── lessons.csv
            │   └── workflows.csv
            ├── schema.json
            └── dataset.pbids

        Args:
            report_data: Report data dict with 'metadata' and 'sections' keys
            output_path: Path to output directory (will be created if doesn't exist)

        Returns:
            Tuple of (success: bool, message: str)
            On success: (True, directory_path)
            On error: (False, error_message)
        """
        try:
            # Validate input
            error = self._validate_data(report_data)
            if error:
                return (False, error)

            output_path = Path(output_path)

            # Create directory structure
            try:
                output_path.mkdir(parents=True, exist_ok=True)
                data_dir = output_path / "data"
                data_dir.mkdir(exist_ok=True)
            except Exception as e:
                return (False, f"Failed to create directory structure: {e}")

            # Create data model from report
            try:
                data_model = self.create_data_model(report_data)
            except Exception as e:
                return (False, f"Failed to create data model: {e}")

            # Export CSV files for each table
            try:
                csv_files = self._export_csv_files(data_model['tables'], data_dir)
            except Exception as e:
                return (False, f"Failed to export CSV files: {e}")

            # Generate schema.json
            try:
                schema_json = self.generate_pbix_metadata(data_model)
                schema_path = output_path / "schema.json"
                with open(schema_path, 'w', encoding='utf-8') as f:
                    f.write(schema_json)
            except Exception as e:
                return (False, f"Failed to generate schema.json: {e}")

            # Generate .pbids connection file
            try:
                pbids_content = self._generate_pbids_file(data_dir)
                pbids_path = output_path / "dataset.pbids"
                with open(pbids_path, 'w', encoding='utf-8') as f:
                    f.write(pbids_content)
            except Exception as e:
                return (False, f"Failed to generate .pbids file: {e}")

            # Generate README for user
            try:
                readme_content = self._generate_readme(csv_files, data_model)
                readme_path = output_path / "README.txt"
                with open(readme_path, 'w', encoding='utf-8') as f:
                    f.write(readme_content)
            except Exception as e:
                # Non-critical error, continue
                pass

            return (True, str(output_path.absolute()))

        except PermissionError:
            return (False, f"Permission denied writing to: {output_path}")
        except OSError as e:
            return (False, f"OS error: {e}")
        except Exception as e:
            return (False, f"Unexpected error: {e}")

    def create_data_model(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Define tables, relationships, and measures from report data

        Args:
            report_data: Report data dict with 'metadata' and 'sections'

        Returns:
            Data model dict with:
                - tables: List of table definitions
                - relationships: List of relationship definitions
                - measures: List of DAX measure definitions
                - hierarchies: List of hierarchy definitions
        """
        metadata = report_data.get('metadata', {})
        sections = report_data.get('sections', [])

        # Extract data from sections by section title
        section_data = {section['title']: section.get('metrics', {}) for section in sections}

        # Build table definitions
        tables = []

        # Skills table
        skills_data = self._extract_section_data(section_data, ['Skills', 'Skill Performance'])
        if skills_data:
            tables.append(self._build_skills_table(skills_data))

        # Tokens table
        tokens_data = self._extract_section_data(section_data, ['Tokens', 'Token Usage', 'Cost Analysis'])
        if tokens_data:
            tables.append(self._build_tokens_table(tokens_data))

        # Sessions table
        sessions_data = self._extract_section_data(section_data, ['Sessions', 'Session Activity'])
        if sessions_data:
            tables.append(self._build_sessions_table(sessions_data))

        # Models table
        models_data = self._extract_section_data(section_data, ['Models', 'Model Usage'])
        if models_data:
            tables.append(self._build_models_table(models_data))

        # Lessons table
        lessons_data = self._extract_section_data(section_data, ['Lessons', 'Lessons Learned'])
        if lessons_data:
            tables.append(self._build_lessons_table(lessons_data))

        # Workflows table
        workflows_data = self._extract_section_data(section_data, ['Workflows', 'Workflow Performance'])
        if workflows_data:
            tables.append(self._build_workflows_table(workflows_data))

        # Add Date table (calendar table for time intelligence)
        date_range = metadata.get('date_range', {})
        tables.append(self._build_date_table(date_range))

        # Define relationships
        relationships = [
            {
                'from_table': 'Sessions',
                'from_column': 'date',
                'to_table': 'Date',
                'to_column': 'date',
                'cardinality': 'many_to_one'
            },
            {
                'from_table': 'Tokens',
                'from_column': 'date',
                'to_table': 'Date',
                'to_column': 'date',
                'cardinality': 'many_to_one'
            }
        ]

        # Define DAX measures
        measures = [
            {
                'name': 'Total Tokens',
                'table': 'Tokens',
                'expression': 'SUM(Tokens[token_count])',
                'format': '#,##0'
            },
            {
                'name': 'Total Cost USD',
                'table': 'Tokens',
                'expression': 'SUM(Tokens[cost_usd])',
                'format': '$#,##0.00'
            },
            {
                'name': 'Avg Success Rate',
                'table': 'Skills',
                'expression': 'AVERAGE(Skills[success_rate])',
                'format': '0.0%'
            },
            {
                'name': 'Total Sessions',
                'table': 'Sessions',
                'expression': 'COUNTROWS(Sessions)',
                'format': '#,##0'
            },
            {
                'name': 'Avg Session Duration',
                'table': 'Sessions',
                'expression': 'AVERAGE(Sessions[duration_minutes])',
                'format': '#,##0.0'
            },
            {
                'name': 'Total Skill Invocations',
                'table': 'Skills',
                'expression': 'SUM(Skills[invocations])',
                'format': '#,##0'
            }
        ]

        # Define hierarchies
        hierarchies = [
            {
                'name': 'Time Hierarchy',
                'table': 'Date',
                'levels': ['year', 'quarter', 'month', 'date']
            }
        ]

        return {
            'tables': tables,
            'relationships': relationships,
            'measures': measures,
            'hierarchies': hierarchies
        }

    def generate_pbix_metadata(self, data_model: Dict[str, Any]) -> str:
        """
        Create schema.json from data model

        Args:
            data_model: Data model dict from create_data_model()

        Returns:
            JSON string for schema.json file
        """
        schema = {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'description': 'Dream Studio Analytics - Power BI Dataset',
            'tables': data_model['tables'],
            'relationships': data_model['relationships'],
            'measures': data_model['measures'],
            'hierarchies': data_model['hierarchies']
        }

        return json.dumps(schema, indent=2)

    # ---- Private helper methods ----

    def _validate_data(self, data: Dict[str, Any]) -> Optional[str]:
        """Validate report data structure"""
        if not isinstance(data, dict):
            return "Data must be a dict"

        if 'sections' not in data:
            return "Data must contain 'sections' key"

        if not isinstance(data['sections'], list):
            return "Data 'sections' must be a list"

        return None  # Valid

    def _extract_section_data(
        self,
        section_data: Dict[str, Dict[str, Any]],
        possible_titles: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Extract section data by matching possible titles

        Args:
            section_data: Dict mapping section title to metrics
            possible_titles: List of possible section titles to match

        Returns:
            Metrics dict if found, None otherwise
        """
        for title in possible_titles:
            if title in section_data:
                return section_data[title]
        return None

    def _build_skills_table(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Skills table definition"""
        # Extract top_skills list or create default
        top_skills = data.get('top_skills', [])

        rows = []
        if isinstance(top_skills, list):
            for i, skill in enumerate(top_skills):
                if isinstance(skill, dict):
                    rows.append({
                        'skill_id': skill.get('name', f'skill_{i+1}'),
                        'skill_name': skill.get('name', 'Unknown'),
                        'invocations': skill.get('count', 0),
                        'success_rate': skill.get('success_rate', 1.0)
                    })

        # Fallback: create summary row
        if not rows:
            rows.append({
                'skill_id': 'all_skills',
                'skill_name': 'All Skills',
                'invocations': data.get('total_invocations', 0),
                'success_rate': data.get('success_rate_overall', 1.0)
            })

        return {
            'name': 'Skills',
            'file': 'data/skills.csv',
            'columns': [
                {'name': 'skill_id', 'type': 'string', 'key': True},
                {'name': 'skill_name', 'type': 'string'},
                {'name': 'invocations', 'type': 'integer'},
                {'name': 'success_rate', 'type': 'decimal'}
            ],
            'rows': rows
        }

    def _build_tokens_table(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Tokens table definition"""
        # Extract by_model or by_date data
        by_model = data.get('by_model', [])
        by_date = data.get('by_date', [])

        rows = []

        # Prefer by_date if available (time-series data)
        if isinstance(by_date, list) and by_date:
            for entry in by_date:
                if isinstance(entry, dict):
                    rows.append({
                        'date': entry.get('date', ''),
                        'token_count': entry.get('tokens', 0),
                        'cost_usd': entry.get('cost', 0.0),
                        'model': 'all'
                    })
        elif isinstance(by_model, list) and by_model:
            # Use by_model data
            for entry in by_model:
                if isinstance(entry, dict):
                    rows.append({
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'token_count': entry.get('tokens', 0),
                        'cost_usd': entry.get('cost', 0.0),
                        'model': entry.get('model', 'unknown')
                    })
        else:
            # Fallback: create summary row
            rows.append({
                'date': datetime.now().strftime('%Y-%m-%d'),
                'token_count': data.get('total_tokens', 0),
                'cost_usd': data.get('total_cost_usd', 0.0),
                'model': 'all'
            })

        return {
            'name': 'Tokens',
            'file': 'data/tokens.csv',
            'columns': [
                {'name': 'date', 'type': 'date'},
                {'name': 'token_count', 'type': 'integer'},
                {'name': 'cost_usd', 'type': 'decimal'},
                {'name': 'model', 'type': 'string'}
            ],
            'rows': rows
        }

    def _build_sessions_table(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Sessions table definition"""
        rows = []

        # Try to extract session list
        sessions = data.get('sessions', [])
        recent_sessions = data.get('recent_sessions', [])

        session_list = sessions if sessions else recent_sessions

        if isinstance(session_list, list) and session_list:
            for i, session in enumerate(session_list):
                if isinstance(session, dict):
                    rows.append({
                        'session_id': session.get('id', f'session_{i+1}'),
                        'date': session.get('date', datetime.now().strftime('%Y-%m-%d')),
                        'duration_minutes': session.get('duration', 0),
                        'project': session.get('project', 'unknown')
                    })
        else:
            # Fallback: create summary row
            rows.append({
                'session_id': 'summary',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'duration_minutes': data.get('avg_duration', 0),
                'project': 'all'
            })

        return {
            'name': 'Sessions',
            'file': 'data/sessions.csv',
            'columns': [
                {'name': 'session_id', 'type': 'string', 'key': True},
                {'name': 'date', 'type': 'date'},
                {'name': 'duration_minutes', 'type': 'integer'},
                {'name': 'project', 'type': 'string'}
            ],
            'rows': rows
        }

    def _build_models_table(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Models table definition"""
        rows = []

        # Try to extract model usage
        by_model = data.get('by_model', [])
        model_usage = data.get('model_usage', [])

        model_list = by_model if by_model else model_usage

        if isinstance(model_list, list) and model_list:
            for entry in model_list:
                if isinstance(entry, dict):
                    rows.append({
                        'model_name': entry.get('model', 'unknown'),
                        'usage_count': entry.get('count', 0),
                        'total_tokens': entry.get('tokens', 0)
                    })
        else:
            # Fallback
            rows.append({
                'model_name': 'all',
                'usage_count': data.get('total_usage', 0),
                'total_tokens': 0
            })

        return {
            'name': 'Models',
            'file': 'data/models.csv',
            'columns': [
                {'name': 'model_name', 'type': 'string', 'key': True},
                {'name': 'usage_count', 'type': 'integer'},
                {'name': 'total_tokens', 'type': 'integer'}
            ],
            'rows': rows
        }

    def _build_lessons_table(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Lessons table definition"""
        rows = []

        lessons = data.get('lessons', [])
        recent_lessons = data.get('recent_lessons', [])

        lesson_list = lessons if lessons else recent_lessons

        if isinstance(lesson_list, list) and lesson_list:
            for i, lesson in enumerate(lesson_list):
                if isinstance(lesson, dict):
                    rows.append({
                        'lesson_id': lesson.get('id', f'lesson_{i+1}'),
                        'category': lesson.get('category', 'general'),
                        'description': lesson.get('description', ''),
                        'created_at': lesson.get('created_at', datetime.now().isoformat())
                    })
        else:
            # Fallback
            rows.append({
                'lesson_id': 'no_lessons',
                'category': 'none',
                'description': 'No lessons captured yet',
                'created_at': datetime.now().isoformat()
            })

        return {
            'name': 'Lessons',
            'file': 'data/lessons.csv',
            'columns': [
                {'name': 'lesson_id', 'type': 'string', 'key': True},
                {'name': 'category', 'type': 'string'},
                {'name': 'description', 'type': 'string'},
                {'name': 'created_at', 'type': 'datetime'}
            ],
            'rows': rows
        }

    def _build_workflows_table(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Workflows table definition"""
        rows = []

        workflows = data.get('workflows', [])
        top_workflows = data.get('top_workflows', [])

        workflow_list = workflows if workflows else top_workflows

        if isinstance(workflow_list, list) and workflow_list:
            for i, workflow in enumerate(workflow_list):
                if isinstance(workflow, dict):
                    rows.append({
                        'workflow_id': workflow.get('id', f'workflow_{i+1}'),
                        'workflow_name': workflow.get('name', 'Unknown'),
                        'executions': workflow.get('count', 0),
                        'avg_duration': workflow.get('avg_duration', 0)
                    })
        else:
            # Fallback
            rows.append({
                'workflow_id': 'no_workflows',
                'workflow_name': 'No Workflows',
                'executions': 0,
                'avg_duration': 0
            })

        return {
            'name': 'Workflows',
            'file': 'data/workflows.csv',
            'columns': [
                {'name': 'workflow_id', 'type': 'string', 'key': True},
                {'name': 'workflow_name', 'type': 'string'},
                {'name': 'executions', 'type': 'integer'},
                {'name': 'avg_duration', 'type': 'decimal'}
            ],
            'rows': rows
        }

    def _build_date_table(self, date_range: Dict[str, Any]) -> Dict[str, Any]:
        """Build Date dimension table for time intelligence"""
        rows = []

        # Generate date rows for the date range
        start_str = date_range.get('start', '')
        end_str = date_range.get('end', '')

        if start_str and end_str:
            try:
                start_date = datetime.strptime(start_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_str, '%Y-%m-%d')

                current_date = start_date
                while current_date <= end_date:
                    rows.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'year': current_date.year,
                        'quarter': f'Q{(current_date.month - 1) // 3 + 1}',
                        'month': current_date.strftime('%B'),
                        'month_number': current_date.month,
                        'day': current_date.day,
                        'day_of_week': current_date.strftime('%A'),
                        'day_of_year': current_date.timetuple().tm_yday
                    })
                    current_date += timedelta(days=1)
            except Exception:
                pass

        # Fallback: at least one row for today
        if not rows:
            today = datetime.now()
            rows.append({
                'date': today.strftime('%Y-%m-%d'),
                'year': today.year,
                'quarter': f'Q{(today.month - 1) // 3 + 1}',
                'month': today.strftime('%B'),
                'month_number': today.month,
                'day': today.day,
                'day_of_week': today.strftime('%A'),
                'day_of_year': today.timetuple().tm_yday
            })

        return {
            'name': 'Date',
            'file': 'data/date.csv',
            'columns': [
                {'name': 'date', 'type': 'date', 'key': True},
                {'name': 'year', 'type': 'integer'},
                {'name': 'quarter', 'type': 'string'},
                {'name': 'month', 'type': 'string'},
                {'name': 'month_number', 'type': 'integer'},
                {'name': 'day', 'type': 'integer'},
                {'name': 'day_of_week', 'type': 'string'},
                {'name': 'day_of_year', 'type': 'integer'}
            ],
            'rows': rows
        }

    def _export_csv_files(
        self,
        tables: List[Dict[str, Any]],
        data_dir: Path
    ) -> List[str]:
        """
        Export each table to CSV file

        Args:
            tables: List of table definitions with 'name', 'columns', 'rows'
            data_dir: Directory to write CSV files to

        Returns:
            List of exported file paths
        """
        exported_files = []

        for table in tables:
            table_name = table['name']
            columns = table['columns']
            rows = table.get('rows', [])

            # Determine filename
            filename = f"{table_name.lower()}.csv"
            file_path = data_dir / filename

            # Write CSV with UTF-8 BOM for Excel compatibility
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[col['name'] for col in columns],
                    quoting=csv.QUOTE_MINIMAL
                )

                # Write header
                writer.writeheader()

                # Write data rows
                writer.writerows(rows)

            exported_files.append(str(file_path.absolute()))

        return exported_files

    def _generate_pbids_file(self, data_dir: Path) -> str:
        """
        Generate .pbids connection file

        Args:
            data_dir: Path to data directory

        Returns:
            JSON string for .pbids file
        """
        # Get absolute path to data directory
        abs_data_path = str(data_dir.absolute())

        pbids = {
            "version": "0.1",
            "connections": [
                {
                    "details": {
                        "protocol": "file",
                        "address": {
                            "path": abs_data_path
                        }
                    },
                    "options": {
                        "fileType": "csv"
                    },
                    "mode": "DirectQuery"
                }
            ]
        }

        return json.dumps(pbids, indent=2)

    def _generate_readme(
        self,
        csv_files: List[str],
        data_model: Dict[str, Any]
    ) -> str:
        """Generate README.txt with usage instructions"""
        lines = [
            "Dream Studio Analytics - Power BI Dataset",
            "=" * 50,
            "",
            "This dataset has been exported for use with Power BI Desktop.",
            "",
            "QUICK START:",
            "1. Open Power BI Desktop",
            "2. Double-click 'dataset.pbids' file",
            "3. Power BI will import the CSV files",
            "4. Review schema.json for table relationships and measures",
            "",
            "INCLUDED FILES:",
            ""
        ]

        # List CSV files
        for csv_file in csv_files:
            filename = Path(csv_file).name
            lines.append(f"  - data/{filename}")

        lines.append("")
        lines.append("  - schema.json (table definitions, relationships, measures)")
        lines.append("  - dataset.pbids (Power BI connection file)")
        lines.append("")

        # List tables
        lines.append("TABLES:")
        for table in data_model['tables']:
            table_name = table['name']
            row_count = len(table.get('rows', []))
            lines.append(f"  - {table_name} ({row_count} rows)")

        lines.append("")

        # List measures
        lines.append("SUGGESTED MEASURES:")
        for measure in data_model['measures']:
            lines.append(f"  - {measure['name']}: {measure['expression']}")

        lines.append("")

        # List relationships
        lines.append("RELATIONSHIPS:")
        for rel in data_model['relationships']:
            lines.append(
                f"  - {rel['from_table']}.{rel['from_column']} → "
                f"{rel['to_table']}.{rel['to_column']} ({rel['cardinality']})"
            )

        lines.append("")
        lines.append("=" * 50)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return '\n'.join(lines)


# Import timedelta for date table generation
from datetime import timedelta
