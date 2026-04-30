"""Workflow token cost estimation — pre-run summary for dream-studio workflows.

Zero new dependencies (stdlib only). Reads parsed workflow dicts (from
workflow_validate.parse_workflow) and produces human-readable cost tables.
Includes pre-run cost gate for informed workflow launch decisions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


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


# ── Pre-run cost gate ────────────────────────────────────────────────


def _get_model_recommendation(skill_name: str) -> str | None:
    """Get model recommendation for a skill via model_selector."""
    try:
        from lib.model_selector import recommend_model
        return recommend_model(skill_name)
    except (ImportError, Exception):
        return None


def pre_run_cost_gate(
    workflow_data: dict,
    context_pct: float | None = None,
) -> str:
    """Format a pre-run cost table with model recommendations.

    Informational only — does not block execution.
    """
    cost = estimate_workflow_cost(workflow_data)
    nodes = workflow_data.get("nodes", [])
    cost_nodes = cost.get("nodes", [])

    if not cost_nodes:
        return "[workflow] No nodes — cannot estimate."

    col_width = max((len(n["id"]) for n in cost_nodes), default=6) + 2
    model_col = 8
    bar = "─" * (col_width + model_col + 22)
    lines = [f"┌─ Pre-Run Cost Gate {bar}┐"]

    yaml_by_id = {n["id"]: n for n in nodes if "id" in n}

    total = 0
    for cn in cost_nodes:
        nid = cn["id"]
        tokens = cn["estimated_tokens"]
        yn = yaml_by_id.get(nid, {})
        skill = yn.get("skill", "")
        yaml_model = yn.get("model", "")

        rec = _get_model_recommendation(skill) if skill else None
        model_str = rec or yaml_model or "—"

        if tokens is not None:
            total += tokens
            lines.append(
                f"│  {nid:<{col_width}}{tokens:>10,} tok  {model_str:<{model_col}}"
            )
        else:
            lines.append(
                f"│  {nid:<{col_width}}{'(unest.)':>10}      {model_str:<{model_col}}"
            )

    lines.append(f"│  {'─' * (col_width + model_col + 20)}")
    lines.append(f"│  {'Total:':<{col_width}}{total:>10,} tokens est.")

    if context_pct is not None:
        lines.append(f"│  Context: {context_pct:.0f}% used")
        if context_pct > 60:
            lines.append(f"│  ⚠ High context — consider /compact before running")

    lines.append(f"└{'─' * (col_width + model_col + 24)}┘")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Workflow cost estimation and pre-run cost gate.",
    )
    parser.add_argument("--gate", metavar="YAML", help="Run pre-run cost gate on a workflow YAML")
    parser.add_argument("--context-pct", type=float, default=None, help="Current context %%")
    args = parser.parse_args()

    if args.gate:
        yaml_path = Path(args.gate)
        if not yaml_path.is_file():
            print(f"Error: {yaml_path} not found", file=sys.stderr)
            sys.exit(1)
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from lib.workflow_validate import parse_workflow
            data = parse_workflow(str(yaml_path))
        except Exception as e:
            print(f"Error parsing {yaml_path}: {e}", file=sys.stderr)
            sys.exit(1)
        output = pre_run_cost_gate(data, context_pct=args.context_pct)
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
