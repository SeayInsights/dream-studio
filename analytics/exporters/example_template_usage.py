"""Real-world usage examples for Excel templates

This demonstrates how to integrate ExcelTemplateBuilder with the analytics
system for various use cases.
"""

from datetime import datetime, timedelta
from analytics.core.reports import ReportGenerator
from analytics.exporters import ExcelExporter, ExcelTemplateBuilder


def example_weekly_dashboard():
    """Generate a weekly summary dashboard for stakeholder review"""
    print("Generating Weekly Dashboard...")

    # Initialize
    generator = ReportGenerator()
    exporter = ExcelExporter()
    builder = ExcelTemplateBuilder()

    # Get last 7 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    report = generator.generate_report(
        report_type="detailed",
        config={
            "date_range": (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d")
            )
        }
    )

    # Build dashboard
    wb = exporter.create_workbook()
    builder.build_summary_dashboard(report, wb)

    # Save with timestamp
    timestamp = datetime.now().strftime("%Y%m%d")
    output_path = f"C:/Users/Dannis Seay/Downloads/weekly_dashboard_{timestamp}.xlsx"

    result = exporter.save_workbook(wb, output_path)

    if result["success"]:
        print(f"✓ Dashboard saved: {result['path']}")
    else:
        print(f"✗ Failed: {result['error']}")


def example_monthly_report():
    """Generate a comprehensive monthly report with all templates"""
    print("Generating Monthly Report...")

    # Initialize
    generator = ReportGenerator()
    exporter = ExcelExporter()
    builder = ExcelTemplateBuilder()

    # Get current month data
    today = datetime.now()
    start_of_month = today.replace(day=1)

    current_report = generator.generate_report(
        report_type="detailed",
        config={
            "date_range": (
                start_of_month.strftime("%Y-%m-%d"),
                today.strftime("%Y-%m-%d")
            )
        }
    )

    # Get previous month data for comparison
    end_of_last_month = start_of_month - timedelta(days=1)
    start_of_last_month = end_of_last_month.replace(day=1)

    previous_report = generator.generate_report(
        report_type="detailed",
        config={
            "date_range": (
                start_of_last_month.strftime("%Y-%m-%d"),
                end_of_last_month.strftime("%Y-%m-%d")
            )
        }
    )

    # Build comprehensive report
    wb = exporter.create_workbook()
    builder.build_summary_dashboard(current_report, wb)
    builder.build_comparison(current_report, wb, previous_report)
    builder.build_trend_analysis(current_report, wb)
    builder.build_raw_data_dump(current_report, wb)

    # Save
    month_name = today.strftime("%B_%Y")
    output_path = f"C:/Users/Dannis Seay/Downloads/monthly_report_{month_name}.xlsx"

    result = exporter.save_workbook(wb, output_path)

    if result["success"]:
        print(f"✓ Monthly report saved: {result['path']}")
        print(f"  Sheets: {len(wb.sheetnames)}")
    else:
        print(f"✗ Failed: {result['error']}")


def example_quarter_comparison():
    """Generate quarter-over-quarter comparison"""
    print("Generating Quarter Comparison...")

    # Initialize
    generator = ReportGenerator()
    exporter = ExcelExporter()
    builder = ExcelTemplateBuilder()

    # Q1 2026
    q1_report = generator.generate_report(
        report_type="detailed",
        config={"date_range": ("2026-01-01", "2026-03-31")}
    )

    # Q2 2026
    q2_report = generator.generate_report(
        report_type="detailed",
        config={"date_range": ("2026-04-01", "2026-06-30")}
    )

    # Build comparison
    wb = exporter.create_workbook()
    builder.build_comparison(q2_report, wb, q1_report)

    # Save
    output_path = "C:/Users/Dannis Seay/Downloads/Q2_vs_Q1_2026.xlsx"
    result = exporter.save_workbook(wb, output_path)

    if result["success"]:
        print(f"✓ Quarter comparison saved: {result['path']}")
    else:
        print(f"✗ Failed: {result['error']}")


def example_data_export_for_analysis():
    """Export raw data for custom analysis in Excel/Power BI"""
    print("Generating Data Export...")

    # Initialize
    generator = ReportGenerator()
    exporter = ExcelExporter()
    builder = ExcelTemplateBuilder()

    # Get all data from last 90 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    report = generator.generate_report(
        report_type="detailed",
        config={
            "date_range": (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d")
            )
        }
    )

    # Export raw data only
    wb = exporter.create_workbook()
    builder.build_raw_data_dump(report, wb)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"C:/Users/Dannis Seay/Downloads/analytics_data_export_{timestamp}.xlsx"

    result = exporter.save_workbook(wb, output_path)

    if result["success"]:
        print(f"✓ Data export saved: {result['path']}")
        print(f"  This file can be imported into Power BI or used for pivot tables")
    else:
        print(f"✗ Failed: {result['error']}")


def example_custom_kpi_report():
    """Generate a custom report with specific metrics"""
    print("Generating Custom KPI Report...")

    # Initialize
    generator = ReportGenerator()
    exporter = ExcelExporter()
    builder = ExcelTemplateBuilder()

    # Define custom report template
    custom_template = {
        'sections': [
            {
                'title': 'Cost Metrics',
                'metrics': [
                    'tokens.total_cost_usd',
                    'tokens.by_model',
                    'tokens.daily_average'
                ],
                'charts': []
            },
            {
                'title': 'Efficiency Metrics',
                'metrics': [
                    'skills.success_rate_overall',
                    'sessions.avg_duration_minutes',
                    'workflows.success_rate'
                ],
                'charts': []
            }
        ]
    }

    # Generate custom report
    report = generator.generate_report(
        report_type="custom",
        config={
            "date_range": ("2026-04-01", "2026-04-30"),
            "template": custom_template
        }
    )

    # Use summary dashboard template (it will extract available metrics)
    wb = exporter.create_workbook()
    builder.build_summary_dashboard(report, wb)

    # Save
    output_path = "C:/Users/Dannis Seay/Downloads/custom_kpi_report.xlsx"
    result = exporter.save_workbook(wb, output_path)

    if result["success"]:
        print(f"✓ Custom KPI report saved: {result['path']}")
    else:
        print(f"✗ Failed: {result['error']}")


def example_automated_weekly_report():
    """Example of how to automate weekly report generation

    This could be scheduled via cron/Task Scheduler to run every Monday.
    """
    print("Generating Automated Weekly Report...")

    try:
        # Initialize
        generator = ReportGenerator()
        exporter = ExcelExporter()
        builder = ExcelTemplateBuilder()

        # Get last 7 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        # Generate report
        report = generator.generate_report(
            report_type="detailed",
            config={
                "date_range": (
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d")
                )
            }
        )

        # Build workbook with dashboard and comparison
        wb = exporter.create_workbook()
        builder.build_summary_dashboard(report, wb)

        # Try to get previous week for comparison
        try:
            prev_end = start_date - timedelta(days=1)
            prev_start = prev_end - timedelta(days=7)

            prev_report = generator.generate_report(
                report_type="detailed",
                config={
                    "date_range": (
                        prev_start.strftime("%Y-%m-%d"),
                        prev_end.strftime("%Y-%m-%d")
                    )
                }
            )

            builder.build_comparison(report, wb, prev_report)
        except Exception as e:
            print(f"  Warning: Could not generate comparison: {e}")

        # Save with week number
        week_num = end_date.strftime("%U")
        year = end_date.strftime("%Y")
        output_path = f"C:/Users/Dannis Seay/Downloads/weekly_report_W{week_num}_{year}.xlsx"

        result = exporter.save_workbook(wb, output_path)

        if result["success"]:
            print(f"✓ Weekly report saved: {result['path']}")

            # In production, you might email this or upload to SharePoint
            # send_email_with_attachment(result['path'])
            # upload_to_sharepoint(result['path'])

            return True
        else:
            print(f"✗ Failed: {result['error']}")
            return False

    except Exception as e:
        print(f"✗ Error generating report: {e}")
        return False


def main():
    """Run example scenarios"""
    print("=" * 60)
    print("Excel Template Usage Examples")
    print("=" * 60)
    print()

    # Run examples
    # Note: Most of these will fail if you don't have a populated database
    # They're meant to show usage patterns

    examples = [
        ("Weekly Dashboard", example_weekly_dashboard),
        ("Monthly Report", example_monthly_report),
        ("Quarter Comparison", example_quarter_comparison),
        ("Data Export", example_data_export_for_analysis),
        ("Custom KPI Report", example_custom_kpi_report),
        ("Automated Weekly", example_automated_weekly_report),
    ]

    print("Select an example to run:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    print("  0. Exit")
    print()

    try:
        choice = input("Enter choice (0-6): ").strip()
        choice_num = int(choice)

        if choice_num == 0:
            print("Exiting...")
            return

        if 1 <= choice_num <= len(examples):
            name, func = examples[choice_num - 1]
            print()
            print(f"Running: {name}")
            print("-" * 60)
            func()
            print()
        else:
            print("Invalid choice")

    except (ValueError, KeyboardInterrupt):
        print("\nExiting...")
    except Exception as e:
        print(f"\nError: {e}")

    print("=" * 60)


if __name__ == "__main__":
    main()
