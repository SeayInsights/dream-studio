"""Unit tests for hooks.lib.workflow_cost."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.workflow_cost import estimate_workflow_cost, format_cost_summary  # noqa: E402


def _nodes(*pairs: tuple[str, int | None]) -> list[dict]:
    """Helper: build a minimal nodes list for test workflows."""
    result = []
    for nid, tokens in pairs:
        n: dict = {"id": nid, "skill": nid}
        if tokens is not None:
            n["estimated_tokens"] = tokens
        result.append(n)
    return result


# ---------------------------------------------------------------------------
# estimate_workflow_cost
# ---------------------------------------------------------------------------


def test_estimate_sums_all_nodes() -> None:
    data = {"nodes": _nodes(("debug", 2000), ("build", 3000), ("verify", 1500))}
    result = estimate_workflow_cost(data)
    assert result["total_estimated"] == 6500
    assert result["node_count"] == 3
    assert result["estimated_count"] == 3
    assert result["unestimated_count"] == 0


def test_estimate_handles_missing_field() -> None:
    data = {"nodes": _nodes(("debug", 2000), ("build", None), ("verify", 1500))}
    result = estimate_workflow_cost(data)
    assert result["total_estimated"] == 3500
    assert result["unestimated_count"] == 1
    assert result["estimated_count"] == 2
    # No KeyError should be raised
    node_ids = [n["id"] for n in result["nodes"]]
    assert "build" in node_ids


def test_estimate_empty_workflow() -> None:
    result = estimate_workflow_cost({})
    assert result["total_estimated"] == 0
    assert result["node_count"] == 0
    assert result["estimated_count"] == 0
    assert result["unestimated_count"] == 0
    assert result["nodes"] == []


# ---------------------------------------------------------------------------
# format_cost_summary
# ---------------------------------------------------------------------------


def test_format_summary_contains_total() -> None:
    data = {"nodes": _nodes(("debug", 2000), ("build", 3000))}
    cost = estimate_workflow_cost(data)
    summary = format_cost_summary(cost)
    assert "Total" in summary
    assert "5,000" in summary


def test_format_summary_marks_unestimated() -> None:
    data = {"nodes": _nodes(("debug", 2000), ("build", None))}
    cost = estimate_workflow_cost(data)
    summary = format_cost_summary(cost)
    assert "unestimated" in summary
