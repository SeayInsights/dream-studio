"""Slice 6c: ds skill invoke / list tests + migration 052 + ingestor normalization."""

from __future__ import annotations

import json


from interfaces.cli.ds import main

NOW = "2026-05-16T00:00:00+00:00"
MARKER_PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def _invoke(tmp_path, monkeypatch, specifier, extra=None):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    argv = ["skill", "invoke", specifier]
    if extra:
        argv.extend(extra)
    return main(argv)


def _spool_events(tmp_path):
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in (tmp_path / "spool-root" / "spool").glob("*.json")
    ]


# ── format and pack/mode validation ──────────────────────────────────────────


def test_valid_specifier_core_build_resolves_correctly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(["skill", "invoke", "core:build"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Skill: core:build" in out
    assert "Invocation recorded." in out


def test_valid_specifier_security_scan_resolves_correctly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(["skill", "invoke", "security:scan"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Skill: security:scan" in out


def test_invalid_format_slash_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(["skill", "invoke", "core/build"])
    assert rc == 1


def test_invalid_format_no_colon_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(["skill", "invoke", "build"])
    assert rc == 1


def test_unknown_pack_exits_1_with_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(["skill", "invoke", "nonexistent:build"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Unknown skill: nonexistent:build" in err


def test_unknown_mode_for_valid_pack_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(["skill", "invoke", "core:nonexistent"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Unknown skill: core:nonexistent" in err


# ── invocation_mode ───────────────────────────────────────────────────────────


def test_work_order_flag_sets_pipeline_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    main(["skill", "invoke", "core:build", "--work-order", WO_ID])
    events = _spool_events(tmp_path)
    assert len(events) == 1
    assert events[0]["invocation_mode"] == "pipeline"


def test_no_work_order_flag_sets_direct_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    main(["skill", "invoke", "core:build"])
    events = _spool_events(tmp_path)
    assert len(events) == 1
    assert events[0]["invocation_mode"] == "direct"


# ── project_id resolution ─────────────────────────────────────────────────────


def test_project_id_from_marker_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    marker = tmp_path / ".dream-studio-project"
    marker.write_text(MARKER_PROJECT_ID + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["skill", "invoke", "core:build"])
    events = _spool_events(tmp_path)
    assert len(events) == 1
    assert events[0]["project_id"] == MARKER_PROJECT_ID


def test_project_id_null_when_no_marker_and_no_project(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    monkeypatch.chdir(tmp_path)
    main(["skill", "invoke", "core:build"])
    events = _spool_events(tmp_path)
    assert len(events) == 1
    assert events[0]["project_id"] is None


# ── spool event content ───────────────────────────────────────────────────────


def test_spool_event_emitted_and_skill_content_printed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(["skill", "invoke", "core:build"])
    assert rc == 0
    events = _spool_events(tmp_path)
    assert len(events) == 1
    assert events[0]["event_type"] == "skill.invoked"
    out = capsys.readouterr().out
    assert "Invocation recorded." in out


def test_spool_event_contains_correct_invocation_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    main(["skill", "invoke", "security:scan", "--work-order", WO_ID])
    events = _spool_events(tmp_path)
    assert len(events) == 1
    ev = events[0]
    assert ev["event_type"] == "skill.invoked"
    assert ev["invocation_mode"] == "pipeline"
    assert ev["skill_id"] == "ds-security"
    assert ev["payload"]["skill_specifier"] == "security:scan"


# ── skill list ────────────────────────────────────────────────────────────────


def test_skill_list_shows_all_packs_and_modes(capsys):
    rc = main(["skill", "list"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    specifiers = {s["specifier"] for s in out["skills"]}
    assert "core:build" in specifiers
    assert "security:scan" in specifiers
    assert "quality:debug" in specifiers
    assert len(out["skills"]) > 10


def test_skill_list_filter_by_pack(capsys):
    rc = main(["skill", "list", "--pack", "security"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    specifiers = {s["specifier"] for s in out["skills"]}
    assert all(s.startswith("security:") for s in specifiers)
    assert "security:scan" in specifiers
    assert "core:build" not in specifiers


# WO-SQUASH-TESTS: test_migration_052_runs_cleanly deleted — it ran
# run_migrations(target_version=52) to assert migration 052's ALTER added
# invocation_mode. Migrations 001-141 are folded into the lean baseline (142),
# so no target_version=52 exists; the column is present in the baseline schema,
# validated by test_migration_142_baseline / the schema-identity proof.


# ── ingestor skill_id normalization ──────────────────────────────────────────


def _make_skill_event(skill_id: str, event_id: str = "evt-skill-1") -> dict:
    return {
        "event_id": event_id,
        "event_type": "skill.invoked",
        "timestamp": NOW,
        "schema_version": 1,
        "skill_id": skill_id,
        "invocation_mode": "direct",
        "payload": {"skill_specifier": "core:build"},
    }


def test_ingestor_rejects_skill_id_with_slash(tmp_path):
    from spool.ingestor import ingest
    from spool.states import ensure_dirs
    from spool.writer import write_event

    ensure_dirs(tmp_path)
    db_path = tmp_path / "test.db"
    event = _make_skill_event("ds-core/build")
    write_event(event, root=tmp_path)

    result = ingest(root=tmp_path, db_path=db_path)
    assert result.failed == 1
    assert result.processed == 0

    reason_files = list((tmp_path / "failed" / "reasons").glob("*.reason.json"))
    assert len(reason_files) == 1
    reason_data = json.loads(reason_files[0].read_text(encoding="utf-8"))
    assert reason_data["reason"] == "malformed_skill_id"


def test_ingestor_rejects_skill_id_without_ds_prefix(tmp_path):
    from spool.ingestor import ingest
    from spool.states import ensure_dirs
    from spool.writer import write_event

    ensure_dirs(tmp_path)
    db_path = tmp_path / "test.db"
    event = _make_skill_event("core:build", event_id="evt-skill-2")
    write_event(event, root=tmp_path)

    result = ingest(root=tmp_path, db_path=db_path)
    assert result.failed == 1
    assert result.processed == 0

    reason_files = list((tmp_path / "failed" / "reasons").glob("*.reason.json"))
    assert len(reason_files) == 1
    reason_data = json.loads(reason_files[0].read_text(encoding="utf-8"))
    assert reason_data["reason"] == "malformed_skill_id"
