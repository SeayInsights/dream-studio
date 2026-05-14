"""Phase 5.3A — Event emission reliability tests.

Proves:
1. emit_event() with default severity ("info") succeeds
2. emit_event() with all explicit valid severity values succeeds
3. Invalid severity still rejected
4. EventValidator allowed severity includes "info"
5. Security emitter no longer imports nonexistent EventPayloadValidator
6. Security emitter routes through canonical emit_event()
7. Security emitter does not directly INSERT into canonical_events
8. Advisory EventType validation remains advisory only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.events.event_type_advisory import (
    AdvisoryResult,
    reset_cache,
    validate_event_type_advisory,
)

pytestmark = pytest.mark.runtime_reliability


@pytest.fixture(autouse=True)
def _clear_advisory_cache():
    reset_cache()
    yield
    reset_cache()


# ── EV-1: Severity enum fix ─────────────────────────────────────────────────


class TestSeverityEnumFix:
    """Verify "info" is now accepted and all other values still work."""

    @pytest.fixture()
    def validator(self):
        from core.validation.event_validator import EventValidator

        taxonomy = "docs/canonical/event_taxonomy_v1.json"
        schema = "docs/canonical/canonical_event_v1_schema.json"
        if not Path(taxonomy).exists() or not Path(schema).exists():
            pytest.skip("Canonical files not found")
        return EventValidator(taxonomy, schema)

    def _make_event(self, severity: str) -> dict:
        return {
            "event_id": "00000000-0000-0000-0000-000000000001",
            "event_type": "security.scan.completed",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "trace": {"project_id": "test"},
            "severity": severity,
            "payload": {},
        }

    def test_info_severity_accepted(self, validator):
        result = validator.validate(self._make_event("info"))
        assert result.is_valid, f"Expected 'info' to be valid, got errors: {result.errors}"

    def test_low_severity_accepted(self, validator):
        result = validator.validate(self._make_event("low"))
        assert result.is_valid

    def test_medium_severity_accepted(self, validator):
        result = validator.validate(self._make_event("medium"))
        assert result.is_valid

    def test_high_severity_accepted(self, validator):
        result = validator.validate(self._make_event("high"))
        assert result.is_valid

    def test_critical_severity_accepted(self, validator):
        result = validator.validate(self._make_event("critical"))
        assert result.is_valid

    def test_invalid_severity_rejected(self, validator):
        result = validator.validate(self._make_event("warning"))
        assert not result.is_valid
        assert any("severity" in e.lower() for e in result.errors)

    def test_bogus_severity_rejected(self, validator):
        result = validator.validate(self._make_event("EXTREME"))
        assert not result.is_valid


class TestEmitEventDefaultSeverity:
    """Verify emit_event() with default severity succeeds."""

    def test_default_severity_succeeds(self):
        from core.events.emitter import emit_event

        with patch("core.events.emitter._get_event_store") as mock_store:
            mock_store.return_value.write_event.return_value = True
            with patch("core.events.emitter.validate_event_type_advisory") as mock_adv:
                mock_adv.return_value = AdvisoryResult(
                    is_registered=True, event_type="test.event.fired"
                )
                result = emit_event("test.event.fired", {"key": "value"})

        assert result is not None
        call_args = mock_store.return_value.write_event.call_args[0][0]
        assert call_args["severity"] == "info"

    def test_explicit_low_severity_succeeds(self):
        from core.events.emitter import emit_event

        with patch("core.events.emitter._get_event_store") as mock_store:
            mock_store.return_value.write_event.return_value = True
            with patch("core.events.emitter.validate_event_type_advisory") as mock_adv:
                mock_adv.return_value = AdvisoryResult(
                    is_registered=True, event_type="test.event.fired"
                )
                result = emit_event("test.event.fired", {"key": "value"}, severity="low")

        assert result is not None
        call_args = mock_store.return_value.write_event.call_args[0][0]
        assert call_args["severity"] == "low"


# ── EV-2/EV-3: Security emitter fix ─────────────────────────────────────────


class TestSecurityEmitterNoDirectSQL:
    """Verify security emitter routes through canonical path."""

    def test_no_payload_validator_import(self):
        source = Path("core/security/event_emitter.py").read_text()
        assert "EventPayloadValidator" not in source
        assert "payload_validator" not in source

    def test_no_direct_sql_insert(self):
        source = Path("core/security/event_emitter.py").read_text()
        assert "INSERT INTO" not in source
        assert "db_conn.execute" not in source
        assert "conn.execute" not in source

    def test_imports_canonical_emit_event(self):
        source = Path("core/security/event_emitter.py").read_text()
        assert "from core.events.emitter import emit_event" in source

    def test_no_transaction_import(self):
        source = Path("core/security/event_emitter.py").read_text()
        assert "from core.config.database import transaction" not in source

    def test_module_imports_cleanly(self):
        import core.security.event_emitter  # noqa: F401


class TestSecurityEmitterRoutesCanonical:
    """Verify emit_security_event delegates to emit_event."""

    def test_emit_security_event_calls_emit_event(self):
        with patch("core.security.event_emitter.emit_event") as mock_emit:
            mock_emit.return_value = "test-uuid"
            from core.security.event_emitter import emit_security_event

            result = emit_security_event(
                "scan.started",
                {"scan_id": "s1", "project_path": "/test"},
                severity="info",
            )

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args
        assert call_kwargs[1]["event_type"] == "security.scan.started"
        assert call_kwargs[1]["severity"] == "info"
        assert call_kwargs[1]["payload"]["scan_id"] == "s1"
        assert result == "test-uuid"

    def test_emit_security_event_prefixes_type(self):
        with patch("core.security.event_emitter.emit_event") as mock_emit:
            mock_emit.return_value = "id"
            from core.security.event_emitter import emit_security_event

            emit_security_event("finding.detected", {"data": 1})

        assert mock_emit.call_args[1]["event_type"] == "security.finding.detected"

    def test_emit_scan_started_convenience(self):
        with patch("core.security.event_emitter.emit_event") as mock_emit:
            mock_emit.return_value = "id"
            from core.security.event_emitter import emit_scan_started

            emit_scan_started("scan-1", "prd-1", "/project")

        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["event_type"] == "security.scan.started"
        assert call_kwargs["payload"]["scan_id"] == "scan-1"
        assert call_kwargs["payload"]["prd_id"] == "prd-1"

    def test_emit_scan_completed_convenience(self):
        with patch("core.security.event_emitter.emit_event") as mock_emit:
            mock_emit.return_value = "id"
            from core.security.event_emitter import emit_scan_completed

            emit_scan_completed("scan-1", 5)

        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["event_type"] == "security.scan.completed"
        assert call_kwargs["payload"]["findings_count"] == 5

    def test_emit_scan_failed_uses_high_severity(self):
        with patch("core.security.event_emitter.emit_event") as mock_emit:
            mock_emit.return_value = "id"
            from core.security.event_emitter import emit_scan_failed

            emit_scan_failed("scan-1", "timeout error")

        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["event_type"] == "security.scan.failed"
        assert call_kwargs["severity"] == "high"
        assert call_kwargs["payload"]["error"] == "timeout error"

    def test_conn_param_accepted_but_ignored(self):
        """conn parameter is accepted for backward compatibility."""
        with patch("core.security.event_emitter.emit_event") as mock_emit:
            mock_emit.return_value = "id"
            from core.security.event_emitter import emit_security_event

            emit_security_event("scan.started", {"data": 1}, conn=MagicMock())

        mock_emit.assert_called_once()

    def test_validate_param_accepted_but_ignored(self):
        """validate parameter is accepted for backward compatibility."""
        with patch("core.security.event_emitter.emit_event") as mock_emit:
            mock_emit.return_value = "id"
            from core.security.event_emitter import emit_security_event

            emit_security_event("scan.started", {"data": 1}, validate=False)

        mock_emit.assert_called_once()


# ── Taxonomy additions ───────────────────────────────────────────────────────


class TestTaxonomySecurityTypes:
    """Verify security event types are registered in taxonomy."""

    @pytest.fixture()
    def taxonomy(self):
        path = Path("docs/canonical/event_taxonomy_v1.json")
        if not path.exists():
            pytest.skip("Taxonomy not found")
        with open(path) as f:
            return json.load(f)

    def test_scan_started_registered(self, taxonomy):
        security_types = taxonomy["allowed_event_types"]["security"]
        assert "security.scan.started" in security_types

    def test_scan_completed_registered(self, taxonomy):
        security_types = taxonomy["allowed_event_types"]["security"]
        assert "security.scan.completed" in security_types

    def test_scan_failed_registered(self, taxonomy):
        security_types = taxonomy["allowed_event_types"]["security"]
        assert "security.scan.failed" in security_types

    def test_finding_detected_registered(self, taxonomy):
        security_types = taxonomy["allowed_event_types"]["security"]
        assert "security.finding.detected" in security_types

    def test_finding_created_still_registered(self, taxonomy):
        security_types = taxonomy["allowed_event_types"]["security"]
        assert "security.finding.created" in security_types


# ── Schema severity enum ────────────────────────────────────────────────────


class TestSchemaIncludesInfo:
    """Verify the JSON schema allows 'info' severity."""

    def test_schema_enum_includes_info(self):
        path = Path("docs/canonical/canonical_event_v1_schema.json")
        if not path.exists():
            pytest.skip("Schema not found")
        with open(path) as f:
            schema = json.load(f)
        allowed = schema["properties"]["severity"]["enum"]
        assert "info" in allowed
        assert "low" in allowed
        assert "medium" in allowed
        assert "high" in allowed
        assert "critical" in allowed


# ── Advisory validation unchanged ────────────────────────────────────────────


class TestAdvisoryUnchanged:
    """Verify advisory validation remains warn-only, never blocking."""

    @pytest.fixture()
    def taxonomy_file(self, tmp_path):
        taxonomy = {
            "schema_version": "1.0.0",
            "allowed_event_types": {
                "test": ["test.event.fired"],
            },
        }
        path = tmp_path / "taxonomy.json"
        path.write_text(json.dumps(taxonomy))
        return path

    def test_advisory_warns_but_does_not_block(self, taxonomy_file):
        result = validate_event_type_advisory("unknown.event.type", taxonomy_file)
        assert result.is_registered is False
        assert result.message is not None

    def test_advisory_passes_known_type(self, taxonomy_file):
        result = validate_event_type_advisory("test.event.fired", taxonomy_file)
        assert result.is_registered is True

    def test_advisory_does_not_raise(self, taxonomy_file):
        result = validate_event_type_advisory("totally.unknown.type", taxonomy_file)
        assert isinstance(result, AdvisoryResult)
