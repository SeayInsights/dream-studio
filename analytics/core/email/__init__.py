"""
Email notification system for analytics reports and alerts.

Exports:
    EmailSender: Main email delivery class
    TemplateRenderer: HTML template rendering
"""

from .sender import EmailSender
from .template_renderer import TemplateRenderer

__all__ = ["EmailSender", "TemplateRenderer"]
