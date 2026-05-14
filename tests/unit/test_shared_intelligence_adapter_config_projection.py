from __future__ import annotations

from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.adapter_config_projection import (
    adapter_config_projection,
    adapter_config_projection_report,
    validate_adapter_config_projection_report,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "adapter-config-projection" / "studio.db"


def test_adapter_config_projection_generates_markdown_from_sqlite_authority(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection = adapter_config_projection(conn, adapter_id="codex", project_id="dream-studio")

    assert projection["adapter_id"] == "codex"
    assert projection["projection_path"] == "adapter-projections/codex/AGENTS.md"
    assert projection["source_authority"] == "sqlite"
    assert projection["config_write_authorized"] is False
    assert projection["adapter_owns_source_of_truth"] is False
    assert "Dream Studio SQLite authority is the source of truth." in projection["content"]
    assert "Adapter must not" not in projection["content"]
    assert projection["content_sha256"]


def test_adapter_config_projection_generates_json_for_tool_like_adapters(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection = adapter_config_projection(conn, adapter_id="shell")

    assert projection["projection_path"] == "adapter-projections/shell/command-policy.json"
    assert '"adapter_id": "shell"' in projection["content"]
    assert '"adapter_owns_source_of_truth": false' in projection["content"]
    assert projection["config_write_authorized"] is False


def test_adapter_config_projection_report_is_non_mutating(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        report = adapter_config_projection_report(conn, project_id="dream-studio")

    assert validate_adapter_config_projection_report(report) == []
    assert report["adapter_count"] == 8
    assert report["derived_view"] is True
    assert report["primary_authority"] is False
    assert report["config_write_authorized"] is False
    assert all(item["content_sha256"] for item in report["projections"])
    assert all(item["config_write_authorized"] is False for item in report["projections"])


def test_adapter_config_projection_refuses_unknown_adapter(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        with pytest.raises(ValueError, match="unknown adapter_id"):
            adapter_config_projection(conn, adapter_id="missing")


def test_adapter_config_projection_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        report = adapter_config_projection_report(conn)

    assert report["adapter_count"] == 8
    assert db_path.is_file()
    assert db_path != live_db
