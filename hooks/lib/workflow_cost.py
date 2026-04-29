"""Workflow token cost estimation — pre-run summary for dream-studio workflows.

Zero new dependencies (stdlib only). Reads parsed workflow dicts (from
workflow_validate.parse_workflow) and produces human-readable cost tables.
"""

from __future__ import annotations


def estimate_workflow_cost(workflow_data: dict) -> dict:
    """Return a cost summary dict for the workflow.

    Args:
        workflow_data: parsed workflow dict (from parse_workflow).

    Returns:
        {
            "total_estimated": int,      # sum of all estimated_tokens values
            "node_count": int,           # total nodes in the workflow
            "estimated_count": int,      # nodes that have estimated_tokens set
            "unestimated_count": int,    # nodes without estimated_tokens
            "nodes": [
                {"id": str, "estimated_tokens": int | None}, ...
            ],
        }
    """
    nodes = workflow_data.get("nodes", [])
    total = 0
    estimated_count = 0
    node_rows = []

    for n in nodes:
        nid = n.get("id", "?")
        raw = n.get("estimated_tokens")
        if raw is not None and isinstance(raw, int):
            total += raw
            estimated_count += 1
            node_rows.append({"id": nid, "estimated_tokens": raw})
        else:
            node_rows.append({"id": nid, "estimated_tokens": None})

    return {
        "total_estimated": total,
        "node_count": len(nodes),
        "estimated_count": estimated_count,
        "unestimated_count": len(nodes) - estimated_count,
        "nodes": node_rows,
    }


def format_cost_summary(cost: dict) -> str:
    """Return a human-readable pre-run cost summary string."""
    nodes = cost.get("nodes", [])
    unestimated = cost.get("unestimated_count", 0)
    total = cost.get("total_estimated", 0)

    if not nodes:
        return "[workflow] No nodes found — cannot estimate cost."

    if cost.get("estimated_count", 0) == 0:
        return (
            "[workflow] No token estimates — add estimated_tokens to nodes "
            "for a pre-run cost summary."
        )

    col_width = max((len(n["id"]) for n in nodes), default=6) + 2
    bar = "─" * (col_width + 20)
    lines = [f"┌─ Workflow Cost Estimate {bar}┐"]

    for n in nodes:
        nid = n["id"]
        tokens = n["estimated_tokens"]
        if tokens is not None:
            lines.append(f"│  {nid:<{col_width}}{tokens:>10,} tokens")
        else:
            lines.append(f"│  {nid:<{col_width}}{'(unestimated)':>10}")

    lines.append(f"│  {'─' * (col_width + 18)}")
    suffix = f"  ({unestimated} node(s) unestimated)" if unestimated else ""
    lines.append(f"│  {'Total:':<{col_width}}{total:>10,} tokens est.{suffix}")
    lines.append(f"└{'─' * (col_width + 22)}┘")
    return "\n".join(lines)
