"""Read a review verdict from wherever it actually landed.

The zero-disk migration moved review verdicts into the authority
(``business_work_order_artifacts``, kind ``review_verdict``). ``_persist_review_verdict``
writes there and falls back to ``<planning_root>/work-orders/<id>/review-verdict.json``
only when the authority write fails, and the ``independent_review`` close gate reads
DB-or-disk for exactly that reason.

Several guards still read the disk path unconditionally, so on a healthy authority -- the
normal case -- the file was absent and they failed with FileNotFoundError. Four of main's
eight failures were this, including
``test_verify_unreviewable_no_score_zero_no_spawned_wos``, the guard against a grader
timeout being scored 0.0. So the guard against that defect was down while the defect was
live in production: four unreviewable verdicts were scored 0.0 in one session.

Reading DB-first-then-disk here matches the gate's own behaviour, so these tests assert
what the product actually does rather than where it used to put files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_stored_verdict(
    work_order_id: str,
    *,
    db_path: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Return the stored verdict body, unwrapped from its provenance envelope.

    Raises AssertionError naming both locations when it is in neither -- "the verdict was
    not stored" and "the test looked in the wrong place" are different failures, and a
    bare FileNotFoundError cannot tell them apart.
    """
    raw: str | None = None

    try:
        from core.work_orders.artifacts import get_wo_artifact

        raw = get_wo_artifact(work_order_id, "review_verdict", db_path=db_path)
    except Exception:  # noqa: BLE001 - fall through to the disk fallback below
        raw = None

    if raw is None and planning_root is not None:
        disk = planning_root / "work-orders" / work_order_id / "review-verdict.json"
        if disk.is_file():
            raw = disk.read_text(encoding="utf-8")

    assert raw is not None, (
        f"no review verdict stored for {work_order_id}: absent from the authority"
        f" (business_work_order_artifacts kind='review_verdict') and from"
        f" {planning_root}/work-orders/{work_order_id}/review-verdict.json"
    )

    # get_wo_artifact already unwraps the provenance envelope; a disk fallback may not be
    # wrapped at all. Try the envelope, then fall back to parsing the body directly.
    try:
        from core.work_orders.artifact_envelope import unwrap

        body = unwrap(raw)[0]
    except Exception:  # noqa: BLE001 - an unwrapped body is valid input
        body = raw

    return json.loads(body)
