"""A work-order type a pack declares is advertised, validated and refused by the MCP server correctly.

The server validates every `tools/call` against the tool's schema (#903), built from
`tool.input_schema`, which carries no `work_order_type` enum because that enum is not fixed: it is
the declared set, and a pack's manifest adds to it. Two things went wrong when the two met on a
throwaway merge:

- the validator no longer saw the enum, so an unknown type stopped being a -32602 error and
  reached the handler;
- building the validator from `tool.schema()` once per tool name would have pinned the FIRST enum
  for the life of the process, so a type declared later would be refused for good.

The validator for a tool with a live enum is built from the schema as it stands at the call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.work_orders.type_registry import (
    DOCUMENT,
    register_work_order_type,
    scoped_pack_manifest,
    scoped_registration,
    work_order_type_names,
)
from integrations.mcp import auth, server
from integrations.mcp.server import _schema_problems, _validator_for, handle_message
from integrations.mcp.tools import TOOLS_BY_NAME

INVALID_PARAMS = -32602
ROOT = auth.Identity(name="operator", capabilities=None)

MANIFEST = """\
schema_version: 2
packs:
  legal:
    contributes:
      work_order_types:
        - name: contract_review
          artifact_class: document
          description: Reviewing a contract for completeness and accuracy
          ui_bearing: false
          exempt_from_verification: false
"""


@pytest.fixture
def packs_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "packs.yaml"
    path.write_text(MANIFEST, encoding="utf-8")
    return path


def _create_args(work_order_type: str) -> dict:
    return {
        "project_id": "p",
        "milestone_id": "m",
        "title": "A thing",
        "description": "A description long enough to clear the prompt floor for a work order.",
        "work_order_type": work_order_type,
    }


def _call(tmp_path: Path, work_order_type: str) -> dict:
    return handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ds_work_order_create", "arguments": _create_args(work_order_type)},
        },
        dream_studio_home=tmp_path,
        identity=ROOT,
    )


def _advertised() -> list[str]:
    listed = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tool = next(t for t in listed["result"]["tools"] if t["name"] == "ds_work_order_create")
    return tool["inputSchema"]["properties"]["work_order_type"]["enum"]


def test_a_pack_declared_type_is_advertised_by_tools_list(packs_yaml):
    assert "contract_review" not in _advertised()
    with scoped_pack_manifest(packs_yaml):
        assert "contract_review" in _advertised()
        assert tuple(_advertised()) == work_order_type_names()
    assert "contract_review" not in _advertised()


def test_a_pack_declared_type_passes_validation_and_an_unknown_one_is_invalid_params(
    packs_yaml, tmp_path
):
    tool = TOOLS_BY_NAME["ds_work_order_create"]
    with scoped_pack_manifest(packs_yaml):
        assert _schema_problems(tool, _create_args("contract_review")) == []
        accepted = _call(tmp_path, "contract_review")
        # Past validation: whatever happens next (no authority in this home) is the handler's.
        assert "error" not in accepted or accepted["error"]["code"] != INVALID_PARAMS
        refused = _call(tmp_path, "no_such_type")
    assert refused["error"]["code"] == INVALID_PARAMS
    assert "work_order_type" in refused["error"]["message"]
    assert "contract_review" in refused["error"]["message"] or "is not one of" in (
        refused["error"]["message"]
    )


def test_an_unknown_type_is_invalid_params_with_no_pack_at_all(tmp_path):
    """The gap the merge opened: with the enum out of `input_schema`, an unknown type reached the
    handler and failed there instead of at validation."""
    response = _call(tmp_path, "no_such_type")
    assert response["error"]["code"] == INVALID_PARAMS


def test_a_type_declared_after_the_first_call_is_accepted_and_then_gone_again(tmp_path):
    """The stale-validator defect: the first call builds a validator; a cache keyed on the tool
    name alone would keep refusing a type declared afterwards."""
    tool = TOOLS_BY_NAME["ds_work_order_create"]
    assert _schema_problems(tool, _create_args("late_type")), "refused before it exists"
    with scoped_registration():
        register_work_order_type("late_type", artifact_class=DOCUMENT)
        assert _schema_problems(tool, _create_args("late_type")) == [], "accepted once declared"
        assert "error" not in _call(tmp_path, "late_type") or (
            _call(tmp_path, "late_type")["error"]["code"] != INVALID_PARAMS
        )
    assert _schema_problems(tool, _create_args("late_type")), "refused again after the scope"


def test_the_validator_for_a_live_enum_tool_is_not_pinned_to_the_first_enum():
    tool = TOOLS_BY_NAME["ds_work_order_create"]
    first = _validator_for(tool)
    with scoped_registration():
        register_work_order_type("another_late_type", artifact_class=DOCUMENT)
        second = _validator_for(tool)
        assert "another_late_type" in second.schema["properties"]["work_order_type"]["enum"]
        assert "another_late_type" not in first.schema["properties"]["work_order_type"]["enum"]


def test_a_static_tool_keeps_its_cached_validator():
    """Only a tool with a live enum is rebuilt per call; the rest stay cached by name."""
    tool = TOOLS_BY_NAME["ds_project_list"]
    assert not tool.live_enums
    assert _validator_for(tool) is _validator_for(tool)


def test_the_guard_reads_the_computed_schema_so_it_sees_the_enum():
    """tests/unit/integrations/test_mcp_tool_arguments_guard.py checks the closed-schema and
    no-authority-argument rules against `tool.schema()`, not `tool.input_schema`."""
    guard = (Path(__file__).parent / "test_mcp_tool_arguments_guard.py").read_text(encoding="utf-8")
    assert "schema = tool.schema()" in guard
    assert "input_schema\n" not in guard.split("def violations")[1].split("def ")[0]


# ── a manifest edited under a running server ──────────────────────────────────


def test_the_server_logs_one_warning_when_its_manifest_changed_after_it_loaded(monkeypatch, caplog):
    """`ds mcp serve` reads the manifest once; an edit needs a restart, and the server says so,
    once per change, rather than silently serving the old types."""
    import logging

    message = "the pack manifest X changed on disk after this process loaded its types; restart"
    monkeypatch.setattr(server, "manifest_changed_since_load", lambda: message)
    monkeypatch.setattr(server, "_WARNED_MANIFEST_CHANGES", set())
    with caplog.at_level(logging.WARNING, logger="dream_studio.mcp.server"):
        handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    warnings = [r.getMessage() for r in caplog.records if "changed on disk" in r.getMessage()]
    assert warnings == [message], warnings


def test_the_server_logs_nothing_when_the_manifest_has_not_changed(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(server, "manifest_changed_since_load", lambda: None)
    with caplog.at_level(logging.WARNING, logger="dream_studio.mcp.server"):
        handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert not [r for r in caplog.records if "changed on disk" in r.getMessage()]


def test_each_distinct_edit_is_reported_once_not_only_the_first_one_a_process_sees(
    monkeypatch, caplog, tmp_path
):
    """The dedupe keyed on the message, and the message named only the file, so the second edit
    of a long-lived server was swallowed as the same warning. The message now carries the file's
    current size and mtime: a new edit is a new message; the same state is not repeated."""
    import logging
    import os
    import time

    from core.work_orders import type_manifest, type_registry

    path = tmp_path / "packs.yaml"
    path.write_text(MANIFEST, encoding="utf-8")
    builtins = {
        n: t
        for n, t in type_registry._REGISTRY.items()
        if n in type_registry.builtin_work_order_type_names()
    }
    monkeypatch.setattr(type_registry, "_REGISTRY", builtins)
    monkeypatch.setattr(type_registry, "_STATE", {"loaded": False, "loading": False})
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: path)
    monkeypatch.setattr(server, "_WARNED_MANIFEST_CHANGES", set())
    work_order_type_names()  # the process loads its manifest

    def tick(extra: str, offset: int) -> None:
        path.write_text(MANIFEST + extra, encoding="utf-8")
        stamp = time.time() + offset
        os.utime(path, (stamp, stamp))

    with caplog.at_level(logging.WARNING, logger="dream_studio.mcp.server"):
        handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert not [r for r in caplog.records if "changed on disk" in r.getMessage()]
        tick("# first edit\n", 60)
        handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        tick("# second edit, longer\n", 120)
        handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
    warnings = [r.getMessage() for r in caplog.records if "changed on disk" in r.getMessage()]
    assert len(warnings) == 2 and warnings[0] != warnings[1], warnings
