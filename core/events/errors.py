"""Event system errors and exceptions.

Created: 2026-05-07 (Phase 1 - Event System Improvements)
"""


class EventEmissionError(Exception):
    """Raised when critical event emission fails.

    This exception is raised when an event marked as CRITICAL fails to persist
    to the database. It should be handled by the calling code to ensure critical
    events are not lost silently.

    Example:
        try:
            emit_event('execution.started', {...}, criticality=EventCriticality.CRITICAL)
        except EventEmissionError as e:
            logger.critical(f"Critical event failed: {e}")
            # Handle failure (retry, alert, etc.)
    """

    pass


class EventValidationError(Exception):
    """Raised when event validation fails.

    This exception provides details about why an event failed validation,
    including which schema rules were violated.
    """

    pass
