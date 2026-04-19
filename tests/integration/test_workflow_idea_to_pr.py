"""Integration test for workflows/idea-to-pr.yaml — DAG structure and state transitions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.workflow_validate import parse_workflow  # noqa: E402


IDEA_TO_PR_YAML = Path(__file__).resolve().parents[2] / "workflows" / "idea-to-pr.yaml"


def test_idea_to_pr_yaml_parses():
    wf = parse_workflow(str(IDEA_TO_PR_YAML))
    assert wf["name"] == "idea-to-pr"
    assert len(wf["nodes"]) >= 4


def test_idea_to_pr_node_ids():
    wf = parse_workflow(str(IDEA_TO_PR_YAML))
    ids = [n["id"] for n in wf["nodes"]]
    assert "think" in ids
    assert "plan" in ids
    assert "build" in ids
    assert "verify" in ids


def test_idea_to_pr_think_has_gate():
    wf = parse_workflow(str(IDEA_TO_PR_YAML))
    nodes_by_id = {n["id"]: n for n in wf["nodes"]}
    think = nodes_by_id.get("think", {})
    assert "gate" in think


def test_idea_to_pr_parallel_review_nodes():
    wf = parse_workflow(str(IDEA_TO_PR_YAML))
    ids = [n["id"] for n in wf["nodes"]]
    review_nodes = [nid for nid in ids if "review" in nid]
    assert len(review_nodes) >= 2, "Expected multiple parallel review nodes"


def test_idea_to_pr_gates_defined():
    wf = parse_workflow(str(IDEA_TO_PR_YAML))
    assert "director-approval" in wf["gates"]
    assert "evidence-required" in wf["gates"]
