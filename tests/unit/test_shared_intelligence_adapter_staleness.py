from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.adapter_config_projection import adapter_config_projection
from core.shared_intelligence.adapter_staleness import (
    adapter_staleness_report,
    validate_adapter_staleness_report,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "adapter-staleness" / "studio.db"


def test_adapter_staleness_detects_aligned_stale_and_missing_configs(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    config_root = tmp_path / "adapter-configs"
    _write(
        home / ".codex" / "hooks.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\\"C:/Users/Example/builds/dream-studio/hooks/run.cmd\\" on-prompt-dispatch"
          }
        ]
      }
    ]
  }
}
""".lstrip(),
    )
    _write(
        home / ".claude" / "settings.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\\" on-prompt-dispatch"
          }
        ]
      }
    ]
  }
}
""".lstrip(),
    )
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        codex = adapter_config_projection(conn, adapter_id="codex", project_id="dream-studio")
        claude = adapter_config_projection(conn, adapter_id="claude", project_id="dream-studio")
        _write(config_root / codex["projection_path"], codex["content"])
        _write(config_root / claude["projection_path"], "stale claude projection\n")
        _write(
            config_root / "AGENTS.md",
            "Dream Studio SQLite authority projection for Codex.\n",
        )
        report = adapter_staleness_report(conn, config_root=config_root, project_id="dream-studio")

    assert validate_adapter_staleness_report(report) == []
    statuses = {check["adapter_id"]: check["status"] for check in report["checks"]}
    checks = {check["adapter_id"]: check for check in report["checks"]}
    assert statuses["codex"] == "aligned"
    assert statuses["claude"] == "stale"
    assert statuses["cursor"] == "missing"
    assert report["aligned_count"] == 1
    assert report["stale_count"] == 1
    assert report["missing_count"] == 6
    assert report["active_repo_surface_count"] == 2
    assert report["synced_active_surface_count"] == 0
    assert report["live_execution_proven"] is False
    assert checks["codex"]["generated_projection"]["classification"] == "generated_projection"
    assert "generated_projection" in checks["codex"]["state_classifications"]
    assert "active_repo_surface" in checks["codex"]["state_classifications"]
    assert "live_execution_unproven" in checks["codex"]["state_classifications"]
    assert checks["codex"]["active_repo_surface"]["consumes_dream_studio_authority"] is True
    assert checks["codex"]["active_repo_surface"]["active_matches_generated_sha256"] is False
    assert checks["codex"]["local_hook_surface"]["status"] == "aligned"
    assert (
        checks["codex"]["local_hook_surface"]["state_classification"]
        == "hook_surface_current_compatible"
    )
    assert checks["claude"]["local_hook_surface"]["status"] == "stale"
    assert "hook_surface_stale" in checks["claude"]["state_classifications"]
    assert report["config_write_authorized"] is False
    assert report["repair_execution_authorized"] is False
    assert all(
        item["execution_authorized"] is False for item in report["repair_work_order_candidates"]
    )


def test_adapter_staleness_empty_state_and_temp_db_boundary(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        report = adapter_staleness_report(conn, config_root=tmp_path / "configs")

    assert validate_adapter_staleness_report(report) == []
    assert report["adapter_count"] == 0
    assert report["empty_state"] == "No adapter projections are registered for staleness detection."
    assert db_path.is_file()
    assert db_path != live_db


def test_adapter_staleness_validator_rejects_repair_execution() -> None:
    report = {
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "config_write_authorized": True,
        "repair_execution_authorized": True,
        "live_execution_proven": True,
        "repair_work_order_candidates": [{"adapter_id": "codex", "execution_authorized": True}],
    }

    assert validate_adapter_staleness_report(report) == [
        "config_write_authorized must be false",
        "repair_execution_authorized must be false",
        "repair candidate codex authorizes execution",
        "live_execution_proven must not be true without explicit runtime evidence",
    ]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
