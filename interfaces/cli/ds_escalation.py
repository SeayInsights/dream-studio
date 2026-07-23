"""ds escalation subcommands — operator escalation surface (WO-FILESDB-C4B S2).

Lists, inspects, and resolves the operator escalations recorded in the authority
artifact store (``business_work_order_artifacts`` kind='escalation'), replacing the
loose ``~/.dream-studio/meta/ESC-*.md`` disk files an operator would otherwise
hand-edit. Store-only and additive: the pulse open-escalation count keeps reading
disk until C4B-3 repoints it at this store, so resolving here becomes pulse-visible
in that later slice.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def cmd_escalation_list(args) -> int:
    """Entry point for `ds escalation list` — open escalations across all work orders."""
    from core.work_orders.escalation import list_escalations

    rows = list_escalations(include_resolved=getattr(args, "all", False))
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "escalations": rows}))
        return 0

    if not rows:
        scope = "escalations" if getattr(args, "all", False) else "open escalations"
        print(f"No {scope}.")
        return 0

    widths = {"wo": 10, "type": 10, "status": 12, "reason": 40}
    header = (
        f"{'WORK_ORDER':<{widths['wo']}}  "
        f"{'TYPE':<{widths['type']}}  "
        f"{'STATUS':<{widths['status']}}  "
        f"{'REASON':<{widths['reason']}}"
    )
    print(header)
    print("-" * len(header))
    for rec in rows:
        wo_short = str(rec.get("work_order_id", ""))[:8]
        reason = str(rec.get("reason", "") or "")
        if len(reason) > widths["reason"]:
            reason = reason[: widths["reason"] - 1] + "…"
        print(
            f"{wo_short:<{widths['wo']}}  "
            f"{str(rec.get('type', '')):<{widths['type']}}  "
            f"{str(rec.get('status', '')):<{widths['status']}}  "
            f"{reason:<{widths['reason']}}"
        )
    print(f"\n{len(rows)} escalation(s).")
    return 0


def cmd_escalation_status(args) -> int:
    """Entry point for `ds escalation status <work_order_id>` — a WO's escalations."""
    from core.work_orders.escalation import get_escalations

    rows = get_escalations(args.work_order_id)
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "work_order_id": args.work_order_id, "escalations": rows}))
        return 0

    if not rows:
        print(f"No escalations for work order {args.work_order_id}.")
        return 0

    print(f"Escalations for work order {args.work_order_id}:")
    for rec in rows:
        line = f"  [{rec.get('status', '')}] {rec.get('type', '')}"
        if rec.get("reason"):
            line += f" — {rec['reason']}"
        print(line)
        if rec.get("created_at"):
            print(f"      created:  {rec['created_at']}")
        if rec.get("resolved_at"):
            print(f"      resolved: {rec['resolved_at']}")
    return 0


def cmd_escalation_resolve(args) -> int:
    """Entry point for `ds escalation resolve <work_order_id>` — mark resolved."""
    from core.work_orders.escalation import resolve_escalation

    result = resolve_escalation(
        args.work_order_id,
        instance_key=getattr(args, "type", None),
        note=getattr(args, "note", "") or "",
    )
    # Exit non-zero when there was nothing to resolve — same in text and JSON modes,
    # so --json changes output format only, never exit semantics.
    rc = 0 if result["found"] else 1
    if getattr(args, "json", False):
        print(json.dumps({"ok": result["found"], **result}))
        return rc

    if not result["found"]:
        target = f" ({args.type})" if getattr(args, "type", None) else ""
        print(f"No escalation{target} found for work order {args.work_order_id}.")
        return rc
    if result["resolved"]:
        print(
            f"Resolved {', '.join(result['resolved'])} escalation(s) "
            f"for work order {args.work_order_id}."
        )
    if result["already_resolved"]:
        print(f"Already resolved: {', '.join(result['already_resolved'])}.")
    return rc


def add_escalation_subcommand(subparsers) -> None:
    """Register the 'escalation' subcommand group."""
    esc_parser = subparsers.add_parser(
        "escalation", help="Operator escalation surface (list/status/resolve)"
    )
    esc_sub = esc_parser.add_subparsers(dest="escalation_cmd", required=True)

    list_parser = esc_sub.add_parser("list", help="List open escalations across all work orders")
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Include resolved escalations (default: only unresolved)",
    )
    list_parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    list_parser.set_defaults(func=cmd_escalation_list)

    status_parser = esc_sub.add_parser("status", help="Show escalations for one work order")
    status_parser.add_argument("work_order_id", help="Work order id")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    status_parser.set_defaults(func=cmd_escalation_status)

    resolve_parser = esc_sub.add_parser(
        "resolve", help="Mark a work order's escalation(s) resolved"
    )
    resolve_parser.add_argument("work_order_id", help="Work order id")
    resolve_parser.add_argument(
        "--type",
        default=None,
        choices=["retrycap", "outcome"],
        help="Resolve only this escalation instance (default: all instances for the WO)",
    )
    resolve_parser.add_argument(
        "--note", default="", help="Optional resolution note stored on the artifact"
    )
    resolve_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    resolve_parser.set_defaults(func=cmd_escalation_resolve)
