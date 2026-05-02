"""
Email sender for analytics notifications and reports.

Uses Python's built-in smtplib and email modules for zero-dependency email delivery.
Supports HTML emails, attachments, inline images, and bulk sending.
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from pathlib import Path
from typing import List, Optional, Union, Dict

from .template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class EmailSender:
    """
    Email sender with SMTP support for analytics notifications.

    Features:
    - HTML and plain text emails
    - File attachments (PDF, Excel, images)
    - Inline images for HTML emails
    - Bulk sending with BCC for privacy
    - Template rendering integration

    Example:
        sender = EmailSender(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            username="user@gmail.com",
            password="app-password",
            from_address="Analytics <noreply@example.com>"
        )

        sender.send_email(
            to="manager@example.com",
            subject="Weekly Report",
            body="<h1>Report ready</h1>",
            html=True
        )
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_address: str,
        use_tls: bool = True
    ):
        """
        Initialize email sender with SMTP configuration.

        Args:
            smtp_host: SMTP server hostname (e.g., smtp.gmail.com)
            smtp_port: SMTP port (587 for TLS, 465 for SSL, 25 for plain)
            username: SMTP authentication username
            password: SMTP authentication password (use app password for Gmail)
            from_address: Sender email address (can include name: "Name <email@example.com>")
            use_tls: Use STARTTLS encryption (default True)
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.use_tls = use_tls
        self.template_renderer = TemplateRenderer()

    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
        attachments: Optional[List[Union[str, Path]]] = None,
        html: bool = True,
        inline_images: Optional[Dict[str, Union[str, Path]]] = None
    ) -> bool:
        """
        Send an email to one or more recipients.

        Args:
            to: Recipient email address(es)
            subject: Email subject line
            body: Email body (HTML or plain text)
            attachments: List of file paths to attach
            html: If True, send as HTML email (default True)
            inline_images: Dict of {cid: image_path} for inline images in HTML
                          Reference in HTML as: <img src="cid:logo">

        Returns:
            True if email sent successfully, False otherwise

        Example:
            sender.send_email(
                to=["user1@example.com", "user2@example.com"],
                subject="Report Ready",
                body="<h1>Your report is attached</h1>",
                attachments=["report.pdf"],
                inline_images={"logo": "logo.png"}
            )
        """
        try:
            # Create message
            msg = MIMEMultipart("related" if inline_images else "mixed")
            msg["From"] = self.from_address
            msg["Subject"] = subject

            # Handle multiple recipients
            recipients = [to] if isinstance(to, str) else to
            msg["To"] = ", ".join(recipients)

            # Attach body
            body_type = "html" if html else "plain"
            msg.attach(MIMEText(body, body_type, "utf-8"))

            # Attach inline images
            if inline_images:
                for cid, image_path in inline_images.items():
                    try:
                        with open(image_path, "rb") as f:
                            img_data = f.read()

                        # Determine image type from extension
                        ext = Path(image_path).suffix.lower()
                        img_type = {
                            ".png": "png",
                            ".jpg": "jpeg",
                            ".jpeg": "jpeg",
                            ".gif": "gif"
                        }.get(ext, "png")

                        img = MIMEImage(img_data, img_type)
                        img.add_header("Content-ID", f"<{cid}>")
                        img.add_header("Content-Disposition", "inline", filename=Path(image_path).name)
                        msg.attach(img)
                    except Exception as e:
                        logger.warning(f"Failed to attach inline image {cid}: {e}")

            # Attach files
            if attachments:
                for attachment_path in attachments:
                    try:
                        path = Path(attachment_path)
                        if not path.exists():
                            logger.error(f"Attachment not found: {attachment_path}")
                            continue

                        with open(path, "rb") as f:
                            attachment_data = f.read()

                        attachment = MIMEApplication(attachment_data)
                        attachment.add_header(
                            "Content-Disposition",
                            "attachment",
                            filename=path.name
                        )
                        msg.attach(attachment)
                    except Exception as e:
                        logger.error(f"Failed to attach file {attachment_path}: {e}")
                        return False

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {len(recipients)} recipient(s)")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPConnectError as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return False

    def send_report(
        self,
        report_path: Union[str, Path],
        recipients: List[str],
        subject: Optional[str] = None,
        report_title: Optional[str] = None,
        date_range: Optional[str] = None,
        key_metrics: Optional[Dict[str, any]] = None
    ) -> bool:
        """
        Send a report file as an email attachment with formatted template.

        Args:
            report_path: Path to report file (PDF, Excel, etc.)
            recipients: List of recipient email addresses
            subject: Email subject (defaults to "Analytics Report")
            report_title: Report title for template (defaults to filename)
            date_range: Date range for template (optional)
            key_metrics: Dict of key metrics for template preview (optional)

        Returns:
            True if email sent successfully, False otherwise

        Example:
            sender.send_report(
                report_path="weekly_report.pdf",
                recipients=["manager@example.com"],
                report_title="Weekly Analytics Summary",
                date_range="April 24-30, 2026",
                key_metrics={"sessions": 145, "tokens": "2.5M"}
            )
        """
        try:
            path = Path(report_path)
            if not path.exists():
                logger.error(f"Report file not found: {report_path}")
                return False

            # Use template renderer
            template_data = {
                "report_title": report_title or path.stem.replace("_", " ").title(),
                "report_filename": path.name,
                "date_range": date_range or "Recent",
                "key_metrics": key_metrics or {}
            }

            html_body = self.template_renderer.render("report_notification.html", template_data)

            # Send with attachment
            return self.send_email(
                to=recipients,
                subject=subject or "Analytics Report Ready",
                body=html_body,
                attachments=[report_path],
                html=True
            )

        except Exception as e:
            logger.error(f"Failed to send report: {e}")
            return False

    def send_bulk(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        html: bool = True
    ) -> bool:
        """
        Send the same email to multiple recipients using BCC for privacy.

        Recipients won't see each other's email addresses.

        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            body: Email body (HTML or plain text)
            html: If True, send as HTML email (default True)

        Returns:
            True if email sent successfully, False otherwise

        Example:
            sender.send_bulk(
                recipients=["user1@example.com", "user2@example.com", "user3@example.com"],
                subject="Weekly Newsletter",
                body="<h1>This week in analytics</h1>"
            )
        """
        try:
            # Create message with BCC
            msg = MIMEMultipart()
            msg["From"] = self.from_address
            msg["Subject"] = subject
            msg["To"] = self.from_address  # Send to self, BCC to others
            msg["Bcc"] = ", ".join(recipients)

            # Attach body
            body_type = "html" if html else "plain"
            msg.attach(MIMEText(body, body_type, "utf-8"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                server.login(self.username, self.password)
                server.sendmail(self.from_address, recipients, msg.as_string())

            logger.info(f"Bulk email sent successfully to {len(recipients)} recipient(s)")
            return True

        except Exception as e:
            logger.error(f"Failed to send bulk email: {e}")
            return False

    def send_alert(
        self,
        recipients: List[str],
        alert_title: str,
        alert_severity: str,
        metric_name: str,
        metric_value: any,
        threshold: any,
        dashboard_url: Optional[str] = None
    ) -> bool:
        """
        Send an alert notification using the alert template.

        Args:
            recipients: List of recipient email addresses
            alert_title: Alert title/description
            alert_severity: Severity level (critical, warning, info)
            metric_name: Name of the metric that triggered alert
            metric_value: Current value of the metric
            threshold: Threshold value that was exceeded
            dashboard_url: Optional URL to view in dashboard

        Returns:
            True if email sent successfully, False otherwise

        Example:
            sender.send_alert(
                recipients=["oncall@example.com"],
                alert_title="High Error Rate Detected",
                alert_severity="critical",
                metric_name="Error Rate",
                metric_value="15.2%",
                threshold="5%",
                dashboard_url="https://example.com/dashboard"
            )
        """
        try:
            template_data = {
                "alert_title": alert_title,
                "alert_severity": alert_severity.upper(),
                "metric_name": metric_name,
                "metric_value": str(metric_value),
                "threshold": str(threshold),
                "dashboard_url": dashboard_url or "#"
            }

            html_body = self.template_renderer.render("alert_notification.html", template_data)

            severity_emoji = {
                "critical": "🔴",
                "warning": "⚠️",
                "info": "ℹ️"
            }.get(alert_severity.lower(), "⚠️")

            subject = f"{severity_emoji} Alert: {alert_title}"

            return self.send_email(
                to=recipients,
                subject=subject,
                body=html_body,
                html=True
            )

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False

    def send_scheduled_report(
        self,
        report_path: Union[str, Path],
        recipients: List[str],
        report_period: str,
        next_scheduled: str,
        manage_subscription_url: Optional[str] = None
    ) -> bool:
        """
        Send a scheduled report using the scheduled report template.

        Args:
            report_path: Path to report file
            recipients: List of recipient email addresses
            report_period: Report period description (e.g., "Weekly: April 24-30")
            next_scheduled: Next scheduled date (e.g., "May 8, 2026")
            manage_subscription_url: URL to manage subscription settings

        Returns:
            True if email sent successfully, False otherwise

        Example:
            sender.send_scheduled_report(
                report_path="weekly_report.pdf",
                recipients=["team@example.com"],
                report_period="Weekly: April 24-30, 2026",
                next_scheduled="May 8, 2026",
                manage_subscription_url="https://example.com/settings"
            )
        """
        try:
            path = Path(report_path)
            if not path.exists():
                logger.error(f"Report file not found: {report_path}")
                return False

            template_data = {
                "report_filename": path.name,
                "report_period": report_period,
                "next_scheduled": next_scheduled,
                "manage_subscription_url": manage_subscription_url or "#"
            }

            html_body = self.template_renderer.render("scheduled_report.html", template_data)

            return self.send_email(
                to=recipients,
                subject=f"Scheduled Report: {report_period}",
                body=html_body,
                attachments=[report_path],
                html=True
            )

        except Exception as e:
            logger.error(f"Failed to send scheduled report: {e}")
            return False
