"""Phase 4E tests — advisory event type validation.

Proves that:
- Known event types pass without warning
- Unknown event types produce advisory warning but do not block emission
- Advisory validation derives from the existing canonical taxonomy
- No new event type authority is created
- Existing EventValidator and emission behavior is unchanged
- No import cycles
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.events.event_type_advisory import (
    AdvisoryResult,
    get_registered_event_types,
    reset_cache,
    validate_event_type_advisory,
)

pytestmark = pytest.mark.runtime_reliability


# ── Fixtures ──────────────────────────────────────────────────────────────────


SAMPLE_TAXONOMY = {
    "schema_version": "1.0.0",
    "allowed_event_types": {
        "analysis": ["analysis.started", "analysis.completed"],
        "execution": ["execution.started", "execution.completed"],
        "session": ["session.started", "session.ended"],
    },
}


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset module cache before each test."""
    reset_cache()
    yield
    reset_cache()


@pytest.fixture()
def taxonomy_file(tmp_path: Path) -> Path:
    """Write a sample taxonomy JSON and return its path."""
    path = tmp_path / "event_taxonomy_v1.json"
    path.write_text(json.dumps(SAMPLE_TAXONOMY))
    return path


@pytest.fixture()
def real_taxonomy() -> Path:
    """Path to the real project taxonomy file."""
    return Path("docs/canonical/event_taxonomy_v1.json")


# ── AdvisoryResult dataclass ──────────────────────────────────────────────────


class TestAdvisoryResult:
    def test_registered_result(self):
        result = AdvisoryResult(is_registered=True, event_type="analysis.started")
        assert result.is_registered is True
        assert result.event_type == "analysis.started"
        assert result.message is None

    def test_unregistered_result(self):
        result = AdvisoryResult(
            is_registered=False,
            event_type="fake.event",
            message="Not registered",
        )
        assert result.is_registered is False
        assert result.message == "Not registered"

    def test_result_is_frozen(self):
        result = AdvisoryResult(is_registered=True, event_type="test")
        with pytest.raises(AttributeError):
            result.is_registered = False


# ── get_registered_event_types ────────────────────────────────────────────────


class TestGetRegisteredEventTypes:
    def test_loads_from_taxonomy_file(self, taxonomy_file):
        types = get_registered_event_types(taxonomy_file)
        assert "analysis.started" in types
        assert "analysis.completed" in types
        assert "execution.started" in types
        assert "session.started" in types

    def test_returns_frozenset(self, taxonomy_file):
        types = get_registered_event_types(taxonomy_file)
        assert isinstance(types, frozenset)

    def test_flattens_all_domains(self, taxonomy_file):
        types = get_registered_event_types(taxonomy_file)
        expected = set()
        for events in SAMPLE_TAXONOMY["allowed_event_types"].values():
            expected.update(events)
        assert types == expected

    def test_caches_after_first_load(self, taxonomy_file):
        first = get_registered_event_types(taxonomy_file)
        second = get_registered_event_types(taxonomy_file)
        assert first is second

    def test_missing_file_returns_empty(self, tmp_path, caplog):
        missing = tmp_path / "nonexistent.json"
        with caplog.at_level(logging.WARNING):
            types = get_registered_event_types(missing)
        assert types == frozenset()
        assert "taxonomy not found" in caplog.text.lower()

    def test_reset_cache_allows_reload(self, taxonomy_file):
        first = get_registered_event_types(taxonomy_file)
        reset_cache()
        second = get_registered_event_types(taxonomy_file)
        assert first == second
        assert first is not second

    def test_loads_real_taxonomy(self, real_taxonomy):
        if not real_taxonomy.exists():
            pytest.skip("Real taxonomy not found")
        types = get_registered_event_types(real_taxonomy)
        assert len(types) > 50
        assert "analysis.started" in types
        assert "execution.started" in types


# ── validate_event_type_advisory ──────────────────────────────────────────────


class TestValidateEventTypeAdvisory:
    def test_known_type_passes(self, taxonomy_file):
        result = validate_event_type_advisory("analysis.started", taxonomy_file)
        assert result.is_registered is True
        assert result.message is None

    def test_unknown_type_warns(self, taxonomy_file):
        result = validate_event_type_advisory("fake.nonexistent.type", taxonomy_file)
        assert result.is_registered is False
        assert result.message is not None
        assert "not registered" in result.message.lower()
        assert "fake.nonexistent.type" in result.message

    def test_unknown_type_does_not_raise(self, taxonomy_file):
        result = validate_event_type_advisory("fake.type", taxonomy_file)
        assert result.is_registered is False

    def test_disabled_when_taxonomy_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = validate_event_type_advisory("anything", missing)
        assert result.is_registered is True
        assert result.message is not None
        assert "disabled" in result.message.lower()

    def test_result_includes_event_type(self, taxonomy_file):
        result = validate_event_type_advisory("execution.started", taxonomy_file)
        assert result.event_type == "execution.started"

    def test_all_sample_types_pass(self, taxonomy_file):
        for events in SAMPLE_TAXONOMY["allowed_event_types"].values():
            for event_type in events:
                result = validate_event_type_advisory(event_type, taxonomy_file)
                assert result.is_registered is True, f"{event_type} should be registered"


# ── Derives from canonical taxonomy (not a new authority) ─────────────────────


class TestDerivesFromCanonicalTaxonomy:
    def test_uses_same_file_as_event_validator(self, real_taxonomy):
        """Advisory helper and EventValidator derive from the same taxonomy JSON."""
        if not real_taxonomy.exists():
            pytest.skip("Real taxonomy not found")

        with open(real_taxonomy) as f:
            taxonomy = json.load(f)
        validator_types = set()
        for events in taxonomy["allowed_event_types"].values():
            validator_types.update(events)

        advisory_types = get_registered_event_types(real_taxonomy)
        assert advisory_types == validator_types

    def test_no_hardcoded_type_list(self):
        """The advisory module must NOT contain a hardcoded ALL_TYPES list."""
        import core.events.event_type_advisory as mod

        source = Path(mod.__file__).read_text()
        assert "ALL_TYPES" not in source
        assert "ALL_EVENT_TYPES" not in source

    def test_advisory_types_subset_matches_validator_flatten(self, real_taxonomy):
        """Advisory types match what EventValidator._flatten_taxonomy() produces."""
        if not real_taxonomy.exists():
            pytest.skip("Real taxonomy not found")

        from core.validation.event_validator import EventValidator

        validator = EventValidator(
            str(real_taxonomy), "docs/canonical/canonical_event_v1_schema.json"
        )
        assert get_registered_event_types(real_taxonomy) == frozenset(validator.allowed_types)


# ── Emitter integration ───────────────────────────────────────────────────────


class TestEmitterIntegration:
    def test_emitter_imports_advisory(self):
        """The emitter module imports advisory validation without error."""
        import core.events.emitter  # noqa: F401

    def test_known_type_no_advisory_warning(self, taxonomy_file, caplog):
        """Known event types do not produce advisory warnings in emit_event."""
        reset_cache()
        get_registered_event_types(taxonomy_file)

        with caplog.at_level(logging.WARNING, logger="core.events.emitter"):
            with patch("core.events.emitter._get_event_store") as mock_store:
                mock_store.return_value.write_event.return_value = True
                with patch(
                    "core.events.emitter.validate_event_type_advisory",
                    wraps=validate_event_type_advisory,
                ) as mock_advisory:
                    mock_advisory.return_value = AdvisoryResult(
                        is_registered=True, event_type="analysis.started"
                    )
                    from core.events.emitter import emit_event

                    emit_event("analysis.started", {"test": True})

        assert "Advisory:" not in caplog.text

    def test_unknown_type_logs_advisory_warning(self, taxonomy_file, caplog):
        """Unknown event types produce advisory warning but emission continues."""
        from core.events.emitter import emit_event

        with caplog.at_level(logging.WARNING, logger="core.events.emitter"):
            with patch("core.events.emitter._get_event_store") as mock_store:
                mock_store.return_value.write_event.return_value = True
                with patch(
                    "core.events.emitter.validate_event_type_advisory",
                ) as mock_advisory:
                    mock_advisory.return_value = AdvisoryResult(
                        is_registered=False,
                        event_type="fake.unknown.type",
                        message="Event type 'fake.unknown.type' is not registered",
                    )
                    result = emit_event("fake.unknown.type", {"test": True})

        assert "Advisory:" in caplog.text
        assert result is not None

    def test_unknown_type_still_emits(self, taxonomy_file):
        """Advisory validation does not block event emission."""
        from core.events.emitter import emit_event

        with patch("core.events.emitter._get_event_store") as mock_store:
            mock_store.return_value.write_event.return_value = True
            with patch(
                "core.events.emitter.validate_event_type_advisory",
            ) as mock_advisory:
                mock_advisory.return_value = AdvisoryResult(
                    is_registered=False,
                    event_type="fake.type",
                    message="Not registered",
                )
                result = emit_event("fake.type", {"data": 1})

        mock_store.return_value.write_event.assert_called_once()
        assert result is not None


# ── Existing behavior preservation ────────────────────────────────────────────


class TestExistingBehaviorPreservation:
    def test_event_validator_unchanged(self, real_taxonomy):
        """EventValidator still validates the same way."""
        if not real_taxonomy.exists():
            pytest.skip("Real taxonomy not found")

        schema_path = "docs/canonical/canonical_event_v1_schema.json"
        if not Path(schema_path).exists():
            pytest.skip("Schema file not found")

        from core.validation.event_validator import EventValidator

        validator = EventValidator(str(real_taxonomy), schema_path)

        # Use 3-segment type that matches both taxonomy and schema format
        result = validator.validate(
            {
                "event_id": "00000000-0000-0000-0000-000000000001",
                "event_type": "workflow.execution.started",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "trace": {"project_id": "test"},
                "severity": "low",
                "payload": {},
            }
        )
        assert result.is_valid is True

        result_bad = validator.validate(
            {
                "event_id": "00000000-0000-0000-0000-000000000002",
                "event_type": "completely.fake.type",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "trace": {"project_id": "test"},
                "severity": "low",
                "payload": {},
            }
        )
        assert result_bad.is_valid is False

    def test_criticality_system_unchanged(self):
        """Criticality system still works as before."""
        from core.events.criticality import (
            EventCriticality,
            get_criticality,
            is_critical,
            is_important,
        )

        assert get_criticality("execution.started") == EventCriticality.CRITICAL
        assert get_criticality("wave.started") == EventCriticality.IMPORTANT
        assert get_criticality("telemetry.something") == EventCriticality.OPTIONAL
        assert is_critical("execution.started") is True
        assert is_important("wave.started") is True


# ── No import cycles ──────────────────────────────────────────────────────────


class TestNoImportCycles:
    def test_advisory_imports_cleanly(self):
        import core.events.event_type_advisory  # noqa: F401

    def test_emitter_imports_cleanly(self):
        import core.events.emitter  # noqa: F401

    def test_advisory_does_not_import_runtime_modules(self):
        """Advisory helper must not import heavy runtime modules."""
        import core.events.event_type_advisory as mod

        source = Path(mod.__file__).read_text()
        forbidden = [
            "from core.event_store",
            "from core.projections",
            "from core.memory",
            "from core.storage",
            "from core.execution",
            "from core.security",
            "import core.event_store",
        ]
        for pattern in forbidden:
            assert pattern not in source, f"Advisory helper must not import: {pattern}"
