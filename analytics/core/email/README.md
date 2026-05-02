# Email Notification System

Production-ready email delivery system for analytics reports and alerts.

## Features

- **Zero external dependencies** - Uses Python's built-in `smtplib` and `email` modules
- **HTML email support** - Mobile-responsive templates with inline CSS
- **File attachments** - PDF, Excel, images, and any file type
- **Inline images** - Embed images directly in HTML emails
- **Bulk sending** - Send to multiple recipients with BCC for privacy
- **Template system** - Simple {{variable}} syntax for template rendering
- **Professional templates** - Pre-built templates for reports, alerts, and scheduled reports

## Quick Start

### 1. Configuration

```python
from analytics.core.email import EmailSender

sender = EmailSender(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="your-email@gmail.com",
    password="your-app-password",  # Use app password for Gmail
    from_address="Analytics <noreply@example.com>",
    use_tls=True
)
```

### 2. Send a Basic Email

```python
sender.send_email(
    to="recipient@example.com",
    subject="Test Email",
    body="<h1>Hello!</h1><p>This is a test.</p>",
    html=True
)
```

### 3. Send a Report

```python
sender.send_report(
    report_path="weekly_report.pdf",
    recipients=["manager@example.com"],
    report_title="Weekly Analytics Summary",
    date_range="April 24-30, 2026",
    key_metrics={
        "Total Sessions": "145",
        "Total Tokens": "2.5M"
    }
)
```

### 4. Send an Alert

```python
sender.send_alert(
    recipients=["oncall@example.com"],
    alert_title="High Error Rate",
    alert_severity="critical",
    metric_name="Error Rate",
    metric_value="15.2%",
    threshold="5%",
    dashboard_url="https://example.com/dashboard"
)
```

## Templates

Three pre-built templates are included:

### 1. Report Notification (`report_notification.html`)
- Professional report delivery
- Key metrics preview
- Download button
- Mobile-responsive

### 2. Alert Notification (`alert_notification.html`)
- Severity-based styling (critical/warning/info)
- Large metric value display
- Threshold comparison
- Action button to dashboard

### 3. Scheduled Report (`scheduled_report.html`)
- Automated delivery badge
- Report period and schedule info
- Next delivery date
- Subscription management

## Template Variables

### Report Notification
- `{{report_title}}` - Report title
- `{{report_filename}}` - Attachment filename
- `{{date_range}}` - Date range covered
- `{{key_metrics}}` - Dict of key metrics (auto-formatted as list)

### Alert Notification
- `{{alert_title}}` - Alert title
- `{{alert_severity}}` - Severity (critical/warning/info)
- `{{metric_name}}` - Metric name
- `{{metric_value}}` - Current value
- `{{threshold}}` - Threshold value
- `{{dashboard_url}}` - Link to dashboard

### Scheduled Report
- `{{report_filename}}` - Attachment filename
- `{{report_period}}` - Report period description
- `{{next_scheduled}}` - Next delivery date
- `{{manage_subscription_url}}` - Subscription settings link

## Custom Templates

Create your own templates with the `TemplateRenderer`:

```python
from analytics.core.email import TemplateRenderer

renderer = TemplateRenderer()

# Render from file
html = renderer.render("my_template.html", {
    "variable1": "value1",
    "variable2": "value2"
})

# Render from string
html = renderer.render_string(
    "<h1>{{title}}</h1><p>{{message}}</p>",
    {"title": "Hello", "message": "World"}
)
```

## SMTP Configuration

### Gmail
```python
smtp_host="smtp.gmail.com"
smtp_port=587
username="your-email@gmail.com"
password="your-app-password"  # Generate at: https://myaccount.google.com/apppasswords
use_tls=True
```

### Outlook/Office 365
```python
smtp_host="smtp.office365.com"
smtp_port=587
username="your-email@outlook.com"
password="your-password"
use_tls=True
```

### SendGrid
```python
smtp_host="smtp.sendgrid.net"
smtp_port=587
username="apikey"
password="<your-sendgrid-api-key>"
use_tls=True
```

### Amazon SES
```python
smtp_host="email-smtp.us-east-1.amazonaws.com"
smtp_port=587
username="<your-smtp-username>"
password="<your-smtp-password>"
use_tls=True
```

## Error Handling

The email sender returns `True` on success, `False` on failure. Errors are logged:

```python
success = sender.send_email(...)
if not success:
    print("Email failed to send - check logs")
```

Common errors:
- **Authentication failed** - Wrong username/password or app password required
- **Connection failed** - SMTP host/port incorrect or firewall blocking
- **File not found** - Attachment path doesn't exist
- **Invalid email** - Malformed recipient address

## Advanced Features

### Multiple Recipients
```python
sender.send_email(
    to=["user1@example.com", "user2@example.com"],
    subject="Report",
    body="<h1>Hello all!</h1>"
)
```

### Bulk Sending (BCC)
```python
sender.send_bulk(
    recipients=["user1@example.com", "user2@example.com", "user3@example.com"],
    subject="Newsletter",
    body="<h1>Weekly update</h1>"
)
```

### Multiple Attachments
```python
sender.send_email(
    to="recipient@example.com",
    subject="Reports Package",
    body="<h1>Reports attached</h1>",
    attachments=["report1.pdf", "report2.xlsx", "chart.png"]
)
```

### Inline Images
```python
html = """
<html>
    <body>
        <h1>Dashboard Preview</h1>
        <img src="cid:logo" alt="Logo">
        <img src="cid:chart" alt="Chart">
    </body>
</html>
"""

sender.send_email(
    to="recipient@example.com",
    subject="Dashboard",
    body=html,
    inline_images={
        "logo": "logo.png",
        "chart": "chart.png"
    }
)
```

## File Structure

```
analytics/core/email/
├── __init__.py                 # Module exports
├── sender.py                   # EmailSender class
├── template_renderer.py        # Template rendering
├── config.example.yaml         # Example configuration
├── example_usage.py            # Usage examples
├── README.md                   # This file
└── templates/
    ├── report_notification.html
    ├── alert_notification.html
    └── scheduled_report.html
```

## Testing

Run the example script to test:

```bash
python analytics/core/email/example_usage.py
```

Update SMTP credentials in the examples before running.

## Security Notes

1. **Never commit SMTP passwords** - Use environment variables or config files (gitignored)
2. **Use app-specific passwords** - Gmail requires app passwords, not your main password
3. **Enable TLS** - Always use `use_tls=True` for secure connections
4. **Validate recipients** - Sanitize email addresses to prevent injection
5. **Rate limiting** - Be mindful of SMTP provider rate limits

## Compliance

All templates include:
- Unsubscribe links (required by CAN-SPAM Act)
- Sender identification
- Clear subject lines
- Physical address recommendation (add to footer for compliance)

## Troubleshooting

**"SMTP Authentication Error"**
- Check username/password
- For Gmail, use an app password instead of your regular password
- Verify 2FA is enabled if using app passwords

**"SMTP Connection Error"**
- Verify smtp_host and smtp_port
- Check firewall/antivirus settings
- Ensure TLS is enabled for port 587

**"Attachment not found"**
- Verify file path is absolute, not relative
- Check file exists before sending
- Ensure proper file permissions

**"Template not found"**
- Check template filename matches exactly
- Verify templates are in `analytics/core/email/templates/`
- Use absolute path if custom template directory

## Examples

See `example_usage.py` for complete working examples of all features.
