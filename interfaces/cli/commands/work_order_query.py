"""ds work-order command group — list/next/verify/executor/artifact/packet reads.

Split from interfaces/cli/commands/work_order.py (WO-GF-CLI-split). The
facade at interfaces/cli/commands/work_order.py re-exports this module's
private implementation helpers; interfaces/cli/commands/work_order_dispatch.py
holds the (unsplit) ``register()``/``dispatch()`` that route to them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _work_order_executor(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Resolve and print the executor (model) for a WO — escalation-aware (T5).

    The autonomous execute-work-orders loop calls this to honor the escalation
    capability flag (route an escalated WO's retry to Opus); the manual path honors
    the same flag via start_work_order's ``executor`` field. Both consume
    ``escalation.resolve_executor`` so routing is identical on both surfaces.
    """
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.escalation import read_escalation, resolve_executor

    db_path = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path
    executor = resolve_executor(work_order_id, db_path=db_path)
    esc = read_escalation(work_order_id, db_path=db_path)
    result = {
        "ok": True,
        "work_order_id": work_order_id,
        "executor": executor,
        "escalated": bool(esc and (esc.get("escalation_level") or 0) >= 1),
        "escalation_level": (esc or {}).get("escalation_level", 0),
    }
    print(json.dumps(result, indent=2))
    return 0


def _work_order_artifact(
    *,
    work_order_id: str,
    kind: str,
    instance_key: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Print a WO ceremony/eval artifact stored in the authority (WO-FILESDB-C1).

    The operator/terminal read surface that replaces reading
    ``.planning/work-orders/<id>/*`` files — artifacts live in
    ``business_work_order_artifacts``, keyed by (work_order_id, kind, instance_key).
    """
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.artifacts import VALID_KINDS, get_wo_artifact

    if kind not in VALID_KINDS:
        print(
            f"Unknown artifact kind: {kind!r}. Valid: {', '.join(sorted(VALID_KINDS))}",
            file=sys.stderr,
        )
        return 1
    db_path = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path
    content = get_wo_artifact(work_order_id, kind, instance_key=instance_key, db_path=db_path)
    if content is None:
        label = f"{kind}" + (f" (instance={instance_key})" if instance_key else "")
        print(f"No {label} artifact stored for work order {work_order_id}", file=sys.stderr)
        return 1
    print(content)
    return 0


def _work_order_packet(
    *,
    work_order_id: str,
    target: str,
    storage_root: Path | None,
) -> int:
    """Render a WO execution packet on demand and print it (WO-FILESDB-C1).

    Derive-on-demand: the packet is rendered from the WO and printed to stdout —
    no ``rendered/<target>.md`` disk cache is written (that write path is retired
    in WO-FILESDB-C5). Reading the file-backed WO is a read, not a write.
    """
    from core.work_orders.models import WorkOrderError
    from core.work_orders.renderers import render_packet_text
    from core.work_orders.storage import load_work_order
    from core.work_orders.validation import validate_work_order

    try:
        work_order, _ = load_work_order(work_order_id, storage_root=storage_root)
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    result = validate_work_order(work_order)
    if not result.ok:
        print(result.format(), file=sys.stderr)
        return 1
    print(render_packet_text(result.work_order, target))
    return 0


def _work_order_list(
    *,
    project_id: str | None,
    status_filter: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.queries import list_work_orders

    result = list_work_orders(
        project_id=project_id,
        status_filter=status_filter,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_verify(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.verify import verify_work_order

    result = verify_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=source_root / ".planning",
    )
    if not result.get("ok"):
        print(f"Error: {result.get('error', 'unknown error')}", file=sys.stderr)
        return 1
    passed = result["passed"]
    print(f"Verification {'PASSED' if passed else 'FAILED'}: {result['summary']}")
    for tv in result.get("tasks_verified", []):
        indicator = "✓" if tv["verdict"] == "pass" else ("~" if tv["verdict"] == "partial" else "✗")
        print(f"  {indicator} [{tv['verdict']}] {tv['task_title']}: {tv['evidence']}")
    spawned = result.get("spawned_work_orders", [])
    if spawned:
        print(f"\nGap work orders created ({len(spawned)}):")
        for wo in spawned:
            print(f"  [{wo['type']}] {wo['title']}  (id: {wo['work_order_id']})")
    # WO-FILESDB-C2: verdict_path is None when the verdict was stored in the authority
    # (read it via `ds work-order artifact <id> review_verdict`).
    _vp = result.get("verdict_path")
    print(
        f"\nVerdict: {_vp if _vp else f'authority (ds work-order artifact {work_order_id} review_verdict)'}"
    )
    return 0 if passed else 1


def _work_order_attest(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """WO cef6ddaa residual (ii): record an operator attestation as a passing review verdict.

    For done work with no machine-traceable evidence — an auditable human certification that
    satisfies the independent_review gate. NOT force; the attestation + reason are persisted.
    """
    from core.work_orders.verify import attest_work_order

    result = attest_work_order(
        work_order_id=work_order_id,
        reason=reason,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=source_root / ".planning",
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_next(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_next_work_order

    result = get_next_work_order(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
