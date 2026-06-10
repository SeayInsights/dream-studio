"""Work-order independent verification via fresh-context subagent.

Entry point: ``verify_work_order(work_order_id=, source_root=, dream_studio_home=)``.

Flow:
1. Read tasks (title + description) from business_tasks.
2. Collect git commits referencing the WO's short ID (first 8 chars).
3. Invoke a fresh-context subagent (``claude --print``) with the verification
   prompt. Set DREAM_STUDIO_VERIFY_MOCK=1 to substitute a deterministic fixture
   for CI (no real API call needed).
4. Parse the JSON response. For each gap, INSERT a new WO + tasks under the
   same milestone as the reviewed WO.
5. Write the full verdict + spawned WO IDs to
   ``.planning/work-orders/<id>/review-verdict.json``.
6. Return a structured result dict.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

_MOCK_ENV = "DREAM_STUDIO_VERIFY_MOCK"
_MOCK_FIXTURE: dict[str, Any] = {
    "passed": True,
    "tasks_verified": [],
    "summary": "[mock] verification fixture — DREAM_STUDIO_VERIFY_MOCK=1",
    "gaps": [],
}

_VERIFICATION_PROMPT_TEMPLATE = """You are an independent code reviewer with no prior context about this work order.

Work order: {title}
Work order ID: {work_order_id}

Tasks that were supposed to be completed:
{task_list}

Git commits and diffs for this work order:
{git_diff}

Review each task against the commits and diffs above. Return ONLY valid JSON with this exact schema (no prose, no markdown fences):
{{
  "passed": <bool: true if all tasks are fully addressed>,
  "tasks_verified": [
    {{
      "task_title": "<task title>",
      "evidence": "<one sentence describing what in the diff addresses this task, or why it is missing>",
      "verdict": "pass" | "partial" | "missing"
    }}
  ],
  "summary": "<2-3 sentence overall assessment>",
  "gaps": [
    {{
      "title": "<imperative title for the gap work order>",
      "description": "<what needs to be done and why, including what was missed>",
      "work_order_type": "cleanup" | "infrastructure" | "documentation",
      "tasks": [
        {{
          "title": "<imperative task title>",
          "description": "<specific acceptance criteria>"
        }}
      ]
    }}
  ]
}}

A gap entry is required for every task with verdict "partial" or "missing", and for any TODO/FIXME/debt noticed in the diff that the task list does not address.
If all tasks pass and no debt is noticed, return gaps as an empty array.
"""


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    return paths.sqlite_path


def _read_tasks(conn: Any, work_order_id: str) -> list[dict[str, str]]:
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    cols = "title, description, status" + (", acceptance_criteria" if has_ac else "")
    rows = conn.execute(
        f"SELECT {cols} FROM business_tasks WHERE work_order_id = ? ORDER BY created_at ASC",
        (work_order_id,),
    ).fetchall()
    return [
        {
            "title": r[0],
            "description": r[1] or "",
            "status": r[2],
            "acceptance_criteria": (r[3] or "") if has_ac else "",
        }
        for r in rows
    ]


def _read_work_order(conn: Any, work_order_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT work_order_id, title, project_id, milestone_id, sequence_order, work_order_type"
        " FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "work_order_id": row[0],
        "title": row[1],
        "project_id": row[2],
        "milestone_id": row[3],
        "sequence_order": row[4],
        "work_order_type": row[5],
    }


def _collect_git_commits(source_root: Path, work_order_id: str) -> str:
    short_id = work_order_id[:8]
    try:
        log_result = subprocess.run(
            ["git", "log", "--oneline", "--all", f"--grep={short_id}"],
            cwd=str(source_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if not log_result.stdout.strip():
            return f"(no commits found referencing {short_id})"
        lines = log_result.stdout.strip().splitlines()
        diff_parts: list[str] = []
        for line in lines[:10]:
            commit_hash = line.split()[0]
            show_result = subprocess.run(
                ["git", "show", "--stat", "--patch", "--no-color", commit_hash],
                cwd=str(source_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff_parts.append(f"=== commit {commit_hash} ===\n{show_result.stdout[:8000]}")
        return "\n\n".join(diff_parts)
    except Exception as exc:
        return f"(error collecting git commits: {exc})"


def _call_subagent(prompt: str) -> dict[str, Any]:
    if os.environ.get(_MOCK_ENV):
        return _MOCK_FIXTURE.copy()
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout.strip()
        # Strip markdown fences if present
        if output.startswith("```"):
            lines = output.splitlines()
            output = "\n".join(line for line in lines if not line.strip().startswith("```")).strip()
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Subagent returned non-JSON output: {exc}\nRaw output:\n{result.stdout[:500]}"
        )
    except Exception as exc:
        raise RuntimeError(f"Subagent invocation failed: {exc}")


def _insert_gap_work_orders(
    conn: Any,
    *,
    gaps: list[dict[str, Any]],
    project_id: str,
    milestone_id: str | None,
    reviewed_wo_title: str,
    reviewed_wo_sequence: int | None,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    spawned: list[dict[str, Any]] = []

    # Find next available sequence_order
    base_seq = reviewed_wo_sequence or 0
    if milestone_id:
        max_seq_row = conn.execute(
            "SELECT MAX(sequence_order) FROM business_work_orders WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if max_seq_row and max_seq_row[0] is not None:
            base_seq = max(base_seq, max_seq_row[0])

    for i, gap in enumerate(gaps):
        new_wo_id = str(uuid.uuid4())
        seq = base_seq + i + 1
        desc = f"Spawned by review of '{reviewed_wo_title}' on {now[:10]}: {gap.get('description', '')}"
        wo_type = gap.get("work_order_type", "cleanup")

        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description,"
            "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?, ?, ?)",
            (new_wo_id, project_id, milestone_id, gap["title"], desc, wo_type, seq, now, now, now),
        )

        for task in gap.get("tasks", []):
            task_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO business_tasks"
                " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (
                    task_id,
                    new_wo_id,
                    project_id,
                    task.get("title", ""),
                    task.get("description", ""),
                    now,
                    now,
                ),
            )

        spawned.append({"work_order_id": new_wo_id, "title": gap["title"], "type": wo_type})

    return spawned


def verify_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Run independent verification for a work order.

    Returns:
        {
            "ok": bool,
            "work_order_id": str,
            "passed": bool,
            "summary": str,
            "tasks_verified": [...],
            "gaps": [...],
            "spawned_work_orders": [...],   # WOs inserted for gaps
            "verdict_path": str,
        }
    """
    p_root = planning_root or Path.cwd() / ".planning"
    db_path = _require_db(source_root, dream_studio_home)

    with _connect(db_path) as conn:
        wo = _read_work_order(conn, work_order_id)
        if wo is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        tasks = _read_tasks(conn, work_order_id)
        if not tasks:
            return {"ok": False, "error": f"No tasks found for work order: {work_order_id}"}

        task_list_str = "\n".join(
            "{n}. [{st}] {title}: {desc}{ac}".format(
                n=i + 1,
                st=t["status"],
                title=t["title"],
                desc=t["description"],
                ac=(
                    f"\n   Acceptance criteria: {t['acceptance_criteria']}"
                    if t.get("acceptance_criteria")
                    else ""
                ),
            )
            for i, t in enumerate(tasks)
        )
        git_diff = _collect_git_commits(source_root, work_order_id)

        prompt = _VERIFICATION_PROMPT_TEMPLATE.format(
            title=wo["title"],
            work_order_id=work_order_id,
            task_list=task_list_str,
            git_diff=git_diff,
        )

        verdict = _call_subagent(prompt)

        spawned: list[dict[str, Any]] = []
        if verdict.get("gaps") and wo.get("project_id") and wo.get("milestone_id"):
            spawned = _insert_gap_work_orders(
                conn,
                gaps=verdict["gaps"],
                project_id=wo["project_id"],
                milestone_id=wo["milestone_id"],
                reviewed_wo_title=wo["title"],
                reviewed_wo_sequence=wo.get("sequence_order"),
            )

        verdict_dir = p_root / "work-orders" / work_order_id
        verdict_dir.mkdir(parents=True, exist_ok=True)
        verdict_path = verdict_dir / "review-verdict.json"
        full_verdict = {
            **verdict,
            "work_order_id": work_order_id,
            "spawned_work_orders": spawned,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        verdict_path.write_text(json.dumps(full_verdict, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": verdict.get("passed", False),
        "summary": verdict.get("summary", ""),
        "tasks_verified": verdict.get("tasks_verified", []),
        "gaps": verdict.get("gaps", []),
        "spawned_work_orders": spawned,
        "verdict_path": str(verdict_path),
    }
