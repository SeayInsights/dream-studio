"""
Dream Studio Analytics Platform - Settings Module

Provides type-safe configuration loading from analytics.yaml with defaults.
Handles missing configuration files gracefully.
"""

from pathlib import Path
from typing import List
import yaml


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

        self.realtime: RealtimeSettings = self._load_realtime(config_path)

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

        self.realtime = self._load_realtime(config_path)


# Global settings instance
settings = Settings()
