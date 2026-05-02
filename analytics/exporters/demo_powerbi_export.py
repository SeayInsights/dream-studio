"""Demo script to test PowerBIExporter with sample data"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from analytics.exporters import PowerBIExporter
import json


def create_sample_report():
    """Create sample report data for testing"""
    return {
        'metadata': {
            'generated_at': '2026-05-01T14:30:00',
            'report_type': 'detailed',
            'date_range': {
                'start': '2026-04-01',
                'end': '2026-04-30',
                'days': 30
            }
        },
        'sections': [
            {
                'title': 'Skills',
                'metrics': {
                    'total_invocations': 250,
                    'success_rate_overall': 0.96,
                    'top_skills': [
                        {'name': 'dream-studio:core', 'count': 80, 'success_rate': 0.97},
                        {'name': 'dream-studio:quality', 'count': 70, 'success_rate': 0.95},
                        {'name': 'dream-studio:domains', 'count': 50, 'success_rate': 0.94},
                        {'name': 'dream-studio:security', 'count': 30, 'success_rate': 0.98},
                        {'name': 'dream-studio:career', 'count': 20, 'success_rate': 0.96}
                    ]
                }
            },
            {
                'title': 'Tokens',
                'metrics': {
                    'total_tokens': 2500000,
                    'total_cost_usd': 75.50,
                    'by_model': [
                        {'model': 'claude-sonnet-4.5', 'tokens': 1800000, 'cost': 54.00},
                        {'model': 'claude-haiku-4', 'tokens': 700000, 'cost': 21.50}
                    ],
                    'by_date': [
                        {'date': '2026-04-01', 'tokens': 100000, 'cost': 3.00},
                        {'date': '2026-04-02', 'tokens': 95000, 'cost': 2.85},
                        {'date': '2026-04-03', 'tokens': 110000, 'cost': 3.30}
                    ]
                }
            },
            {
                'title': 'Sessions',
                'metrics': {
                    'recent_sessions': [
                        {'id': 'sess_001', 'date': '2026-04-15', 'duration': 120, 'project': 'dream-studio'},
                        {'id': 'sess_002', 'date': '2026-04-16', 'duration': 90, 'project': 'client-work'},
                        {'id': 'sess_003', 'date': '2026-04-18', 'duration': 150, 'project': 'dream-studio'},
                        {'id': 'sess_004', 'date': '2026-04-20', 'duration': 75, 'project': 'dashboard'},
                        {'id': 'sess_005', 'date': '2026-04-22', 'duration': 110, 'project': 'security-scan'}
                    ]
                }
            },
            {
                'title': 'Models',
                'metrics': {
                    'by_model': [
                        {'model': 'claude-sonnet-4.5', 'count': 180, 'tokens': 1800000},
                        {'model': 'claude-haiku-4', 'count': 70, 'tokens': 700000}
                    ]
                }
            },
            {
                'title': 'Lessons',
                'metrics': {
                    'recent_lessons': [
                        {
                            'id': 'lesson_001',
                            'category': 'performance',
                            'description': 'Use Haiku for exploration subagents to save costs',
                            'created_at': '2026-04-10T10:00:00'
                        },
                        {
                            'id': 'lesson_002',
                            'category': 'workflow',
                            'description': 'Always check for open PRs before creating new branch',
                            'created_at': '2026-04-12T14:30:00'
                        },
                        {
                            'id': 'lesson_003',
                            'category': 'quality',
                            'description': 'Run /compact before large tasks to save context',
                            'created_at': '2026-04-15T09:15:00'
                        }
                    ]
                }
            },
            {
                'title': 'Workflows',
                'metrics': {
                    'top_workflows': [
                        {'id': 'wf_001', 'name': 'build-test-deploy', 'count': 25, 'avg_duration': 45.5},
                        {'id': 'wf_002', 'name': 'security-scan-mitigate', 'count': 15, 'avg_duration': 60.2},
                        {'id': 'wf_003', 'name': 'debug-fix-verify', 'count': 20, 'avg_duration': 35.8}
                    ]
                }
            }
        ]
    }


def main():
    """Run PowerBI export demo"""
    print("=" * 60)
    print("PowerBI Exporter Demo")
    print("=" * 60)
    print()

    # Create sample report
    print("1. Creating sample report data...")
    report = create_sample_report()
    print(f"   [OK] Report generated with {len(report['sections'])} sections")
    print()

    # Initialize exporter
    print("2. Initializing PowerBIExporter...")
    exporter = PowerBIExporter()
    print("   [OK] Exporter initialized")
    print()

    # Export dataset
    print("3. Exporting dataset...")
    output_path = Path("demo_powerbi_export")

    success, result = exporter.export_dataset(report, output_path)

    if not success:
        print(f"   [ERROR] Export failed: {result}")
        return

    print(f"   [OK] Dataset exported to: {result}")
    print()

    # Verify files
    print("4. Verifying exported files...")
    output_dir = Path(result)
    data_dir = output_dir / "data"

    expected_files = [
        (data_dir / "skills.csv", "Skills data"),
        (data_dir / "tokens.csv", "Token usage data"),
        (data_dir / "sessions.csv", "Session data"),
        (data_dir / "models.csv", "Model usage data"),
        (data_dir / "lessons.csv", "Lessons learned"),
        (data_dir / "workflows.csv", "Workflow data"),
        (data_dir / "date.csv", "Date dimension"),
        (output_dir / "schema.json", "Schema metadata"),
        (output_dir / "dataset.pbids", "Power BI connection file"),
        (output_dir / "README.txt", "Usage instructions")
    ]

    all_exist = True
    for file_path, description in expected_files:
        exists = file_path.exists()
        status = "[OK]" if exists else "[MISSING]"
        print(f"   {status} {file_path.name} - {description}")
        all_exist = all_exist and exists

    print()

    if not all_exist:
        print("[WARNING] Some files are missing!")
        return

    # Display schema summary
    print("5. Schema Summary:")
    print()

    schema_path = output_dir / "schema.json"
    with open(schema_path, 'r') as f:
        schema = json.load(f)

    print(f"   Tables: {len(schema['tables'])}")
    for table in schema['tables']:
        row_count = len(table.get('rows', []))
        print(f"     - {table['name']}: {row_count} rows, {len(table['columns'])} columns")

    print()
    print(f"   Relationships: {len(schema['relationships'])}")
    for rel in schema['relationships']:
        print(f"     - {rel['from_table']}.{rel['from_column']} -> {rel['to_table']}.{rel['to_column']}")

    print()
    print(f"   Measures: {len(schema['measures'])}")
    for measure in schema['measures']:
        print(f"     - {measure['name']}: {measure['expression']}")

    print()

    # Next steps
    print("6. Next Steps:")
    print()
    print("   To use this dataset in Power BI Desktop:")
    print(f"     1. Navigate to: {output_dir.absolute()}")
    print("     2. Double-click: dataset.pbids")
    print("     3. Power BI will open and load all CSV files")
    print()
    print("   Suggested visuals:")
    print("     - Total Tokens (Card)")
    print("     - Total Cost USD (Card)")
    print("     - Token usage over time (Line Chart)")
    print("     - Top Skills by Invocations (Bar Chart)")
    print()

    print("=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
