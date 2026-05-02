"""NotificationDispatcher - Sends alerts to registered notification channels"""
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    HAS_REQUESTS = False


logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Base class for notification channels"""

    def __init__(self, name: str):
        """
        Initialize notification channel

        Args:
            name: Unique identifier for this channel
        """
        self.name = name

    @abstractmethod
    def send(self, notification: Dict[str, Any]) -> bool:
        """
        Send a notification

        Args:
            notification: Notification data containing alert_id, severity, message, timestamp, etc.

        Returns:
            True if notification was sent successfully, False otherwise
        """
        pass


class ConsoleChannel(NotificationChannel):
    """Console/log notification channel - prints to stdout and logger"""

    def __init__(self, name: str = "console"):
        """
        Initialize console channel

        Args:
            name: Channel identifier (default: "console")
        """
        super().__init__(name)

    def send(self, notification: Dict[str, Any]) -> bool:
        """
        Print notification to console and log

        Args:
            notification: Notification data

        Returns:
            True (console operations always succeed)
        """
        try:
            severity = notification.get("severity", "info").upper()
            message = notification.get("message", "No message provided")
            alert_id = notification.get("alert_id", "unknown")
            timestamp = notification.get("timestamp", datetime.now().isoformat())

            # Format message
            formatted = f"[{timestamp}] [{severity}] Alert {alert_id}: {message}"

            # Print to console
            print(formatted)

            # Also log with appropriate level
            if severity in ("CRITICAL", "ERROR"):
                logger.error(formatted)
            elif severity == "WARNING":
                logger.warning(formatted)
            else:
                logger.info(formatted)

            return True

        except Exception as e:
            logger.error(f"ConsoleChannel: Failed to send notification: {e}")
            return False


class FileChannel(NotificationChannel):
    """File-based notification channel - appends to JSON log file"""

    def __init__(self, name: str = "file", log_path: Optional[str] = None):
        """
        Initialize file channel

        Args:
            name: Channel identifier (default: "file")
            log_path: Path to JSON log file. If None, uses ~/.dream-studio/logs/notifications.jsonl
        """
        super().__init__(name)

        if log_path is None:
            log_dir = Path.home() / ".dream-studio" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_path = log_dir / "notifications.jsonl"
        else:
            self.log_path = Path(log_path)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, notification: Dict[str, Any]) -> bool:
        """
        Append notification to JSON log file (JSONL format - one JSON object per line)

        Args:
            notification: Notification data

        Returns:
            True if written successfully, False otherwise
        """
        try:
            # Add timestamp if not present
            if "timestamp" not in notification:
                notification["timestamp"] = datetime.now().isoformat()

            # Append to file as JSONL (one JSON object per line)
            with open(self.log_path, "a", encoding="utf-8") as f:
                json.dump(notification, f)
                f.write("\n")

            logger.debug(f"FileChannel: Notification written to {self.log_path}")
            return True

        except Exception as e:
            logger.error(f"FileChannel: Failed to write notification to {self.log_path}: {e}")
            return False


class WebhookChannel(NotificationChannel):
    """Webhook notification channel - sends HTTP POST to webhook URL"""

    def __init__(self, name: str, webhook_url: str, timeout: int = 10):
        """
        Initialize webhook channel

        Args:
            name: Channel identifier
            webhook_url: HTTP(S) URL to send POST requests to
            timeout: Request timeout in seconds (default: 10)
        """
        super().__init__(name)
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, notification: Dict[str, Any]) -> bool:
        """
        Send notification via HTTP POST to webhook URL

        Args:
            notification: Notification data (will be sent as JSON body)

        Returns:
            True if request succeeded (2xx status), False otherwise
        """
        try:
            # Add timestamp if not present
            if "timestamp" not in notification:
                notification["timestamp"] = datetime.now().isoformat()

            payload = json.dumps(notification).encode("utf-8")

            if HAS_REQUESTS:
                # Use requests library if available
                response = requests.post(
                    self.webhook_url,
                    json=notification,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )
                success = 200 <= response.status_code < 300

                if success:
                    logger.debug(f"WebhookChannel: Notification sent to {self.webhook_url} (status: {response.status_code})")
                else:
                    logger.error(f"WebhookChannel: Request failed with status {response.status_code}: {response.text}")

                return success

            else:
                # Fallback to urllib
                req = urllib.request.Request(
                    self.webhook_url,
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )

                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    status = response.getcode()
                    success = 200 <= status < 300

                    if success:
                        logger.debug(f"WebhookChannel: Notification sent to {self.webhook_url} (status: {status})")
                    else:
                        logger.error(f"WebhookChannel: Request failed with status {status}")

                    return success

        except Exception as e:
            logger.error(f"WebhookChannel: Failed to send notification to {self.webhook_url}: {e}")
            return False


class NotificationDispatcher:
    """Dispatches notifications to registered channels"""

    def __init__(self):
        """Initialize dispatcher with empty channel registry"""
        self.channels: Dict[str, NotificationChannel] = {}

    def register_channel(self, channel: NotificationChannel) -> None:
        """
        Register a notification channel

        Args:
            channel: NotificationChannel instance to register
        """
        self.channels[channel.name] = channel
        logger.info(f"NotificationDispatcher: Registered channel '{channel.name}'")

    def unregister_channel(self, channel_name: str) -> bool:
        """
        Remove a notification channel

        Args:
            channel_name: Name of the channel to remove

        Returns:
            True if channel was found and removed, False if not found
        """
        if channel_name in self.channels:
            del self.channels[channel_name]
            logger.info(f"NotificationDispatcher: Unregistered channel '{channel_name}'")
            return True
        else:
            logger.warning(f"NotificationDispatcher: Channel '{channel_name}' not found")
            return False

    def send(self, notification: Dict[str, Any]) -> bool:
        """
        Dispatch notification to all registered channels

        Args:
            notification: Notification data containing:
                - alert_id: str - Unique alert identifier
                - severity: str - Alert severity (e.g., "critical", "warning", "info")
                - message: str - Human-readable alert message
                - timestamp: str - ISO format timestamp (optional, will be added if missing)
                - Additional fields as needed (rule_id, metric_path, metric_value, etc.)

        Returns:
            True if at least one channel sent successfully, False if all failed or no channels registered
        """
        if not self.channels:
            logger.warning("NotificationDispatcher: No channels registered, notification not sent")
            return False

        # Add timestamp if not present
        if "timestamp" not in notification:
            notification["timestamp"] = datetime.now().isoformat()

        # Track success across all channels
        results = []

        for channel_name, channel in self.channels.items():
            try:
                success = channel.send(notification)
                results.append(success)

                if not success:
                    logger.warning(f"NotificationDispatcher: Channel '{channel_name}' failed to send notification")

            except Exception as e:
                logger.error(f"NotificationDispatcher: Exception in channel '{channel_name}': {e}")
                results.append(False)

        # Return True if at least one channel succeeded
        overall_success = any(results)

        if overall_success:
            logger.info(f"NotificationDispatcher: Notification sent ({sum(results)}/{len(results)} channels succeeded)")
        else:
            logger.error("NotificationDispatcher: All channels failed to send notification")

        return overall_success
