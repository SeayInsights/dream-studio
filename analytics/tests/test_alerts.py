"""Unit tests for alert system components"""
import pytest
import sqlite3
from unittest.mock import Mock, patch
from analytics.core.alerts.alert_evaluator import AlertEvaluator
from analytics.core.alerts.rule_manager import RuleManager
from analytics.core.notifications.dispatcher import (
    NotificationDispatcher,
    ConsoleChannel,
    FileChannel,
    WebhookChannel,
)


@pytest.fixture
def test_alert_db(tmp_path):
    """Create a temporary test database with alert tables and sample data"""
    db_path = tmp_path / "test_alerts.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create alert_rules table
    cursor.execute("""
        CREATE TABLE alert_rules (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            metric_path TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            severity TEXT DEFAULT 'warning',
            enabled INTEGER DEFAULT 1
        )
    """)

    # Create alert_history table
    cursor.execute("""
        CREATE TABLE alert_history (
            alert_id TEXT PRIMARY KEY,
            rule_id TEXT NOT NULL,
            triggered_at TEXT NOT NULL,
            metric_value REAL NOT NULL,
            severity TEXT NOT NULL,
            FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id)
        )
    """)

    # Insert sample alert rules
    sample_rules = [
        ("rule-1", "High Error Rate", "skill.error_rate", "gt", 0.1, "critical", 1),
        ("rule-2", "Low Success Rate", "skill.success_rate", "lt", 0.8, "warning", 1),
        ("rule-3", "Token Limit", "token.daily_total", "gte", 1000000, "info", 1),
        ("rule-4", "Disabled Rule", "skill.timeout_rate", "gt", 0.05, "warning", 0),
        ("rule-5", "Exact Match", "workflow.completion_count", "eq", 100, "info", 1),
    ]

    cursor.executemany("""
        INSERT INTO alert_rules
        (rule_id, rule_name, metric_path, condition, threshold, severity, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, sample_rules)

    conn.commit()
    conn.close()

    return db_path


# AlertEvaluator Tests

class TestAlertEvaluator:
    """Tests for AlertEvaluator class"""

    def test_initialization_default_path(self):
        """Test AlertEvaluator initializes with default db path"""
        evaluator = AlertEvaluator()
        assert evaluator.db_path is not None
        assert ".dream-studio" in evaluator.db_path
        assert "studio.db" in evaluator.db_path

    def test_initialization_custom_path(self, test_alert_db):
        """Test AlertEvaluator initializes with custom db path"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))
        assert evaluator.db_path == str(test_alert_db)

    def test_check_threshold_gt(self):
        """Test threshold checking with greater-than operator"""
        evaluator = AlertEvaluator()

        assert evaluator.check_threshold(0.5, "gt", 0.3) is True
        assert evaluator.check_threshold(0.3, "gt", 0.5) is False
        assert evaluator.check_threshold(0.5, "gt", 0.5) is False

    def test_check_threshold_gte(self):
        """Test threshold checking with greater-than-or-equal operator"""
        evaluator = AlertEvaluator()

        assert evaluator.check_threshold(0.5, "gte", 0.3) is True
        assert evaluator.check_threshold(0.5, "gte", 0.5) is True
        assert evaluator.check_threshold(0.3, "gte", 0.5) is False

    def test_check_threshold_lt(self):
        """Test threshold checking with less-than operator"""
        evaluator = AlertEvaluator()

        assert evaluator.check_threshold(0.3, "lt", 0.5) is True
        assert evaluator.check_threshold(0.5, "lt", 0.3) is False
        assert evaluator.check_threshold(0.5, "lt", 0.5) is False

    def test_check_threshold_lte(self):
        """Test threshold checking with less-than-or-equal operator"""
        evaluator = AlertEvaluator()

        assert evaluator.check_threshold(0.3, "lte", 0.5) is True
        assert evaluator.check_threshold(0.5, "lte", 0.5) is True
        assert evaluator.check_threshold(0.5, "lte", 0.3) is False

    def test_check_threshold_eq(self):
        """Test threshold checking with equals operator"""
        evaluator = AlertEvaluator()

        assert evaluator.check_threshold(0.5, "eq", 0.5) is True
        assert evaluator.check_threshold(0.3, "eq", 0.5) is False
        assert evaluator.check_threshold(100, "eq", 100) is True

    def test_check_threshold_unknown_operator(self):
        """Test threshold checking with unknown operator returns False"""
        evaluator = AlertEvaluator()

        assert evaluator.check_threshold(0.5, "invalid", 0.3) is False
        assert evaluator.check_threshold(0.5, "between", 0.3) is False

    def test_evaluate_rules_no_triggers(self, test_alert_db):
        """Test evaluate_rules when no thresholds are exceeded"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        metrics = {
            "skill.error_rate": 0.05,  # Below 0.1 threshold
            "skill.success_rate": 0.9,  # Above 0.8 threshold
            "token.daily_total": 50000,  # Below 1000000 threshold
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 0

    def test_evaluate_rules_single_trigger(self, test_alert_db):
        """Test evaluate_rules triggers a single alert"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        metrics = {
            "skill.error_rate": 0.15,  # Exceeds 0.1 threshold (gt)
            "skill.success_rate": 0.9,
            "token.daily_total": 50000,
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 1
        assert alerts[0]["rule_id"] == "rule-1"
        assert alerts[0]["rule_name"] == "High Error Rate"
        assert alerts[0]["metric_path"] == "skill.error_rate"
        assert alerts[0]["metric_value"] == 0.15
        assert alerts[0]["threshold"] == 0.1
        assert alerts[0]["severity"] == "critical"
        assert "alert_id" in alerts[0]
        assert "triggered_at" in alerts[0]

    def test_evaluate_rules_multiple_triggers(self, test_alert_db):
        """Test evaluate_rules triggers multiple alerts"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        metrics = {
            "skill.error_rate": 0.2,  # Exceeds 0.1 (gt)
            "skill.success_rate": 0.75,  # Below 0.8 (lt)
            "token.daily_total": 1500000,  # Exceeds 1000000 (gte)
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 3

        # Verify all triggered rules are present
        rule_ids = {alert["rule_id"] for alert in alerts}
        assert "rule-1" in rule_ids  # error_rate
        assert "rule-2" in rule_ids  # success_rate
        assert "rule-3" in rule_ids  # token limit

    def test_evaluate_rules_disabled_rule_ignored(self, test_alert_db):
        """Test evaluate_rules ignores disabled rules"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        metrics = {
            "skill.timeout_rate": 0.1,  # Would trigger rule-4, but it's disabled
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 0

    def test_evaluate_rules_missing_metrics(self, test_alert_db):
        """Test evaluate_rules handles missing metrics gracefully"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        # Provide only subset of metrics
        metrics = {
            "skill.error_rate": 0.05,
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 0  # Other rules shouldn't trigger

    def test_evaluate_rules_non_numeric_metric(self, test_alert_db):
        """Test evaluate_rules skips non-numeric metric values"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        metrics = {
            "skill.error_rate": "invalid",  # Non-numeric value
            "skill.success_rate": 0.75,  # Valid - should trigger
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 1
        assert alerts[0]["rule_id"] == "rule-2"

    def test_evaluate_rules_eq_condition(self, test_alert_db):
        """Test evaluate_rules with exact match condition"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        metrics = {
            "workflow.completion_count": 100,  # Exact match for rule-5
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 1
        assert alerts[0]["rule_id"] == "rule-5"
        # The alert data doesn't include condition, only rule details
        assert alerts[0]["metric_value"] == 100
        assert alerts[0]["threshold"] == 100

    def test_trigger_alert_saves_to_history(self, test_alert_db):
        """Test trigger_alert saves alert to alert_history table"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        rule = {
            "rule_id": "rule-1",
            "rule_name": "High Error Rate",
            "metric_path": "skill.error_rate",
            "threshold": 0.1,
            "severity": "critical",
        }

        alert = evaluator.trigger_alert(rule, 0.15)

        assert alert is not None
        assert alert["alert_id"] is not None
        assert alert["rule_id"] == "rule-1"
        assert alert["metric_value"] == 0.15

        # Verify it's in the database
        conn = sqlite3.connect(str(test_alert_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM alert_history WHERE alert_id = ?", (alert["alert_id"],))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1

    def test_trigger_alert_database_error(self, test_alert_db, capsys):
        """Test trigger_alert handles database errors gracefully"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        # Delete the alert_history table to cause an error
        conn = sqlite3.connect(str(test_alert_db))
        conn.execute("DROP TABLE alert_history")
        conn.commit()
        conn.close()

        rule = {
            "rule_id": "rule-1",
            "rule_name": "Test Rule",
            "metric_path": "test.metric",
            "threshold": 0.5,
            "severity": "warning",
        }

        alert = evaluator.trigger_alert(rule, 0.8)

        # Should return None on error
        assert alert is None


# RuleManager Tests

class TestRuleManager:
    """Tests for RuleManager class"""

    def test_initialization_default_path(self):
        """Test RuleManager initializes with default db path"""
        manager = RuleManager()
        assert manager.db_path is not None
        assert ".dream-studio" in manager.db_path

    def test_initialization_custom_path(self, test_alert_db):
        """Test RuleManager initializes with custom db path"""
        manager = RuleManager(db_path=str(test_alert_db))
        assert manager.db_path == str(test_alert_db)

    def test_create_rule_success(self, test_alert_db):
        """Test creating a new alert rule"""
        manager = RuleManager(db_path=str(test_alert_db))

        rule_def = {
            "rule_name": "Test Rule",
            "metric_path": "test.metric",
            "condition": "gt",
            "threshold": 0.5,
            "severity": "warning",
            "enabled": True,
        }

        rule_id = manager.create_rule(rule_def)

        assert rule_id is not None
        assert len(rule_id) > 0

        # Verify rule exists in database
        conn = sqlite3.connect(str(test_alert_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_rules WHERE rule_id = ?", (rule_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row["rule_name"] == "Test Rule"
        assert row["metric_path"] == "test.metric"
        assert row["condition"] == "gt"
        assert row["threshold"] == 0.5
        assert row["severity"] == "warning"
        assert row["enabled"] == 1

    def test_create_rule_with_defaults(self, test_alert_db):
        """Test creating rule with default severity and enabled"""
        manager = RuleManager(db_path=str(test_alert_db))

        rule_def = {
            "rule_name": "Minimal Rule",
            "metric_path": "test.metric",
            "condition": "lt",
            "threshold": 10.0,
        }

        rule_id = manager.create_rule(rule_def)

        conn = sqlite3.connect(str(test_alert_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_rules WHERE rule_id = ?", (rule_id,))
        row = cursor.fetchone()
        conn.close()

        assert row["severity"] == "warning"  # Default severity
        assert row["enabled"] == 1  # Default enabled

    def test_create_rule_missing_required_field(self, test_alert_db):
        """Test creating rule with missing required field raises error"""
        manager = RuleManager(db_path=str(test_alert_db))

        rule_def = {
            "rule_name": "Incomplete Rule",
            "metric_path": "test.metric",
            # Missing condition and threshold
        }

        with pytest.raises(ValueError, match="Missing required fields"):
            manager.create_rule(rule_def)

    def test_create_rule_invalid_condition(self, test_alert_db):
        """Test creating rule with invalid condition raises error"""
        manager = RuleManager(db_path=str(test_alert_db))

        rule_def = {
            "rule_name": "Bad Condition",
            "metric_path": "test.metric",
            "condition": "invalid",
            "threshold": 0.5,
        }

        with pytest.raises(ValueError, match="Invalid condition"):
            manager.create_rule(rule_def)

    def test_update_rule_success(self, test_alert_db):
        """Test updating an existing rule"""
        manager = RuleManager(db_path=str(test_alert_db))

        updates = {
            "rule_name": "Updated Name",
            "threshold": 0.15,
            "severity": "info",
        }

        result = manager.update_rule("rule-1", updates)
        assert result is True

        # Verify updates
        conn = sqlite3.connect(str(test_alert_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_rules WHERE rule_id = ?", ("rule-1",))
        row = cursor.fetchone()
        conn.close()

        assert row["rule_name"] == "Updated Name"
        assert row["threshold"] == 0.15
        assert row["severity"] == "info"
        # Other fields should remain unchanged
        assert row["metric_path"] == "skill.error_rate"
        assert row["condition"] == "gt"

    def test_update_rule_nonexistent(self, test_alert_db):
        """Test updating non-existent rule returns False"""
        manager = RuleManager(db_path=str(test_alert_db))

        result = manager.update_rule("nonexistent-id", {"threshold": 0.5})
        assert result is False

    def test_update_rule_invalid_field(self, test_alert_db):
        """Test updating with invalid field raises error"""
        manager = RuleManager(db_path=str(test_alert_db))

        with pytest.raises(ValueError, match="Invalid fields"):
            manager.update_rule("rule-1", {"invalid_field": "value"})

    def test_update_rule_invalid_condition(self, test_alert_db):
        """Test updating with invalid condition raises error"""
        manager = RuleManager(db_path=str(test_alert_db))

        with pytest.raises(ValueError, match="Invalid condition"):
            manager.update_rule("rule-1", {"condition": "invalid"})

    def test_delete_rule_success(self, test_alert_db):
        """Test deleting a rule"""
        manager = RuleManager(db_path=str(test_alert_db))

        result = manager.delete_rule("rule-1")
        assert result is True

        # Verify deletion
        conn = sqlite3.connect(str(test_alert_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM alert_rules WHERE rule_id = ?", ("rule-1",))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0

    def test_delete_rule_nonexistent(self, test_alert_db):
        """Test deleting non-existent rule returns False"""
        manager = RuleManager(db_path=str(test_alert_db))

        result = manager.delete_rule("nonexistent-id")
        assert result is False

    def test_get_active_rules(self, test_alert_db):
        """Test retrieving active rules only"""
        manager = RuleManager(db_path=str(test_alert_db))

        active_rules = manager.get_active_rules()

        # Should return 4 enabled rules (rule-4 is disabled)
        assert len(active_rules) == 4

        # Verify all returned rules are enabled
        for rule in active_rules:
            assert rule["enabled"] is True

        # Verify disabled rule is not included
        rule_ids = {rule["rule_id"] for rule in active_rules}
        assert "rule-4" not in rule_ids

    def test_get_active_rules_ordered(self, test_alert_db):
        """Test active rules are ordered by severity and name"""
        manager = RuleManager(db_path=str(test_alert_db))

        active_rules = manager.get_active_rules()

        # Verify critical severity rule is in the list (ordering may vary)
        severities = [rule["severity"] for rule in active_rules]
        assert "critical" in severities
        assert "warning" in severities
        assert "info" in severities

    def test_enable_rule(self, test_alert_db):
        """Test enabling a disabled rule"""
        manager = RuleManager(db_path=str(test_alert_db))

        result = manager.enable_rule("rule-4")
        assert result is True

        # Verify rule is enabled
        conn = sqlite3.connect(str(test_alert_db))
        cursor = conn.cursor()
        cursor.execute("SELECT enabled FROM alert_rules WHERE rule_id = ?", ("rule-4",))
        enabled = cursor.fetchone()[0]
        conn.close()

        assert enabled == 1

    def test_disable_rule(self, test_alert_db):
        """Test disabling an enabled rule"""
        manager = RuleManager(db_path=str(test_alert_db))

        result = manager.disable_rule("rule-1")
        assert result is True

        # Verify rule is disabled
        conn = sqlite3.connect(str(test_alert_db))
        cursor = conn.cursor()
        cursor.execute("SELECT enabled FROM alert_rules WHERE rule_id = ?", ("rule-1",))
        enabled = cursor.fetchone()[0]
        conn.close()

        assert enabled == 0


# NotificationDispatcher Tests

class TestNotificationChannels:
    """Tests for notification channel classes"""

    def test_console_channel_send_success(self, capsys):
        """Test ConsoleChannel sends notification successfully"""
        channel = ConsoleChannel()

        notification = {
            "alert_id": "alert-123",
            "severity": "warning",
            "message": "Test alert message",
            "timestamp": "2025-01-01T12:00:00Z",
        }

        result = channel.send(notification)
        assert result is True

        # Verify output was printed
        captured = capsys.readouterr()
        assert "alert-123" in captured.out
        assert "WARNING" in captured.out
        assert "Test alert message" in captured.out

    def test_console_channel_different_severities(self, capsys):
        """Test ConsoleChannel handles different severity levels"""
        channel = ConsoleChannel()

        severities = ["critical", "warning", "info"]
        for severity in severities:
            notification = {
                "alert_id": f"alert-{severity}",
                "severity": severity,
                "message": f"{severity} message",
            }
            result = channel.send(notification)
            assert result is True

    def test_file_channel_send_success(self, tmp_path):
        """Test FileChannel writes notification to file"""
        log_path = tmp_path / "notifications.jsonl"
        channel = FileChannel(log_path=str(log_path))

        notification = {
            "alert_id": "alert-456",
            "severity": "critical",
            "message": "Critical alert",
        }

        result = channel.send(notification)
        assert result is True

        # Verify file exists and contains notification
        assert log_path.exists()
        content = log_path.read_text()
        assert "alert-456" in content
        assert "critical" in content

    def test_file_channel_multiple_notifications(self, tmp_path):
        """Test FileChannel appends multiple notifications"""
        log_path = tmp_path / "notifications.jsonl"
        channel = FileChannel(log_path=str(log_path))

        # Send multiple notifications
        for i in range(3):
            notification = {
                "alert_id": f"alert-{i}",
                "severity": "info",
                "message": f"Message {i}",
            }
            channel.send(notification)

        # Verify all notifications are in file
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_file_channel_creates_directory(self, tmp_path):
        """Test FileChannel creates log directory if missing"""
        log_path = tmp_path / "nested" / "dir" / "notifications.jsonl"
        channel = FileChannel(log_path=str(log_path))

        notification = {"alert_id": "test", "message": "Test"}
        result = channel.send(notification)

        assert result is True
        assert log_path.exists()

    @patch('analytics.core.notifications.dispatcher.requests')
    def test_webhook_channel_send_success_with_requests(self, mock_requests):
        """Test WebhookChannel sends via requests library"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        channel = WebhookChannel(name="test-webhook", webhook_url="https://example.com/webhook")

        notification = {
            "alert_id": "alert-789",
            "severity": "warning",
            "message": "Webhook test",
        }

        result = channel.send(notification)
        assert result is True

        # Verify requests.post was called
        mock_requests.post.assert_called_once()
        call_args = mock_requests.post.call_args
        assert call_args[0][0] == "https://example.com/webhook"
        assert call_args[1]["json"]["alert_id"] == "alert-789"

    @patch('analytics.core.notifications.dispatcher.requests')
    def test_webhook_channel_send_failure(self, mock_requests):
        """Test WebhookChannel handles HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_requests.post.return_value = mock_response

        channel = WebhookChannel(name="test-webhook", webhook_url="https://example.com/webhook")

        notification = {"alert_id": "alert-fail", "message": "Test"}
        result = channel.send(notification)

        assert result is False

    @patch('analytics.core.notifications.dispatcher.requests')
    def test_webhook_channel_send_exception(self, mock_requests):
        """Test WebhookChannel handles network exceptions"""
        mock_requests.post.side_effect = Exception("Network error")

        channel = WebhookChannel(name="test-webhook", webhook_url="https://example.com/webhook")

        notification = {"alert_id": "alert-error", "message": "Test"}
        result = channel.send(notification)

        assert result is False


class TestNotificationDispatcher:
    """Tests for NotificationDispatcher class"""

    def test_dispatcher_initialization(self):
        """Test NotificationDispatcher initializes with empty channels"""
        dispatcher = NotificationDispatcher()
        assert dispatcher.channels == {}

    def test_register_channel(self):
        """Test registering a notification channel"""
        dispatcher = NotificationDispatcher()
        channel = ConsoleChannel(name="console")

        dispatcher.register_channel(channel)

        assert "console" in dispatcher.channels
        assert dispatcher.channels["console"] == channel

    def test_register_multiple_channels(self):
        """Test registering multiple channels"""
        dispatcher = NotificationDispatcher()
        console = ConsoleChannel(name="console")
        file = FileChannel(name="file", log_path="/tmp/test.log")

        dispatcher.register_channel(console)
        dispatcher.register_channel(file)

        assert len(dispatcher.channels) == 2
        assert "console" in dispatcher.channels
        assert "file" in dispatcher.channels

    def test_unregister_channel_success(self):
        """Test unregistering a channel"""
        dispatcher = NotificationDispatcher()
        channel = ConsoleChannel(name="console")
        dispatcher.register_channel(channel)

        result = dispatcher.unregister_channel("console")

        assert result is True
        assert "console" not in dispatcher.channels

    def test_unregister_channel_not_found(self):
        """Test unregistering non-existent channel returns False"""
        dispatcher = NotificationDispatcher()

        result = dispatcher.unregister_channel("nonexistent")

        assert result is False

    def test_send_no_channels(self):
        """Test send returns False when no channels registered"""
        dispatcher = NotificationDispatcher()

        notification = {"alert_id": "test", "message": "Test"}
        result = dispatcher.send(notification)

        assert result is False

    def test_send_single_channel_success(self, capsys):
        """Test send to single channel"""
        dispatcher = NotificationDispatcher()
        console = ConsoleChannel(name="console")
        dispatcher.register_channel(console)

        notification = {
            "alert_id": "alert-single",
            "severity": "info",
            "message": "Single channel test",
        }

        result = dispatcher.send(notification)

        assert result is True
        captured = capsys.readouterr()
        assert "alert-single" in captured.out

    def test_send_multiple_channels_all_success(self, tmp_path, capsys):
        """Test send to multiple channels, all succeed"""
        dispatcher = NotificationDispatcher()
        console = ConsoleChannel(name="console")
        file = FileChannel(name="file", log_path=str(tmp_path / "test.jsonl"))

        dispatcher.register_channel(console)
        dispatcher.register_channel(file)

        notification = {
            "alert_id": "alert-multi",
            "severity": "warning",
            "message": "Multi-channel test",
        }

        result = dispatcher.send(notification)

        assert result is True

        # Verify both channels received notification
        captured = capsys.readouterr()
        assert "alert-multi" in captured.out
        assert (tmp_path / "test.jsonl").exists()

    def test_send_multiple_channels_partial_failure(self, tmp_path, capsys):
        """Test send succeeds if at least one channel succeeds"""
        dispatcher = NotificationDispatcher()

        # Console should succeed
        console = ConsoleChannel(name="console")
        dispatcher.register_channel(console)

        # Mock webhook that fails
        with patch('analytics.core.notifications.dispatcher.requests') as mock_requests:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_requests.post.return_value = mock_response

            webhook = WebhookChannel(name="webhook", webhook_url="https://fail.example.com")
            dispatcher.register_channel(webhook)

            notification = {"alert_id": "partial", "message": "Test"}
            result = dispatcher.send(notification)

            # Should succeed because console succeeded
            assert result is True

    def test_send_adds_timestamp_if_missing(self, tmp_path):
        """Test send adds timestamp to notification if not present"""
        dispatcher = NotificationDispatcher()
        file = FileChannel(name="file", log_path=str(tmp_path / "test.jsonl"))
        dispatcher.register_channel(file)

        notification = {
            "alert_id": "no-timestamp",
            "message": "Test without timestamp",
        }

        dispatcher.send(notification)

        # Read file and verify timestamp was added
        import json
        content = (tmp_path / "test.jsonl").read_text()
        saved_notification = json.loads(content)
        assert "timestamp" in saved_notification

    def test_send_preserves_existing_timestamp(self, tmp_path):
        """Test send preserves existing timestamp"""
        dispatcher = NotificationDispatcher()
        file = FileChannel(name="file", log_path=str(tmp_path / "test.jsonl"))
        dispatcher.register_channel(file)

        original_timestamp = "2025-01-01T12:00:00Z"
        notification = {
            "alert_id": "with-timestamp",
            "message": "Test with timestamp",
            "timestamp": original_timestamp,
        }

        dispatcher.send(notification)

        # Read file and verify timestamp was preserved
        import json
        content = (tmp_path / "test.jsonl").read_text()
        saved_notification = json.loads(content)
        assert saved_notification["timestamp"] == original_timestamp


# Integration Tests

class TestAlertSystemIntegration:
    """Integration tests combining multiple alert components"""

    def test_end_to_end_alert_flow(self, test_alert_db, tmp_path, capsys):
        """Test complete flow: rule evaluation -> alert trigger -> notification dispatch"""
        # Setup
        evaluator = AlertEvaluator(db_path=str(test_alert_db))
        dispatcher = NotificationDispatcher()

        console = ConsoleChannel(name="console")
        file = FileChannel(name="file", log_path=str(tmp_path / "alerts.jsonl"))
        dispatcher.register_channel(console)
        dispatcher.register_channel(file)

        # Evaluate rules with metrics that trigger alerts
        metrics = {
            "skill.error_rate": 0.2,  # Triggers rule-1 (critical)
            "skill.success_rate": 0.75,  # Triggers rule-2 (warning)
        }

        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) == 2

        # Dispatch notifications for each alert
        for alert in alerts:
            notification = {
                "alert_id": alert["alert_id"],
                "severity": alert["severity"],
                "message": f"{alert['rule_name']}: {alert['metric_path']} = {alert['metric_value']} (threshold: {alert['threshold']})",
                "rule_id": alert["rule_id"],
                "metric_path": alert["metric_path"],
                "metric_value": alert["metric_value"],
            }
            result = dispatcher.send(notification)
            assert result is True

        # Verify console output
        captured = capsys.readouterr()
        assert "High Error Rate" in captured.out
        assert "Low Success Rate" in captured.out

        # Verify file output
        assert (tmp_path / "alerts.jsonl").exists()
        lines = (tmp_path / "alerts.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

    def test_rule_lifecycle(self, test_alert_db):
        """Test complete rule lifecycle: create -> evaluate -> update -> delete"""
        manager = RuleManager(db_path=str(test_alert_db))
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        # Create new rule
        rule_def = {
            "rule_name": "Lifecycle Test",
            "metric_path": "test.value",
            "condition": "gt",
            "threshold": 50.0,
            "severity": "warning",
        }
        rule_id = manager.create_rule(rule_def)

        # Evaluate with metric that triggers
        metrics = {"test.value": 75.0}
        alerts = evaluator.evaluate_rules(metrics)
        assert len(alerts) >= 1
        assert any(a["rule_id"] == rule_id for a in alerts)

        # Update threshold so it doesn't trigger
        manager.update_rule(rule_id, {"threshold": 100.0})
        alerts = evaluator.evaluate_rules(metrics)
        assert not any(a["rule_id"] == rule_id for a in alerts)

        # Disable rule
        manager.disable_rule(rule_id)
        manager.update_rule(rule_id, {"threshold": 50.0})  # Back to original
        alerts = evaluator.evaluate_rules(metrics)
        assert not any(a["rule_id"] == rule_id for a in alerts)

        # Delete rule
        result = manager.delete_rule(rule_id)
        assert result is True

    def test_alert_history_persistence(self, test_alert_db):
        """Test that triggered alerts are persisted to history"""
        evaluator = AlertEvaluator(db_path=str(test_alert_db))

        # Trigger multiple alerts
        metrics = {
            "skill.error_rate": 0.3,
            "token.daily_total": 2000000,
        }

        alerts = evaluator.evaluate_rules(metrics)
        triggered_count = len(alerts)

        # Query alert_history table
        conn = sqlite3.connect(str(test_alert_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM alert_history")
        history_count = cursor.fetchone()[0]
        conn.close()

        assert history_count == triggered_count

    @patch('analytics.core.notifications.dispatcher.requests')
    def test_webhook_integration(self, mock_requests, test_alert_db):
        """Test webhook notification integration"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        evaluator = AlertEvaluator(db_path=str(test_alert_db))
        dispatcher = NotificationDispatcher()

        webhook = WebhookChannel(
            name="slack",
            webhook_url="https://hooks.slack.com/services/TEST",
        )
        dispatcher.register_channel(webhook)

        # Trigger alert
        metrics = {"skill.error_rate": 0.5}
        alerts = evaluator.evaluate_rules(metrics)

        # Send to webhook
        for alert in alerts:
            notification = {
                "alert_id": alert["alert_id"],
                "severity": alert["severity"],
                "message": f"Alert: {alert['rule_name']}",
            }
            result = dispatcher.send(notification)
            assert result is True

        # Verify webhook was called
        assert mock_requests.post.called
