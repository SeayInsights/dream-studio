"""
Example usage of the email notification system.

This demonstrates how to:
1. Configure the email sender
2. Send basic emails
3. Send reports with templates
4. Send alerts
5. Send scheduled reports
6. Send bulk emails
"""

from analytics.core.email import EmailSender, TemplateRenderer


def example_basic_email():
    """Send a basic HTML email."""

    sender = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="your-email@gmail.com",
        password="your-app-password",
        from_address="Analytics <noreply@example.com>"
    )

    success = sender.send_email(
        to="recipient@example.com",
        subject="Test Email",
        body="<h1>Hello!</h1><p>This is a test email.</p>",
        html=True
    )

    print(f"Email sent: {success}")


def example_report_email():
    """Send a report with the report notification template."""

    sender = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="your-email@gmail.com",
        password="your-app-password",
        from_address="Analytics <noreply@example.com>"
    )

    success = sender.send_report(
        report_path="weekly_report.pdf",
        recipients=["manager@example.com", "team@example.com"],
        report_title="Weekly Analytics Summary",
        date_range="April 24-30, 2026",
        key_metrics={
            "Total Sessions": "145",
            "Total Tokens": "2.5M",
            "Avg Session Duration": "12.5 min",
            "Active Users": "32"
        }
    )

    print(f"Report sent: {success}")


def example_alert_email():
    """Send an alert notification."""

    sender = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="your-email@gmail.com",
        password="your-app-password",
        from_address="Analytics <noreply@example.com>"
    )

    success = sender.send_alert(
        recipients=["oncall@example.com"],
        alert_title="High Error Rate Detected",
        alert_severity="critical",
        metric_name="Error Rate",
        metric_value="15.2%",
        threshold="5%",
        dashboard_url="https://analytics.example.com/dashboard/errors"
    )

    print(f"Alert sent: {success}")


def example_scheduled_report():
    """Send a scheduled report."""

    sender = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="your-email@gmail.com",
        password="your-app-password",
        from_address="Analytics <noreply@example.com>"
    )

    success = sender.send_scheduled_report(
        report_path="monthly_report.pdf",
        recipients=["stakeholders@example.com"],
        report_period="Monthly: April 2026",
        next_scheduled="June 1, 2026",
        manage_subscription_url="https://analytics.example.com/settings/subscriptions"
    )

    print(f"Scheduled report sent: {success}")


def example_bulk_email():
    """Send the same email to multiple recipients (BCC for privacy)."""

    sender = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="your-email@gmail.com",
        password="your-app-password",
        from_address="Analytics <noreply@example.com>"
    )

    recipients = [
        "user1@example.com",
        "user2@example.com",
        "user3@example.com"
    ]

    success = sender.send_bulk(
        recipients=recipients,
        subject="Weekly Analytics Newsletter",
        body="<h1>This Week in Analytics</h1><p>Your weekly summary...</p>",
        html=True
    )

    print(f"Bulk email sent to {len(recipients)} recipients: {success}")


def example_custom_template():
    """Use the template renderer directly for custom templates."""

    renderer = TemplateRenderer()

    # Render from template file
    html = renderer.render("report_notification.html", {
        "report_title": "Custom Report",
        "report_filename": "custom_report.xlsx",
        "date_range": "Last 30 Days",
        "key_metrics": {
            "Metric 1": "100",
            "Metric 2": "200",
            "Metric 3": "300"
        }
    })

    # Render from string
    custom_html = renderer.render_string(
        "<h1>{{title}}</h1><p>{{message}}</p>",
        {"title": "Hello", "message": "World"}
    )

    print("Template rendered successfully")


def example_email_with_attachments():
    """Send an email with multiple attachments."""

    sender = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="your-email@gmail.com",
        password="your-app-password",
        from_address="Analytics <noreply@example.com>"
    )

    success = sender.send_email(
        to="recipient@example.com",
        subject="Monthly Reports Package",
        body="<h1>Monthly Reports</h1><p>Please find attached this month's reports.</p>",
        attachments=[
            "report_summary.pdf",
            "detailed_metrics.xlsx",
            "charts.png"
        ],
        html=True
    )

    print(f"Email with attachments sent: {success}")


def example_email_with_inline_images():
    """Send an email with inline images (embedded in HTML)."""

    sender = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="your-email@gmail.com",
        password="your-app-password",
        from_address="Analytics <noreply@example.com>"
    )

    html_body = """
    <html>
        <body>
            <h1>Analytics Dashboard Preview</h1>
            <p>Here's a preview of your dashboard:</p>
            <img src="cid:dashboard_screenshot" alt="Dashboard" style="max-width: 100%;">
            <p>Full report attached.</p>
        </body>
    </html>
    """

    success = sender.send_email(
        to="recipient@example.com",
        subject="Dashboard Preview",
        body=html_body,
        inline_images={
            "dashboard_screenshot": "dashboard.png"
        },
        html=True
    )

    print(f"Email with inline image sent: {success}")


if __name__ == "__main__":
    print("Email notification system examples")
    print("-" * 50)
    print("\nNote: Update SMTP credentials before running these examples!")
    print("\nAvailable examples:")
    print("1. example_basic_email()")
    print("2. example_report_email()")
    print("3. example_alert_email()")
    print("4. example_scheduled_report()")
    print("5. example_bulk_email()")
    print("6. example_custom_template()")
    print("7. example_email_with_attachments()")
    print("8. example_email_with_inline_images()")
    print("\nUncomment the examples you want to run:")

    # Uncomment to run examples:
    # example_basic_email()
    # example_report_email()
    # example_alert_email()
    # example_scheduled_report()
    # example_bulk_email()
    # example_custom_template()
    # example_email_with_attachments()
    # example_email_with_inline_images()
