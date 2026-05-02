"""Example usage of CSVExporter

This script demonstrates the three export methods:
1. export_to_csv - Single CSV file with all data flattened
2. export_multiple - Multiple CSV files (one per section)
3. export_as_zip - ZIP archive with multiple CSV files
"""
from pathlib import Path
from analytics.core.reports import ReportGenerator
from analytics.exporters import CSVExporter


def main():
    """Run CSV export examples"""

    print("CSV Exporter Example Usage")
    print("=" * 60)

    # Generate a report
    print("\n1. Generating report...")
    generator = ReportGenerator()
    report = generator.generate_report("detailed")

    print(f"   Report type: {report['metadata']['report_type']}")
    print(f"   Date range: {report['metadata']['date_range']['start']} to {report['metadata']['date_range']['end']}")
    print(f"   Sections: {len(report['sections'])}")

    # Initialize exporter
    exporter = CSVExporter()

    # Create output directory
    output_dir = Path("exports/csv_examples")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n2. Exporting to CSV formats...")
    print(f"   Output directory: {output_dir.absolute()}")

    # Example 1: Single CSV file
    print("\n   a) Single CSV file export")
    single_path = output_dir / "report_single.csv"
    success, result = exporter.export_to_csv(report, single_path)

    if success:
        print(f"      ✓ Created: {Path(result).name}")
        print(f"        Size: {Path(result).stat().st_size:,} bytes")
    else:
        print(f"      ✗ Failed: {result}")

    # Example 2: Multiple CSV files
    print("\n   b) Multiple CSV files export")
    multi_dir = output_dir / "multiple"
    success, result = exporter.export_multiple(report, multi_dir)

    if success:
        print(f"      ✓ Created {len(result)} files:")
        for path in result:
            file_path = Path(path)
            print(f"        - {file_path.name} ({file_path.stat().st_size:,} bytes)")
    else:
        print(f"      ✗ Failed: {result}")

    # Example 3: ZIP archive
    print("\n   c) ZIP archive export")
    zip_path = output_dir / "report_archive.zip"
    success, result = exporter.export_as_zip(report, zip_path)

    if success:
        print(f"      ✓ Created: {Path(result).name}")
        print(f"        Size: {Path(result).stat().st_size:,} bytes")

        # Show ZIP contents
        import zipfile
        with zipfile.ZipFile(result, 'r') as zipf:
            print(f"        Contents: {', '.join(zipf.namelist())}")
    else:
        print(f"      ✗ Failed: {result}")

    print("\n" + "=" * 60)
    print("Export complete!")
    print(f"\nView results in: {output_dir.absolute()}")


if __name__ == "__main__":
    main()
