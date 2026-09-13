"""Gate: the number of tasks nobody can check may not rise.

THE DEFECT THIS EXISTS FOR, measured 2026-09-10 on the live authority: 1766 of 3278 tasks
(53%) carry no acceptance criterion at all. They came from two unguarded doors --
`_attach_gap_tasks` hardcoding `acceptance_criteria: None`, and `add-task --acceptance`
being optional behind a nudge printed AFTER the task was created -- and from a close gate
that requires one executable check per WORK ORDER, so every other task on it may be prose
and the work order still closes.

`core/work_orders/admission.py` stops the number growing at the doors. This is the ratchet
that proves it, and it is a ratchet rather than a demand for zero because operator
direction was freeze-and-burn-down rather than backfill-before-enforcing: a blocking
requirement of zero on day one would have to be met by 1766 invented criteria, and a
criterion invented for a closed work order proves nothing about work already delivered.

WHY A CEILING AND NOT A DIFF SCAN. A diff-scoped check sees the tasks a change set writes,
and tasks are not written by change sets -- they are written at runtime by the CLI and by
review fan-out. Only a population count can see them, so this reads the authority the
operator actually uses.

DELIBERATELY THE SAME SHAPE AS `normative_baseline`, which the operator already accepted
(187, held): a recorded baseline, `--update` as the only way to move it, and the movement
visible in the diff as a reviewable act rather than a silent drift.

IT REPORTS THE COUNT EVEN WHEN CLEAN, because a ratchet that prints nothing on a clean run
is indistinguishable from one that measured nothing -- the fail-open shape
`core/gates/fail_open_probe.py` exists for. And it FAILS rather than passing when the
authority cannot be read: a count of zero from an unreadable database would read as
perfect compliance.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BASELINE_PATH = REPO_ROOT / "canonical" / "task_criteria_baseline.json"

#: A declared reason lives in the task description, mirroring `--why` on `add-task`. A task
#: carrying one is not a stub -- it is a claim someone recorded as uncomputable -- so it is
#: outside the population this gate counts.
#:
#: IMPORTED, NOT RETYPED. The writer and this reader agreed on a hardcoded phrase until
#: the Warden's lane was asked of it; the marker now has one definition, beside the
#: admission check that grants the declaration.
from core.work_orders.admission import DECLARED_PREFIX as DECLARED_MARKER  # noqa: E402


def _db_path() -> Path:
    from core.config.database import _default_db_path

    return Path(_default_db_path())


def measure(db_path: Path | None = None) -> dict[str, object]:
    """Tasks with no acceptance criterion and no declared reason.

    Returns ``status: "unknown"`` with a reason when the authority cannot be read, never a
    count of zero: "I could not look" and "there are none" have different remedies, and
    collapsing them is how a gate starts passing for the wrong reason.
    """
    path = db_path or _db_path()
    if not Path(path).is_file():
        return {"status": "unknown", "reason": f"no authority database at {path}"}
    try:
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"status": "unknown", "reason": f"authority could not be opened ({exc})"}
    try:
        total = conn.execute("SELECT COUNT(*) FROM business_tasks").fetchone()[0]
        rows = conn.execute(
            "SELECT COALESCE(description, '') FROM business_tasks"
            " WHERE acceptance_criteria IS NULL OR TRIM(acceptance_criteria) = ''"
        ).fetchall()
    except sqlite3.Error as exc:
        conn.close()
        return {"status": "unknown", "reason": f"business_tasks could not be read ({exc})"}

    # A SECOND WAY TO BE UNCHECKABLE, and the count above cannot see it (WO f769de79). A
    # task with no criterion is uncheckable because nothing names a check. A task whose
    # criterion is ALSO carried by an open sibling is uncheckable for the opposite reason:
    # a check names it and names the other one too, so one run marks both done and neither
    # can independently fail.
    #
    # MEASURED SEPARATELY, AND ITS FAILURE IS NOT THE GATE'S FAILURE. This began inside the
    # try above, sharing one except with the count that BLOCKS -- so a supplementary
    # observation touching columns the primary count never needed could take the whole gate
    # to UNKNOWN, which fails closed and refuses every push. It did exactly that: the gate's
    # own test fixture has no `status` or `work_order_id` column, and five tests went red
    # reporting "business_tasks could not be read". An observation that can veto the
    # measurement it decorates is worse than no observation, so this one reports None and
    # the ceiling is decided without it.
    shared: int | None
    try:
        shared = conn.execute(
            "SELECT COUNT(*) FROM business_tasks t"
            " WHERE t.status IN ('pending', 'in_progress')"
            "   AND TRIM(COALESCE(t.acceptance_criteria, '')) != ''"
            "   AND EXISTS (SELECT 1 FROM business_tasks o"
            "               WHERE o.work_order_id = t.work_order_id"
            "                 AND o.task_id != t.task_id"
            "                 AND o.status IN ('pending', 'in_progress')"
            "                 AND TRIM(COALESCE(o.acceptance_criteria, ''))"
            "                     = TRIM(COALESCE(t.acceptance_criteria, '')))"
        ).fetchone()[0]
    except sqlite3.Error:
        shared = None
    finally:
        conn.close()

    declared = sum(1 for (description,) in rows if DECLARED_MARKER in description)
    return {
        "status": "computed",
        "total_tasks": total,
        "without_criterion": len(rows),
        "of_those_declared": declared,
        "uncheckable": len(rows) - declared,
        # REPORTED, NOT ADDED TO THE CEILING. Folding this into `uncheckable` would move a
        # blocking baseline under everyone mid-stream and refuse pushes for a number that
        # just changed meaning. Enforcement for new tasks is the Herald refusing them at
        # admission; this is the standing count of what is already filed.
        "shared_criterion": shared,
    }


def _baseline() -> int | None:
    try:
        return int(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["uncheckable"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def run(db_path: Path | None = None) -> dict[str, object]:
    report = measure(db_path)
    ceiling = _baseline()
    report["ceiling"] = ceiling

    if report["status"] != "computed":
        # FAILS, not passes. A gate that cannot measure has not found compliance.
        report["ok"] = False
        report["reason"] = (
            f"{report.get('reason')} -- a count this gate could not take is not a count of"
            " zero, so it blocks rather than reporting clean"
        )
        return report
    if ceiling is None:
        report["ok"] = False
        report["reason"] = (
            f"no baseline recorded at {BASELINE_PATH.name}. Record the current measurement"
            " with --update, in the same change set as the rule that earns it"
        )
        return report

    report["ok"] = int(report["uncheckable"]) <= ceiling
    if not report["ok"]:
        report["reason"] = (
            f"{report['uncheckable']} tasks carry no acceptance criterion and no declared"
            f" reason, against a ceiling of {ceiling}"
            f" (+{int(report['uncheckable']) - ceiling}). A task nobody can check is a claim"
            " that gets marked done by reading. Give it a TEST-CHECK / SQL-CHECK /"
            " API-CHECK, or record why the claim cannot be computed. Raising the ceiling is"
            " a reviewable act: --update, in the same change set as the reason it is earned."
        )
    return report


def update(db_path: Path | None = None) -> dict[str, object]:
    report = measure(db_path)
    if report["status"] != "computed":
        return {"ok": False, **report}
    BASELINE_PATH.write_text(
        json.dumps(
            {
                "uncheckable": report["uncheckable"],
                "total_tasks": report["total_tasks"],
                "note": (
                    "Tasks with no acceptance criterion and no declared reason. This number"
                    " may fall and may not rise. Operator direction 2026-09-10 was"
                    " freeze-and-ratchet rather than backfill-before-enforcing; WO 09a00064"
                    " burns it down, triaging first, because a criterion invented for a"
                    " closed work order proves nothing about work already delivered."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "recorded": report["uncheckable"], **report}


def _render(report: dict[str, object]) -> str:
    if report["status"] != "computed":
        return f"task-criteria-baseline: UNKNOWN - {report.get('reason')}"
    head = (
        f"task-criteria-baseline: {report['uncheckable']} uncheckable of"
        f" {report['total_tasks']} task(s)"
        f" (ceiling {report['ceiling']}; {report['of_those_declared']} declared)"
    )
    # THE OBSERVATION IS PRINTED, NOT ONLY SERIALISED. Deliberately outside the ok
    # decision -- this is not a ceiling -- but a number that appears only under --json is
    # a number nobody reads, which is the same mechanism-with-no-reader shape the count
    # itself exists to surface. Phrased as an observation, and silent at zero so a clean
    # run stays clean.
    # `None` means the observation could not be taken, which is not the same as zero and
    # is not worth a line either -- the gate's own verdict does not rest on it.
    shared = report.get("shared_criterion") or 0
    note = (
        f"\n  NOTED: {shared} open task(s) share an acceptance criterion with a sibling,"
        " so one check run marks both done. Not counted against the ceiling -- a check"
        " can legitimately cover two changes -- but worth confirming it covers both."
        if shared
        else ""
    )
    if report.get("ok"):
        return head + note + "\n  OK - the count has not risen."
    return head + note + "\n  " + str(report.get("reason"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hold the number of uncheckable tasks at or below its baseline."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Record the current measurement as the new ceiling (a reviewable act).",
    )
    args = parser.parse_args(argv)

    report = update() if args.update else run()
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
