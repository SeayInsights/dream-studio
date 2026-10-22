"""A pack manifest that does not load must not take MCP tool discovery down with it.

MEASURED. `Tool.schema()` fills the work-order-type enum from the registry, and the registry raises
`PackManifestError` for a manifest that does not load. `tools/list` calls `schema()` for every
tool and nothing caught it, so `POST /mcp` answered a bare HTTP 500 with no diagnostic, for every
client and every tool, where on main `tools/list` could not fail that way. `ds_project_list` and
the rest still worked when called, which made the server look half alive.

Now discovery survives: the tool is advertised with the BUILT-IN types and a description that says
why the pack's are missing, every other tool is listed and callable, and a call that needs the full
set fails in the handler with the loader's message, as a JSON-RPC tool error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders import type_manifest, type_registry
from integrations.mcp import auth
from integrations.mcp.app import build_app
from integrations.mcp.server import handle_message
from integrations.mcp.tools import TOOLS, TOOLS_BY_NAME

ROOT = auth.Identity(name="operator", capabilities=None)

BROKEN = "schema_version: 2\npacks:\n  legal:\n    contributes:\n      gates: [anything]\n"


@pytest.fixture
def broken_manifest(monkeypatch, tmp_path):
    """The registry as a process started against a manifest that does not load."""
    builtins = {
        n: t
        for n, t in type_registry._REGISTRY.items()
        if n in type_registry.builtin_work_order_type_names()
    }
    monkeypatch.setattr(type_registry, "_REGISTRY", builtins)
    monkeypatch.setattr(type_registry, "_STATE", {"loaded": False, "loading": False})
    path = tmp_path / "packs.yaml"
    path.write_text(BROKEN, encoding="utf-8")
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: path)
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    from core.installed_runtime import resolve_installed_runtime_paths

    home = tmp_path / "mcp-home"
    bootstrap_database(resolve_installed_runtime_paths(dream_studio_home=home).sqlite_path)
    return home


def _rpc(method: str, params: dict | None = None, *, home: Path | None = None) -> dict:
    message = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        message["params"] = params
    return handle_message(message, dream_studio_home=home, identity=ROOT)


def test_tools_list_over_http_is_a_200_with_every_tool_when_the_manifest_is_broken(
    broken_manifest, home
):
    from fastapi.testclient import TestClient

    token, _created = auth.ensure_token(dream_studio_home=home)
    # raise_server_exceptions=False: an unhandled error must show up as the 500 a client sees.
    client = TestClient(build_app(dream_studio_home=home), raise_server_exceptions=False)
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    tools = {t["name"]: t for t in response.json()["result"]["tools"]}
    assert set(tools) == {t.name for t in TOOLS}


def test_the_create_tool_advertises_the_built_in_types_and_says_why_the_rest_are_missing(
    broken_manifest,
):
    listed = _rpc("tools/list")["result"]["tools"]
    create = next(t for t in listed if t["name"] == "ds_work_order_create")
    prop = create["inputSchema"]["properties"]["work_order_type"]
    assert tuple(prop["enum"]) == type_registry.builtin_work_order_type_names()
    assert "UNAVAILABLE" in prop["description"]
    assert "(invalid)" in prop["description"], "a one-word reason from a fixed vocabulary"
    assert "unsupported key" not in prop["description"], "no parser or loader text to a client"
    assert str(broken_manifest.parent) not in prop["description"], "no absolute path to a client"
    assert len(prop["description"]) < 500


def test_every_other_tool_is_listed_unchanged_and_callable_under_a_broken_manifest(
    broken_manifest, home
):
    listed = {t["name"]: t for t in _rpc("tools/list")["result"]["tools"]}
    for tool in TOOLS:
        if tool.name == "ds_work_order_create":
            continue
        assert listed[tool.name]["inputSchema"] == tool.input_schema, tool.name
        # Called with no arguments: an answer, never an exception out of handle_message. A tool
        # with required arguments is refused as invalid params; the rest run.
        response = _rpc("tools/call", {"name": tool.name, "arguments": {}}, home=home)
        assert "result" in response or "error" in response, (tool.name, response)
        text = str(response)
        assert "pack manifest" not in text, f"{tool.name} reported the manifest: {text[:300]}"


def test_a_read_tool_still_returns_its_answer_under_a_broken_manifest(broken_manifest, home):
    response = _rpc("tools/call", {"name": "ds_project_list", "arguments": {}}, home=home)
    assert response["result"]["isError"] is False, response


def test_creating_a_work_order_fails_as_a_tool_error_naming_the_manifest(broken_manifest, home):
    response = _rpc(
        "tools/call",
        {
            "name": "ds_work_order_create",
            "arguments": {
                "project_id": "p",
                "milestone_id": "m",
                "title": "A thing",
                "description": "A description long enough to clear the prompt floor for a work order.",
                "work_order_type": "documentation",
            },
        },
        home=home,
    )
    assert "error" not in response, response
    assert response["result"]["isError"] is True
    text = response["result"]["content"][0]["text"]
    assert "PackManifestError" in text and "unsupported key" in text


def test_an_unknown_type_is_still_invalid_params_under_a_broken_manifest(broken_manifest, home):
    response = _rpc(
        "tools/call",
        {
            "name": "ds_work_order_create",
            "arguments": {
                "project_id": "p",
                "milestone_id": "m",
                "title": "A thing",
                "description": "A description long enough to clear the prompt floor for a work order.",
                "work_order_type": "contract_review",
            },
        },
        home=home,
    )
    assert response["error"]["code"] == -32602


def test_the_tool_schema_of_a_healthy_registry_is_unchanged_by_the_fallback():
    prop = TOOLS_BY_NAME["ds_work_order_create"].schema()["properties"]["work_order_type"]
    assert "UNAVAILABLE" not in prop.get("description", "")
    assert tuple(prop["enum"]) == type_registry.work_order_type_names()


@pytest.mark.parametrize(
    ("content", "kind"),
    [
        pytest.param(b"packs: [unclosed", "malformed", id="syntax-error"),
        pytest.param(b"schema_version: 2\n# caf\xe9\n", "unreadable", id="not-utf8"),
        pytest.param(None, "unreadable", id="missing"),
        pytest.param(BROKEN.encode(), "invalid", id="unsupported-key"),
    ],
)
def test_the_client_sees_a_one_word_reason_and_the_log_has_the_detail(
    monkeypatch, tmp_path, caplog, content, kind
):
    """File NAME and a fixed-vocabulary reason go to the client. The absolute path and the
    parser's own text (up to 300 characters of it) used to go too; they stay in the log."""
    import logging

    from integrations.mcp import tools

    builtins = {
        n: t
        for n, t in type_registry._REGISTRY.items()
        if n in type_registry.builtin_work_order_type_names()
    }
    monkeypatch.setattr(type_registry, "_REGISTRY", builtins)
    monkeypatch.setattr(type_registry, "_STATE", {"loaded": False, "loading": False})
    monkeypatch.setattr(tools, "_LOGGED_MANIFEST_FAILURES", set())
    path = tmp_path / "secret-dir" / "packs.yaml"
    path.parent.mkdir()
    if content is not None:
        path.write_bytes(content)
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: path)

    with caplog.at_level(logging.WARNING, logger="dream_studio.mcp.tools"):
        listed = _rpc("tools/list")["result"]["tools"]
    create = next(t for t in listed if t["name"] == "ds_work_order_create")
    shown = create["inputSchema"]["properties"]["work_order_type"]["description"]
    assert f"({kind})" in shown and "packs.yaml" in shown
    assert "secret-dir" not in shown and str(tmp_path) not in shown
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "secret-dir" in logged, "the full detail, path included, is in the server log"


def test_an_untraversable_trust_file_does_not_break_tool_discovery(monkeypatch, tmp_path):
    """`Path.exists` raised PermissionError out of the registry and `tools/list` with it."""
    builtins = {
        n: t
        for n, t in type_registry._REGISTRY.items()
        if n in type_registry.builtin_work_order_type_names()
    }
    monkeypatch.setattr(type_registry, "_REGISTRY", builtins)
    monkeypatch.setattr(type_registry, "_STATE", {"loaded": False, "loading": False})
    manifest = tmp_path / "packs.yaml"
    manifest.write_text(
        "schema_version: 2\npacks:\n  legal:\n    contributes:\n      work_order_types:\n"
        "        - {name: contract_review, artifact_class: document, description: A contract,"
        " ui_bearing: false, exempt_from_verification: true}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: manifest)
    real_exists = Path.exists

    def refuses(self):
        if self.name == "pack-trust.yaml":
            raise PermissionError("access denied")
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", refuses)
    listed = _rpc("tools/list")["result"]["tools"]
    create = next(t for t in listed if t["name"] == "ds_work_order_create")
    assert "(unreadable)" in create["inputSchema"]["properties"]["work_order_type"]["description"]
