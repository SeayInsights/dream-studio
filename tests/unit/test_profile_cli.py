"""ds profile command group is wired and dispatches to the core/profiles engine.
Mirrors tests/unit/test_client_cli.py's shape for the sibling client CLI."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.commands import profile as profile_cmd
from interfaces.cli.ds import main


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    profile_cmd.register(sub)
    return parser


@pytest.mark.parametrize(
    "argv,expected_sub",
    [
        (["profile", "create", "--name", "Fulcrum", "--client", "fulcrum"], "create"),
        (["profile", "list"], "list"),
        (["profile", "switch", "p1"], "switch"),
        (["profile", "show"], "show"),
    ],
)
def test_profile_subcommands_registered(argv, expected_sub):
    args = _parser().parse_args(argv)
    assert args.command == "profile"
    assert args.profile_command == expected_sub


def test_profile_create_parses_optional_fields():
    args = _parser().parse_args(
        [
            "profile",
            "create",
            "--name",
            "Fulcrum",
            "--client",
            "fulcrum",
            "--claude-config-dir",
            "/x/.claude-fulcrum",
            "--mcp-client-name",
            "fulcrum-mcp",
        ]
    )
    assert args.client_id == "fulcrum"
    assert args.claude_config_dir == "/x/.claude-fulcrum"
    assert args.mcp_client_name == "fulcrum-mcp"


def _dispatch(argv):
    args = _parser().parse_args(argv)
    return profile_cmd.dispatch(args, source_root=Path("."), dream_studio_home=None)


def test_profile_create_dispatches_to_engine(monkeypatch, capsys):
    from core.profiles import mutations

    calls = []
    monkeypatch.setattr(
        mutations,
        "create_profile",
        lambda **kw: calls.append(kw)
        or {"ok": True, "profile_id": "p1", "client_id": kw["client_id"], "name": kw["name"]},
    )
    rc = _dispatch(["profile", "create", "--name", "Fulcrum", "--client", "fulcrum"])
    assert rc == 0
    assert calls[0]["name"] == "Fulcrum"
    assert calls[0]["client_id"] == "fulcrum"
    assert json.loads(capsys.readouterr().out)["profile_id"] == "p1"


def test_profile_switch_dispatches_to_engine(monkeypatch, capsys):
    from core.profiles import mutations

    calls = []
    monkeypatch.setattr(
        mutations,
        "switch_active_profile",
        lambda **kw: calls.append(kw)
        or {"ok": True, "profile_id": kw["profile_id"], "status": "active"},
    )
    rc = _dispatch(["profile", "switch", "p1"])
    assert rc == 0
    assert calls == [{"profile_id": "p1", "source_root": Path("."), "dream_studio_home": None}]


def test_profile_show_no_active_profile(monkeypatch, capsys):
    from core.profiles import queries

    monkeypatch.setattr(profile_cmd, "_db_path", lambda *a, **k: Path("/tmp/x.db"))
    monkeypatch.setattr(queries, "active_profile", lambda db_path=None: None)
    rc = _dispatch(["profile", "show"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["profile"] is None


def test_profile_show_returns_active_profile(monkeypatch, capsys):
    from core.profiles import queries

    monkeypatch.setattr(profile_cmd, "_db_path", lambda *a, **k: Path("/tmp/x.db"))
    monkeypatch.setattr(
        queries, "active_profile", lambda db_path=None: {"profile_id": "p1", "name": "Fulcrum"}
    )
    rc = _dispatch(["profile", "show"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["profile"]["name"] == "Fulcrum"


# ── seeded end-to-end (real DB via the ds main() entry, no mocks) ────────────


def _home(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    return tmp_path


def test_e2e_create_list_switch_show(tmp_path, capsys):
    home = _home(tmp_path)

    assert (
        main(
            [
                "--home",
                str(home),
                "profile",
                "create",
                "--name",
                "SeayInsights",
                "--client",
                "seayinsights",
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    assert first["ok"] is True
    first_id = first["profile_id"]

    assert (
        main(["--home", str(home), "profile", "create", "--name", "Fulcrum", "--client", "fulcrum"])
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    second_id = second["profile_id"]

    assert main(["--home", str(home), "profile", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)["profiles"]
    assert {p["profile_id"] for p in listed} == {first_id, second_id}

    assert main(["--home", str(home), "profile", "switch", second_id]) == 0
    switched = json.loads(capsys.readouterr().out)
    assert switched == {"ok": True, "profile_id": second_id, "status": "active"}

    assert main(["--home", str(home), "profile", "show"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["profile"]["profile_id"] == second_id
    assert shown["profile"]["status"] == "active"

    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        assert (
            conn.execute(
                "SELECT status FROM business_profiles WHERE profile_id = ?", (first_id,)
            ).fetchone()[0]
            == "paused"
        )
    finally:
        conn.close()


def test_e2e_create_with_invalid_client_refuses(tmp_path, capsys):
    home = _home(tmp_path)
    rc = main(["--home", str(home), "profile", "create", "--name", "Nope", "--client", "bogus"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "bogus" in out["error"]
