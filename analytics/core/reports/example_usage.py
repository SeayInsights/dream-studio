"""Example usage of ReportGenerator - demonstrates report generation"""
from analytics.core.reports import ReportGenerator


def example_summary_report():
    """Generate a summary report for the last 30 days"""
    generator = ReportGenerator(db_path="~/.dream-studio/state/studio.db")

    report = generator.generate_report(
        report_type="summary",
        config={"date_range": ("2026-04-01", "2026-04-30")}
    )

    print("=== Summary Report ===")
    print(f"Generated: {report['metadata']['generated_at']}")
    print(f"Date range: {report['metadata']['date_range']['start']} to {report['metadata']['date_range']['end']}")
    print(f"Days: {report['metadata']['date_range']['days']}")
    print()

    for section in report['sections']:
        print(f"--- {section['title']} ---")
        for key, value in section['metrics'].items():
            print(f"  {key}: {value}")
        print()


def example_detailed_report():
    """Generate a detailed report"""
    generator = ReportGenerator()

    # Last 7 days
    report = generator.generate_report(
        report_type="detailed"
    )

    print("=== Detailed Report ===")
    print(f"Generated: {report['metadata']['generated_at']}")
    print(f"Sections: {len(report['sections'])}")

    for section in report['sections']:
        print(f"  - {section['title']}")


def example_custom_report():
    """Generate a custom report with specific metrics"""
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
                'charts': [
                    {'type': 'line', 'metric': 'tokens.daily_average'}
                ]
            },
            {
                'title': 'Top Skills Performance',
                'metrics': [
                    'skills.top_skills',
                    'skills.success_rate_overall'
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

    print("=== Custom Report ===")
    for section in report['sections']:
        print(f"--- {section['title']} ---")
        for key, value in section['metrics'].items():
            print(f"  {key}: {value}")
        print()


if __name__ == "__main__":
    print("ReportGenerator Examples\n")

    # Uncomment to run examples
    # example_summary_report()
    # example_detailed_report()
    # example_custom_report()

    print("Examples ready to run. Uncomment the function calls above.")
