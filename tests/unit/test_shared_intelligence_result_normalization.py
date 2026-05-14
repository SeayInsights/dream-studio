from __future__ import annotations

from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.result_normalization import (
    adapter_result_summary,
    normalize_adapter_result_payload,
    record_normalized_adapter_result,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "result-normalization" / "studio.db"


def test_normalize_adapter_result_payload_maps_refs_and_status() -> None:
    normalized = normalize_adapter_result_payload(
        {
            "type": "code_change",
            "status": "passed",
            "decisions": "decision://1",
            "code_changes": ["git://commit"],
            "evidence": ["evidence://validation"],
            "validations": ["pytest://suite"],
            "research": ["research://note"],
            "risks": ["risk://low"],
            "artifacts": ["artifact://report"],
            "outcomes": ["outcome://complete"],
        }
    )

    assert normalized["result_type"] == "code_change"
    assert normalized["normalized_status"] == "validated"
    assert normalized["decision_refs"] == ["decision://1"]
    assert normalized["code_change_refs"] == ["git://commit"]
    assert normalized["validation_refs"] == ["pytest://suite"]
    assert normalized["payload"]["adapter_output_is_authority"] is False


def test_record_normalized_adapter_result_writes_sqlite_result_record(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        summary = record_normalized_adapter_result(
            conn,
            result_id="adapter-result-codex-1",
            adapter_id="codex",
            packet_id=None,
            project_id="dream-studio",
            milestone_id="adapter_result_normalization",
            task_id="wo-result-normalization",
            process_run_id="process-result-normalization",
            raw_result={
                "result_type": "validation",
                "status": "success",
                "evidence_refs": ["evidence://adapter-result"],
                "validation_refs": ["pytest://adapter-result"],
            },
        )
        row = conn.execute(
            "SELECT * FROM adapter_result_records WHERE result_id = ?",
            ("adapter-result-codex-1",),
        ).fetchone()

    assert summary["result_count"] == 1
    assert summary["adapter_counts"] == {"codex": 1}
    assert summary["status_counts"] == {"validated": 1}
    assert row["normalized_status"] == "validated"


def test_adapter_result_summary_is_scoped_and_non_authoritative(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        record_normalized_adapter_result(
            conn,
            result_id="adapter-result-codex-1",
            adapter_id="codex",
            project_id="dream-studio",
            raw_result={"result_type": "decision", "status": "completed"},
        )
        record_normalized_adapter_result(
            conn,
            result_id="adapter-result-chatgpt-1",
            adapter_id="chatgpt",
            project_id="other-project",
            raw_result={"result_type": "research", "status": "partial"},
        )
        summary = adapter_result_summary(conn, project_id="dream-studio")
        empty = adapter_result_summary(conn, project_id="missing")

    assert summary["derived_view"] is True
    assert summary["primary_authority"] is False
    assert summary["adapter_output_is_authority"] is False
    assert summary["result_type_counts"] == {"decision": 1}
    assert empty["result_count"] == 0
    assert empty["empty_state"] == "No normalized adapter results recorded for the selected scope."


def test_record_normalized_adapter_result_requires_registered_adapter(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        with pytest.raises(ValueError, match="unknown adapter_id"):
            record_normalized_adapter_result(
                conn,
                result_id="adapter-result-missing",
                adapter_id="missing",
                raw_result={"result_type": "validation"},
            )


def test_adapter_result_normalization_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        record_normalized_adapter_result(
            conn,
            result_id="adapter-result-codex-1",
            adapter_id="codex",
            raw_result={"result_type": "validation", "status": "passed"},
        )

    assert db_path.is_file()
    assert db_path != live_db
