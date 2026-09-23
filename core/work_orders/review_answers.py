"""The answers half of the round table.

WHAT WAS MISSING. `core/gates/round_table.py` convenes the lanes, names the reviewer each
judgment lane needs, and prints `awaiting_judgment`. The nine reviewers exist, compiled
from the seats they sit in, each carrying a contract that says exactly what to return.
Nothing carried an answer back: the per-lane entry had no field an answer could go in, so
every review's answers lived in a transcript and the next convening could not tell an
answered lane from an unreached one.

A LANE TESTS; IT DOES NOT READ AND OPINE. Lanes replaced hardcoded seats because a seat
could claim something was wrong without testing it (operator, 2026-09-23). So a `pass`
or a `finding` carries a REPRODUCTION -- the command the reviewer ran in the lane's
container and the exit code it saw -- and this door re-runs it in a fresh container
(`core/gates/lane_sandbox.py`) before storing anything. A reproduction that does not
reproduce is refused. Docker being unavailable refuses the whole submission: there is no
fallback to trusting a pasted transcript. Reading alone can produce `cannot-tell`, which
is first-class and says what would have been needed.

THE ROUND. `ds review --dispatch --work-order W` builds the lane image from one commit and
RECORDS who was asked what. Recording then holds each reviewer to that record rather than
to a scope recomputed at recording time -- the first live convening found the two
disagreeing, so a reviewer that answered exactly what it was sent was reported incomplete,
and could record lanes it was never sent. A later dispatch is a new round.

A FINDING STAYS OPEN UNTIL A LATER ANSWER ON THAT LANE IS A VERIFIED PASS. Every
submission is kept; nothing is overwritten. The first convening found a later record
silently replacing a finding with a pass -- the finding simply vanished. Now the history
is the record, and a finding that became a pass says which round resolved it. And every
dispatch includes the lanes that still hold an open finding, even when the new change set
would not select them by relevance, so a fix cannot escape re-review by moving files.

THE WORK ORDER IS HELD BY THE FINDING ITSELF. `review_status` reports what blocks: no
dispatch, an unanswered lane, an open finding. A finding filed as a task is convenient;
one that could not be filed (no executable check yet) blocks exactly as hard, because the
first convening showed 10 of 12 findings unfilable -- and a gate that turned on filing
would have let all ten through.

Three refusals come from the reviewers' own contract:
  - A REVIEWER ANSWERS ONLY THE LANES IT WAS DISPATCHED. "Do not answer a lane you were
    not given."
  - A FINDING CARRIES EVIDENCE. "A finding with no evidence is an opinion."
  - `cannot-tell` SAYS WHAT WOULD HAVE BEEN NEEDED, in `why` or `evidence`.

WHAT IT CANNOT DO. A reviewer is identified by the name the caller passes. A local CLI has
no identity to check that against; the recorded dispatch bounds what a name may answer,
and the provenance envelope records which commit it was answered against, and neither
proves who typed it. That limit is stated here rather than implied away.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: The closed verdict set, from the reviewers' own contract in
#: integrations/compiler/reviewers.py. One vocabulary, one definition.
LANE_VERDICTS = ("pass", "finding", "cannot-tell")

#: The verdicts that claim something was TESTED, and so must carry a reproduction.
TESTED_VERDICTS = ("pass", "finding")

#: Where a review lives: kind review_verdict, beside the verify verdict (instance_key '').
#: Answers are keyed per reviewer under a prefix; the dispatch has its own key.
ARTIFACT_KIND = "review_verdict"
INSTANCE_PREFIX = "lanes:"
DISPATCH_KEY = "dispatch"

#: The chair's lanes are dispatched to no one -- a subagent sees only its own lanes and
#: cannot reconcile findings it was never given. The caller is the chair, and its decision
#: is the act of advancing the work order or not. They are reported, not gated on.
CHAIR = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instance_key(reviewer: str) -> str:
    """Namespaced so lane answers never collide with the verify verdict or the dispatch.

    `_persist_review_verdict` writes kind=review_verdict at instance_key='' and the close
    gate reads exactly that row.
    """
    return f"{INSTANCE_PREFIX}{reviewer}"


# ── the work order ──────────────────────────────────────────────────────────


def work_order_project(work_order_id: str, *, db_path: Path | None = None) -> str | None:
    """The work order's project, or None when no such work order exists.

    The recording door refuses an id that names no work order. The first convening found
    a mistyped id recording a "complete" review that nothing would ever read: the artifact
    table has no foreign key, so the write succeeded against nothing.
    """
    import sqlite3

    from core.work_orders.artifacts import _resolve_db

    try:
        conn = sqlite3.connect(f"file:{_resolve_db(db_path)}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT project_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return str(row[0]) if row and row[0] else None


# ── the dispatch ────────────────────────────────────────────────────────────


def read_dispatch(work_order_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    from core.work_orders.artifacts import list_wo_artifacts

    for key, content in list_wo_artifacts(work_order_id, ARTIFACT_KIND, db_path=db_path):
        if key == DISPATCH_KEY:
            try:
                return json.loads(content)
            except (ValueError, TypeError):
                return None
    return None


def record_dispatch(
    work_order_id: str,
    *,
    sha: str,
    image: str,
    change_set: list[str] | str,
    assignments: list[dict[str, Any]],
    db_path: Path | None = None,
    project_root: Path | None = None,
    ownership: dict[Any, set[str]] | None = None,
) -> dict[str, Any]:
    """Record who was asked what, against which commit, as a new round.

    Every assignment is held to the registry's seat-to-lane mapping; a lane handed to a
    reviewer whose seat does not own it raises ValueError and nothing is recorded.

    `assignments` is extended with every lane that still holds an open finding, assigned
    to the reviewer that found it -- a finding is resolved by a later verified pass on the
    same lane, and a dispatch that dropped the lane because the new change set did not
    select it would let the finding lapse unanswered.
    """
    owned = lane_ownership(project_root) if ownership is None else ownership
    for slot in assignments:
        reviewer = slot.get("reviewer")
        stray = sorted(set(slot.get("lanes") or []) - set(owned.get(reviewer, ())))
        if stray:
            raise ValueError(
                f"{reviewer or 'the chair'} does not own {', '.join(stray)} in the lane"
                " registry. A dispatch may only hand a reviewer its own seat's lanes --"
                " anything else lets a name answer a question it was never compiled to ask."
            )

    prior = read_dispatch(work_order_id, db_path=db_path)
    round_no = int(prior.get("round", 0)) + 1 if prior else 1

    slots: dict[Any, dict[str, Any]] = {}
    for slot in assignments:
        slots[slot.get("reviewer")] = {
            "reviewer": slot.get("reviewer"),
            "seat": slot.get("seat"),
            "lanes": sorted(set(slot.get("lanes") or [])),
        }
    carried: list[str] = []
    for finding in open_findings(work_order_id, db_path=db_path):
        reviewer = finding.get("reviewer")
        lane = finding.get("lane")
        slot = slots.setdefault(
            reviewer, {"reviewer": reviewer, "seat": finding.get("seat"), "lanes": []}
        )
        if lane not in slot["lanes"]:
            slot["lanes"] = sorted([*slot["lanes"], lane])
            carried.append(lane)

    doc = {
        "round": round_no,
        "sha": sha,
        "image": image,
        "change_set": change_set,
        "assignments": sorted(
            slots.values(), key=lambda s: (s["reviewer"] is None, str(s["reviewer"]))
        ),
        "carried_open_findings": sorted(carried),
        "at": _now(),
    }

    from core.work_orders.artifacts import set_wo_artifact

    stored = set_wo_artifact(
        work_order_id,
        ARTIFACT_KIND,
        json.dumps(doc, indent=2, sort_keys=True),
        instance_key=DISPATCH_KEY,
        db_path=db_path,
        generator="ds review --dispatch",
        project_root=project_root,
    )
    doc["stored"] = stored
    return doc


def lane_ownership(repo_root: Path | None = None) -> dict[Any, set[str]]:
    """Which lanes each reviewer owns, from the registry: lane -> seat -> reviewer.

    The chair's seat has no compiled reviewer and maps to None. Read from the registry
    rather than from a convened table, because a convening leaves out an abstaining seat
    and ownership does not change with who happens to be asked this round.
    """
    from core.gates.round_table import _lanes
    from integrations.compiler.reviewers import reviewer_for_seat

    owned: dict[Any, set[str]] = {}
    for lane in _lanes(repo_root):
        reviewer = reviewer_for_seat(str(lane.get("seat", "")))
        owned.setdefault(reviewer, set()).add(str(lane.get("id")))
    return owned


def dispatched_lanes(dispatch: dict[str, Any] | None, reviewer: str) -> list[str]:
    """The lanes one reviewer was sent in this round. Never recomputed at recording time."""
    for slot in (dispatch or {}).get("assignments") or []:
        if slot.get("reviewer") == reviewer:
            return list(slot.get("lanes") or [])
    return []


# ── validating answers ──────────────────────────────────────────────────────


def validate_answers(
    answers: list[dict[str, Any]],
    *,
    reviewer: str,
    assigned_lanes: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a reviewer's answers into accepted and refused on SHAPE alone.

    No container is run here; `record_answers` verifies reproductions afterwards. Returns
    ``(accepted, refused)``, every refusal named -- a thrown-away answer would report a
    lane answered while the record shows it unanswered.
    """
    accepted: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    seen: set[str] = set()
    assigned = set(assigned_lanes)

    for raw in answers:
        if not isinstance(raw, dict):
            refused.append({"lane": "(malformed)", "reason": f"not an object: {raw!r}"})
            continue

        lane = str(raw.get("lane", "") or "").strip()
        verdict = str(raw.get("verdict", "") or "").strip()
        evidence = str(raw.get("evidence", "") or "").strip()
        why = str(raw.get("why", "") or "").strip()
        check = str(raw.get("check", "") or "").strip()
        declare = str(raw.get("declare", "") or "").strip()
        reproduction = raw.get("reproduction")

        if not lane:
            refused.append({"lane": "(missing)", "reason": "no lane id on the answer"})
            continue
        if lane not in assigned:
            refused.append(
                {
                    "lane": lane,
                    "reason": (
                        f"{reviewer} was not dispatched this lane this round. Its lanes:"
                        f" {', '.join(sorted(assigned)) or '(none)'}"
                    ),
                }
            )
            continue
        if lane in seen:
            refused.append({"lane": lane, "reason": "answered twice in one submission"})
            continue
        if verdict not in LANE_VERDICTS:
            refused.append(
                {
                    "lane": lane,
                    "reason": f"verdict {verdict!r} is not one of {', '.join(LANE_VERDICTS)}",
                }
            )
            continue
        if verdict == "finding" and not evidence:
            refused.append(
                {
                    "lane": lane,
                    "reason": (
                        "a finding with no evidence is an opinion -- say what the"
                        " reproduction's output shows and where the defect is"
                    ),
                }
            )
            continue
        if verdict == "cannot-tell" and not (why or evidence):
            refused.append(
                {"lane": lane, "reason": "cannot-tell must say what would have been needed"}
            )
            continue
        if verdict in TESTED_VERDICTS:
            # A LANE TESTS. A pass says "I ran this and it held"; a finding says "I ran
            # this and it failed". Either without a command is a claim from reading.
            if (
                not isinstance(reproduction, dict)
                or not str(reproduction.get("command", "") or "").strip()
            ):
                refused.append(
                    {
                        "lane": lane,
                        "reason": (
                            f"a {verdict} must carry a reproduction -- the command you ran"
                            " in the lane container and the exit_code it returned. Reading"
                            " alone can only answer cannot-tell."
                        ),
                    }
                )
                continue
            code = reproduction.get("exit_code")
            if not isinstance(code, int) or isinstance(code, bool):
                refused.append(
                    {
                        "lane": lane,
                        "reason": "the reproduction must report the integer exit_code it saw",
                    }
                )
                continue

        seen.add(lane)
        entry = {
            "lane": lane,
            "verdict": verdict,
            "evidence": evidence,
            "why": why,
            "check": check,
            "declare": declare,
        }
        if isinstance(reproduction, dict):
            entry["reproduction"] = {
                "command": str(reproduction.get("command", "") or "").strip(),
                "exit_code": reproduction.get("exit_code"),
            }
        accepted.append(entry)

    return accepted, refused


# ── recording ───────────────────────────────────────────────────────────────


def _reviewer_doc(work_order_id: str, reviewer: str, *, db_path: Path | None) -> dict[str, Any]:
    from core.work_orders.artifacts import list_wo_artifacts

    for key, content in list_wo_artifacts(work_order_id, ARTIFACT_KIND, db_path=db_path):
        if key == _instance_key(reviewer):
            try:
                doc = json.loads(content)
            except (ValueError, TypeError):
                break
            if isinstance(doc, dict):
                doc.setdefault("submissions", [])
                return doc
    return {"reviewer": reviewer, "submissions": []}


def record_answers(
    work_order_id: str,
    reviewer: str,
    answers: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
    project_root: Path | None = None,
    available: Callable[[], tuple[bool, str]] | None = None,
    verify: Callable[..., tuple[bool, dict[str, Any] | None, str]] | None = None,
) -> dict[str, Any]:
    """Validate, verify and store a reviewer's answers for the current round.

    Refuses outright (``{"refused_submission": reason}``, nothing stored) when the work
    order does not exist, when no dispatch is recorded for it, or when Docker cannot run.
    Otherwise every answer is shape-checked, every reproduction re-run, and the
    submission APPENDED to that reviewer's history.

    ``complete`` requires the write to have landed: the first convening found `stored`
    returned False and read by nothing, so a failed write reported a complete review.
    """
    if work_order_project(work_order_id, db_path=db_path) is None:
        return {
            "refused_submission": (
                f"no work order {work_order_id!r} in this authority. A review recorded"
                " against an id that names nothing is a review nobody will ever read."
            )
        }
    dispatch = read_dispatch(work_order_id, db_path=db_path)
    if dispatch is None:
        return {
            "refused_submission": (
                f"no dispatch is recorded for {work_order_id}. Run `ds review --dispatch"
                f" --work-order {work_order_id}` first: it builds the lane image and records"
                " which lanes each reviewer is asked, and answers are held to that record."
            )
        }
    assigned = dispatched_lanes(dispatch, reviewer)
    if not assigned:
        return {
            "refused_submission": (
                f"{reviewer!r} was dispatched no lane in round {dispatch.get('round')} of"
                f" {work_order_id}."
            )
        }

    from core.gates import lane_sandbox

    available = available or lane_sandbox.docker_available
    verify = verify or lane_sandbox.verify_reproduction
    ok, why_not = available()
    if not ok:
        return {
            "refused_submission": (
                f"cannot re-run reproductions: {why_not}. Nothing is recorded -- a"
                " reproduction the door cannot run is a claim it would be taking on trust."
            )
        }

    accepted, refused = validate_answers(answers, reviewer=reviewer, assigned_lanes=assigned)

    verified: list[dict[str, Any]] = []
    image = str(dispatch.get("image", ""))
    for entry in accepted:
        repro = entry.get("reproduction")
        if entry["verdict"] in TESTED_VERDICTS:
            holds, run, reason = verify(image, repro)
            if not holds:
                refused.append({"lane": entry["lane"], "reason": reason, "run": run})
                continue
            entry["run"] = {
                "exit_code": run.get("exit_code") if run else None,
                "output_sha256": run.get("output_sha256") if run else None,
                "output_tail": (run.get("output_tail") or "")[-1500:] if run else "",
                "image": image,
            }
        verified.append(entry)

    doc = _reviewer_doc(work_order_id, reviewer, db_path=db_path)
    round_no = int(dispatch.get("round", 1))
    if verified:
        doc["submissions"].append({"round": round_no, "at": _now(), "lanes": verified})

    answered_this_round = {
        lane["lane"]
        for sub in doc["submissions"]
        if int(sub.get("round", 0)) == round_no
        for lane in sub.get("lanes") or []
    }
    unanswered = sorted(set(assigned) - answered_this_round)

    stored = True
    if verified:
        from core.work_orders.artifacts import set_wo_artifact

        stored = set_wo_artifact(
            work_order_id,
            ARTIFACT_KIND,
            json.dumps(doc, indent=2, sort_keys=True),
            instance_key=_instance_key(reviewer),
            db_path=db_path,
            generator=f"ds review --record ({reviewer})",
            project_root=project_root,
        )

    return {
        "reviewer": reviewer,
        "work_order_id": work_order_id,
        "round": round_no,
        "stored": stored,
        "accepted": verified,
        "refused": refused,
        "unanswered": unanswered,
        "complete": bool(stored) and not unanswered and not refused,
    }


# ── reading back ────────────────────────────────────────────────────────────


def _all_reviewer_docs(work_order_id: str, *, db_path: Path | None) -> list[dict[str, Any]]:
    from core.work_orders.artifacts import list_wo_artifacts

    docs = []
    for key, content in list_wo_artifacts(work_order_id, ARTIFACT_KIND, db_path=db_path):
        if not key.startswith(INSTANCE_PREFIX):
            continue
        try:
            doc = json.loads(content)
        except (ValueError, TypeError):
            continue
        if isinstance(doc, dict):
            doc.setdefault("reviewer", key.removeprefix(INSTANCE_PREFIX))
            doc.setdefault("submissions", [])
            docs.append(doc)
    return docs


def recorded_answers(work_order_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    """The CURRENT answer per (reviewer, lane): the latest one recorded.

    Each carries ``round`` and, when an earlier answer on the same lane was a finding and
    this one is a pass, ``resolves_finding_from_round`` -- so a finding that became a pass
    says so instead of vanishing.
    """
    out: list[dict[str, Any]] = []
    for doc in _all_reviewer_docs(work_order_id, db_path=db_path):
        reviewer = str(doc["reviewer"])
        latest: dict[str, dict[str, Any]] = {}
        found_in: dict[str, int] = {}
        for sub in doc["submissions"]:
            for lane in sub.get("lanes") or []:
                name = str(lane.get("lane"))
                entry = dict(lane)
                entry["reviewer"] = reviewer
                entry["round"] = int(sub.get("round", 0))
                if name in latest and latest[name].get("verdict") == "finding":
                    found_in.setdefault(name, latest[name]["round"])
                latest[name] = entry
        for name, entry in latest.items():
            if entry.get("verdict") == "pass" and name in found_in:
                entry["resolves_finding_from_round"] = found_in[name]
            out.append(entry)
    return sorted(out, key=lambda e: (str(e.get("reviewer")), str(e.get("lane"))))


def open_findings(work_order_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Lanes whose latest recorded answer is a finding."""
    return [
        a for a in recorded_answers(work_order_id, db_path=db_path) if a.get("verdict") == "finding"
    ]


def review_status(work_order_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    """What the review of this work order currently holds, and whether it blocks.

    Blocks on: no dispatch recorded; a lane dispatched this round that no reviewer has
    answered; any open finding, filed as a task or not. `cannot-tell` is reported, not
    blocked on -- it is an honest answer, and the chair decides what to do with it.
    """
    dispatch = read_dispatch(work_order_id, db_path=db_path)
    answers = recorded_answers(work_order_id, db_path=db_path)
    findings = [a for a in answers if a.get("verdict") == "finding"]
    cannot_tell = [a for a in answers if a.get("verdict") == "cannot-tell"]
    resolved = [a for a in answers if a.get("resolves_finding_from_round")]

    reasons: list[str] = []
    unanswered: dict[str, list[str]] = {}
    chair_lanes: list[str] = []
    if dispatch is None:
        reasons.append("no review has been dispatched for this work order")
    else:
        round_no = int(dispatch.get("round", 1))
        this_round = {
            (a["reviewer"], a["lane"]) for a in answers if int(a.get("round", 0)) == round_no
        }
        for slot in dispatch.get("assignments") or []:
            reviewer = slot.get("reviewer")
            if reviewer is CHAIR:
                chair_lanes.extend(slot.get("lanes") or [])
                continue
            missing = [ln for ln in slot.get("lanes") or [] if (reviewer, ln) not in this_round]
            if missing:
                unanswered[str(reviewer)] = missing
        if unanswered:
            count = sum(len(v) for v in unanswered.values())
            reasons.append(f"{count} dispatched lane(s) unanswered in round {round_no}")
    if findings:
        reasons.append(f"{len(findings)} open finding(s)")

    return {
        "work_order_id": work_order_id,
        "dispatched": dispatch is not None,
        "round": (dispatch or {}).get("round"),
        "sha": (dispatch or {}).get("sha"),
        "image": (dispatch or {}).get("image"),
        "unanswered": unanswered,
        "open_findings": findings,
        "cannot_tell": cannot_tell,
        "resolved": resolved,
        "chair_lanes": sorted(chair_lanes),
        "blocking": bool(reasons),
        "reasons": reasons,
    }


# ── findings become work ────────────────────────────────────────────────────


def finding_as_task(finding: dict[str, Any]) -> dict[str, Any]:
    """One finding, shaped as a task proposal for the admission gate.

    The title names the LANE, because that is the finding's identity across rounds: a
    reviewer that rewords the same defect between convenings produces a new sentence for
    the same lane, and title dedup one level down cannot see through a reworded title.
    """
    lane = str(finding.get("lane", "") or "unknown-lane")
    why = str(finding.get("why", "") or "").strip()
    evidence = str(finding.get("evidence", "") or "").strip()
    reviewer = str(finding.get("reviewer", "") or "a reviewer")
    repro = finding.get("reproduction") or {}

    summary = why or evidence or "see the recorded finding"
    reproduce = (
        f"\n\nReproduce (exits {repro.get('exit_code')} in the lane image):"
        f" {repro.get('command')}"
        if repro.get("command")
        else ""
    )
    return {
        "title": f"Answer the {lane} finding",
        # The reviewer's own check when it gave one. Admission decides whether it is
        # executable; this module does not invent one, because a criterion invented here
        # is exactly the unfalsifiable claim the admission gate was built to refuse.
        "acceptance_criteria": str(finding.get("check", "") or "").strip() or None,
        # THE PROSE IS A DESCRIPTION, NOT A DECLARATION. `admit_task`'s `why` answers
        # one narrow question -- why this claim CANNOT be computed -- and a task
        # admitted on it is recorded as declared, the formal no-criterion route.
        #
        # Found by this module's own test. Passing the finding's explanation as `why`
        # satisfied that door on length alone, so every finding was admitted with no
        # check and stamped as a declared one -- the stub factory the admission gate
        # was built to close, re-entered through the field names.
        "description": (
            f"{reviewer} on lane {lane}: {summary}\n\nEvidence: {evidence}{reproduce}"
        ).strip(),
        # Only when the reviewer explicitly declares the check cannot be computed.
        "why": str(finding.get("declare", "") or "").strip() or None,
    }


def file_findings_as_tasks(
    work_order_id: str,
    *,
    project_id: str,
    db_path: Path | None = None,
    conn: Any = None,
) -> dict[str, Any]:
    """File each open finding as a task on the work order under review.

    Goes through `_attach_gap_tasks`, which already dedupes on title AND criterion, runs
    each proposal past `admit_task`, and returns what it refused rather than dropping it.
    An unfiled finding still blocks the work order through `review_status`; filing is
    for tracking the work, not for making the finding count.
    """
    findings = open_findings(work_order_id, db_path=db_path)
    if not findings:
        return {"added": 0, "unfiled": [], "noted": [], "findings": 0}

    tasks = [finding_as_task(f) for f in findings]

    # Imported from the module that owns the filing rules rather than reimplemented.
    from core.work_orders.verify_gaps import _attach_gap_tasks

    opened = False
    if conn is None:
        import sqlite3

        from core.work_orders.artifacts import _resolve_db

        conn = sqlite3.connect(str(_resolve_db(db_path)))
        opened = True
    try:
        result = _attach_gap_tasks(
            conn,
            work_order_id=work_order_id,
            project_id=project_id,
            tasks=tasks,
            now=_now(),
            gap_key="review-lane",
        )
        if opened:
            conn.commit()
    finally:
        if opened:
            conn.close()

    result["findings"] = len(findings)
    return result
