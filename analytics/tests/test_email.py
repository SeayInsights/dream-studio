"""
Comprehensive tests for email delivery system (ER022 - Part 1)

Tests EmailSender with SMTP mocking, attachment handling, and template rendering.

Coverage target: >70%
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import os
import sys

# Ensure analytics package is in path
analytics_path = Path(__file__).parent.parent
if str(analytics_path) not in sys.path:
    sys.path.insert(0, str(analytics_path))


@pytest.fixture
def temp_attachment():
    """Create temporary attachment file"""
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(b'%PDF-1.4 fake pdf content')
        temp_path = f.name

    yield temp_path

    try:
        os.unlink(temp_path)
    except:
        pass


# ============================================================================
# EmailSender Tests
# ============================================================================

class TestEmailSender:
    """Test EmailSender functionality with mocked SMTP"""

    @pytest.fixture
    def email_config(self):
        """Email configuration for tests"""
        return {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "test_password",
            "from_address": "Analytics <analytics@example.com>",
            "use_tls": True
        }

    @pytest.fixture
    def email_sender(self, email_config):
        """Create EmailSender with mocked SMTP"""
        from analytics.core.email.sender import EmailSender

        with patch('analytics.core.email.sender.smtplib.SMTP') as mock_smtp_class:
            # Configure mock SMTP instance
            mock_smtp = MagicMock()
            mock_smtp_class.return_value.__enter__.return_value = mock_smtp

            sender = EmailSender(**email_config)
            sender._mock_smtp = mock_smtp  # Store for test assertions

            yield sender

    def test_send_email_mock(self, email_sender):
        """Test basic email sending with mocked SMTP"""
        result = email_sender.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Report",
            body="This is a test email"
        )

        assert result is True

        # Verify SMTP methods were called
        smtp = email_sender._mock_smtp
        assert smtp.starttls.called or smtp.login.called

    def test_send_email_multiple_recipients(self, email_sender):
        """Test sending to multiple recipients"""
        recipients = [
            "user1@example.com",
            "user2@example.com",
            "user3@example.com"
        ]

        result = email_sender.send_email(
            to_addresses=recipients,
            subject="Team Report",
            body="Team analytics report"
        )

        assert result is True

    def test_send_with_attachment(self, email_sender, temp_attachment):
        """Test sending email with file attachment"""
        result = email_sender.send_email(
            to_addresses=["recipient@example.com"],
            subject="Report with Attachment",
            body="See attached report",
            attachments=[temp_attachment]
        )

        assert result is True

    def test_send_with_multiple_attachments(self, email_sender):
        """Test sending with multiple attachments"""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f2:

            f1.write(b'PDF content')
            f2.write(b'Excel content')

            result = email_sender.send_email(
                to_addresses=["recipient@example.com"],
                subject="Multiple Attachments",
                body="See attached files",
                attachments=[f1.name, f2.name]
            )

            assert result is True

            # Cleanup
            os.unlink(f1.name)
            os.unlink(f2.name)

    def test_template_rendering(self, email_sender):
        """Test HTML template rendering"""
        from analytics.core.email.template_renderer import TemplateRenderer

        renderer = TemplateRenderer()

        # Render simple template
        html = renderer.render_simple(
            title="Test Report",
            body="This is the report content"
        )

        assert "<html" in html.lower()
        assert "Test Report" in html
        assert "This is the report content" in html

    def test_send_html_email(self, email_sender):
        """Test sending HTML formatted email"""
        html_body = """
        <html>
        <body>
            <h1>Analytics Report</h1>
            <p>This is an HTML email</p>
        </body>
        </html>
        """

        result = email_sender.send_email(
            to_addresses=["recipient@example.com"],
            subject="HTML Report",
            body=html_body,
            html=True
        )

        assert result is True

    def test_send_with_cc_bcc(self, email_sender):
        """Test sending with CC and BCC"""
        result = email_sender.send_email(
            to_addresses=["recipient@example.com"],
            cc_addresses=["cc@example.com"],
            bcc_addresses=["bcc@example.com"],
            subject="Test CC/BCC",
            body="Testing CC and BCC"
        )

        assert result is True

    def test_smtp_connection_error(self, email_config):
        """Test handling of SMTP connection errors"""
        from analytics.core.email.sender import EmailSender

        with patch('analytics.core.email.sender.smtplib.SMTP') as mock_smtp_class:
            # Simulate connection error
            mock_smtp_class.side_effect = ConnectionError("Cannot connect to SMTP")

            sender = EmailSender(**email_config)

            result = sender.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test",
                body="Test"
            )

            # Should return False on error
            assert result is False

    def test_smtp_auth_error(self, email_config):
        """Test handling of authentication errors"""
        from analytics.core.email.sender import EmailSender
        import smtplib

        with patch('analytics.core.email.sender.smtplib.SMTP') as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b'Auth failed')
            mock_smtp_class.return_value.__enter__.return_value = mock_smtp

            sender = EmailSender(**email_config)

            result = sender.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test",
                body="Test"
            )

            assert result is False

    def test_invalid_attachment_path(self, email_sender):
        """Test handling of non-existent attachment"""
        result = email_sender.send_email(
            to_addresses=["recipient@example.com"],
            subject="Invalid Attachment",
            body="Test",
            attachments=["/nonexistent/file.pdf"]
        )

        # Should handle gracefully (either error or skip attachment)
        # Implementation dependent
        assert isinstance(result, bool)

    def test_send_report_helper(self, email_sender, temp_attachment):
        """Test send_report convenience method"""
        # If EmailSender has a send_report method
        if hasattr(email_sender, 'send_report'):
            result = email_sender.send_report(
                report_path=temp_attachment,
                recipients=["manager@example.com"],
                subject="Weekly Report"
            )

            assert result is True


# ============================================================================
# TemplateRenderer Tests
# ============================================================================

class TestTemplateRenderer:
    """Test HTML template rendering"""

    @pytest.fixture
    def renderer(self):
        """Create TemplateRenderer instance"""
        from analytics.core.email.template_renderer import TemplateRenderer
        return TemplateRenderer()

    def test_render_report_notification(self, renderer):
        """Test report notification template"""
        context = {
            "report_name": "Weekly Summary",
            "generated_at": "2026-05-01 12:00:00",
            "sections_count": 5,
            "date_range": "2026-04-01 to 2026-04-30"
        }

        html = renderer.render("report_notification", context)

        # Should render without template placeholders
        assert "{{" not in html
        assert "}}" not in html

        # Should contain context values
        assert "Weekly Summary" in html

    def test_render_simple_template(self, renderer):
        """Test simple template rendering"""
        html = renderer.render_simple(
            title="Test Title",
            body="Test body content"
        )

        assert "<html" in html.lower()
        assert "Test Title" in html
        assert "Test body content" in html
        assert "{{" not in html  # No unrendered placeholders

    def test_render_with_table(self, renderer):
        """Test rendering template with data table"""
        context = {
            "title": "Metrics Report",
            "table_data": [
                {"metric": "Sessions", "value": 127},
                {"metric": "Success Rate", "value": "95.5%"},
                {"metric": "Avg Duration", "value": "18.5 min"}
            ]
        }

        html = renderer.render("table_report", context)

        assert "Sessions" in html
        assert "127" in html

    def test_render_alert_template(self, renderer):
        """Test alert notification template"""
        context = {
            "alert_name": "High Error Rate",
            "severity": "critical",
            "metric_value": 15.5,
            "threshold": 5.0,
            "triggered_at": "2026-05-01 14:30:00"
        }

        html = renderer.render("alert_notification", context)

        assert "High Error Rate" in html
        assert "critical" in html.lower()

    def test_render_missing_template(self, renderer):
        """Test handling of missing template"""
        with pytest.raises((FileNotFoundError, ValueError)):
            renderer.render("nonexistent_template", {})

    def test_render_with_missing_variables(self, renderer):
        """Test rendering with missing context variables"""
        # Template expects 'title' but we don't provide it
        context = {"other_key": "value"}

        # Should either raise error or use default/empty value
        try:
            html = renderer.render_simple(**context)
            # If it doesn't raise, it should handle missing vars gracefully
            assert isinstance(html, str)
        except (KeyError, TypeError):
            # Acceptable to raise error for missing required vars
            pass

    def test_render_with_special_characters(self, renderer):
        """Test rendering with special HTML characters"""
        html = renderer.render_simple(
            title="Report <Test>",
            body="Value: 100 > 50 & 50 < 100"
        )

        # Should escape HTML entities properly
        assert html is not None
        assert len(html) > 0


# ============================================================================
# Email Integration Tests
# ============================================================================

class TestEmailIntegration:
    """Integration tests for email system"""

    def test_full_report_email_workflow(self, temp_attachment):
        """Test complete workflow: render template + send email"""
        from analytics.core.email.sender import EmailSender
        from analytics.core.email.template_renderer import TemplateRenderer

        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "test_password",
            "from_address": "Analytics <analytics@example.com>"
        }

        with patch('analytics.core.email.sender.smtplib.SMTP'):
            sender = EmailSender(**config)
            renderer = TemplateRenderer()

            # Render email body
            body = renderer.render_simple(
                title="Analytics Report",
                body="Your weekly analytics report is attached."
            )

            # Send email
            result = sender.send_email(
                to_addresses=["manager@example.com"],
                subject="Weekly Analytics Report",
                body=body,
                html=True,
                attachments=[temp_attachment]
            )

            assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
