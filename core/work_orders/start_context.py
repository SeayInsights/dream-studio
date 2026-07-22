"""Context.md markdown generator for work-order start.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/start.py``. Holds
``write_work_order_context`` — the pure markdown generator plus its
authority-first (with disk fallback) persistence. No logic changes —
extracted verbatim from the original module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_work_order_context(
    brief_data: dict[str, Any],
    *,
    planning_root: Path,
    now: str | None = None,
    db_path: Path | None = None,
) -> Path | None:
    """Markdown generator + authority-first store (WO-FILESDB-C2).

    Takes the dict returned by `read_work_order_brief` and stores the rendered
    context in the authority (``business_work_order_artifacts``, kind=``context``).
    Returns ``None`` when the artifact was stored in the DB; falls back to writing
    ``<planning_root>/work-orders/<wo_id>/context.md`` and returning that Path only
    when the artifact table is absent (migration unreleased during the transition —
    C6 removes the fallback after the artifact-table migration is released).
    """

    if not brief_data.get("ok"):
        raise ValueError(
            "write_work_order_context requires an ok=True brief_data dict; " f"got {brief_data}"
        )

    now = now or datetime.now(UTC).isoformat()
    work_order_id = brief_data["work_order_id"]
    title = brief_data["title"]
    type_id = brief_data["type_id"]
    label = brief_data["label"]
    wo_status = brief_data["status"]
    project_id = brief_data["project_id"]
    project_name = brief_data["project_name"]
    milestone_title = brief_data.get("milestone_title")
    marker_project_id = brief_data.get("marker_project_id")
    pre_gate = brief_data.get("pre_gate")
    build_exec = brief_data.get("build_exec")
    post_gate = brief_data.get("post_gate")
    workflow_template = brief_data.get("workflow_template")
    pending_tasks = brief_data.get("pending_tasks") or []
    brief_locked = brief_data.get("brief_locked")
    brief_warning = brief_data.get("brief_warning", False)
    gotchas = brief_data.get("gotchas") or []

    lines = [
        f"# Work Order: {title}",
        "",
        f"**ID:** `{work_order_id}`",
        f"**Type:** {label} (`{type_id}`)",
        f"**Status:** {wo_status}",
        f"**Project:** {project_name} (`{project_id}`)",
    ]
    if milestone_title:
        lines.append(f"**Milestone:** {milestone_title}")
    if marker_project_id:
        lines.append(f"**Active project (marker):** `{marker_project_id}`")
    lines += [
        "",
        "## Gates",
        "",
        f"- **Pre-build gate:** {pre_gate or '—'}",
        f"- **Build executor:** {build_exec or '—'}",
        f"- **Post-build gate:** {post_gate or '—'}",
    ]
    if workflow_template:
        lines.append(f"- **Workflow:** {workflow_template} — invoke `ds-core:think` to begin")
    lines += [
        "",
        "## Open Tasks",
        "",
    ]
    if pending_tasks:
        for task in pending_tasks:
            lines.append(f"- [ ] {task['title']}")
    else:
        lines.append("_No pending tasks._")

    if brief_locked:
        lines += ["", "## Design Brief", ""]
        for _lbl, _key in [
            ("Purpose", "purpose"),
            ("Audience", "audience"),
            ("Tone", "tone"),
            ("Font pairing", "font_pairing"),
            ("Brand tokens", "brand_tokens"),
        ]:
            _val = brief_locked.get(_key)
            if _val:
                lines.append(f"- **{_lbl}:** {_val}")
        if brief_locked.get("design_system"):
            _ds = brief_locked["design_system"]
            lines += [
                "",
                "## Design System",
                "",
                f"System: {_ds}",
                f"Reference: canonical/skills/domains/design-systems/{_ds}/",
                "",
                "Apply the principles from this design system to all UI output in this"
                " work order. Do not deviate from the system's token definitions.",
            ]
    elif brief_warning:
        lines += [
            "",
            "> **WARNING:** No locked design brief found."
            " Run `website:discover` before building UI for consistent results.",
        ]

    lines += [
        "",
        "## DREAM STUDIO ENFORCEMENT",
        "",
        "You are operating in Dream Studio managed mode.",
        "This is a hard boundary, not a suggestion.",
        "",
        f"AUTHORIZED scope: {type_id}",
        f"ACTIVE work order: {work_order_id}",
        "AUTHORIZED tasks: listed above under ## Tasks",
        "",
        "RULES:",
        "1. Do not create or modify files outside the authorized scope above.",
        "2. Complete tasks in the order listed unless tasks are clearly independent",
        "   of each other; independent tasks may be executed in parallel waves, but",
        "   each task must still be marked done individually via ds-workorder:execute",
        "   as it completes.",
        "3. Mark each task done by invoking ds-workorder:execute with the task ID.",
        "4. When all tasks are complete, invoke ds-workorder:close.",
        "5. Do not start work on any other work order until this one is closed.",
        "6. If you encounter an out-of-scope defect, register it as a NEW authority",
        "   work order (status 'created', backlog sequence) before continuing, and",
        "   put the GitHub issue number in the WO description if you file one.",
        "   A note alone or a GitHub issue alone is NOT sufficient tracking —",
        "   anything outside the authority is invisible to Dream Studio routing.",
        "   Do not fix it inline.",
        "7. Mirror the task list above into your native todo display and keep it in",
        "   sync with SQLite as tasks complete. SQLite is the authority; the todo",
        "   display is a mirror.",
        "",
        "Violations of these rules break traceability.",
        "Dream Studio exists to make your work verifiable.",
    ]

    if gotchas:
        lines += ["", "## Known Issues (from past sessions)", ""]
        for g in gotchas:
            lines.append(f"- **[{g['severity']}]** {g['title']}")
            if g.get("fix"):
                lines.append(f"  Fix: {g['fix']}")

    lines += ["", f"_Generated: {now}_", ""]
    content = "\n".join(lines)

    # WO-FILESDB-C2: DB-first. Store the context in the authority; write the
    # .planning file only when the artifact table is absent (unreleased migration
    # on the live DB during the transition). Checkboxes reflect task status at
    # render time; live status comes from business_tasks (`ds work-order tasks`),
    # not a mutated context.md (the read-modify-write in mutations.py is removed).
    from core.work_orders.artifacts import set_wo_artifact

    if set_wo_artifact(work_order_id, "context", content, db_path=db_path):
        return None
    context_dir = planning_root / "work-orders" / work_order_id
    context_dir.mkdir(parents=True, exist_ok=True)
    context_path = context_dir / "context.md"
    context_path.write_text(content, encoding="utf-8")
    return context_path
