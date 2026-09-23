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

WHO MAY ANSWER. Each dispatch issues every named reviewer a one-time credential, stores
only its sha256, and returns the plaintext once to the dispatcher, who hands each reviewer
its own. A submission must carry the credential issued to the reviewer it claims to be, and
a round with no credential on record fails closed -- so one seat cannot answer as another,
the evidence-referee included. The recorded dispatch bounds which lanes a reviewer may
answer; the provenance envelope records which commit it answered against.

WHAT IT CANNOT DO. The dispatcher holds every credential it issues, because handing them
out is its job. That is the chair -- the operator's own process -- and it is the trust
boundary: a local tool without an identity system cannot prove the chair did not answer
as a seat. The limit is stated here rather than implied away.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# The one work-order -> project lookup; the review door refuses a miss rather than
# recording a review against an id that names nothing.
from core.work_orders.queries import work_order_project  # noqa: E402,F401

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
#: is the act of advancing the work order or not. They are reported, not gated on. Only
#: the chair's SEAT is the chair's: another seat with no compiled reviewer is a question
#: nobody can answer, and it blocks as unanswered.
CHAIR_SEAT = "Chair and verdict owner"

#: The lane that judges whether a replacement test actually exercises the defect it
#: resolves. The door proves a `resolves_with` test discriminates the fix; only a judgment
#: can say it is ABOUT the defect, and this is the seat whose question that is.
REFEREE_LANE = "evidence-referee"


def _credential_hash(credential: str) -> str:
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instance_key(reviewer: str) -> str:
    """Namespaced so lane answers never collide with the verify verdict or the dispatch.

    `_persist_review_verdict` writes kind=review_verdict at instance_key='' and the close
    gate reads exactly that row.
    """
    return f"{INSTANCE_PREFIX}{reviewer}"


# ── the work order ──────────────────────────────────────────────────────────


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
    # THE MECHANISM CHECKS, not one caller. The existence check lived in the CLI's
    # dispatch handler only, so any other caller could record a round against an id that
    # names nothing (the bench's boundary-semantics seat, round two).
    if work_order_project(work_order_id, db_path=db_path) is None:
        raise ValueError(f"no work order {work_order_id!r} in this authority")

    owned = lane_ownership(project_root) if ownership is None else ownership
    for slot in assignments:
        reviewer = slot.get("reviewer")
        key = _owner_key(reviewer, slot.get("seat"))
        stray = sorted(set(slot.get("lanes") or []) - set(owned.get(key, ())))
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
        # Keyed by reviewer, or by seat when there is none, so two reviewer-less seats do
        # not collapse into one slot.
        slots[_owner_key(slot.get("reviewer"), slot.get("seat"))] = {
            "reviewer": slot.get("reviewer"),
            "seat": slot.get("seat"),
            "lanes": sorted(set(slot.get("lanes") or [])),
        }
    carried: list[str] = []
    for finding in open_findings(work_order_id, db_path=db_path):
        reviewer = finding.get("reviewer")
        lane = finding.get("lane")
        slot = slots.setdefault(
            _owner_key(reviewer, finding.get("seat")),
            {"reviewer": reviewer, "seat": finding.get("seat"), "lanes": []},
        )
        if lane not in slot["lanes"]:
            slot["lanes"] = sorted([*slot["lanes"], lane])
            carried.append(lane)

    # A REPLACEMENT RESOLUTION GOES TO THE REFEREE. It proves the test discriminates the
    # two commits, not that the test is about the defect -- a grep of churned source did
    # it in round four. The evidence-referee is carried to its owner so that judgment is
    # made, and review_status blocks until it has been.
    if awaiting_referee(work_order_id, db_path=db_path):
        referee = next((key for key, lanes in owned.items() if REFEREE_LANE in lanes), None)
        if referee is None:
            raise ValueError(
                f"a finding was resolved by a replacement test and no seat owns"
                f" {REFEREE_LANE!r} to judge whether that test exercises the defect"
            )
        is_seat = str(referee).startswith("seat:")
        slot = slots.setdefault(
            referee,
            {
                "reviewer": None if is_seat else referee,
                "seat": str(referee).removeprefix("seat:") if is_seat else None,
                "lanes": [],
            },
        )
        if REFEREE_LANE not in slot["lanes"]:
            slot["lanes"] = sorted([*slot["lanes"], REFEREE_LANE])
            carried.append(REFEREE_LANE)

    # ONE CREDENTIAL PER NAMED REVIEWER, hashed at rest. The plaintext leaves this function
    # once, in its return value, for the dispatcher to hand each reviewer its own.
    # HEX, because a url-safe token can begin with "-", and `--credential -abc...` is read
    # by argparse as a new option: the command fails at random, one dispatch in sixty-four.
    # Found by the recording door re-running a reviewer's pass in round six and getting the
    # other side of the coin.
    credentials = {
        str(slot["reviewer"]): secrets.token_hex(16)
        for slot in slots.values()
        if slot.get("reviewer")
    }

    doc = {
        "credential_hashes": {name: _credential_hash(c) for name, c in credentials.items()},
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
    doc["credentials"] = credentials  # returned, never stored
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
        seat = str(lane.get("seat", ""))
        owned.setdefault(_owner_key(reviewer_for_seat(seat), seat), set()).add(str(lane.get("id")))
    return owned


def _owner_key(reviewer: str | None, seat: str | None) -> str:
    """Who owns a lane: the reviewer, or the seat itself when it has no compiled reviewer.

    Keying by reviewer alone put every reviewer-less seat in one None bucket, so the guard
    could not tell the chair's lane from a newly added seat's (boundary-semantics, round
    three). The same key names dispatch slots.
    """
    return reviewer if reviewer else f"seat:{seat}"


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
        resolves_with = str(raw.get("resolves_with", "") or "").strip()
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
        if resolves_with and verdict == "pass":
            entry["resolves_with"] = resolves_with
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


def _current_by_lane(submissions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The answer that currently stands on each lane, with its round.

    A finding opens a lane and only a pass closes it; a cannot-tell becomes current only
    when no finding is open, because "I could not tell" is not "it is fixed". The first
    live convening found a later cannot-tell silently clearing a finding.
    """
    current: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        for lane in submission.get("lanes") or []:
            name = str(lane.get("lane"))
            entry = dict(lane)
            entry["round"] = int(submission.get("round", 0))
            standing = current.get(name)
            if (
                entry.get("verdict") == "cannot-tell"
                and standing is not None
                and standing.get("verdict") == "finding"
            ):
                standing.setdefault("cannot_tell_rounds", []).append(entry["round"])
                continue
            if (
                entry.get("verdict") == "pass"
                and standing is not None
                and standing.get("verdict") == "finding"
            ):
                entry["resolves_finding_from_round"] = standing["round"]
            current[name] = entry
    return current


def record_answers(
    work_order_id: str,
    reviewer: str,
    answers: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
    project_root: Path | None = None,
    available: Callable[[], tuple[bool, str]] | None = None,
    verify: Callable[..., tuple[bool, dict[str, Any] | None, str]] | None = None,
    ensure_image: Callable[[str], str] | None = None,
    credential: str | None = None,
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

    # A NAME IS NOT A REVIEWER, and the check FAILS CLOSED. The referee hold was cleared in
    # round five by an answer under the referee's typed name; the credential issued at
    # dispatch is what a name is now held to. A round with no credential on record for
    # this reviewer -- dispatched before credentials existed, or written by any path but
    # record_dispatch -- is refused rather than waved through: the first version skipped
    # the check when no hash existed, and every such round accepted any credential or none
    # (access-and-reach, round six). The remedy is cheap: dispatch a new round.
    expected = (dispatch.get("credential_hashes") or {}).get(reviewer)
    if not expected:
        return {
            "refused_submission": (
                f"round {dispatch.get('round')} of {work_order_id} carries no credential for"
                f" {reviewer!r}, so nothing can show this submission comes from it. Dispatch"
                f" a new round (`ds review --dispatch --work-order {work_order_id}`), which"
                " issues each reviewer its own."
            )
        }
    if _credential_hash(str(credential or "")) != expected:
        return {
            "refused_submission": (
                f"this submission does not carry the credential issued to {reviewer!r} when"
                f" round {dispatch.get('round')} was dispatched. Each reviewer is handed its"
                " own; one seat cannot answer as another."
            )
        }

    from core.gates import lane_sandbox

    available = available or lane_sandbox.docker_available
    verify = verify or lane_sandbox.verify_reproduction
    ensure_image = ensure_image or lane_sandbox.build_image
    ok, why_not = available()
    if not ok:
        return {
            "refused_submission": (
                f"cannot re-run reproductions: {why_not}. Nothing is recorded -- a"
                " reproduction the door cannot run is a claim it would be taking on trust."
            )
        }

    accepted, refused = validate_answers(answers, reviewer=reviewer, assigned_lanes=assigned)

    doc = _reviewer_doc(work_order_id, reviewer, db_path=db_path)
    standing = _current_by_lane(doc["submissions"])

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
        prior = standing.get(entry["lane"])
        if entry["verdict"] == "pass" and prior and prior.get("verdict") == "finding":
            # A PASS RESOLVES A FINDING ONLY WHEN THE FINDING'S OWN TEST GOES GREEN. The
            # pass's own reproduction proves something held; it does not prove the defect
            # is gone -- a vacuous `true` resolved a real finding in round three. The
            # finding's reproduction exited non-zero because the defect was there; run in
            # this round's image it must now exit 0.
            replacement = entry.get("resolves_with")
            if replacement:
                # A REPLACEMENT TEST MUST DISCRIMINATE THE FIX: fail at the commit the
                # finding was recorded against, pass at this one. Round three found a
                # finding's own reproduction gone stale -- its harness broke on a guard
                # added since -- with the defect fixed and no way to show it.
                old_tag = str((prior.get("run") or {}).get("image") or "")
                if ":" not in old_tag:
                    refused.append(
                        {
                            "lane": entry["lane"],
                            "reason": (
                                f"the finding from round {prior['round']} records no image,"
                                " so a replacement test cannot be run against the commit it"
                                " was found in"
                            ),
                        }
                    )
                    continue
                try:
                    before_image = ensure_image(old_tag.split(":", 1)[1])
                except Exception as exc:  # noqa: BLE001 - reported, never trusted
                    refused.append(
                        {
                            "lane": entry["lane"],
                            "reason": f"cannot rebuild {old_tag} to test the replacement: {exc}",
                        }
                    )
                    continue
                now_ok, now_run, now_reason = verify(
                    image, {"command": replacement, "exit_code": 0}
                )
                if not now_ok:
                    refused.append(
                        {
                            "lane": entry["lane"],
                            "reason": (
                                "the replacement test does not pass at this commit --"
                                f" {now_reason}"
                            ),
                            "run": now_run,
                        }
                    )
                    continue
                before_ok, before_run, _ = verify(
                    before_image, {"command": replacement, "exit_code": 0}
                )
                if before_ok or before_run is None or before_run.get("timed_out"):
                    refused.append(
                        {
                            "lane": entry["lane"],
                            "reason": (
                                f"the replacement test did not fail at {old_tag}, where the"
                                f" finding was recorded in round {prior['round']}, so it does"
                                " not discriminate the fix -- a test that passes before and"
                                " after resolves nothing"
                            ),
                            "run": before_run,
                        }
                    )
                    continue
                entry["resolution_run"] = {
                    "command": replacement,
                    "kind": "replacement",
                    "exit_code_before": before_run.get("exit_code"),
                    "image_before": before_image,
                    "exit_code": now_run.get("exit_code") if now_run else None,
                    "image": image,
                }
                verified.append(entry)
                continue
            found = prior.get("reproduction") or {}
            if not str(found.get("command", "") or "").strip():
                refused.append(
                    {
                        "lane": entry["lane"],
                        "reason": (
                            f"the finding from round {prior['round']} carries no reproduction"
                            " to re-run, so no pass can show it resolved"
                        ),
                    }
                )
                continue
            holds, run, reason = verify(image, {"command": found["command"], "exit_code": 0})
            if not holds:
                refused.append(
                    {
                        "lane": entry["lane"],
                        "reason": (
                            f"lane {entry['lane']} holds an open finding from round"
                            f" {prior['round']}, and a pass resolves it only when that"
                            f" finding's own reproduction now exits 0 -- {reason}. If that"
                            " reproduction has gone stale, give a `resolves_with` test that"
                            " fails at the finding's commit and passes at this one"
                        ),
                        "run": run,
                    }
                )
                continue
            entry["resolution_run"] = {
                "command": found["command"],
                "exit_code": run.get("exit_code") if run else None,
                "output_sha256": run.get("output_sha256") if run else None,
                "image": image,
            }
        verified.append(entry)

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
    """The answer that currently stands per (reviewer, lane).

    A finding stays current until a later verified pass on the lane; that pass carries
    ``resolves_finding_from_round``. A later cannot-tell does not displace a finding; it is
    noted on it as ``cannot_tell_rounds``.
    """
    out: list[dict[str, Any]] = []
    for doc in _all_reviewer_docs(work_order_id, db_path=db_path):
        reviewer = str(doc["reviewer"])
        for entry in _current_by_lane(doc["submissions"]).values():
            entry["reviewer"] = reviewer
            out.append(entry)
    return sorted(out, key=lambda e: (str(e.get("reviewer")), str(e.get("lane"))))


def _answered_in_round(work_order_id: str, round_no: int, *, db_path: Path | None) -> set:
    """(reviewer, lane) pairs answered in a round, from the raw submissions -- so a
    cannot-tell answers its lane even while the finding it did not resolve stays current."""
    answered = set()
    for doc in _all_reviewer_docs(work_order_id, db_path=db_path):
        for submission in doc["submissions"]:
            if int(submission.get("round", 0)) != round_no:
                continue
            for lane in submission.get("lanes") or []:
                answered.add((str(doc["reviewer"]), str(lane.get("lane"))))
    return answered


def awaiting_referee(work_order_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Findings resolved by a replacement test that the evidence-referee has not yet seen.

    Seen means a referee PASS in a round AFTER the one the replacement was recorded in: an
    answer in the same round may have been given before the replacement existed, and a
    cannot-tell certifies nothing.
    """
    last_referee_round = 0
    for doc in _all_reviewer_docs(work_order_id, db_path=db_path):
        for submission in doc["submissions"]:
            for lane in submission.get("lanes") or []:
                # ONLY A PASS RELEASES IT. A referee cannot-tell is an honest "I could not
                # judge this", not a certification; counting it released the hold exactly
                # as a pass would (boundary-semantics, round five) -- round three's
                # cannot-tell-clears-a-finding, one level up. A referee finding is an open
                # finding on its own lane and holds the review by itself.
                if lane.get("lane") == REFEREE_LANE and lane.get("verdict") == "pass":
                    last_referee_round = max(last_referee_round, int(submission.get("round", 0)))
    # FROM THE HISTORY, not the current answer. A later plain pass on the same lane became
    # the current answer and the replacement fell out of view, so the referee requirement
    # vanished without anyone judging it -- found writing the round-five cannot-tell test,
    # whose sibling had been passing for exactly that wrong reason.
    pending: list[dict[str, Any]] = []
    for doc in _all_reviewer_docs(work_order_id, db_path=db_path):
        for submission in doc["submissions"]:
            round_no = int(submission.get("round", 0))
            if round_no < last_referee_round:
                continue
            for lane in submission.get("lanes") or []:
                if (lane.get("resolution_run") or {}).get("kind") == "replacement":
                    entry = dict(lane)
                    entry["reviewer"] = str(doc["reviewer"])
                    entry["round"] = round_no
                    pending.append(entry)
    return sorted(pending, key=lambda e: (str(e.get("reviewer")), str(e.get("lane"))))


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
        this_round = _answered_in_round(work_order_id, round_no, db_path=db_path)
        for slot in dispatch.get("assignments") or []:
            reviewer = slot.get("reviewer")
            if reviewer is None and slot.get("seat") == CHAIR_SEAT:
                chair_lanes.extend(slot.get("lanes") or [])
                continue
            if reviewer is None:
                # A seat with no compiled reviewer: nobody can answer it, so every lane
                # in it is unanswered, and says why.
                unanswered[f"(no reviewer compiled for {slot.get('seat')})"] = list(
                    slot.get("lanes") or []
                )
                continue
            missing = [ln for ln in slot.get("lanes") or [] if (reviewer, ln) not in this_round]
            if missing:
                unanswered[str(reviewer)] = missing
        if unanswered:
            count = sum(len(v) for v in unanswered.values())
            reasons.append(f"{count} dispatched lane(s) unanswered in round {round_no}")
    if findings:
        reasons.append(f"{len(findings)} open finding(s)")
    pending_referee = awaiting_referee(work_order_id, db_path=db_path)
    if pending_referee:
        reasons.append(
            f"{len(pending_referee)} finding(s) resolved by a replacement test await the"
            f" {REFEREE_LANE} lane, which judges whether that test exercises the defect"
        )

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
        "awaiting_referee": pending_referee,
        "chair_lanes": sorted(chair_lanes),
        "blocking": bool(reasons),
        "reasons": reasons,
    }


def lane_review_state(work_order_id: str, *, db_path: Path | None = None) -> str:
    """One word for the record: ``never_dispatched``, ``blocking`` or ``clear``."""
    status = review_status(work_order_id, db_path=db_path)
    if not status["dispatched"]:
        return "never_dispatched"
    return "blocking" if status["blocking"] else "clear"


def lane_review_failure(work_order_id: str, *, db_path: Path | None = None) -> str | None:
    """A close-gate failure when the lane review holds the work order, or never ran.

    None only when a dispatched review is clear. The text starts with ``lane_review`` so the close path's independent_review
    waivers -- which answer whether the verify verdict can be trusted -- never strip it.
    """
    status = review_status(work_order_id, db_path=db_path)
    if not status["dispatched"]:
        # "Never reviewed" is not "reviewed clean". Close accepts only a work order at
        # `pushed` or `ci_issues`, both past review, so a missing dispatch here is a
        # review that never happened. A work order used to be able to close straight from
        # in_progress and was exempt; the phase order removed that path, and the exemption
        # with it.
        return (
            "lane_review: this work order is past review but no review was ever"
            f" dispatched. Run `ds review --dispatch --work-order {work_order_id}`."
        )
    if not status["blocking"]:
        return None
    return (
        f"lane_review: the round {status['round']} lane review still holds this work order"
        f" -- {'; '.join(status['reasons'])}. See `ds review --status --work-order"
        f" {work_order_id}`."
    )


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
