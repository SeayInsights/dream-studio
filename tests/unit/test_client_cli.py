"""WO-CLIENT-CLI: the ds client command group + ds project --client extensions are wired and
dispatch to the event-sourced client engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from interfaces.cli.commands import client as client_cmd
from interfaces.cli.commands import project as project_cmd


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    client_cmd.register(sub)
    project_cmd.register(sub)
    return parser


@pytest.mark.parametrize(
    "argv,expected_sub",
    [
        (["client", "create", "--name", "Acme"], "create"),
        (["client", "list"], "list"),
        (["client", "show", "acme"], "show"),
        (["client", "archive", "acme"], "archive"),
        (["client", "delete", "acme"], "delete"),
        (["client", "attach", "p1", "--client", "acme"], "attach"),
        (["client", "detach", "p1"], "detach"),
    ],
)
def test_client_subcommands_registered(argv, expected_sub):
    args = _parser().parse_args(argv)
    assert args.command == "client"
    assert args.client_command == expected_sub


def test_project_register_and_list_gain_client_arg():
    reg = _parser().parse_args(
        ["project", "register", "--name", "X", "--path", "/tmp/x", "--client", "fulcrum"]
    )
    assert reg.client_id == "fulcrum"
    lst = _parser().parse_args(["project", "list", "--client", "fulcrum"])
    assert lst.client_id == "fulcrum"


def _dispatch(argv, **mocks):
    args = _parser().parse_args(argv)
    return client_cmd.dispatch(args, source_root=Path("."), dream_studio_home=None)


def test_client_create_dispatches_to_engine(monkeypatch, capsys):
    from core.clients import mutations

    calls = []
    monkeypatch.setattr(
        mutations,
        "create_client",
        lambda **kw: calls.append(kw) or {"ok": True, "client_id": "acme", "name": kw["name"]},
    )
    rc = _dispatch(["client", "create", "--name", "Acme", "--description", "d"])
    assert rc == 0
    assert calls == [{"name": "Acme", "description": "d"}]
    assert json.loads(capsys.readouterr().out)["client_id"] == "acme"


def test_client_attach_dispatches_to_engine(monkeypatch, capsys):
    from core.clients import mutations

    calls = []
    monkeypatch.setattr(
        mutations,
        "assign_project_client",
        lambda **kw: calls.append(kw) or {"ok": True, **kw},
    )
    rc = _dispatch(["client", "attach", "p1", "--client", "fulcrum"])
    assert rc == 0
    assert calls == [{"project_id": "p1", "client_id": "fulcrum"}]


def test_client_show_dispatches_to_queries(monkeypatch, capsys):
    from core.clients import queries

    monkeypatch.setattr(client_cmd, "_db_path", lambda *a, **k: Path("/tmp/x.db"))
    monkeypatch.setattr(
        queries, "get_client", lambda cid, db_path=None: {"client_id": cid, "name": "Fulcrum"}
    )
    monkeypatch.setattr(
        queries, "projects_for_client", lambda cid, db_path=None: [{"project_id": "p1"}]
    )
    rc = _dispatch(["client", "show", "fulcrum"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["client"]["name"] == "Fulcrum"
    assert out["client"]["projects"] == [{"project_id": "p1"}]


def test_client_show_missing_returns_error(monkeypatch, capsys):
    from core.clients import queries

    monkeypatch.setattr(client_cmd, "_db_path", lambda *a, **k: Path("/tmp/x.db"))
    monkeypatch.setattr(queries, "get_client", lambda cid, db_path=None: None)
    rc = _dispatch(["client", "show", "nope"])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
