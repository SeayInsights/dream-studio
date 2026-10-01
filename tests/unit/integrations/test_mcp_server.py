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
    layer -- a network client cannot see a Python traceback.

    The root identity is passed on every call so a capability-gated tool's own
    permission check (a JSON-RPC-level `error`, not a tool result -- see
    test_capability_gated_tool_denies_an_identity_without_it) never masks what this
    test actually checks: the HANDLER's own behavior once it's reached.
    """
    root = auth.Identity(name="operator", capabilities=None)
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
            },
            identity=root,
        )
        assert "result" in resp, f"{tool.name} raised out of handle_message: {resp}"
        if required:
            assert resp["result"]["isError"] is True


# ── review tools distinguish "no such work order" from "not yet reviewed" ──


@pytest.fixture
def bootstrapped_home(tmp_path):
    """A home with a real SQLite authority carrying one real, undispatched work order."""
    import sqlite3

    from core.config.sqlite_bootstrap import bootstrap_database
    from core.installed_runtime import resolve_installed_runtime_paths

    home = tmp_path / "ds_home"
    db_path = resolve_installed_runtime_paths(dream_studio_home=home).sqlite_path
    bootstrap_database(db_path)
    now = "2026-01-01T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, "
        "project_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("proj-1", "p", "p", "active", "/tmp", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, "
        "title, description, status, work_order_type, created_at, updated_at) "
        "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
        ("wo-real", "proj-1", "t", "d", "in_progress", "infrastructure", now, now),
    )
    conn.commit()
    conn.close()
    return home


def test_review_status_rejects_a_work_order_id_that_names_nothing(bootstrapped_home):
    """Round 2 finding: review_status()/open_findings() return the SAME shape for a
    typo'd id as for a real, not-yet-dispatched one -- a caller can't tell "this id is
    wrong" from "this id is real but unreviewed". `ds review --status` already makes
    this distinction (interfaces/cli/commands/review.py); the MCP tool must too."""
    with pytest.raises(ValueError, match="no work order"):
        TOOLS_BY_NAME["ds_review_status"].handler(
            work_order_id="wo-does-not-exist", dream_studio_home=bootstrapped_home
        )


def test_review_status_succeeds_for_a_real_undispatched_work_order(bootstrapped_home):
    result = TOOLS_BY_NAME["ds_review_status"].handler(
        work_order_id="wo-real", dream_studio_home=bootstrapped_home
    )
    assert result["blocking"] is True
    assert "no review has been dispatched" in " ".join(result["reasons"])


def test_review_findings_rejects_a_work_order_id_that_names_nothing(bootstrapped_home):
    with pytest.raises(ValueError, match="no work order"):
        TOOLS_BY_NAME["ds_review_findings"].handler(
            work_order_id="wo-does-not-exist", dream_studio_home=bootstrapped_home
        )


def test_review_findings_succeeds_for_a_real_work_order(bootstrapped_home):
    result = TOOLS_BY_NAME["ds_review_findings"].handler(
        work_order_id="wo-real", dream_studio_home=bootstrapped_home
    )
    assert result == {"open_findings": []}


def test_tools_call_surfaces_the_unknown_work_order_as_isError(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_status",
                "arguments": {"work_order_id": "wo-does-not-exist"},
            },
        },
        dream_studio_home=bootstrapped_home,
    )
    assert resp["result"]["isError"] is True
    assert "no work order" in resp["result"]["content"][0]["text"]


# ── work-order task mutations (capability-gated) ────────────────────────────


@pytest.fixture
def bootstrapped_home_with_task(bootstrapped_home):
    """bootstrapped_home's work order, plus one real task on it."""
    import sqlite3

    from core.installed_runtime import resolve_installed_runtime_paths

    db_path = resolve_installed_runtime_paths(dream_studio_home=bootstrapped_home).sqlite_path
    now = "2026-01-01T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, "
        "description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("task-real", "wo-real", "proj-1", "t", "d", "created", now, now),
    )
    conn.commit()
    conn.close()
    return bootstrapped_home


def _mcp_client_identity(name="fulcrum", capabilities=("work_order:task_mutate",)):
    return auth.Identity(name=name, capabilities=frozenset(capabilities))


@pytest.fixture
def dispatched(bootstrapped_home):
    """bootstrapped_home's work order, with a real dispatch round recorded against
    this repo's own registry -- review-finding-integrity really does own
    evidence-referee, so record_dispatch's ownership check passes for real, not via a
    fake ownership map. Returns (home, reviewer, credential)."""
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import record_dispatch

    db_path = resolve_installed_runtime_paths(dream_studio_home=bootstrapped_home).sqlite_path
    doc = record_dispatch(
        "wo-real",
        sha="a" * 40,
        image="ds-review:fake",
        change_set=["x.py"],
        assignments=[
            {
                "reviewer": "review-finding-integrity",
                "seat": "Finding integrity",
                "lanes": ["evidence-referee"],
            }
        ],
        db_path=db_path,
    )
    return (
        bootstrapped_home,
        "review-finding-integrity",
        doc["credentials"]["review-finding-integrity"],
    )


def test_task_start_denies_an_identity_without_the_capability(bootstrapped_home_with_task):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_task_start",
                "arguments": {"work_order_id": "wo-real", "task_id": "task-real"},
            },
        },
        dream_studio_home=bootstrapped_home_with_task,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_task_start_succeeds_for_an_identity_with_the_capability(bootstrapped_home_with_task):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_task_start",
                "arguments": {"work_order_id": "wo-real", "task_id": "task-real"},
            },
        },
        dream_studio_home=bootstrapped_home_with_task,
        identity=_mcp_client_identity(),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["status"] == "in_progress"


def test_task_start_attributes_the_emitted_event_to_the_calling_client(
    bootstrapped_home_with_task, monkeypatch
):
    captured = []
    import spool.writer as _writer

    monkeypatch.setattr(
        _writer, "write_event", lambda envelope, root=None: captured.append(envelope)
    )
    handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_task_start",
                "arguments": {"work_order_id": "wo-real", "task_id": "task-real"},
            },
        },
        dream_studio_home=bootstrapped_home_with_task,
        identity=_mcp_client_identity(name="fulcrum"),
    )
    assert len(captured) == 1
    assert captured[0]["trace"]["mcp_client"] == "fulcrum"


def test_task_done_succeeds_for_an_identity_with_the_capability(bootstrapped_home_with_task):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_task_done",
                "arguments": {"work_order_id": "wo-real", "task_id": "task-real"},
            },
        },
        dream_studio_home=bootstrapped_home_with_task,
        identity=_mcp_client_identity(),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True


def test_task_done_denies_an_identity_without_the_capability(bootstrapped_home_with_task):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_task_done",
                "arguments": {"work_order_id": "wo-real", "task_id": "task-real"},
            },
        },
        dream_studio_home=bootstrapped_home_with_task,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_task_mutations_work_for_the_root_identity_too(bootstrapped_home_with_task):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_task_start",
                "arguments": {"work_order_id": "wo-real", "task_id": "task-real"},
            },
        },
        dream_studio_home=bootstrapped_home_with_task,
        identity=auth.Identity(name="operator", capabilities=None),
    )
    assert resp["result"]["isError"] is False


# ── ds_review_dispatch (capability-gated) ───────────────────────────────────
#
# dispatch_review_round itself (convene + build the lane image + record) is exercised
# for real, Docker faked, in tests/unit/test_review_answers.py -- these tests are
# about the MCP wiring around it: the capability gate, and the response carrying
# dispatched_by, which is mocked here rather than re-proving the orchestration.


def test_review_dispatch_denies_an_identity_without_the_capability(bootstrapped_home, monkeypatch):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_dispatch",
                "arguments": {"work_order_id": "wo-real"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_review_dispatch_succeeds_and_carries_dispatched_by(bootstrapped_home, monkeypatch):
    import core.work_orders.review_answers as ra_mod

    fake_doc = {"stored": True, "round": 1, "credentials": {"review-finding-integrity": "abc123"}}
    monkeypatch.setattr(ra_mod, "dispatch_review_round", lambda *a, **k: dict(fake_doc))

    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_dispatch",
                "arguments": {"work_order_id": "wo-real"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"review:dispatch"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["dispatched_by"] == "fulcrum"
    assert payload["credentials"] == fake_doc["credentials"]


def test_review_dispatch_threads_force_new_round_through(bootstrapped_home, monkeypatch):
    """A kwarg-spy, not an outcome check -- the idempotency/force_new_round behavior
    itself is proven in test_review_answers.py; this proves the MCP tool actually
    passes the argument through rather than silently dropping it."""
    import core.work_orders.review_answers as ra_mod

    captured_kwargs = {}

    def _fake_dispatch(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {"stored": True, "round": 2}

    monkeypatch.setattr(ra_mod, "dispatch_review_round", _fake_dispatch)

    handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_dispatch",
                "arguments": {"work_order_id": "wo-real", "force_new_round": True},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"review:dispatch"})),
    )
    assert captured_kwargs["force_new_round"] is True


def test_review_dispatch_force_new_round_defaults_false(bootstrapped_home, monkeypatch):
    import core.work_orders.review_answers as ra_mod

    captured_kwargs = {}

    def _fake_dispatch(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {"stored": True, "round": 1}

    monkeypatch.setattr(ra_mod, "dispatch_review_round", _fake_dispatch)

    handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_review_dispatch", "arguments": {"work_order_id": "wo-real"}},
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"review:dispatch"})),
    )
    assert captured_kwargs["force_new_round"] is False


def test_review_dispatch_works_for_the_root_identity_too(bootstrapped_home, monkeypatch):
    import core.work_orders.review_answers as ra_mod

    monkeypatch.setattr(
        ra_mod, "dispatch_review_round", lambda *a, **k: {"stored": True, "round": 1}
    )
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_dispatch",
                "arguments": {"work_order_id": "wo-real"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="operator", capabilities=None),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["dispatched_by"] == "operator"


# ── ds_review_run (capability-gated) ────────────────────────────────────────
#
# run_review_command itself is exercised for real (Docker faked) in
# test_review_answers.py -- these are about the MCP wiring: the capability gate
# (review:run, deliberately separate from review:dispatch/review:record) and the
# response carrying run_by.


def test_review_run_denies_an_identity_without_the_capability(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_run",
                "arguments": {"work_order_id": "wo-real", "command": "echo hi"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="dispatcher-only", capabilities=frozenset({"review:dispatch"})),
    )
    assert resp["error"]["code"] == -32001


def test_review_run_succeeds_and_carries_run_by(bootstrapped_home, monkeypatch):
    import core.work_orders.review_answers as ra_mod

    fake_result = {"command": "echo hi", "exit_code": 0, "timed_out": False, "output_tail": "hi\n"}
    monkeypatch.setattr(ra_mod, "run_review_command", lambda *a, **k: dict(fake_result))

    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_run",
                "arguments": {"work_order_id": "wo-real", "command": "echo hi"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"review:run"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["run_by"] == "fulcrum"
    assert payload["exit_code"] == 0


# ── ds_review_record (capability-gated) ─────────────────────────────────────
#
# record_answers is Dream Studio's own long-established recording door, fully
# exercised for real in test_review_answers.py -- these are about the MCP wiring:
# the capability gate (review:record) and the response carrying recorded_by. The
# credential check itself is record_answers' own -- proven here by one negative
# case (wrong credential refused) and one degenerate positive case (an empty
# answers list, so no Docker reproduction is needed to prove the door was reached).


def test_review_record_denies_an_identity_without_the_capability(dispatched):
    home, reviewer, credential = dispatched
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_record",
                "arguments": {
                    "work_order_id": "wo-real",
                    "reviewer": reviewer,
                    "credential": credential,
                    "answers": [],
                },
            },
        },
        dream_studio_home=home,
        identity=auth.Identity(name="runner-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_review_record_refuses_the_wrong_credential(dispatched):
    home, reviewer, _credential = dispatched
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_record",
                "arguments": {
                    "work_order_id": "wo-real",
                    "reviewer": reviewer,
                    "credential": "not-the-real-one",
                    "answers": [],
                },
            },
        },
        dream_studio_home=home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"review:record"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert "does not carry the credential" in payload["refused_submission"]


def test_review_record_reaches_the_door_and_carries_recorded_by(dispatched, monkeypatch):
    """Docker's availability is faked here -- record_answers checks it unconditionally,
    even for an empty answers list with nothing to verify, and this test's point is
    proving the credential passed, not this machine's own Docker state."""
    from core.gates import lane_sandbox

    monkeypatch.setattr(lane_sandbox, "docker_available", lambda: (True, "ok"))

    home, reviewer, credential = dispatched
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_review_record",
                "arguments": {
                    "work_order_id": "wo-real",
                    "reviewer": reviewer,
                    "credential": credential,
                    "answers": [],
                },
            },
        },
        dream_studio_home=home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"review:record"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    # The credential passed -- an empty answers list reaches the door and completes
    # (nothing to verify), rather than being refused for the credential.
    assert "refused_submission" not in payload
    assert payload["recorded_by"] == "fulcrum"


# ── ds_project_create (capability-gated) ────────────────────────────────────


def test_project_create_denies_an_identity_without_the_capability(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_project_create", "arguments": {"name": "New Project"}},
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_project_create_succeeds_and_carries_registered_by(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_project_create",
                "arguments": {"name": "New Project", "description": "d"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"project:create"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["name"] == "New Project"
    assert payload["registered_by"] == "fulcrum"


def test_milestone_create_denies_an_identity_without_the_capability(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_milestone_create",
                "arguments": {"project_id": "proj-1", "title": "m", "description": "x" * 60},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_milestone_create_succeeds_and_attributes_the_emitted_event(bootstrapped_home, monkeypatch):
    captured = []
    import spool.writer as _writer

    monkeypatch.setattr(
        _writer, "write_event", lambda envelope, root=None: captured.append(envelope)
    )
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_milestone_create",
                "arguments": {
                    "project_id": "proj-1",
                    "title": "A milestone",
                    "description": "x" * 60,
                },
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"milestone:create"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["project_id"] == "proj-1"
    created_events = [e for e in captured if e["event_type"] == "milestone.created"]
    assert len(created_events) == 1
    assert created_events[0]["trace"]["mcp_client"] == "fulcrum"


def test_milestone_create_refuses_an_unknown_project(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_milestone_create",
                "arguments": {
                    "project_id": "proj-does-not-exist",
                    "title": "m",
                    "description": "x" * 60,
                },
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"milestone:create"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "Project not found" in payload["error"]


# ── ds_project_create: idempotency ───────────────────────────────────────────


def test_project_create_is_idempotent_on_the_same_project_path(bootstrapped_home, tmp_path):
    args = {"name": "New Project", "project_path": str(tmp_path)}
    identity = auth.Identity(name="fulcrum", capabilities=frozenset({"project:create"}))
    first = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_project_create", "arguments": args},
        },
        dream_studio_home=bootstrapped_home,
        identity=identity,
    )
    second = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "ds_project_create", "arguments": args},
        },
        dream_studio_home=bootstrapped_home,
        identity=identity,
    )
    first_payload = json.loads(first["result"]["content"][0]["text"])
    second_payload = json.loads(second["result"]["content"][0]["text"])
    assert second_payload["project_id"] == first_payload["project_id"]
    assert second_payload.get("idempotent") is True


# ── ds_work_order_start (capability-gated) ──────────────────────────────────
#
# start_work_order's own behavior (brief checks, phase transitions, sequence/
# structure guards) is exercised for real in tests/unit/test_work_order_start.py --
# these are about the MCP wiring around it.


def test_work_order_start_denies_an_identity_without_the_capability(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_work_order_start", "arguments": {"work_order_id": "wo-real"}},
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_work_order_start_succeeds_on_a_resume_and_attributes_the_emitted_event(
    bootstrapped_home, monkeypatch
):
    """wo-real is already in_progress -- start_work_order treats this as a resume
    (status does not move, the rest of the sequence still runs), the cheapest real
    end-to-end path with no extra fixture for a brief-less UI work order."""
    captured = []
    import spool.writer as _writer

    monkeypatch.setattr(
        _writer, "write_event", lambda envelope, root=None: captured.append(envelope)
    )
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_work_order_start", "arguments": {"work_order_id": "wo-real"}},
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:start"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True
    started_events = [e for e in captured if e["event_type"] == "work_order.started"]
    assert len(started_events) == 1
    assert started_events[0]["trace"]["mcp_client"] == "fulcrum"


def test_work_order_start_threads_its_arguments_through(bootstrapped_home, monkeypatch):
    """A kwarg-spy, not an outcome check -- proves the MCP tool actually forwards
    accept_no_brief/in_sequence/accept_structure rather than silently dropping them."""
    import core.work_orders.start as start_mod

    captured_kwargs = {}

    def _fake_start(**kwargs):
        captured_kwargs.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(start_mod, "start_work_order", _fake_start)

    handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_start",
                "arguments": {
                    "work_order_id": "wo-real",
                    "accept_no_brief": True,
                    "in_sequence": True,
                    "accept_structure": "fewer than 2 tasks, reviewed and accepted",
                },
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:start"})),
    )
    assert captured_kwargs["accept_no_brief"] is True
    assert captured_kwargs["in_sequence"] is True
    assert captured_kwargs["accept_structure"] == "fewer than 2 tasks, reviewed and accepted"
    assert captured_kwargs["actor"] == "fulcrum"


# ── ds_work_order_create (capability-gated) ─────────────────────────────────


@pytest.fixture
def bootstrapped_home_with_milestone(bootstrapped_home):
    import sqlite3

    from core.installed_runtime import resolve_installed_runtime_paths

    db_path = resolve_installed_runtime_paths(dream_studio_home=bootstrapped_home).sqlite_path
    now = "2026-01-01T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_milestones (milestone_id, project_id, title, description, "
        "status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ms-real", "proj-1", "m", "d", "pending", now, now),
    )
    conn.commit()
    conn.close()
    return bootstrapped_home


def test_work_order_create_denies_an_identity_without_the_capability(
    bootstrapped_home_with_milestone,
):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_create",
                "arguments": {
                    "project_id": "proj-1",
                    "milestone_id": "ms-real",
                    "title": "t",
                    "description": "x" * 70,
                },
            },
        },
        dream_studio_home=bootstrapped_home_with_milestone,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_work_order_create_succeeds_and_attributes_the_emitted_event(
    bootstrapped_home_with_milestone, monkeypatch
):
    captured = []
    import spool.writer as _writer

    monkeypatch.setattr(
        _writer, "write_event", lambda envelope, root=None: captured.append(envelope)
    )
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_create",
                "arguments": {
                    "project_id": "proj-1",
                    "milestone_id": "ms-real",
                    "title": "A new work order",
                    "description": "x" * 70,
                },
            },
        },
        dream_studio_home=bootstrapped_home_with_milestone,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:create"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["status"] == "created"
    created_events = [e for e in captured if e["event_type"] == "work_order.created"]
    assert len(created_events) == 1
    assert created_events[0]["trace"]["mcp_client"] == "fulcrum"


def test_work_order_create_refuses_an_unknown_milestone(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_create",
                "arguments": {
                    "project_id": "proj-1",
                    "milestone_id": "ms-does-not-exist",
                    "title": "t",
                    "description": "x" * 70,
                },
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:create"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "Milestone not found" in payload["error"]


# ── ds_work_order_add_task (capability-gated) ───────────────────────────────


def test_work_order_add_task_denies_an_identity_without_the_capability(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_add_task",
                "arguments": {
                    "work_order_id": "wo-real",
                    "title": "t",
                    "acceptance_criteria": "TEST-CHECK: tests/unit/test_x.py::test_y",
                },
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_work_order_add_task_succeeds_and_attributes_the_emitted_event(
    bootstrapped_home, monkeypatch
):
    captured = []
    import spool.writer as _writer

    monkeypatch.setattr(
        _writer, "write_event", lambda envelope, root=None: captured.append(envelope)
    )
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_add_task",
                "arguments": {
                    "work_order_id": "wo-real",
                    "title": "A new task",
                    "acceptance_criteria": (
                        "TEST-CHECK: tests/unit/integrations/test_mcp_server.py::test_placeholder"
                    ),
                },
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:add_task"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["status"] == "pending"
    created_events = [e for e in captured if e["event_type"] == "task.created"]
    assert len(created_events) == 1
    assert created_events[0]["trace"]["mcp_client"] == "fulcrum"


def test_work_order_add_task_refuses_a_task_nobody_can_check(bootstrapped_home):
    """The same admission the CLI's own `ds work-order add-task` runs -- not a thinner
    MCP-only gate. Without acceptance_criteria or why, the Warden refuses it."""
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_add_task",
                "arguments": {"work_order_id": "wo-real", "title": "A task nobody can check"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:add_task"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "refused to file this task" in payload["error"]


def test_work_order_add_task_accepts_a_declared_reason_in_place_of_a_criterion(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_add_task",
                "arguments": {
                    "work_order_id": "wo-real",
                    "title": "Operator attests the thing",
                    "why": "No computation can establish that a person accepted a risk.",
                },
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:add_task"})),
    )
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True


# ── ds_work_order_close (capability-gated) ──────────────────────────────────


def test_work_order_close_denies_an_identity_without_the_capability(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_work_order_close", "arguments": {"work_order_id": "wo-real"}},
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_work_order_close_refuses_from_the_wrong_phase(bootstrapped_home):
    """close_work_order's own phase check runs before force/skip_verify are even
    consulted (force waives gate CONTENT, never the pushed/ci_issues phase
    requirement) -- so this proves the refusal path works end to end over MCP, not
    that force is hardcoded false. See
    test_work_order_close_is_never_passed_force_or_skip_verify for that proof
    directly, against the handler's own call to close_work_order."""
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_work_order_close", "arguments": {"work_order_id": "wo-real"}},
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:close"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is False
    # fixture's work order is "in_progress" -- closed only reaches from pushed/ci_issues.
    assert payload.get("phase_refused") is True


def test_work_order_close_is_never_passed_force_or_skip_verify(bootstrapped_home, monkeypatch):
    """Direct proof the handler hardcodes both to False, not just an assertion on one
    observable outcome -- spies on close_work_order's own call signature."""
    import core.work_orders.close_main as close_main_mod

    captured_kwargs = {}

    def _fake_close(**kwargs):
        captured_kwargs.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(close_main_mod, "close_work_order", _fake_close)

    handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_work_order_close", "arguments": {"work_order_id": "wo-real"}},
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:close"})),
    )
    assert captured_kwargs["force"] is False
    assert captured_kwargs["skip_verify"] is False


# ── ds_work_order_advance (capability-gated) ────────────────────────────────


def test_work_order_advance_denies_an_identity_without_the_capability(bootstrapped_home):
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_advance",
                "arguments": {"work_order_id": "wo-real", "to": "in_review"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="reader-only", capabilities=frozenset({"review:run"})),
    )
    assert resp["error"]["code"] == -32001


def test_work_order_advance_succeeds_and_attributes_the_emitted_event(
    bootstrapped_home, monkeypatch
):
    captured = []
    import spool.writer as _writer

    monkeypatch.setattr(
        _writer, "write_event", lambda envelope, root=None: captured.append(envelope)
    )
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_advance",
                "arguments": {"work_order_id": "wo-real", "to": "in_review", "note": "handing off"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:advance"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["status"] == "in_review"
    events = [e for e in captured if e["event_type"] == "work_order.review_requested"]
    assert len(events) == 1
    assert events[0]["trace"]["mcp_client"] == "fulcrum"


def test_work_order_advance_refuses_an_out_of_order_move(bootstrapped_home):
    """The fixture's work order is "in_progress" -- phases run in order, so jumping
    straight to "pushed" (skipping "in_review") must be refused, not silently honored."""
    resp = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_advance",
                "arguments": {"work_order_id": "wo-real", "to": "pushed"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:advance"})),
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "cannot move to pushed" in payload["error"]


def test_work_order_advance_refuses_pushed_while_the_review_still_holds_it(bootstrapped_home):
    """The other half of ds_work_order_close being reachable at all: this is the ONE
    place advance_work_order consults the review (core.work_orders.mutations), so a
    work order cannot reach "pushed" -- and therefore cannot reach ds_work_order_close
    -- with an undispatched review."""
    identity = auth.Identity(name="fulcrum", capabilities=frozenset({"work_order:advance"}))
    to_review = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_advance",
                "arguments": {"work_order_id": "wo-real", "to": "in_review"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=identity,
    )
    assert json.loads(to_review["result"]["content"][0]["text"])["ok"] is True

    to_pushed = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "ds_work_order_advance",
                "arguments": {"work_order_id": "wo-real", "to": "pushed"},
            },
        },
        dream_studio_home=bootstrapped_home,
        identity=identity,
    )
    payload = json.loads(to_pushed["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "review still holds it" in payload["error"]


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


def test_authenticate_accepts_the_current_root_token(mcp_home):
    token, _ = auth.ensure_token(dream_studio_home=mcp_home)
    identity = auth.authenticate(f"Bearer {token}", dream_studio_home=mcp_home)
    assert identity == auth.Identity(name="operator", capabilities=None)


def test_authenticate_rejects_wrong_or_missing_token(mcp_home):
    auth.ensure_token(dream_studio_home=mcp_home)
    assert auth.authenticate("Bearer wrong", dream_studio_home=mcp_home) is None
    assert auth.authenticate(None, dream_studio_home=mcp_home) is None
    assert auth.authenticate("not-even-bearer-shaped", dream_studio_home=mcp_home) is None


def test_authenticate_rejects_when_no_token_was_ever_generated(mcp_home):
    assert auth.authenticate("Bearer anything", dream_studio_home=mcp_home) is None


def test_token_file_has_restrictive_permissions_on_posix(mcp_home):
    import stat
    import sys

    token, _ = auth.ensure_token(dream_studio_home=mcp_home)
    path = mcp_home / "state" / "mcp-token.json"
    assert path.is_file()
    if sys.platform != "win32":
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"token file mode is {oct(mode)}, expected 0o600"


# ── named, capability-scoped clients ────────────────────────────────────────


def test_add_client_round_trips_through_authenticate(mcp_home):
    token = auth.add_client(
        "fulcrum", capabilities=["work_order:task_mutate"], dream_studio_home=mcp_home
    )
    identity = auth.authenticate(f"Bearer {token}", dream_studio_home=mcp_home)
    assert identity == auth.Identity(
        name="fulcrum", capabilities=frozenset({"work_order:task_mutate"})
    )


def test_add_client_rejects_an_unknown_capability(mcp_home):
    with pytest.raises(ValueError, match="unknown capability"):
        auth.add_client("x", capabilities=["not:a:real:capability"], dream_studio_home=mcp_home)


def test_add_client_rejects_empty_capabilities(mcp_home):
    with pytest.raises(ValueError, match="non-empty"):
        auth.add_client("x", capabilities=[], dream_studio_home=mcp_home)


def test_add_client_rejects_dispatch_and_record_together(mcp_home):
    """The chair/reviewer collapse: one identity must never be able to both mint
    every reviewer's credential (dispatch) and spend one (record)."""
    with pytest.raises(ValueError, match="cannot hold both"):
        auth.add_client(
            "chair-and-reviewer",
            capabilities=["review:dispatch", "review:record"],
            dream_studio_home=mcp_home,
        )


def test_add_client_allows_dispatch_and_run_together(mcp_home):
    """run consumes no reviewer credential -- only dispatch+record is refused."""
    token = auth.add_client(
        "dispatcher-and-runner",
        capabilities=["review:dispatch", "review:run"],
        dream_studio_home=mcp_home,
    )
    assert token


def test_add_client_refuses_a_duplicate_name(mcp_home):
    auth.add_client("x", capabilities=["review:run"], dream_studio_home=mcp_home)
    with pytest.raises(ValueError, match="already exists"):
        auth.add_client("x", capabilities=["review:run"], dream_studio_home=mcp_home)


def test_list_clients_never_exposes_the_token_hash(mcp_home):
    auth.add_client("x", capabilities=["review:run"], dream_studio_home=mcp_home)
    clients = auth.list_clients(dream_studio_home=mcp_home)
    assert clients["x"]["capabilities"] == ["review:run"]
    assert "token_hash" not in clients["x"]


def test_revoke_client_removes_access(mcp_home):
    token = auth.add_client("x", capabilities=["review:run"], dream_studio_home=mcp_home)
    auth.revoke_client("x", dream_studio_home=mcp_home)
    assert auth.authenticate(f"Bearer {token}", dream_studio_home=mcp_home) is None
    assert "x" not in auth.list_clients(dream_studio_home=mcp_home)


def test_revoke_client_raises_on_an_unknown_name(mcp_home):
    with pytest.raises(ValueError, match="no such client"):
        auth.revoke_client("does-not-exist", dream_studio_home=mcp_home)


def test_rotate_client_issues_a_new_token_same_capabilities(mcp_home):
    old_token = auth.add_client("x", capabilities=["review:run"], dream_studio_home=mcp_home)
    new_token = auth.rotate_client("x", dream_studio_home=mcp_home)
    assert new_token != old_token
    assert auth.authenticate(f"Bearer {old_token}", dream_studio_home=mcp_home) is None
    identity = auth.authenticate(f"Bearer {new_token}", dream_studio_home=mcp_home)
    assert identity == auth.Identity(name="x", capabilities=frozenset({"review:run"}))


def test_rotate_client_raises_on_an_unknown_name(mcp_home):
    with pytest.raises(ValueError, match="no such client"):
        auth.rotate_client("does-not-exist", dream_studio_home=mcp_home)


def test_rotate_token_does_not_wipe_provisioned_clients(mcp_home):
    """The bug the pressure-test caught: rotate_token used to overwrite the whole
    file with a fresh two-key dict, silently deleting every client. Guards the fix,
    not just the current behavior -- see rotate_token's own docstring."""
    client_token = auth.add_client("x", capabilities=["review:run"], dream_studio_home=mcp_home)
    auth.rotate_token(dream_studio_home=mcp_home)
    identity = auth.authenticate(f"Bearer {client_token}", dream_studio_home=mcp_home)
    assert identity == auth.Identity(name="x", capabilities=frozenset({"review:run"}))


def test_ensure_token_does_not_wipe_provisioned_clients(mcp_home):
    auth.add_client("x", capabilities=["review:run"], dream_studio_home=mcp_home)
    auth.ensure_token(dream_studio_home=mcp_home)  # a no-op write path (token exists)
    assert "x" in auth.list_clients(dream_studio_home=mcp_home)


def test_a_v1_token_file_with_no_clients_key_loads_cleanly(mcp_home):
    """An existing installed user's token file predates the clients key entirely."""
    import json as _json

    mcp_home.joinpath("state").mkdir(parents=True)
    (mcp_home / "state" / "mcp-token.json").write_text(
        _json.dumps({"schema_version": 1, "token": "legacy-token-value"}), encoding="utf-8"
    )
    identity = auth.authenticate("Bearer legacy-token-value", dream_studio_home=mcp_home)
    assert identity == auth.Identity(name="operator", capabilities=None)
    assert auth.list_clients(dream_studio_home=mcp_home) == {}


# ── capability enforcement in the JSON-RPC layer ────────────────────────────


def _fake_capability_gated_tool(name="ds_fake_mutation", capability="review:dispatch"):
    from integrations.mcp.tools import Tool

    return Tool(
        name=name,
        description="test-only",
        input_schema={"type": "object", "properties": {}},
        handler=lambda **kwargs: {"called_with": sorted(kwargs)},
        required_capability=capability,
    )


def test_capability_gated_tool_denies_an_identity_without_it(monkeypatch):
    from integrations.mcp import server as server_mod

    tool = _fake_capability_gated_tool()
    monkeypatch.setitem(server_mod.TOOLS_BY_NAME, tool.name, tool)
    identity = auth.Identity(name="x", capabilities=frozenset({"review:run"}))
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool.name}},
        identity=identity,
    )
    assert resp["error"]["code"] == -32001
    assert "review:dispatch" in resp["error"]["message"]


def test_capability_gated_tool_allows_an_identity_with_it(monkeypatch):
    from integrations.mcp import server as server_mod

    tool = _fake_capability_gated_tool()
    monkeypatch.setitem(server_mod.TOOLS_BY_NAME, tool.name, tool)
    identity = auth.Identity(name="x", capabilities=frozenset({"review:dispatch"}))
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool.name}},
        identity=identity,
    )
    assert resp["result"]["isError"] is False


def test_capability_gated_tool_allows_the_root_identity(monkeypatch):
    from integrations.mcp import server as server_mod

    tool = _fake_capability_gated_tool()
    monkeypatch.setitem(server_mod.TOOLS_BY_NAME, tool.name, tool)
    identity = auth.Identity(name="operator", capabilities=None)
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool.name}},
        identity=identity,
    )
    assert resp["result"]["isError"] is False


def test_capability_gated_tool_denies_a_missing_identity_rather_than_defaulting_open(monkeypatch):
    """identity=None (a direct/internal call with no auth attached) must fail closed
    on a capability-gated tool, not be treated as trusted."""
    from integrations.mcp import server as server_mod

    tool = _fake_capability_gated_tool()
    monkeypatch.setitem(server_mod.TOOLS_BY_NAME, tool.name, tool)
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool.name}}
    )
    assert resp["error"]["code"] == -32001


def test_every_declared_capability_is_a_known_one():
    """A typo in a future Tool(required_capability=...) would silently create an
    unenforceable gate -- KNOWN_CAPABILITIES is the one place that string is allowed
    to come from."""
    for tool in TOOLS:
        if tool.required_capability is not None:
            assert tool.required_capability in auth.KNOWN_CAPABILITIES


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


def test_no_read_only_tool_name_suggests_a_write_or_destructive_action():
    """A cheap standing guard, not a substitute for reading tools.py: a tool that
    claims to be read-only (required_capability=None) but is named like a mutation is
    exactly the kind of thing this registry is scoped to exclude. A tool that DOES
    declare a capability is deliberately a mutation -- reviewed via that declaration,
    not by this substring check (see test_every_declared_capability_is_a_known_one)."""
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
        if tool.required_capability is not None:
            continue
        lowered = tool.name.lower()
        hits = [w for w in forbidden_substrings if w in lowered]
        assert not hits, f"{tool.name} looks like a write/destructive tool: {hits}"


def test_every_capability_gated_tool_name_is_forthright_about_it():
    """The flip side of the guard above: a tool that DOES mutate state must not be
    named to look read-only -- required_capability is the enforcement mechanism, but
    the name is what a human skimming tools/list sees first."""
    mutation_hints = (
        "start",
        "done",
        "close",
        "dispatch",
        "run",
        "record",
        "mutate",
        "create",
        "advance",
        "add",
    )
    for tool in TOOLS:
        if tool.required_capability is None:
            continue
        lowered = tool.name.lower()
        assert any(
            hint in lowered for hint in mutation_hints
        ), f"{tool.name} is capability-gated but its name gives no hint it mutates state"


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


# ── `ds mcp client` CLI, end to end ─────────────────────────────────────────


def _client_dispatch(mcp_home, subcommand, **kwargs):
    import argparse

    from interfaces.cli.commands import mcp as mcp_cmd

    args = argparse.Namespace(mcp_command="client", mcp_client_command=subcommand, **kwargs)
    mcp_cmd.dispatch(args, source_root=mcp_home, dream_studio_home=mcp_home)


def test_cli_client_add_issues_a_token_that_authenticates(mcp_home, capsys):
    _client_dispatch(mcp_home, "add", name="fulcrum", capabilities="review:run")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    identity = auth.authenticate(f"Bearer {payload['token']}", dream_studio_home=mcp_home)
    assert identity == auth.Identity(name="fulcrum", capabilities=frozenset({"review:run"}))


def test_cli_client_add_reports_a_validation_error_without_raising(mcp_home, capsys):
    _client_dispatch(mcp_home, "add", name="x", capabilities="not:real")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "unknown capability" in payload["error"]


def test_cli_client_list_reports_every_client(mcp_home, capsys):
    _client_dispatch(mcp_home, "add", name="a", capabilities="review:run")
    capsys.readouterr()
    _client_dispatch(mcp_home, "list")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["clients"]["a"]["capabilities"] == ["review:run"]


def test_cli_client_revoke_removes_access(mcp_home, capsys):
    _client_dispatch(mcp_home, "add", name="a", capabilities="review:run")
    token = json.loads(capsys.readouterr().out)["token"]
    _client_dispatch(mcp_home, "revoke", name="a")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert auth.authenticate(f"Bearer {token}", dream_studio_home=mcp_home) is None


def test_cli_client_rotate_replaces_the_token(mcp_home, capsys):
    _client_dispatch(mcp_home, "add", name="a", capabilities="review:run")
    old_token = json.loads(capsys.readouterr().out)["token"]
    _client_dispatch(mcp_home, "rotate", name="a")
    new_token = json.loads(capsys.readouterr().out)["token"]
    assert new_token != old_token
    assert auth.authenticate(f"Bearer {old_token}", dream_studio_home=mcp_home) is None
    assert auth.authenticate(f"Bearer {new_token}", dream_studio_home=mcp_home) is not None
