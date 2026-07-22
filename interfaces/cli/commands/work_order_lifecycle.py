"""ds work-order command group — start/close/block/unblock lifecycle transitions.

Split from interfaces/cli/commands/work_order.py (WO-GF-CLI-split). The
facade at interfaces/cli/commands/work_order.py re-exports this module's
private implementation helpers; interfaces/cli/commands/work_order_dispatch.py
holds the (unsplit) ``register()``/``dispatch()`` that route to them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _work_order_start(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
    accept_no_brief: bool = False,
    in_sequence: bool = False,
) -> int:
    """CLI wrapper around `core.work_orders.start.start_work_order`.

    Preserves the legacy operator-terminal behavior: prints a stderr WARNING
    when the work order is UI-typed but lacks a locked design brief; if the
    operator is running interactively (TTY), prompts y/N; otherwise auto-
    accepts (so test fixtures and non-interactive scripts keep working).

    Skills should call `start_work_order(accept_no_brief=...)` directly and
    never go through this CLI surface.
    """

    from core.work_orders.start import read_work_order_brief, start_work_order

    brief_data = read_work_order_brief(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not brief_data.get("ok"):
        print(json.dumps(brief_data, indent=2))
        return 1

    if brief_data.get("brief_warning") and not accept_no_brief:
        print(
            "WARNING: No locked design brief found. It is strongly recommended to run "
            "website:discover before building UI. Continue anyway? [y/N]",
            file=sys.stderr,
        )
        if sys.stdin.isatty():
            try:
                answer = sys.stdin.readline().strip().lower()
            except OSError:
                # On Windows, stdin may claim isatty()=True but fail on read
                # (WinError 1) in certain pipe/test contexts. Treat as non-interactive.
                answer = ""
            if answer not in ("y", "yes"):
                return 0
        # Non-interactive context (tests, scripts): auto-accept to preserve
        # legacy behavior — the warning is still emitted to stderr.
        accept_no_brief = True

    result = start_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
        accept_no_brief=accept_no_brief,
        brief_data=brief_data,
        in_sequence=in_sequence,
    )
    if result.get("ok") and result.get("sequence_warning"):
        print(result["sequence_warning"], file=sys.stderr)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_close(
    *,
    work_order_id: str,
    force: bool = False,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """CLI wrapper around `core.work_orders.close.close_work_order`.

    Preserves the legacy operator-terminal behaviour by re-emitting
    `[gate.bypassed] WARNING: <reason>` to stderr from the returned
    `bypassed_gates` list. Skills should call `close_work_order` directly.
    """

    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=work_order_id,
        force=force,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if result.get("ok") and result.get("forced") and result.get("bypassed_gates"):
        for reason in result["bypassed_gates"]:
            print(f"[gate.bypassed] WARNING: {reason}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    if result.get("ok") and result.get("next_block"):
        print(file=sys.stderr)
        print(result["next_block"], file=sys.stderr)
    return 0 if result.get("ok") else 1


def _work_order_block(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.mutations import block_work_order

    result = block_work_order(
        work_order_id=work_order_id,
        reason=reason,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_unblock(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.mutations import unblock_work_order

    result = unblock_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
