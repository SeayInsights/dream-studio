"""Example usage of PowerBIExporter - demonstrates Power BI dataset export"""
from pathlib import Path
from analytics.core.reports import ReportGenerator
from analytics.exporters import PowerBIExporter


def example_export_powerbi_dataset():
    """
    Generate a detailed analytics report and export as Power BI dataset

    Creates a directory with:
    - CSV files for each table
    - schema.json with relationships and measures
    - dataset.pbids connection file
    - README.txt with usage instructions
    """
    print("=== Power BI Dataset Export Example ===\n")

    # Step 1: Generate analytics report
    print("1. Generating analytics report...")
    generator = ReportGenerator(db_path="~/.dream-studio/state/studio.db")

    report = generator.generate_report(
        report_type="detailed",
        config={
            "date_range": ("2026-04-01", "2026-04-30")
        }
    )

    print(f"   Report generated with {len(report['sections'])} sections")
    print()

    # Step 2: Export to Power BI dataset
    print("2. Exporting to Power BI dataset...")
    exporter = PowerBIExporter()

    # Export to Downloads folder (as per CLAUDE.md)
    output_path = Path.home() / "Downloads" / "dream_studio_analytics"

    success, result = exporter.export_dataset(report, output_path)

    if success:
        print(f"   SUCCESS: Dataset exported to {result}")
        print()

        # List exported files
        print("3. Exported files:")
        output_dir = Path(result)

        # List data files
        data_dir = output_dir / "data"
        for csv_file in sorted(data_dir.glob("*.csv")):
            print(f"   - data/{csv_file.name}")

        # List metadata files
        print(f"   - schema.json")
        print(f"   - dataset.pbids")
        print(f"   - README.txt")
        print()

        # Instructions
        print("4. Next Steps:")
        print("   a) Open Power BI Desktop")
        print(f"   b) Double-click: {output_dir / 'dataset.pbids'}")
        print("   c) Power BI will import the CSV files")
        print(f"   d) Review schema.json for table relationships and measures")
        print()
        print("5. Suggested Power BI Visuals:")
        print("   - Total Tokens (Card)")
        print("   - Total Cost USD (Card)")
        print("   - Token usage over time (Line Chart)")
        print("   - Top Skills by Invocations (Bar Chart)")
        print("   - Model Usage Distribution (Pie Chart)")
        print("   - Average Success Rate (Gauge)")
        print()

    else:
        print(f"   ERROR: {result}")
        print()


def example_custom_export():
    """
    Generate a custom report focused on cost analysis and export to Power BI
    """
    print("=== Custom Cost Analysis Power BI Export ===\n")

    # Generate custom report focused on costs
    generator = ReportGenerator()

    template = {
        'sections': [
            {
                'title': 'Cost Analysis',
                'metrics': [
                    'tokens.total_cost_usd',
                    'tokens.by_model',
                    'tokens.daily_average'
                ],
                'charts': []
            },
            {
                'title': 'Token Usage',
                'metrics': [
                    'tokens.total_tokens',
                    'tokens.by_date'
                ],
                'charts': []
            }
        ]
    }

    report = generator.generate_report(
        report_type="custom",
        config={
            "date_range": ("2026-04-01", "2026-04-30"),
            "template": template
        }
    )

    # Export to Power BI
    exporter = PowerBIExporter()
    output_path = Path.home() / "Downloads" / "cost_analysis_powerbi"

    success, result = exporter.export_dataset(report, output_path)

    if success:
        print(f"Cost analysis dataset exported to: {result}")
        print("\nThis focused dataset is ideal for:")
        print("  - Executive cost dashboards")
        print("  - Budget tracking")
        print("  - Model cost comparison")
    else:
        print(f"Export failed: {result}")


def example_inspect_schema():
    """
    Generate a report and inspect the Power BI schema
    """
    print("=== Inspect Power BI Schema ===\n")

    generator = ReportGenerator()
    report = generator.generate_report("detailed")

    exporter = PowerBIExporter()

    # Create data model
    data_model = exporter.create_data_model(report)

    # Display schema details
    print("TABLES:")
    for table in data_model['tables']:
        print(f"\n  {table['name']}:")
        print(f"    File: {table['file']}")
        print(f"    Columns:")
        for col in table['columns']:
            key_marker = " (KEY)" if col.get('key') else ""
            print(f"      - {col['name']}: {col['type']}{key_marker}")
        print(f"    Rows: {len(table.get('rows', []))}")

    print("\n\nRELATIONSHIPS:")
    for rel in data_model['relationships']:
        print(f"  - {rel['from_table']}.{rel['from_column']} → {rel['to_table']}.{rel['to_column']}")
        print(f"    Cardinality: {rel['cardinality']}")

    print("\n\nMEASURES:")
    for measure in data_model['measures']:
        print(f"  - {measure['name']}")
        print(f"    Table: {measure['table']}")
        print(f"    Expression: {measure['expression']}")
        print(f"    Format: {measure['format']}")
        print()

    print("\nHIERARCHIES:")
    for hierarchy in data_model['hierarchies']:
        print(f"  - {hierarchy['name']} ({hierarchy['table']})")
        print(f"    Levels: {' → '.join(hierarchy['levels'])}")


if __name__ == "__main__":
    print("PowerBIExporter Examples\n")
    print("Choose an example to run:")
    print("1. Basic export")
    print("2. Custom cost analysis export")
    print("3. Inspect schema (no export)")
    print()

    # Uncomment to run examples:
    # example_export_powerbi_dataset()
    # example_custom_export()
    # example_inspect_schema()

    print("Examples ready to run. Uncomment the function calls above.")
