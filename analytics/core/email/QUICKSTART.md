# Email Notification System - Quick Start Guide

## 5-Minute Setup

### Step 1: Import the Module

```python
from analytics.core.email import EmailSender, TemplateRenderer
```

### Step 2: Configure SMTP (Gmail Example)

```python
sender = EmailSender(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="your-email@gmail.com",
    password="your-app-password",  # NOT your regular Gmail password!
    from_address="Analytics <noreply@example.com>",
    use_tls=True
)
```

**Gmail App Password Setup:**
1. Go to https://myaccount.google.com/apppasswords
2. Generate a new app password
3. Use that password (not your regular Gmail password)

### Step 3: Send Your First Email

**Basic Email:**
```python
sender.send_email(
    to="recipient@example.com",
    subject="Test Email",
    body="<h1>Hello!</h1><p>This works!</p>",
    html=True
)
```

**Report with Template:**
```python
sender.send_report(
    report_path="my_report.pdf",
    recipients=["manager@example.com"],
    report_title="Weekly Analytics",
    date_range="April 24-30, 2026",
    key_metrics={
        "Sessions": "145",
        "Tokens": "2.5M"
    }
)
```

**Alert:**
```python
sender.send_alert(
    recipients=["oncall@example.com"],
    alert_title="High CPU Usage",
    alert_severity="critical",  # critical, warning, or info
    metric_name="CPU Usage",
    metric_value="95%",
    threshold="80%",
    dashboard_url="https://example.com/dashboard"
)
```

## Common Use Cases

### 1. Daily Report Automation

```python
from analytics.core.email import EmailSender
from datetime import datetime

sender = EmailSender(...)  # Configure once

# Generate report (your code)
report_path = generate_daily_report()

# Send to team
sender.send_scheduled_report(
    report_path=report_path,
    recipients=["team@example.com"],
    report_period=f"Daily: {datetime.now().strftime('%B %d, %Y')}",
    next_scheduled="Tomorrow",
    manage_subscription_url="https://example.com/settings"
)
```

### 2. Alert Monitoring

```python
def check_metrics():
    metrics = get_current_metrics()
    
    if metrics['error_rate'] > 5:
        sender.send_alert(
            recipients=["devops@example.com"],
            alert_title="Error Rate Spike",
            alert_severity="critical",
            metric_name="Error Rate",
            metric_value=f"{metrics['error_rate']}%",
            threshold="5%"
        )
```

### 3. Weekly Newsletter

```python
recipients = [
    "user1@example.com",
    "user2@example.com",
    "user3@example.com"
]

newsletter_html = """
<html>
    <body>
        <h1>This Week in Analytics</h1>
        <ul>
            <li>Total sessions: 1,234</li>
            <li>Active users: 567</li>
            <li>New features: 3</li>
        </ul>
    </body>
</html>
"""

sender.send_bulk(
    recipients=recipients,
    subject="Weekly Analytics Update",
    body=newsletter_html,
    html=True
)
```

## Troubleshooting

### "SMTP Authentication Error"
- **Gmail users:** You MUST use an app password, not your regular password
- Generate at: https://myaccount.google.com/apppasswords
- Make sure 2FA is enabled on your Google account

### "Connection Error"
- Check `smtp_host` and `smtp_port` are correct
- Verify firewall isn't blocking port 587
- Try `use_tls=True`

### "Template not found"
- Templates are in `analytics/core/email/templates/`
- Use exact template names: `report_notification.html`, `alert_notification.html`, `scheduled_report.html`

### "Attachment not found"
- Use absolute paths, not relative
- Check file exists: `Path(report_path).exists()`

## SMTP Providers Quick Reference

**Gmail:**
```python
smtp_host="smtp.gmail.com"
smtp_port=587
use_tls=True
# Requires app password
```

**Outlook:**
```python
smtp_host="smtp.office365.com"
smtp_port=587
use_tls=True
```

**SendGrid:**
```python
smtp_host="smtp.sendgrid.net"
smtp_port=587
username="apikey"
password="<your-api-key>"
use_tls=True
```

## Template Variables

**Report Notification:**
- `report_title`
- `report_filename`
- `date_range`
- `key_metrics` (dict)

**Alert Notification:**
- `alert_title`
- `alert_severity`
- `metric_name`
- `metric_value`
- `threshold`
- `dashboard_url`

**Scheduled Report:**
- `report_filename`
- `report_period`
- `next_scheduled`
- `manage_subscription_url`

## Custom Templates

```python
renderer = TemplateRenderer()

# From file
html = renderer.render("my_template.html", {
    "variable": "value"
})

# From string
html = renderer.render_string(
    "<h1>{{title}}</h1>",
    {"title": "Hello"}
)
```

## Best Practices

1. **Store credentials securely** - Use environment variables or config files
2. **Enable TLS** - Always use `use_tls=True` for security
3. **Validate recipients** - Check email format before sending
4. **Handle errors** - Check return value: `if not sender.send_email(...): handle_error()`
5. **Rate limiting** - Be mindful of SMTP provider limits (Gmail: ~500/day)
6. **Test first** - Send test emails before production use

## Next Steps

- Read full documentation: `README.md`
- See all examples: `example_usage.py`
- Customize templates: `templates/*.html`
- Configure SMTP: `config.example.yaml`

## Support

Common issues and solutions in `README.md` → Troubleshooting section.

For template customization, see `README.md` → Custom Templates section.
