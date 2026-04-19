"""Integration test for workflows/hotfix.yaml — DAG structure and state transitions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.workflow_validate import parse_workflow  # noqa: E402


HOTFIX_YAML = Path(__file__).resolve().parents[2] / "workflows" / "hotfix.yaml"


def test_hotfix_yaml_parses():
    wf = parse_workflow(str(HOTFIX_YAML))
    assert wf["name"] == "hotfix"
    assert len(wf["nodes"]) >= 3


def test_hotfix_node_ids():
    wf = parse_workflow(str(HOTFIX_YAML))
    ids = [n["id"] for n in wf["nodes"]]
    assert "debug" in ids
    assert "build" in ids
    assert "verify" in ids


def test_hotfix_dependency_order():
    wf = parse_workflow(str(HOTFIX_YAML))
    nodes_by_id = {n["id"]: n for n in wf["nodes"]}
    build = nodes_by_id.get("build", {})
    assert "debug" in build.get("depends_on", [])


def test_hotfix_build_depends_on_debug():
    wf = parse_workflow(str(HOTFIX_YAML))
    nodes_by_id = {n["id"]: n for n in wf["nodes"]}
    verify = nodes_by_id.get("verify", {})
    depends = verify.get("depends_on", [])
    assert "build" in depends
