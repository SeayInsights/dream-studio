"""Render-only Work Order execution packets."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from compat import UTC

from .evals import create_render_completeness_eval, create_skill_identifier_safety_eval
from .models import WorkOrderError
from .storage import load_work_order, work_order_dir, write_existing_work_order
from .validation import validate_work_order

SUPPORTED_RENDER_TARGETS = frozenset({"codex", "claude"})


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _section(title: str, items: list[Any]) -> str:
    if not items:
        return f"**{title}**\n- none\n"
    lines = "\n".join(f"- {item}" for item in items)
    return f"**{title}**\n{lines}\n"


def _workflow_lines(workflow: Any) -> list[str]:
    if isinstance(workflow, list):
        return [str(item) for item in workflow]
    if isinstance(workflow, dict):
        return [f"{key}: {value}" for key, value in workflow.items()]
    if workflow:
        return [str(workflow)]
    return []


def _common_packet_header(work_order: dict[str, Any], target: str) -> list[str]:
    return [
        f"# Work Order Execution Packet ({target})",
        "",
        f"Packet ID: {work_order['work_order_id']}.{target}",
        f"Target: {target}",
        f"Work Order ID: {work_order['work_order_id']}",
        f"Project Name: {work_order['project_name']}",
        f"Target Project Path: {work_order['target_path']}",
        f"Objective: {work_order['objective']}",
        f"Approval Mode: {work_order['approval_mode']}",
        f"Risk Level: {work_order['risk_level']}",
        f"Privacy Export Classification: {work_order['privacy_export_classification']}",
        f"Rendered At: {_now()}",
        "Renderer: dream-studio work order file-backed renderer",
        "Render Only: true",
        "",
    ]


def render_codex_packet(work_order: dict[str, Any]) -> str:
    scope = work_order.get("scope", {})
    lines = [
        *_common_packet_header(work_order, "codex"),
        "**Render-Only Posture**",
        "- This packet is instructions only. Do not execute rendered steps automatically.",
        "- Do not inspect, modify, or write target repo files while rendering.",
        "- Local canonical runtime state remains authoritative.",
        "",
        _section("Scope Include", _as_list(scope.get("include"))),
        _section("Scope Exclude", _as_list(scope.get("exclude"))),
        _section("Allowed Skills", _as_list(work_order.get("allowed_skills"))),
        _section("Allowed Agents", _as_list(work_order.get("allowed_agents"))),
        _section("Workflow", _workflow_lines(work_order.get("workflow"))),
        _section("Forbidden Actions", _as_list(work_order.get("forbidden_actions"))),
        "**Validation Commands**",
        "- Treat validation commands as inspect-only expectations unless an operator explicitly approves safe execution.",
        *[f"- {command}" for command in _as_list(work_order.get("validation_commands"))],
        "",
        _section("Stop Conditions", _as_list(work_order.get("stop_conditions"))),
        _section("Expected Output", _as_list(work_order.get("expected_outputs"))),
        "**Explicit Prohibitions**",
        "- Do not edit files.",
        "- Do not delete files.",
        "- Do not commit, stage, or push changes.",
        "- Do not change dependencies.",
        "- Do not change schema.",
        "- Do not mutate target repositories.",
        "- Do not open or write the native runtime DB.",
        "- Do not execute target repositories.",
        "",
        "**Report Format**",
        "- Summarize what was rendered.",
        "- List evidence paths under Work Order storage only.",
        "- List missing information as unavailable instead of guessing.",
        "- Recommend next action without executing it.",
    ]
    return "\n".join(lines) + "\n"


def render_claude_packet(work_order: dict[str, Any]) -> str:
    scope = work_order.get("scope", {})
    lines = [
        *_common_packet_header(work_order, "claude"),
        "**Working Directory**",
        f"- {work_order['target_path']}",
        "",
        "**Work Order Authority Statement**",
        "- The Work Order is the file-backed authority for this packet.",
        "- Claude Code is a target rendering surface only.",
        "- Do not execute this packet during render.",
        "",
        "**Render-Only Posture**",
        "- This packet is instructions only. Do not execute rendered steps automatically.",
        "- Do not inspect, modify, or write target repo files while rendering.",
        "- Local canonical runtime state remains authoritative.",
        "",
        f"**Mode**\n- {work_order['approval_mode']}\n",
        _section("Scope Include", _as_list(scope.get("include"))),
        _section("Scope Exclude", _as_list(scope.get("exclude"))),
        _section("Allowed Skills", _as_list(work_order.get("allowed_skills"))),
        _section("Allowed Agents", _as_list(work_order.get("allowed_agents"))),
        _section("Workflow", _workflow_lines(work_order.get("workflow"))),
        _section("Forbidden Actions", _as_list(work_order.get("forbidden_actions"))),
        "**Validation Commands**",
        "- Validation commands are evidence expectations. Treat them as inspect-only unless separately approved.",
        *[f"- {command}" for command in _as_list(work_order.get("validation_commands"))],
        "",
        _section("Stop Conditions", _as_list(work_order.get("stop_conditions"))),
        _section("Expected Output", _as_list(work_order.get("expected_outputs"))),
        "**Explicit Observe-Only And Render-Only Prohibitions**",
        "- Do not edit files.",
        "- Do not delete files.",
        "- Do not commit, stage, or push changes.",
        "- Do not change dependencies.",
        "- Do not change schema.",
        "- Do not mutate target repositories.",
        "- Do not open or write the native runtime DB.",
        "- Do not execute target repositories.",
        "",
        "**Report Format**",
        "- Report rendered packet completeness.",
        "- Report any missing fields as unavailable.",
        "- Report no target repo mutation.",
    ]
    return "\n".join(lines) + "\n"


def render_packet_text(work_order: dict[str, Any], target: str) -> str:
    if target == "codex":
        return render_codex_packet(work_order)
    if target == "claude":
        return render_claude_packet(work_order)
    raise WorkOrderError(f"Unsupported render target: {target}")


def render_work_order(
    work_order_id: str,
    *,
    target: str,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Render a stored Work Order and write file-backed eval artifacts."""
    if target not in SUPPORTED_RENDER_TARGETS:
        raise WorkOrderError(f"Unsupported render target: {target}")

    work_order, _ = load_work_order(work_order_id, storage_root=storage_root)
    result = validate_work_order(work_order)
    if not result.ok:
        raise WorkOrderError(result.format())

    packet_text = render_packet_text(result.work_order, target)
    # WO-FILESDB-C5: the rendered packet is a file-backed PACKET-system artifact —
    # stored in the authority-free packet store (kind='packet', instance_key=target)
    # instead of a rendered/<target>.md disk cache. It is also derivable on demand via
    # `ds work-order packet <id> --target <target>`. packet_path stays the logical ref.
    from core.work_orders.packet_store import set_packet_artifact

    target_dir = work_order_dir(work_order_id, storage_root=storage_root)
    packet_path = target_dir / "rendered" / f"{target}.md"
    set_packet_artifact(
        work_order_id, "packet", packet_text, instance_key=target, storage_root=storage_root
    )

    updated = dict(result.work_order)
    updated["status"] = "rendered"
    write_existing_work_order(updated, storage_root=storage_root)

    render_eval, render_eval_path = create_render_completeness_eval(
        work_order=updated,
        target=target,
        packet_path=packet_path,
        packet_text=packet_text,
        storage_root=storage_root,
    )
    skill_eval, skill_eval_path = create_skill_identifier_safety_eval(
        work_order=updated,
        storage_root=storage_root,
    )

    # WO-FILESDB-C3: eval artifacts live in the packet store (kind='eval'); the
    # per-eval path is None (no disk file). Surface only real disk paths, if any.
    eval_paths = [str(p) for p in (render_eval_path, skill_eval_path) if p is not None]

    return {
        "work_order_id": work_order_id,
        "target": target,
        "packet_path": str(packet_path),
        "eval_paths": eval_paths,
        "evals": [render_eval, skill_eval],
        "status": "rendered",
    }
