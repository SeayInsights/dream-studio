"""Phase 7A canonical event contract boundary tests."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from core.event_store.event_store import EventStore
from core.validation.event_validator import EventValidator

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "event-contract.md"
SCHEMA_PATH = REPO_ROOT / "docs" / "canonical" / "canonical_event_v1_schema.json"
TAXONOMY_PATH = REPO_ROOT / "docs" / "canonical" / "event_taxonomy_v1.json"


def _valid_event() -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": "workflow.execution.started",
        "timestamp": "2026-05-10T00:00:00Z",
        "trace": {"workflow_id": "phase-7a", "execution_id": "contract-test"},
        "severity": "info",
        "payload": {"phase": "7A", "source": "core"},
        "source_type": "confirmed",
    }


def _read_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_event_contract_document_defines_phase7a_envelope_and_boundaries():
    contract = CONTRACT_PATH.read_text(encoding="utf-8")

    for section in [
        "## Authority",
        "## Event Envelope",
        "## Versioning Rules",
        "## Replay Expectations",
        "## Export Expectations",
        "## What Is Not An Event",
        "## Boundary Rules",
    ]:
        assert section in contract

    for semantic_slot in [
        "`event_id`",
        "`event_type`",
        "`schema_version`",
        "`source`",
        "adapter/tool/model metadata",
        "subject/resource",
        "`timestamp`",
        "correlation/session/workflow IDs",
        "`payload`",
        "privacy/export classification",
    ]:
        assert semantic_slot in contract

    assert "Dashboards, API routes, telemetry views" in contract
    assert "Phase 7A does not require schema churn" in contract


def test_canonical_event_v1_schema_remains_strict_root_contract():
    schema = _read_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "event_id",
        "event_type",
        "timestamp",
        "trace",
        "severity",
        "payload",
    ]
    assert set(schema["properties"]) == {
        "event_id",
        "event_type",
        "timestamp",
        "trace",
        "severity",
        "payload",
        "actor",
        "confidence_score",
        "source_type",
    }
    assert schema["properties"]["trace"]["additionalProperties"] is False
    assert set(schema["properties"]["source_type"]["enum"]) == {
        "confirmed",
        "inferred",
        "weak_inference",
    }


def test_validator_rejects_future_root_slots_until_versioned_schema_exists():
    validator = EventValidator(str(TAXONOMY_PATH), str(SCHEMA_PATH))
    event = _valid_event()
    event["schema_version"] = "1.0.0"

    result = validator.validate(event)

    assert not result.is_valid
    assert any("Additional properties are not allowed" in error for error in result.errors)


def test_event_store_logs_rejected_root_shape_without_persisting_invalid_event(tmp_path):
    validator = EventValidator(str(TAXONOMY_PATH), str(SCHEMA_PATH))
    store = EventStore(str(tmp_path / "events.db"), validator)
    event = _valid_event()
    event["schema_version"] = "1.0.0"

    try:
        assert store.write_event(event) is False

        # _emit_validation_failure_event writes to ai_canonical_events (event.validation.failed → _AI)
        # which also creates the table. Check the invalid event is NOT there, failure event IS.
        invalid_rows = store.db.execute(
            "SELECT COUNT(*) FROM ai_canonical_events WHERE event_id = ?",
            (event["event_id"],),
        ).fetchone()[0]
        # Note: get_validation_failures() returns [] since migration 129 (WO-READMODELS-DUCKDB)
        # dropped the SQLite validation_failures table. Validation failures are now served by
        # the DuckDB validation_failures VIEW in aggregate_metrics.db via events_fact pipeline.
        failures = store.get_validation_failures()
        failure_events = store.db.execute(
            "SELECT COUNT(*) FROM ai_canonical_events WHERE event_type = ?",
            ("event.validation.failed",),
        ).fetchone()[0]

        assert invalid_rows == 0
        # SQLite validation_failures table was dropped in migration 129; get_validation_failures()
        # is now a stub returning []. The canonical evidence lives in ai_canonical_events.
        assert failures == []
        assert failure_events == 1
    finally:
        store.close()


def test_projection_api_surfaces_do_not_write_or_emit_canonical_events():
    api_paths = sorted((REPO_ROOT / "projections" / "api").rglob("*.py"))
    assert api_paths

    forbidden = [
        "EventStore(",
        "emit_event(",
        "INSERT INTO canonical_events",
        "UPDATE canonical_events",
        "DELETE FROM canonical_events",
    ]
    offenders: list[str] = []
    for path in api_paths:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                offenders.append(f"{path.relative_to(REPO_ROOT)} contains {token}")

    assert offenders == []


def test_adapter_interfaces_do_not_own_event_store_persistence():
    adapter_paths = sorted((REPO_ROOT / "interfaces" / "adapters").rglob("*.py"))
    assert not adapter_paths, "adapters/ was retired in Slice 4 — this directory must remain absent"

    forbidden = [
        "EventStore(",
        "emit_event(",
        "canonical_events",
        "validation_failures",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    ]
    offenders: list[str] = []
    for path in adapter_paths:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                offenders.append(f"{path.relative_to(REPO_ROOT)} contains {token}")

    assert offenders == []
