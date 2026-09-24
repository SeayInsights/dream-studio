"""The MCP server: protocol handling, auth, and the curated tool registry.

Curated and read-only by design (see integrations/mcp/tools.py's module docstring):
this covers the JSON-RPC message handler in isolation (no HTTP), the bearer-token
auth helpers, and the FastAPI transport wiring end to end via TestClient.
"""

from __future__ import annotations

import json

import pytest

from integrations.mcp import auth
from integrations.mcp.app import build_app
from integrations.mcp.server import handle_message
from integrations.mcp.tools import TOOLS, TOOLS_BY_NAME

# ── protocol handler (no HTTP) ──────────────────────────────────────────────


def test_initialize_returns_protocol_version_and_capabilities():
    resp = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"]
    assert resp["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert resp["result"]["serverInfo"]["name"] == "dream-studio"


def test_initialized_notification_gets_no_response():
    resp = handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None


def test_an_arbitrary_notification_gets_no_response():
    """No `id` on a message means no response is ever sent, per JSON-RPC 2.0 -- not
    just for the one notification method this server recognizes by name."""
    resp = handle_message({"jsonrpc": "2.0", "method": "notifications/whatever"})
    assert resp is None


def test_tools_list_names_every_registered_tool():
    resp = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {t.name for t in TOOLS}


def test_every_tool_carries_a_description_and_input_schema():
    resp = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    for tool in resp["result"]["tools"]:
        assert tool["description"], f"{tool['name']} has no description"
        assert tool["inputSchema"]["type"] == "object"


def test_tools_call_on_a_readonly_tool_succeeds():
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ds_skill_list", "arguments": {}},
        }
    )
    result = resp["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert "skills" in payload


def test_tools_call_unknown_tool_is_refused_as_invalid_params():
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "not_a_real_tool"}}
    )
    assert "error" in resp
    assert resp["error"]["code"] == -32602


def test_tools_call_missing_required_argument_reports_isError_not_a_crash():
    """A required argument missing is the caller's mistake, not a server fault -- it
    must come back as a tool result with isError, not raise out of handle_message."""
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "ds_project_status", "arguments": {}},
        }
    )
    result = resp["result"]
    assert result["isError"] is True
    assert "project_id" in result["content"][0]["text"]


def test_unknown_method_is_method_not_found():
    resp = handle_message({"jsonrpc": "2.0", "id": 6, "method": "resources/list"})
    assert resp["error"]["code"] == -32601


def test_non_jsonrpc_message_is_invalid_request():
    resp = handle_message({"id": 7, "method": "initialize"})
    assert resp["error"]["code"] == -32600


def test_every_tool_handler_reports_an_exception_as_isError_not_a_raise():
    """A handler that raises (bad SQLite path, missing authority, whatever) must
    become an isError tool result over the wire, never propagate out of the RPC
    layer -- a network client cannot see a Python traceback."""
    for tool in TOOLS:
        required = [
            name
            for name, spec in tool.input_schema.get("properties", {}).items()
            if name in tool.input_schema.get("required", [])
        ]
        # Calling with no arguments either succeeds (no required args) or comes back
        # as an isError result -- either way handle_message must not raise.
        resp = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {"name": tool.name, "arguments": {}},
            }
        )
        assert "result" in resp, f"{tool.name} raised out of handle_message: {resp}"
        if required:
            assert resp["result"]["isError"] is True


# ── auth ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def mcp_home(tmp_path):
    return tmp_path / "ds_home"


def test_ensure_token_creates_and_persists(mcp_home):
    token, created = auth.ensure_token(dream_studio_home=mcp_home)
    assert created is True
    assert len(token) > 20
    again, created_again = auth.ensure_token(dream_studio_home=mcp_home)
    assert created_again is False
    assert again == token


def test_rotate_token_changes_the_value(mcp_home):
    first, _ = auth.ensure_token(dream_studio_home=mcp_home)
    second = auth.rotate_token(dream_studio_home=mcp_home)
    assert second != first
    assert auth.read_token(dream_studio_home=mcp_home) == second


def test_verify_bearer_accepts_the_current_token(mcp_home):
    token, _ = auth.ensure_token(dream_studio_home=mcp_home)
    assert auth.verify_bearer(f"Bearer {token}", dream_studio_home=mcp_home) is True


def test_verify_bearer_rejects_wrong_or_missing_token(mcp_home):
    auth.ensure_token(dream_studio_home=mcp_home)
    assert auth.verify_bearer("Bearer wrong", dream_studio_home=mcp_home) is False
    assert auth.verify_bearer(None, dream_studio_home=mcp_home) is False
    assert auth.verify_bearer("not-even-bearer-shaped", dream_studio_home=mcp_home) is False


def test_verify_bearer_rejects_when_no_token_was_ever_generated(mcp_home):
    assert auth.verify_bearer("Bearer anything", dream_studio_home=mcp_home) is False


def test_token_file_has_restrictive_permissions_on_posix(mcp_home):
    import stat
    import sys

    token, _ = auth.ensure_token(dream_studio_home=mcp_home)
    path = mcp_home / "state" / "mcp-token.json"
    assert path.is_file()
    if sys.platform != "win32":
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"token file mode is {oct(mode)}, expected 0o600"


# ── HTTP transport ───────────────────────────────────────────────────────────


@pytest.fixture
def client(mcp_home):
    from fastapi.testclient import TestClient

    app = build_app(dream_studio_home=mcp_home)
    return TestClient(app), mcp_home


def test_health_endpoint_needs_no_auth(client):
    test_client, _home = client
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_mcp_endpoint_refuses_missing_auth(client):
    test_client, _home = client
    resp = test_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp.status_code == 401


def test_mcp_endpoint_refuses_wrong_token(client):
    test_client, home = client
    auth.ensure_token(dream_studio_home=home)
    resp = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_mcp_endpoint_serves_a_tool_call_with_the_right_token(client):
    test_client, home = client
    token, _ = auth.ensure_token(dream_studio_home=home)
    resp = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_skill_list", "arguments": {}},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["isError"] is False


def test_mcp_endpoint_returns_202_for_a_notification(client):
    test_client, home = client
    token, _ = auth.ensure_token(dream_studio_home=home)
    resp = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202


def test_mcp_endpoint_rejects_malformed_json_body(client):
    test_client, home = client
    token, _ = auth.ensure_token(dream_studio_home=home)
    resp = test_client.post(
        "/mcp",
        content=b"not json",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


# ── no destructive tool sneaks into the curated set ─────────────────────────


def test_no_tool_name_suggests_a_write_or_destructive_action():
    """A cheap standing guard, not a substitute for reading tools.py: a tool named
    like a mutation is exactly the kind of thing this registry is scoped to exclude."""
    forbidden_substrings = (
        "delete",
        "purge",
        "uninstall",
        "record",
        "execute",
        "write",
        "create",
        "close",
        "start",
        "block",
        "unblock",
        "rotate",
    )
    for tool in TOOLS:
        lowered = tool.name.lower()
        hits = [w for w in forbidden_substrings if w in lowered]
        assert not hits, f"{tool.name} looks like a write/destructive tool: {hits}"


# ── the token is never disclosed by `ds mcp serve` ──────────────────────────


def _serve_stderr(mcp_home, monkeypatch, capsys, *, host="127.0.0.1"):
    """Run the `serve` dispatch path with uvicorn.run stubbed out, and return stderr."""
    import argparse

    import uvicorn

    from interfaces.cli.commands import mcp as mcp_cmd

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    args = argparse.Namespace(mcp_command="serve", host=host, port=8765)
    mcp_cmd.dispatch(args, source_root=mcp_home, dream_studio_home=mcp_home)
    return capsys.readouterr().err


def test_serve_never_prints_the_token_on_first_run(mcp_home, monkeypatch, capsys):
    """Round 1 finding: `serve` used to print the freshly-generated token to stderr,
    while the docs and auth.py's own docstring claimed it never does -- a real
    disclosure path, since a long-running server's stderr commonly ends up captured
    in a log (systemd, docker logs, CI)."""
    err = _serve_stderr(mcp_home, monkeypatch, capsys)
    token = auth.read_token(dream_studio_home=mcp_home)
    assert token is not None, "serve should have generated a token"
    assert token not in err
    assert "ds mcp token" in err


def test_serve_never_prints_the_token_on_a_later_run(mcp_home, monkeypatch, capsys):
    """Same property on a run where the token already existed (the common case)."""
    token, _ = auth.ensure_token(dream_studio_home=mcp_home)
    err = _serve_stderr(mcp_home, monkeypatch, capsys)
    assert token not in err
    assert "ds mcp token" in err


def test_serve_still_warns_on_non_localhost_bind(mcp_home, monkeypatch, capsys):
    err = _serve_stderr(mcp_home, monkeypatch, capsys, host="0.0.0.0")
    assert "0.0.0.0" in err
    assert "WARNING" in err
