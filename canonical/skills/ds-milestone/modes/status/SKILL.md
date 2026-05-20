# ds-milestone:status — Read-only milestone state

**Wraps:**
- `core.milestones.queries.get_milestone_status(milestone_id=..., source_root=..., dream_studio_home=..., planning_root=...)` — full status of a single milestone including work-order counts and which gate artifacts are still open.
- `core.milestones.queries.list_milestones(project_id=..., source_root=..., dream_studio_home=...)` — all milestones for a project with work-order counts.

---

## When to invoke this mode

The user asked about milestone progress — "what milestones are open?", "how's milestone 1 going?", "where are we on the alpha release?", "what gates are open on this milestone?". This mode is **read-only** — it does not mutate state or emit spool events.

## What to do

1. **If the user asked broadly about milestones:** call `list_milestones(project_id=<active project>, source_root=..., dream_studio_home=...)`. Present the returned `milestones` list grouped by `status` (active, pending, complete). Each row has `milestone_id`, `title`, `status`, `work_order_count`. Use the title in conversation; keep the ID internal.

2. **If the user asked about a specific milestone:** call `get_milestone_status(milestone_id=<ms>, source_root=..., dream_studio_home=..., planning_root=...)`. Surface:
   - `title` and `status`
   - `work_order_count` and how many of each status (open / in_progress / complete / blocked)
   - `open_gate_checks` — the list tells the user which artifact files still need to be written before the milestone can close. Present each as a one-liner.
   - `next_action` if present — surface verbatim.

3. **Surface only what the function returned.** If the user asks for fields the function doesn't expose (recent activity, who closed which WO), tell them this mode doesn't have that and point at the source — `git log` for code, the dashboard for spool events.

4. **Do not chain into a close.** Closing a milestone is a separate explicit action under `ds-milestone:close`. If the user asks "should I close?" surface the gate state and let them decide.

## Surface contract

`list_milestones` returns::

    {
      "ok": True,
      "milestones": [
        {"milestone_id": str, "title": str, "status": str, "work_order_count": int},
        ...
      ],
    }

`get_milestone_status` returns::

    {
      "ok": True,
      "milestone_id": str,
      "title": str,
      "status": str,
      "project_id": str,
      "work_order_count": int,
      "work_orders_by_status": {"open": int, "in_progress": int, "complete": int, ...},
      "open_gate_checks": [str, ...],
      "next_action": str | absent,
    }

## Side effects

None. Both functions are reads against the SQLite authority + planning artifact tree.
