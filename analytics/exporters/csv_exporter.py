"""CSVExporter - Export analytics reports to CSV format"""
import csv
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime


class CSVExporter:
    """
    Export analytics reports to CSV format.

    Supports single-file, multi-file, and ZIP archive exports with
    proper Excel compatibility (UTF-8 with BOM, proper escaping).
    """

    def __init__(self):
        """Initialize CSVExporter"""
        pass

    def export_to_csv(
        self,
        data: Dict[str, Any],
        output_path: Union[str, Path]
    ) -> Tuple[bool, str]:
        """
        Export report data to a single CSV file

        Flattens all sections and metrics into a simple table:
        Section, Metric, Value

        Args:
            data: Report data dict with 'metadata' and 'sections' keys
            output_path: Path to output CSV file

        Returns:
            Tuple of (success: bool, message: str)
            On success: (True, file_path)
            On error: (False, error_message)
        """
        try:
            # Validate data structure
            error = self._validate_data(data)
            if error:
                return (False, error)

            output_path = Path(output_path)

            # Check parent directory exists
            if not output_path.parent.exists():
                return (False, f"Directory does not exist: {output_path.parent}")

            # Flatten data to rows
            rows = self._flatten_to_rows(data)

            # Write CSV with UTF-8 BOM for Excel compatibility
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)

                # Write header
                writer.writerow(['Section', 'Metric', 'Value'])

                # Write data rows
                writer.writerows(rows)

            return (True, str(output_path.absolute()))

        except PermissionError:
            return (False, f"Permission denied writing to: {output_path}")
        except OSError as e:
            return (False, f"OS error: {e}")
        except Exception as e:
            return (False, f"Unexpected error: {e}")

    def export_multiple(
        self,
        data: Dict[str, Any],
        output_dir: Union[str, Path]
    ) -> Tuple[bool, Union[List[str], str]]:
        """
        Export report data to multiple CSV files (one per section)

        Creates separate CSV files for each section with metric-specific
        structure. File names are derived from section titles.

        Args:
            data: Report data dict with 'metadata' and 'sections' keys
            output_dir: Directory to write CSV files to

        Returns:
            Tuple of (success: bool, result: List[str] or str)
            On success: (True, [file_paths])
            On error: (False, error_message)
        """
        try:
            # Validate data structure
            error = self._validate_data(data)
            if error:
                return (False, error)

            output_dir = Path(output_dir)

            # Create directory if it doesn't exist
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return (False, f"Failed to create directory {output_dir}: {e}")

            # Export each section to its own file
            file_paths = []
            sections = data.get('sections', [])

            for section in sections:
                title = section.get('title', 'Untitled')
                filename = self._sanitize_filename(title) + '.csv'
                file_path = output_dir / filename

                # Convert section to CSV
                success, result = self._export_section_to_csv(section, file_path)

                if not success:
                    return (False, f"Failed to export section '{title}': {result}")

                file_paths.append(str(file_path.absolute()))

            # Also create metadata file
            metadata_path = output_dir / 'metadata.txt'
            success, result = self._export_metadata_txt(data.get('metadata', {}), metadata_path)

            if not success:
                return (False, f"Failed to export metadata: {result}")

            file_paths.append(str(metadata_path.absolute()))

            return (True, file_paths)

        except Exception as e:
            return (False, f"Unexpected error: {e}")

    def export_as_zip(
        self,
        data: Dict[str, Any],
        output_path: Union[str, Path]
    ) -> Tuple[bool, str]:
        """
        Export report data as a ZIP archive containing multiple CSV files

        Same as export_multiple but packages all files in a .zip archive.

        Args:
            data: Report data dict with 'metadata' and 'sections' keys
            output_path: Path to output ZIP file

        Returns:
            Tuple of (success: bool, message: str)
            On success: (True, file_path)
            On error: (False, error_message)
        """
        try:
            # Validate data structure
            error = self._validate_data(data)
            if error:
                return (False, error)

            output_path = Path(output_path)

            # Check parent directory exists
            if not output_path.parent.exists():
                return (False, f"Directory does not exist: {output_path.parent}")

            # Create ZIP file
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                sections = data.get('sections', [])

                # Add each section as a CSV file
                for section in sections:
                    title = section.get('title', 'Untitled')
                    filename = self._sanitize_filename(title) + '.csv'

                    # Generate CSV content in memory
                    csv_content = self._section_to_csv_string(section)

                    # Write to ZIP
                    zipf.writestr(filename, csv_content)

                # Add metadata as text file
                metadata_content = self._metadata_to_string(data.get('metadata', {}))
                zipf.writestr('metadata.txt', metadata_content)

            return (True, str(output_path.absolute()))

        except PermissionError:
            return (False, f"Permission denied writing to: {output_path}")
        except OSError as e:
            return (False, f"OS error: {e}")
        except Exception as e:
            return (False, f"Unexpected error: {e}")

    # ---- Private helper methods ----

    def _validate_data(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Validate report data structure

        Returns:
            Error message string if invalid, None if valid
        """
        if not isinstance(data, dict):
            return "Data must be a dict"

        if 'sections' not in data:
            return "Data must contain 'sections' key"

        if not isinstance(data['sections'], list):
            return "Data 'sections' must be a list"

        return None  # Valid

    def _flatten_to_rows(self, data: Dict[str, Any]) -> List[List[str]]:
        """
        Flatten report data into rows for single-file CSV export

        Returns:
            List of [section, metric, value] rows
        """
        rows = []

        sections = data.get('sections', [])

        for section in sections:
            section_title = section.get('title', 'Untitled')
            metrics = section.get('metrics', {})

            # Flatten metrics recursively
            flattened = self._flatten_dict(metrics)

            for metric_name, value in flattened.items():
                # Format value
                formatted_value = self._format_value(value)
                rows.append([section_title, metric_name, formatted_value])

        return rows

    def _flatten_dict(self, d: Any, prefix: str = '') -> Dict[str, Any]:
        """
        Recursively flatten nested dict into dot-notation keys

        Args:
            d: Dict to flatten (or other value)
            prefix: Current key prefix

        Returns:
            Flattened dict with dot-notation keys
        """
        if not isinstance(d, dict):
            return {prefix: d} if prefix else {}

        result = {}

        for key, value in d.items():
            new_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                # Recurse into nested dict
                result.update(self._flatten_dict(value, new_key))
            elif isinstance(value, list):
                # Handle lists - enumerate items
                if value and isinstance(value[0], dict):
                    # List of dicts - expand each item
                    for i, item in enumerate(value):
                        item_key = f"{new_key}[{i}]"
                        result.update(self._flatten_dict(item, item_key))
                else:
                    # Simple list - join as string
                    result[new_key] = value
            else:
                # Scalar value
                result[new_key] = value

        return result

    def _format_value(self, value: Any) -> str:
        """
        Format value for CSV output

        Handles booleans, numbers, dates, lists, etc.
        """
        if value is None:
            return ''
        elif isinstance(value, bool):
            return 'True' if value else 'False'
        elif isinstance(value, (int, float)):
            # Plain number format (no commas)
            if isinstance(value, float):
                # Round to 2 decimal places if needed
                if value == int(value):
                    return str(int(value))
                else:
                    return f"{value:.2f}"
            return str(value)
        elif isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, list):
            # Join list items
            return ', '.join(str(item) for item in value)
        else:
            return str(value)

    def _sanitize_filename(self, name: str) -> str:
        """
        Convert section title to safe filename

        Args:
            name: Section title

        Returns:
            Safe filename (lowercase, underscores, no special chars)
        """
        # Convert to lowercase, replace spaces with underscores
        safe = name.lower().replace(' ', '_')

        # Remove special characters
        safe = ''.join(c for c in safe if c.isalnum() or c == '_')

        # Limit length
        return safe[:50]

    def _export_section_to_csv(
        self,
        section: Dict[str, Any],
        file_path: Path
    ) -> Tuple[bool, str]:
        """
        Export a single section to CSV file

        Creates a metric-specific structure based on section content.
        """
        try:
            # Generate CSV content
            csv_content = self._section_to_csv_string(section)

            # Write to file
            with open(file_path, 'w', encoding='utf-8-sig') as f:
                f.write(csv_content)

            return (True, str(file_path.absolute()))

        except Exception as e:
            return (False, str(e))

    def _section_to_csv_string(self, section: Dict[str, Any]) -> str:
        """
        Convert a section to CSV string

        Returns CSV content as string
        """
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        title = section.get('title', 'Untitled')
        metrics = section.get('metrics', {})

        # Determine CSV structure based on metrics content
        if self._is_table_data(metrics):
            # Table-like data (e.g., top_skills with name/count)
            rows = self._metrics_to_table_rows(metrics)

            if rows:
                # Write header
                writer.writerow(rows[0])
                # Write data rows
                for row in rows[1:]:
                    writer.writerow(row)
        else:
            # Simple key-value pairs
            writer.writerow(['Metric', 'Value'])

            flattened = self._flatten_dict(metrics)
            for metric, value in flattened.items():
                writer.writerow([metric, self._format_value(value)])

        return output.getvalue()

    def _is_table_data(self, metrics: Dict[str, Any]) -> bool:
        """
        Check if metrics contain table-like data

        Table data = contains a list of dicts with consistent keys
        """
        for value in metrics.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return True
        return False

    def _metrics_to_table_rows(self, metrics: Dict[str, Any]) -> List[List[str]]:
        """
        Convert metrics to table rows

        Extracts list-of-dict data and converts to rows
        """
        # Find the main table data
        table_key = None
        table_data = None

        for key, value in metrics.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                table_key = key
                table_data = value
                break

        if not table_data:
            return []

        # Extract headers from first item
        headers = list(table_data[0].keys())

        # Build rows
        rows = [headers]  # Header row

        for item in table_data:
            row = [self._format_value(item.get(h)) for h in headers]
            rows.append(row)

        return rows

    def _export_metadata_txt(
        self,
        metadata: Dict[str, Any],
        file_path: Path
    ) -> Tuple[bool, str]:
        """
        Export metadata to text file
        """
        try:
            content = self._metadata_to_string(metadata)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return (True, str(file_path.absolute()))

        except Exception as e:
            return (False, str(e))

    def _metadata_to_string(self, metadata: Dict[str, Any]) -> str:
        """
        Convert metadata dict to formatted text string
        """
        lines = ['Report Metadata', '=' * 40, '']

        for key, value in metadata.items():
            if isinstance(value, dict):
                # Nested dict - format with indentation
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  {sub_key}: {self._format_value(sub_value)}")
            else:
                lines.append(f"{key}: {self._format_value(value)}")

        return '\n'.join(lines)
