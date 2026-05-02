"""
Dream Studio Analytics Platform - Settings Module

Provides type-safe configuration loading from analytics.yaml with defaults.
Handles missing configuration files gracefully.
"""

from pathlib import Path
from typing import List, Dict, Any
import yaml
import os


class RealtimeSettings:
    """Real-time monitoring and alerting configuration."""

    def __init__(self, config: dict | None = None):
        """
        Initialize real-time settings.

        Args:
            config: Configuration dictionary from YAML file. Uses defaults if None.
        """
        config = config or {}

        self.enabled: bool = config.get("enabled", True)
        self.poll_interval: int = config.get("poll_interval", 60)
        self.alert_check_interval: int = config.get("alert_check_interval", 60)
        self.notification_channels: List[str] = config.get(
            "notification_channels", ["console", "file", "webhook"]
        )
        self.sla_window: int = config.get("sla_window", 24)

    def validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        if not isinstance(self.enabled, bool):
            raise ValueError("realtime.enabled must be a boolean")

        if self.poll_interval <= 0:
            raise ValueError("realtime.poll_interval must be positive")

        if self.alert_check_interval <= 0:
            raise ValueError("realtime.alert_check_interval must be positive")

        if not isinstance(self.notification_channels, list):
            raise ValueError("realtime.notification_channels must be a list")

        valid_channels = {"console", "file", "webhook"}
        for channel in self.notification_channels:
            if channel not in valid_channels:
                raise ValueError(
                    f"Invalid notification channel: {channel}. "
                    f"Must be one of {valid_channels}"
                )

        if self.sla_window <= 0:
            raise ValueError("realtime.sla_window must be positive")


class ExportSettings:
    """Export and reporting configuration."""

    def __init__(self, config: dict | None = None):
        """
        Initialize export settings.

        Args:
            config: Configuration dictionary from YAML file. Uses defaults if None.
        """
        config = config or {}

        self.output_dir: str = config.get("output_dir", "exports/")
        self.max_file_size: int = config.get("max_file_size", 104857600)  # 100MB
        self.retention_days: int = config.get("retention_days", 30)
        self.formats: List[str] = config.get("formats", ["pdf", "excel", "pptx", "csv", "powerbi"])

        # Format-specific settings
        self.pdf: Dict[str, str] = config.get("pdf", {"page_size": "letter", "orientation": "portrait"})
        self.excel: Dict[str, Any] = config.get("excel", {"max_rows_per_sheet": 1000000, "include_charts": True})
        self.pptx: Dict[str, str] = config.get("pptx", {"slide_size": "16:9", "template": "default"})


class EmailSettings:
    """Email notification configuration."""

    def __init__(self, config: dict | None = None):
        """
        Initialize email settings.

        Args:
            config: Configuration dictionary from YAML file. Uses defaults if None.
        """
        config = config or {}

        self.smtp_host: str = config.get("smtp_host", "smtp.gmail.com")
        self.smtp_port: int = config.get("smtp_port", 587)
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.from_address: str = config.get("from_address", "Dream Studio Analytics <noreply@example.com>")
        self.use_tls: bool = config.get("use_tls", True)
        self.timeout: int = config.get("timeout", 30)

        # Override with environment variables
        if os.getenv("ANALYTICS_SMTP_USER"):
            self.username = os.getenv("ANALYTICS_SMTP_USER")
        if os.getenv("ANALYTICS_SMTP_PASS"):
            self.password = os.getenv("ANALYTICS_SMTP_PASS")


class SchedulerSettings:
    """Scheduler configuration."""

    def __init__(self, config: dict | None = None):
        """
        Initialize scheduler settings.

        Args:
            config: Configuration dictionary from YAML file. Uses defaults if None.
        """
        config = config or {}

        self.enabled: bool = config.get("enabled", True)
        self.timezone: str = config.get("timezone", "UTC")
        self.max_concurrent_jobs: int = config.get("max_concurrent_jobs", 5)
        self.job_defaults: Dict[str, Any] = config.get("job_defaults", {
            "misfire_grace_time": 900,  # 15 minutes
            "coalesce": True,
            "max_instances": 1
        })


class Settings:
    """Main analytics platform configuration."""

    def __init__(self, config_path: Path | None = None):
        """
        Initialize settings from YAML configuration file.

        Args:
            config_path: Path to analytics.yaml. If None, uses default location.
                        Falls back to defaults if file doesn't exist.
        """
        if config_path is None:
            config_path = Path(__file__).parent / "analytics.yaml"

        # Load all configuration sections
        config = self._load_config(config_path)

        self.realtime: RealtimeSettings = RealtimeSettings(config.get("realtime"))
        self.export: ExportSettings = ExportSettings(config.get("export"))
        self.email: EmailSettings = EmailSettings(config.get("email"))
        self.scheduler: SchedulerSettings = SchedulerSettings(config.get("scheduler"))

    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to analytics.yaml

        Returns:
            Configuration dictionary or empty dict if file doesn't exist/invalid
        """
        try:
            if not config_path.exists():
                return {}

            with open(config_path, "r", encoding='utf-8') as f:
                config = yaml.safe_load(f)

            return config if config else {}

        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse {config_path}: {e}")
            print("Using default configuration")
            return {}

        except Exception as e:
            print(f"Warning: Failed to load configuration from {config_path}: {e}")
            print("Using default configuration")
            return {}

    def _load_realtime(self, config_path: Path) -> RealtimeSettings:
        """
        Load real-time configuration from YAML file.

        Args:
            config_path: Path to analytics.yaml

        Returns:
            RealtimeSettings instance with configuration or defaults
        """
        try:
            if not config_path.exists():
                # File doesn't exist, use all defaults
                return RealtimeSettings()

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            if not config or "realtime" not in config:
                # Empty or missing realtime section, use defaults
                return RealtimeSettings()

            settings = RealtimeSettings(config["realtime"])
            settings.validate()
            return settings

        except yaml.YAMLError as e:
            # Invalid YAML, use defaults and warn
            print(f"Warning: Failed to parse {config_path}: {e}")
            print("Using default configuration")
            return RealtimeSettings()

        except ValueError as e:
            # Invalid configuration values, use defaults and warn
            print(f"Warning: Invalid configuration in {config_path}: {e}")
            print("Using default configuration")
            return RealtimeSettings()

    def reload(self, config_path: Path | None = None) -> None:
        """
        Reload configuration from file.

        Args:
            config_path: Path to analytics.yaml. If None, uses default location.
        """
        if config_path is None:
            config_path = Path(__file__).parent / "analytics.yaml"

        config = self._load_config(config_path)
        self.realtime = RealtimeSettings(config.get("realtime"))
        self.export = ExportSettings(config.get("export"))
        self.email = EmailSettings(config.get("email"))
        self.scheduler = SchedulerSettings(config.get("scheduler"))

    @property
    def export_config(self) -> ExportSettings:
        """Get export configuration (backward compatibility)"""
        return self.export

    @property
    def email_config(self) -> EmailSettings:
        """Get email configuration (backward compatibility)"""
        return self.email

    @property
    def scheduler_config(self) -> SchedulerSettings:
        """Get scheduler configuration (backward compatibility)"""
        return self.scheduler

    @property
    def realtime_config(self) -> RealtimeSettings:
        """Get real-time configuration (backward compatibility)"""
        return self.realtime


# Global settings instance
settings = Settings()
