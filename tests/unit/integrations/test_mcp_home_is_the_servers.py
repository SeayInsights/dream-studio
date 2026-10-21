"""The MCP server's home is the only home -- a client cannot choose which authority a call uses.

Issue #903. `tools/call` used to build `{"dream_studio_home": <server's home>, **arguments}`,
so an argument the client sent with that name replaced the server's own binding and every
handler took it as a real parameter. A read-only client could point any read tool at another
Dream Studio home on the server's disk; a client holding a mutating capability could write to
another authority. The capability model says what a client may do, never which authority it
does it against.

Two homes, A (the one the server was started with) and B (any other on the same disk), each
holding rows the other lacks, so a call that reached B is visible in what it returns and in B's
database digest. Everything goes through `handle_message` / the real HTTP app, the same entry
the network client uses.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from integrations.mcp import auth
from integrations.mcp.server import handle_message
from integrations.mcp.tools import TOOLS, TOOLS_BY_NAME

NOW = "2026-01-01T00:00:00+00:00"
INVALID_PARAMS = -32602

READ_ONLY = auth.Identity(name="read-only-gateway", capabilities=frozenset())
ROOT = auth.Identity(name="operator", capabilities=None)
TASK_MUTATOR = auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:task_mutate"}))


def _db_path(home: Path) -> Path:
    from core.installed_runtime import resolve_installed_runtime_paths

    return resolve_installed_runtime_paths(dream_studio_home=home).sqlite_path


def _make_home(root: Path, tag: str) -> Path:
    """A bootstrapped authority carrying one project, work order and task, all named for `tag`."""
    from core.config.sqlite_bootstrap import bootstrap_database

    home = root / f"home_{tag}"
    db = _db_path(home)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, "
        "project_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"proj-{tag}", f"PROJECT-OF-{tag}", "p", "active", "/tmp", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, "
        "title, description, status, work_order_type, created_at, updated_at) "
        "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
        (
            f"wo-{tag}",
            f"proj-{tag}",
            f"TITLE-OF-{tag}",
            "d",
            "in_progress",
            "infrastructure",
            NOW,
            NOW,
        ),
    )
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, "
        "description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"task-{tag}", f"wo-{tag}", f"proj-{tag}", f"TASK-OF-{tag}", "d", "created", NOW, NOW),
    )
    conn.commit()
    conn.close()
    return home


def _digest(home: Path) -> str:
    """Every row of every table, so any write to the authority changes it."""
    conn = sqlite3.connect(str(_db_path(home)))
    try:
        return hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest()
    finally:
        conn.close()


@pytest.fixture
def homes(tmp_path):
    """(A, B): A is the home the server is started with, B is any other on the same disk."""
    return _make_home(tmp_path, "A"), _make_home(tmp_path, "B")


def _call(
    name: str,
    arguments: Any,
    *,
    home: Path,
    identity: auth.Identity | None,
) -> dict[str, Any]:
    return handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        dream_studio_home=home,
        identity=identity,
    )


def _text(resp: dict[str, Any]) -> str:
    return json.dumps(resp, default=str)


def _minimal_arguments(tool) -> dict[str, Any]:
    """The smallest arguments the advertised schema accepts: every required property, typed.

    Ids name nothing ("wo-nothing") so a call that is wrongly let through changes no row of
    either home -- the digests below are what prove it, not this."""
    schema = tool.input_schema
    out: dict[str, Any] = {}
    for key in schema.get("required", []):
        spec = schema["properties"][key]
        kind = spec["type"]
        if "enum" in spec:
            out[key] = spec["enum"][0]
        elif kind == "string":
            out[key] = "wo-nothing"
        elif kind == "integer":
            out[key] = 0
        elif kind == "boolean":
            out[key] = False
        elif kind == "array":
            out[key] = []
        else:
            raise AssertionError(f"{tool.name}.{key}: no minimal value for type {kind!r}")
    return out


# ── the reproduction: B's state was reachable through the argument ────────────


READ_CALLS_AGAINST_B = [
    ("ds_project_list", {"status_filter": "all"}),
    ("ds_project_status", {"project_id": "proj-B"}),
    ("ds_work_order_list", {}),
    ("ds_work_order_tasks", {"work_order_id": "wo-B"}),
    ("ds_gate_check", {"work_order_id": "wo-B"}),
    ("ds_review_status", {"work_order_id": "wo-B"}),
    ("ds_review_findings", {"work_order_id": "wo-B"}),
]


@pytest.mark.parametrize(
    ("tool", "arguments"), READ_CALLS_AGAINST_B, ids=[c[0] for c in READ_CALLS_AGAINST_B]
)
def test_a_read_only_client_cannot_aim_a_read_tool_at_another_home(homes, tool, arguments):
    """B holds the row; A does not. With dream_studio_home=B the call used to answer from B."""
    home_a, home_b = homes
    resp = _call(
        tool, {**arguments, "dream_studio_home": str(home_b)}, home=home_a, identity=READ_ONLY
    )
    assert (
        resp.get("error", {}).get("code") == INVALID_PARAMS
    ), f"{tool} accepted a client-supplied dream_studio_home and answered: {_text(resp)[:400]}"
    assert "PROJECT-OF-B" not in _text(resp) and "TASK-OF-B" not in _text(resp)


def test_without_the_argument_the_server_answers_from_its_own_home(homes):
    """The control: A is distinguishable, and a call that names no home reads A."""
    home_a, _ = homes
    resp = _call("ds_project_list", {"status_filter": "all"}, home=home_a, identity=READ_ONLY)
    text = resp["result"]["content"][0]["text"]
    assert "PROJECT-OF-A" in text and "PROJECT-OF-B" not in text


def test_a_mutating_tool_cannot_write_to_another_home(homes):
    """A client holding work_order:task_mutate used to mark a task done in a home it was
    never connected to: the server's A has no such work order, B does."""
    home_a, home_b = homes
    before = (_digest(home_a), _digest(home_b))
    for tool in ("ds_work_order_task_start", "ds_work_order_task_done"):
        resp = _call(
            tool,
            {"work_order_id": "wo-B", "task_id": "task-B", "dream_studio_home": str(home_b)},
            home=home_a,
            identity=TASK_MUTATOR,
        )
        assert resp.get("error", {}).get("code") == INVALID_PARAMS, _text(resp)[:400]
    assert (_digest(home_a), _digest(home_b)) == before, "a refused call changed an authority"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
@pytest.mark.parametrize("identity", [READ_ONLY, ROOT], ids=["read_only", "root"])
def test_every_tool_refuses_a_client_supplied_home_and_changes_nothing(homes, tool, identity):
    """Every tool, for a client without the capability (refused for that reason before the
    arguments are even looked at, or -- for a read tool -- as invalid params) and for the root
    token, which satisfies every capability so only the argument check can stop it."""
    home_a, home_b = homes
    before = (_digest(home_a), _digest(home_b))
    resp = _call(
        tool.name,
        {**_minimal_arguments(tool), "dream_studio_home": str(home_b)},
        home=home_a,
        identity=identity,
    )
    assert "error" in resp, f"{tool.name} did not refuse dream_studio_home: {_text(resp)[:400]}"
    gated_for_identity = tool.required_capability is not None and identity.capabilities is not None
    expected = -32001 if gated_for_identity else INVALID_PARAMS
    assert resp["error"]["code"] == expected, _text(resp)[:400]
    if expected == INVALID_PARAMS:
        assert "dream_studio_home" in resp["error"]["message"]
    assert (_digest(home_a), _digest(home_b)) == before


def test_params_outside_arguments_cannot_redirect_the_home_either(homes):
    """`params.dream_studio_home` (next to name/arguments, not inside it) is never read."""
    home_a, home_b = homes
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_project_list",
                "arguments": {"status_filter": "all"},
                "dream_studio_home": str(home_b),
                "_meta": {"dream_studio_home": str(home_b)},
            },
        },
        dream_studio_home=home_a,
        identity=READ_ONLY,
    )
    text = resp["result"]["content"][0]["text"]
    assert "PROJECT-OF-A" in text and "PROJECT-OF-B" not in text


def test_over_http_a_read_only_client_cannot_aim_a_read_tool_at_another_home(homes):
    from fastapi.testclient import TestClient

    from integrations.mcp.app import build_app

    home_a, home_b = homes
    token = auth.add_client("gateway", capabilities=[], dream_studio_home=home_a)
    client = TestClient(build_app(dream_studio_home=home_a))
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "ds_project_list",
            "arguments": {"status_filter": "all", "dream_studio_home": str(home_b)},
        },
    }
    resp = client.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == INVALID_PARAMS
    assert "PROJECT-OF-B" not in resp.text
    body["params"]["arguments"] = {"status_filter": "all"}
    ok = client.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"})
    assert "PROJECT-OF-A" in ok.json()["result"]["content"][0]["text"]


# ── strict validation: nothing outside the advertised schema reaches a handler ──


REJECTED = [
    # (id, tool, arguments, a fragment the message must carry)
    ("unknown_argument", "ds_work_order_tasks", {"work_order_id": "wo-A", "extra": 1}, "extra"),
    ("source_root", "ds_project_state", {"source_root": "C:/elsewhere"}, "source_root"),
    ("db_path", "ds_work_order_tasks", {"work_order_id": "wo-A", "db_path": "x.db"}, "db_path"),
    (
        "planning_root",
        "ds_gate_check",
        {"work_order_id": "wo-A", "planning_root": "x"},
        "planning_root",
    ),
    ("run_checks", "ds_gate_check", {"work_order_id": "wo-A", "run_checks": True}, "run_checks"),
    (
        "read_planning_dir",
        "ds_gate_check",
        {"work_order_id": "wo-A", "read_planning_dir": True},
        "read_planning_dir",
    ),
    ("force_on_close", "ds_work_order_close", {"work_order_id": "wo-A", "force": True}, "force"),
    (
        "skip_verify",
        "ds_work_order_close",
        {"work_order_id": "wo-A", "skip_verify": True},
        "skip_verify",
    ),
    (
        "identity_smuggle",
        "ds_work_order_task_done",
        {"work_order_id": "wo-A", "task_id": "task-A", "identity": {"name": "x"}},
        "identity",
    ),
    (
        "actor_smuggle",
        "ds_work_order_task_done",
        {"work_order_id": "wo-A", "task_id": "task-A", "actor": "x"},
        "actor",
    ),
    ("ctx_smuggle", "ds_project_state", {"ctx": 1}, "ctx"),
    ("wrong_type_string", "ds_project_status", {"project_id": 5}, "project_id"),
    ("wrong_type_integer_string", "ds_memory_query", {"limit": "10"}, "limit"),
    ("wrong_type_integer_bool", "ds_memory_query", {"limit": True}, "limit"),
    ("wrong_type_integer_float", "ds_memory_query", {"limit": 1.5}, "limit"),
    (
        "wrong_type_integer_whole_float",
        "ds_milestone_create",
        {"project_id": "proj-A", "title": "t", "description": "d", "order_index": 1.0},
        "order_index",
    ),
    ("wrong_type_array", "ds_memory_query", {"tags": "a"}, "tags"),
    ("wrong_type_array_item", "ds_memory_query", {"tags": [1]}, "tags"),
    (
        "wrong_type_boolean",
        "ds_review_dispatch",
        {"work_order_id": "wo-A", "force_new_round": "yes"},
        "force_new_round",
    ),
    ("missing_required", "ds_project_status", {}, "project_id"),
    ("missing_required_mutating", "ds_work_order_task_done", {"work_order_id": "wo-A"}, "task_id"),
    ("not_in_enum", "ds_work_order_advance", {"work_order_id": "wo-A", "to": "closed"}, "to"),
    (
        "nested_extra_property",
        "ds_review_record",
        {
            "work_order_id": "wo-A",
            "reviewer": "r",
            "credential": "c",
            "answers": [{"lane": "l", "verdict": "pass", "dream_studio_home": "x"}],
        },
        "dream_studio_home",
    ),
    (
        "nested_extra_property_two_levels_down",
        "ds_review_record",
        {
            "work_order_id": "wo-A",
            "reviewer": "r",
            "credential": "c",
            "answers": [
                {
                    "lane": "l",
                    "verdict": "pass",
                    "reproduction": {"command": "c", "exit_code": 0, "cwd": "/"},
                }
            ],
        },
        "cwd",
    ),
    (
        "nested_wrong_type",
        "ds_review_record",
        {
            "work_order_id": "wo-A",
            "reviewer": "r",
            "credential": "c",
            "answers": [
                {"lane": "l", "verdict": "pass", "reproduction": {"command": "c", "exit_code": "0"}}
            ],
        },
        "exit_code",
    ),
    (
        "nested_missing_required",
        "ds_review_record",
        {"work_order_id": "wo-A", "reviewer": "r", "credential": "c", "answers": [{"lane": "l"}]},
        "verdict",
    ),
    (
        "nested_bad_enum",
        "ds_review_record",
        {
            "work_order_id": "wo-A",
            "reviewer": "r",
            "credential": "c",
            "answers": [{"lane": "l", "verdict": "maybe"}],
        },
        "verdict",
    ),
    ("arguments_is_a_list", "ds_project_state", [], "arguments"),
    ("arguments_is_a_list_with_items", "ds_project_state", ["dream_studio_home"], "arguments"),
    ("arguments_is_a_string", "ds_project_state", "dream_studio_home", "arguments"),
    ("arguments_is_a_number", "ds_project_state", 0, "arguments"),
    ("arguments_is_false", "ds_project_state", False, "arguments"),
]


@pytest.mark.parametrize(
    ("case", "tool", "arguments", "fragment"), REJECTED, ids=[r[0] for r in REJECTED]
)
def test_a_call_outside_the_advertised_schema_is_invalid_params_and_changes_nothing(
    homes, case, tool, arguments, fragment
):
    home_a, home_b = homes
    before = (_digest(home_a), _digest(home_b))
    resp = _call(tool, arguments, home=home_a, identity=ROOT)
    assert resp.get("error", {}).get("code") == INVALID_PARAMS, _text(resp)[:400]
    assert fragment in resp["error"]["message"], resp["error"]["message"]
    assert (_digest(home_a), _digest(home_b)) == before


def test_null_or_absent_arguments_mean_no_arguments(homes):
    home_a, _ = homes
    for arguments in (None,):
        resp = _call("ds_project_state", arguments, home=home_a, identity=READ_ONLY)
        assert resp["result"]["isError"] is False
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ds_project_state"}},
        dream_studio_home=home_a,
        identity=READ_ONLY,
    )
    assert resp["result"]["isError"] is False


def test_the_error_names_every_problem_it_found_and_never_echoes_a_secret(homes):
    home_a, _ = homes
    resp = _call(
        "ds_review_record",
        {
            "work_order_id": 1,
            "reviewer": "r",
            "credential": "TOP-SECRET-CREDENTIAL-VALUE",
            "answers": [],
            "dream_studio_home": "x",
        },
        home=home_a,
        identity=ROOT,
    )
    message = resp["error"]["message"]
    assert "work_order_id" in message and "dream_studio_home" in message
    assert "TOP-SECRET-CREDENTIAL-VALUE" not in message


def test_a_valid_call_is_unchanged_for_the_root_token_and_a_capable_client(homes):
    """The existing behaviour the fix must keep: read-only reads, a held capability writes,
    a missing capability is -32001, and the root token satisfies every capability."""
    home_a, home_b = homes
    assert (
        _call("ds_work_order_tasks", {"work_order_id": "wo-A"}, home=home_a, identity=READ_ONLY)[
            "result"
        ]["isError"]
        is False
    )
    resp = _call(
        "ds_work_order_task_start",
        {"work_order_id": "wo-A", "task_id": "task-A"},
        home=home_a,
        identity=TASK_MUTATOR,
    )
    assert json.loads(resp["result"]["content"][0]["text"])["status"] == "in_progress"
    denied = _call(
        "ds_work_order_task_done",
        {"work_order_id": "wo-A", "task_id": "task-A"},
        home=home_a,
        identity=READ_ONLY,
    )
    assert denied["error"]["code"] == -32001
    root = _call(
        "ds_work_order_task_done",
        {"work_order_id": "wo-A", "task_id": "task-A"},
        home=home_a,
        identity=ROOT,
    )
    assert root["result"]["isError"] is False


def test_a_denied_client_is_refused_before_its_arguments_are_examined(homes):
    """Capability first: a client without it learns nothing about the schema from the error,
    exactly as before."""
    home_a, _ = homes
    resp = _call("ds_work_order_task_done", {"nonsense": 1}, home=home_a, identity=READ_ONLY)
    assert resp["error"]["code"] == -32001


def test_a_handler_is_never_reached_with_an_argument_the_schema_does_not_name(homes, monkeypatch):
    """The seam itself, independent of any real tool: a spy handler records what it receives."""
    from integrations.mcp import tools as tools_mod

    seen: list[tuple[Any, dict[str, Any]]] = []

    def spy(ctx, /, *, a: str):
        seen.append((ctx, {"a": a}))
        return {"ok": True}

    fake = tools_mod.Tool(
        name="ds_spy",
        description="spy",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
            "additionalProperties": False,
        },
        handler=spy,
    )
    monkeypatch.setitem(tools_mod.TOOLS_BY_NAME, "ds_spy", fake)
    home_a, home_b = homes
    for bad in (
        {"a": "x", "dream_studio_home": str(home_b)},
        {"a": "x", "ctx": 1},
        {"a": "x", "identity": 1},
        {"a": 1},
        {},
    ):
        assert _call("ds_spy", bad, home=home_a, identity=ROOT)["error"]["code"] == INVALID_PARAMS
    assert seen == []
    resp = _call("ds_spy", {"a": "x"}, home=home_a, identity=ROOT)
    assert resp["result"]["isError"] is False
    ((ctx, _),) = seen
    assert ctx.dream_studio_home == home_a and ctx.identity is ROOT


def test_every_registered_tool_is_in_the_registry_these_tests_iterate():
    assert {t.name for t in TOOLS} == set(TOOLS_BY_NAME)
