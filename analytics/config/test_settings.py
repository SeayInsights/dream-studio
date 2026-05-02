"""Test script for analytics configuration settings"""
from analytics.config.settings import settings


def test_settings():
    """Test that all configuration settings load correctly"""
    print("Testing Analytics Configuration Settings...")
    print("=" * 60)

    # Test realtime config
    print("\n[Real-time Configuration]")
    print(f"  Enabled: {settings.realtime.enabled}")
    print(f"  Poll Interval: {settings.realtime.poll_interval}s")
    print(f"  Alert Check Interval: {settings.realtime.alert_check_interval}s")
    print(f"  Notification Channels: {', '.join(settings.realtime.notification_channels)}")
    print(f"  SLA Window: {settings.realtime.sla_window}h")

    # Test export config
    print("\n[Export Configuration]")
    print(f"  Output Directory: {settings.export.output_dir}")
    print(f"  Max File Size: {settings.export.max_file_size / 1024 / 1024:.0f}MB")
    print(f"  Retention Days: {settings.export.retention_days}")
    print(f"  Supported Formats: {', '.join(settings.export.formats)}")
    print(f"  PDF Settings: {settings.export.pdf}")
    print(f"  Excel Settings: {settings.export.excel}")
    print(f"  PPTX Settings: {settings.export.pptx}")

    # Test email config
    print("\n[Email Configuration]")
    print(f"  SMTP Host: {settings.email.smtp_host}")
    print(f"  SMTP Port: {settings.email.smtp_port}")
    print(f"  Username: {'***' if settings.email.username else '(not set)'}")
    print(f"  Password: {'***' if settings.email.password else '(not set)'}")
    print(f"  From Address: {settings.email.from_address}")
    print(f"  Use TLS: {settings.email.use_tls}")
    print(f"  Timeout: {settings.email.timeout}s")

    # Test scheduler config
    print("\n[Scheduler Configuration]")
    print(f"  Enabled: {settings.scheduler.enabled}")
    print(f"  Timezone: {settings.scheduler.timezone}")
    print(f"  Max Concurrent Jobs: {settings.scheduler.max_concurrent_jobs}")
    print(f"  Job Defaults: {settings.scheduler.job_defaults}")

    # Test backward compatibility properties
    print("\n[Backward Compatibility - deprecated properties]")
    print(f"  export_config: {type(settings.export_config).__name__}")
    print(f"  email_config: {type(settings.email_config).__name__}")
    print(f"  scheduler_config: {type(settings.scheduler_config).__name__}")
    print(f"  realtime_config: {type(settings.realtime_config).__name__}")

    print("\n" + "=" * 60)
    print("SUCCESS: All configuration settings loaded successfully!")


if __name__ == "__main__":
    test_settings()
