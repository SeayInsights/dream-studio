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

A LANE CAN DEMAND HOW, NOT JUST WHETHER. The lane registry already says what to ask;
nothing said how to investigate it well, and four techniques (enumerate every paired
site before answering a shared-predicate question, prove the break with a counterfactual
rather than trusting a guard reads right, fetch a tool's own current docs rather than
answer from memory, verify every cited record by opening it) lived in reviewers' heads the
same way the lane questions themselves once did. `method_requirements` on a lane
(canonical/review_lanes.yml, `METHOD_VOCABULARY` below) names which apply; `validate_answers`
refuses a submission that declares a required technique and carries no structured evidence
for it (`paired_sites`, `counterfactual`, `docs_consulted`, `citations_verified`), the same
enforce-or-refuse shape as the reproduction requirement above, not a softer, separate one.

A SEAT'S PINNED MODEL WAS INVISIBLE HERE. `core.config.seat_providers` lets an operator
pin a seat to a specific model, and `integrations.compiler.reviewers.
resolve_seat_assignment()` already bakes that pin into a COMPILED, INSTALLED subagent
file -- but this module, the live credentialed dispatch path, never consulted it: a
pinned seat's model changed what got installed and nothing about what a live round
actually recorded. `lane_models()` below reads the same pin, pin-aware, for a live
round; `record_dispatch`/`dispatch_review_round` fold the result onto each seat's
assignment slot as a `model` key, and `review_status` reads it back. INFORMATIONAL ONLY:
there is no way to prove which model actually produced a submitted answer, so this is
metadata on the dispatch record, never a check `record_answers` enforces against it.

ONE LANE FIRED REGARDLESS OF WHO WAS BEING REVIEWED. `mission-domain-consequence` (seat
"The receiver's view") asks a CUI/classification question with every cited precedent
Fulcrum-sourced, and carries no `scope:` in canonical/review_lanes.yml -- so
`lane_is_relevant`'s path-based default ("absence means always-relevant") handed it to
every dispatch of every project, Fulcrum or not. `scope:` cannot fix this: the lane isn't
about which files changed, it's about what the software DOES, which
`core/gates/round_table.py` has no business concept of and should not gain one.
`apply_mission_lane_client_gate` is the client-level relevance gate instead, applied as a
post-filter on `dispatch_review_round`'s own `computed_assignments` -- `MISSION_LANE_ID` /
`MISSION_REVIEW_CLIENTS` name what it gates and who it is for. It reads
`business_projects.client_id` back from `_client_id_for_work_order`, the same signal
`reconcile_project_client_from_review` (#871) resolves just before it runs, NEVER the
operator's own active profile (`core.profiles`) -- that names the operator's own working
context, which can disagree with which client the reviewed project itself belongs to.
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

#: THE FOUR TECHNIQUES, as a closed vocabulary -- same reason `LANE_VERDICTS` and the
#: seat roster (`core.gates.review_lane_registry.SEATS`) are closed sets rather than
#: free text: a lane declaring a misspelled technique would require evidence nothing
#: ever checks for, which reads as enforcement and is not. A lane names zero, one, or
#: several of these in its `method_requirements:` list (canonical/review_lanes.yml,
#: authored in scripts/seat_lanes_data.py's `METHOD_REQUIREMENTS` table); `validate_answers`
#: below is the enforcement side, extending the same answer-shape contract that already
#: refuses a `pass` with no reproduction to these four investigation techniques.
METHOD_ENUMERATE_PAIRED_SITES = "enumerate_paired_sites"
METHOD_PROVE_THE_BREAK = "prove_the_break"
METHOD_FETCH_AUTHORITATIVE_DOCS = "fetch_authoritative_docs"
METHOD_VERIFY_CITED_RECORDS = "verify_cited_records"

METHOD_VOCABULARY = (
    METHOD_ENUMERATE_PAIRED_SITES,
    METHOD_PROVE_THE_BREAK,
    METHOD_FETCH_AUTHORITATIVE_DOCS,
    METHOD_VERIFY_CITED_RECORDS,
)

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

#: The one lane canonical/review_lanes.yml gates by CLIENT rather than by changed paths.
#: `core.gates.round_table.lane_is_relevant`'s scope mechanism is PATH-based -- it asks
#: "did the diff touch something this lane cares about" -- and `mission-domain-consequence`
#: has no `scope:` at all (confirmed against the live registry), so that mechanism's own
#: documented default ("a lane with no scope fires unconditionally... absence means
#: always-relevant") hands it to every single dispatch of every project, Fulcrum-related
#: or not. The lane is not about which files changed; it is about what the reviewed
#: software DOES, a different kind of relevance question that `lane_is_relevant`
#: deliberately does not learn -- `core/gates/round_table.py` stays free of any
#: client/work-order concept -- so the second gate belongs here instead, in the module
#: that already crosses that boundary for `reconcile_project_client_from_review`. See
#: `apply_mission_lane_client_gate` below.
MISSION_LANE_ID = "mission-domain-consequence"

#: Clients `mission-domain-consequence`'s CUI/classification question actually applies to.
#: Seeded with just `fulcrum`: every one of the lane's own cited precedents in
#: canonical/review_lanes.yml -- platform#504, platform#673, fulcrum-gateway#53 -- is
#: Fulcrum-sourced, and nothing in the registry backs asking a SeayInsights SaaS product or
#: an open-source library about CUI marking, dissemination controls, or an air-gap
#: assumption. Adding a second client here is a deliberate, reviewed decision that THAT
#: client's own work also warrants this lane -- never inferred from a name or a guess.
MISSION_REVIEW_CLIENTS: frozenset[str] = frozenset({"fulcrum"})


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


def already_dispatched_response(prior: dict[str, Any], sha: str) -> dict[str, Any]:
    """The response record_dispatch() and dispatch_review_round() both return when
    *prior* already carries *sha* and force_new_round was not asked for -- ONE PLACE
    this shape is built, not two separate copies that could drift (the exact signature
    `the-other-half-enforced-by-nothing` exists to catch)."""
    return {
        **prior,
        "stored": True,
        "credentials": {},
        "already_dispatched": True,
        "note": (
            f"round {prior.get('round')} already dispatched at this commit ({sha[:12]})"
            " -- no new round opened, no image rebuilt, no credentials reissued. A"
            " credential is shown once, in its own round's dispatch response, and is"
            " never stored anywhere that could return it again. Pass force_new_round=True"
            " for a fresh round and fresh credentials."
        ),
    }


def resolve_round_content(
    work_order_id: str,
    assignments: list[dict[str, Any]],
    *,
    db_path: Path | None,
    owned: dict[Any, set[str]],
    models: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The (assignments, carried_open_findings) a round dispatched right now with
    *assignments* would actually contain -- open findings and an awaiting referee
    folded in, exactly as `record_dispatch` stores them. Pulled out of `record_dispatch`
    so its idempotency check can compare against precisely what a NEW round would hold,
    not an approximation of it: a redispatch at an unchanged sha with a finding newly
    carried in is a materially different round, and must open one even without
    force_new_round, while a byte-identical redispatch is the no-op this exists for.

    *models* is `lane_models()`'s seat -> resolved model mapping (empty/omitted when the
    caller has none to give). Folded onto each slot by SEAT, after every slot -- fresh,
    carried-finding, and referee -- already exists, so one pass covers all three sources
    rather than three separate writes that could drift. A seat absent from *models*
    (unresolvable, or simply not looked up) keeps no `model` key at all, same as every
    other optional field this module adds only when it has something to say.

    THIS IS WHY A CHANGED PIN FORCES A NEW ROUND. `record_dispatch`'s idempotency check
    compares the PRIOR round's stored assignments against what resolving right now would
    produce; a pin that changed a seat's model between two dispatches of the same commit
    changes that seat's `model` value here, so the comparison correctly reads as new
    content -- not a cache that would miss it.
    """
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

    if models:
        for slot in slots.values():
            seat = slot.get("seat")
            if seat and seat in models:
                slot["model"] = models[seat]

    resolved = sorted(slots.values(), key=lambda s: (s["reviewer"] is None, str(s["reviewer"])))
    return resolved, sorted(carried)


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
    models: dict[str, str] | None = None,
    force_new_round: bool = False,
) -> dict[str, Any]:
    """Record who was asked what, against which commit, as a new round.

    Every assignment is held to the registry's seat-to-lane mapping; a lane handed to a
    reviewer whose seat does not own it raises ValueError and nothing is recorded.

    `assignments` is extended with every lane that still holds an open finding, assigned
    to the reviewer that found it -- a finding is resolved by a later verified pass on the
    same lane, and a dispatch that dropped the lane because the new change set did not
    select it would let the finding lapse unanswered.

    IDEMPOTENT ON (work_order_id, sha, resolved assignments) UNLESS force_new_round.
    Found by a retried ds_review_dispatch call stacking a second round:
    `ds_review_dispatch` (MCP) builds a multi-minute Docker image before reaching
    here, and a caller whose own read timeout fires before that finishes (the
    http_mcp connector's old 30s default, against a build that legitimately takes
    minutes) has no way to know the first call actually completed. Retrying hit this
    function with no guard at all -- a second image build, round N+1, and
    credentials for round N that could never be collected (the plaintext left this
    function once, in round N's own, now-discarded response; nothing here ever
    stores it to reissue).

    RESOLVED, NOT RAW -- comparing against the raw *assignments* argument alone
    would miss a redispatch at the SAME sha that genuinely needs a new round: a
    finding recorded since the last dispatch carries a lane forward
    (`resolve_round_content`'s whole job), and that changes what the round
    actually contains even when the caller passes the identical input. Only a
    redispatch whose fully resolved content -- sha AND assignments AND carried
    findings -- is byte-identical to the standing round is treated as a no-op.
    force_new_round=True always opens a new one regardless, same cost as before
    this existed.

    *models* defaults the same way *ownership* does -- `lane_models(project_root)` when
    omitted -- and is folded into `resolved_assignments` by `resolve_round_content`
    before the idempotency comparison above, so a seat's pin changing between two
    dispatches of the SAME sha is a resolved-content change too: it forces a new round
    exactly like a newly carried finding already does, and an unchanged pin stays
    byte-identical and short-circuits as before this existed.
    """
    # THE MECHANISM CHECKS, not one caller. The existence check lived in the CLI's
    # dispatch handler only, so any other caller could record a round against an id that
    # names nothing (the bench's boundary-semantics seat, round two).
    if work_order_project(work_order_id, db_path=db_path) is None:
        raise ValueError(f"no work order {work_order_id!r} in this authority")

    owned = lane_ownership(project_root) if ownership is None else ownership
    models = lane_models(project_root) if models is None else models
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

    resolved_assignments, carried = resolve_round_content(
        work_order_id, assignments, db_path=db_path, owned=owned, models=models
    )

    prior = read_dispatch(work_order_id, db_path=db_path)
    if (
        prior is not None
        and not force_new_round
        and str(prior.get("sha")) == sha
        and prior.get("assignments") == resolved_assignments
        and prior.get("carried_open_findings") == carried
    ):
        return already_dispatched_response(prior, sha)

    round_no = int(prior.get("round", 0)) + 1 if prior else 1

    # ONE CREDENTIAL PER NAMED REVIEWER, hashed at rest. The plaintext leaves this function
    # once, in its return value, for the dispatcher to hand each reviewer its own.
    # HEX, because a url-safe token can begin with "-", and `--credential -abc...` is read
    # by argparse as a new option: the command fails at random, one dispatch in sixty-four.
    # Found by the recording door re-running a reviewer's pass in round six and getting the
    # other side of the coin.
    credentials = {
        str(slot["reviewer"]): secrets.token_hex(16)
        for slot in resolved_assignments
        if slot.get("reviewer")
    }

    doc = {
        "credential_hashes": {name: _credential_hash(c) for name, c in credentials.items()},
        "round": round_no,
        "sha": sha,
        "image": image,
        "change_set": change_set,
        "assignments": resolved_assignments,
        "carried_open_findings": carried,
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


def _client_id_for_work_order(work_order_id: str, *, db_path: Path | None) -> str | None:
    """`business_projects.client_id` for this work order's project, read fresh -- or None
    when nothing is known: no such work order, no project, the column is NULL, or the
    authority cannot be reached at all.

    A PLAIN COLUMN READ, NOT A SECOND CLASSIFICATION. `core.clients.backfill
    .classify_project_for_work_order` answers a different question -- what a project
    SHOULD map to, guessed from its name/path -- and calling it here would let this gate
    override an operator's own `assign_project_client` call with a guess of its own. By
    the time `dispatch_review_round` reaches this, `reconcile_project_client_from_review`
    has already had its one live chance to correct a stale/default client against the real
    resolved root (#871); this reads exactly what that left standing, never a second,
    independently-derived guess at the same fact.
    """
    import sqlite3

    from core.work_orders.artifacts import _resolve_db

    try:
        conn = sqlite3.connect(f"file:{_resolve_db(db_path)}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT p.client_id FROM business_work_orders w"
            " JOIN business_projects p ON w.project_id = p.project_id"
            " WHERE w.work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return str(row[0]) if row and row[0] else None


def apply_mission_lane_client_gate(
    assignments: list[dict[str, Any]],
    client_id: str | None,
    *,
    lane_id: str = MISSION_LANE_ID,
    mission_clients: frozenset[str] = MISSION_REVIEW_CLIENTS,
) -> list[dict[str, Any]]:
    """Strip *lane_id* out of every assignment slot when *client_id* is affirmatively
    known and not in *mission_clients* -- the client-level relevance gate
    `core.gates.round_table.lane_is_relevant`'s path-based `scope:` mechanism cannot fit,
    because this lane is not asking "did the diff touch X", it is asking "what does this
    software DO" (see `MISSION_LANE_ID`'s own comment above).

    FAILS OPEN ON AN UNKNOWN CLIENT -- same direction, and the same reasoning,
    `lane_is_relevant`'s own "a lane with no scope fires unconditionally... absence means
    always-relevant" default already uses: the cost of wrongly hiding a mission-consequence
    question is a missed classification/mission risk, and this lane's own precedent
    (platform#673, "called the highest-weighted finding in that review" despite being low
    code-severity) is direct evidence that omission can be worse here than for the median
    lane. So `client_id=None` -- no work order, no project_path, or
    `reconcile_project_client_from_review` genuinely could not resolve one -- leaves every
    assignment untouched. Only a client this system actually RECORDED a value for, and
    that value disagreeing with *mission_clients*, excludes the lane.

    THIS HOLDS EVEN WHEN THE RESOLVED CLIENT IS THE DEFAULT, `seayinsights`
    (`core.clients.queries.DEFAULT_CLIENT_ID`). `core.clients.backfill` treats that same
    value as a SENTINEL meaning "not particularly attributed" for one specific purpose --
    deciding whether an automatic reclassification is allowed to overwrite it -- but that
    is a different question from the one asked here. An unrelated SaaS product or an
    open-source library is exactly what resolves to that default, and excluding the lane
    for it is the whole reason this gate exists; treating the default as "unknown" here
    would leave the confirmed problem -- every review asked a CUI question regardless of
    project -- unfixed for the overwhelming majority of real cases.

    A slot left with no lanes after stripping *lane_id* is dropped entirely, not kept as
    an assignment with nothing in it -- a seat that owns other lanes besides this one keeps
    its slot when the change set's own scope selected any of them; a seat whose only
    selected lane WAS this one must not dispatch a reviewer nothing to review.
    """
    if client_id is None or client_id in mission_clients:
        return assignments
    out: list[dict[str, Any]] = []
    for slot in assignments:
        lanes = list(slot.get("lanes") or [])
        if lane_id not in lanes:
            out.append(slot)
            continue
        kept = [ln for ln in lanes if ln != lane_id]
        if kept:
            out.append({**slot, "lanes": kept})
    return out


def dispatch_review_round(
    work_order_id: str,
    *,
    repo_root: Path,
    db_path: Path | None = None,
    force_new_round: bool = False,
) -> dict[str, Any]:
    """Convene the round table against HEAD, build the lane image, and record the
    round -- the same sequence `ds review --dispatch --work-order <id>` runs from a
    terminal. A `core.*` function so a non-CLI caller (the MCP server's
    `ds_review_dispatch` tool) gets the identical sequence rather than a second,
    drifting reimplementation of it.

    Deliberately narrower than the CLI's own `_dispatch`: HEAD only, no `--pr` head
    resolution and no dirty-working-tree warning -- add those here, not in a second
    copy, if a caller needs them.

    Raises RuntimeError when Docker is unavailable (naming why), when no reviewable
    project root could be resolved for this work order, or when that root is not
    itself a git repository (a declared container folder holding several -- see
    `ProjectRoots.primary`'s own docstring on why that is reported honestly rather
    than guessed at). Raises ValueError for an unknown work order or an assignment a
    reviewer's seat does not own (`record_dispatch`'s own check). None of these are
    swallowed into a quiet no-op result.

    REVIEWS THE WORK ORDER'S OWN PROJECT, not *repo_root*. A real, reported bug: this
    used to resolve HEAD and build the lane image from *repo_root* -- Dream Studio's
    own tree, always, regardless of which project the work order actually belongs to.
    A work order delivering into another repository (core.work_orders.project_roots)
    got a container built from Dream Studio's OWN source with no git repository
    inside it at all for that project's code -- every finding would be about the
    wrong codebase, and the reviewed project's own git history was simply absent.
    `repo_root` still has a real job: it is where the lane REGISTRY lives
    (`canonical/review_lanes.yml`) and stays Dream Studio's own tree even when the
    code under review lives elsewhere, exactly as `core.gates.round_table.convene`'s
    own "TWO ROOTS, BECAUSE THEY ARE TWO QUESTIONS" docstring already describes and
    `core.work_orders.verify_main` already fixed for verify's own equivalent call.

    CHECKS IDEMPOTENCY BEFORE THE EXPENSIVE PART. `record_dispatch()` is idempotent on
    (work_order_id, sha, resolved assignments) too, but by the time a caller reaches it
    here, `build_image()` has already spent its minutes -- exactly the cost a retried
    `ds_review_dispatch` call (the http_mcp connector's old 30s read timeout against a
    build that legitimately takes minutes) wastes. `convene()` and the open-findings/
    referee lookup `resolve_round_content` does are both cheap (no Docker); only
    `build_image()` is not, so this resolves the round FIRST and checks it against the
    standing one before ever reaching the build -- the same precise comparison
    `record_dispatch` makes, not an approximation that might short-circuit a redispatch
    a newly carried finding actually needs.
    """
    from core.gates import lane_sandbox
    from core.gates.round_table import assignments, convene
    from core.work_orders.artifacts import _resolve_db
    from core.work_orders.project_roots import resolve_project_roots

    if work_order_project(work_order_id, db_path=db_path) is None:
        raise ValueError(f"no work order {work_order_id!r} in this authority")

    # DOCKER CHECKED FIRST, before anything that needs a real git repository to
    # resolve. Nothing below can succeed without it either way, and checking it here
    # (cheap -- a few-second subprocess call, not `build_image()`'s minutes) answers
    # the more basic precondition before the project-root/git requirements do.
    ok, why_not = lane_sandbox.docker_available()
    if not ok:
        raise RuntimeError(
            f"{why_not} A lane tests in a container; without one there is no review to" " dispatch."
        )

    roots = resolve_project_roots(work_order_id, _resolve_db(db_path))
    change_root = roots.primary
    if change_root is None:
        raise RuntimeError(
            f"no reviewable project root for {work_order_id!r}: {roots.describe()}. A"
            " review must be built from the project's own code, not Dream Studio's --"
            " set this work order's project_path (ds_project_create) to where its code"
            " actually lives."
        )

    # THE ROUND-TABLE BUG: a project registered from wherever the review happened to check
    # code out (a worktree taken under round-table's own tree, say) carries a project_path
    # that names the TOOL's layout, not the client's repository, and the bare path-prefix
    # classifier mistags it -- "round-table/_reviews/plat-roundtable" has no "fulcrum" in it
    # even when every commit inside is Fulcrum's. `roots` is already resolved here, so this
    # reuses it rather than re-deriving a second answer; see
    # `core.clients.backfill.reconcile_project_client_from_review` for the never-overwrite
    # rule that keeps this from clobbering a deliberate client assignment. Best-effort: a
    # client-tagging hiccup must never block a review dispatch.
    try:
        from core.clients.backfill import reconcile_project_client_from_review

        reconcile_project_client_from_review(work_order_id, roots, db_path=db_path)
    except Exception as exc:  # noqa: BLE001 - metadata, never the dispatch itself
        from core.telemetry.diagnostics import log_diagnostic

        log_diagnostic(
            category="failure",
            source="dispatch_review_round.reconcile_project_client_from_review",
            context={"work_order_id": work_order_id},
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
        )

    sha = lane_sandbox.resolve_sha("HEAD", repo_root=change_root)
    report = convene(repo_root=repo_root, change_root=change_root)
    computed_assignments = assignments(report)

    # THE CLIENT GATE. mission-domain-consequence has no `scope:` in
    # canonical/review_lanes.yml, so convene()/assignments() above hand it to every single
    # dispatch of every project regardless of relevance. reconcile_project_client_from_review
    # just above is this project's own live moment of truth for its client -- reading that
    # back is this gate's whole input, never a second guess re-derived here and never the
    # OPERATOR's own active profile (core.profiles.queries.active_profile): that describes
    # the operator's own working context, which can disagree with which client THIS work
    # order's own project actually belongs to, and gating on it would ask the wrong question.
    computed_assignments = apply_mission_lane_client_gate(
        computed_assignments, _client_id_for_work_order(work_order_id, db_path=db_path)
    )

    # BOTH READ FROM THE REGISTRY ROOT, NOT change_root -- the same "two roots" reason
    # this function's own docstring gives for repo_root vs change_root. Letting
    # record_dispatch() default either one from project_root=change_root would resolve
    # seat ownership AND seat models against the wrong tree whenever they differ, so both
    # are computed here and passed through explicitly, never left to that fallback.
    owned = lane_ownership(repo_root)
    models = lane_models(repo_root)
    if not force_new_round:
        resolved, carried = resolve_round_content(
            work_order_id, computed_assignments, db_path=db_path, owned=owned, models=models
        )
        prior = read_dispatch(work_order_id, db_path=db_path)
        if (
            prior is not None
            and str(prior.get("sha")) == sha
            and prior.get("assignments") == resolved
            and prior.get("carried_open_findings") == carried
        ):
            return already_dispatched_response(prior, sha)

    image = lane_sandbox.build_image(sha, repo_root=change_root)
    return record_dispatch(
        work_order_id,
        sha=sha,
        image=image,
        change_set="(local working tree)",
        assignments=computed_assignments,
        db_path=db_path,
        project_root=change_root,
        ownership=owned,
        models=models,
        force_new_round=force_new_round,
    )


def run_review_command(
    work_order_id: str, command: str, *, db_path: Path | None = None
) -> dict[str, Any]:
    """Run one shell command in the dispatched lane's Docker container -- the same
    sequence `ds review --run` runs from a terminal, and what a reviewer uses to
    produce the reproduction a `pass`/`finding` must carry (`core.gates.lane_sandbox`).

    Raises ValueError when no dispatch has been recorded for this work order (nothing
    to run a command against -- dispatch a round first) and RuntimeError when Docker
    is unavailable.

    UNCREDENTIALED ON PURPOSE TO NAME IT: unlike `record_answers` ("the recording
    door"), this does not check who is asking -- any caller who can reach this at all
    can run any command in the lane, scoped only to "a dispatch exists for this work
    order", not to being one of its named reviewers. The lane itself is what bounds
    the blast radius (`--network none`, `--rm`, nothing mounted, built from the commit
    not the working tree -- see `lane_sandbox`'s own docstring), not an identity
    check here. An MCP capability grants a caller this power over EVERY dispatched
    work order at once; that is a real, independent risk to weigh on its own terms
    when deciding who gets `review:run`, not a lesser one because it isn't credentialed
    the way dispatch/record are.
    """
    from core.gates import lane_sandbox

    dispatch = read_dispatch(work_order_id, db_path=db_path)
    if dispatch is None:
        raise ValueError(
            f"no dispatch recorded for {work_order_id!r}; dispatch a review round first"
        )
    ok, why_not = lane_sandbox.docker_available()
    if not ok:
        raise RuntimeError(why_not)
    return lane_sandbox.run_in_lane(str(dispatch["image"]), command)


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
        reviewer = reviewer_for_seat(seat, repo_root=repo_root)
        owned.setdefault(_owner_key(reviewer, seat), set()).add(str(lane.get("id")))
    return owned


def lane_models(repo_root: Path | None = None) -> dict[str, str]:
    """Each seat's live model right now, pin-aware: `core.config.seat_providers`'s pin
    when it names one, else the registry's own per-seat model, aggregated across that
    seat's lanes the same way the compiled reviewer file is
    (`integrations.compiler.reviewers.resolve_live_model`, the live-dispatch counterpart
    of `resolve_seat_assignment`'s compile-time reading of the same pin store).

    INFORMATIONAL METADATA ON A DISPATCH RECORD, NOT ENFORCEMENT. There is no way to
    prove which model actually answered a lane; this records which model a seat was
    CONFIGURED to run on at the moment a round was dispatched, so `record_answers` never
    reads it and no submission is ever accepted or refused on it.

    Read fresh from `_lanes()`, same as `lane_ownership` above and for the same reason: a
    pin can change between two dispatches of the same commit, and the model a round
    records must reflect the pin standing WHEN THAT ROUND WAS DISPATCHED, not whatever a
    later read happens to find.

    Keyed by seat name, not by owner_key/reviewer -- a pin is set per seat, and every
    assignment slot already carries its own seat name to look up here. A seat whose
    lanes cannot resolve to one model (disagreeing, or none declared) is left out rather
    than raising: that is a registry-authoring defect
    `integrations.compiler.reviewers.check()` already owns catching before a push, and
    this is metadata on a dispatch record, not a second gate over the same fact.
    """
    from core.gates.round_table import _lanes
    from integrations.compiler.reviewers import group_by_seat, resolve_live_model

    out: dict[str, str] = {}
    for seat, seat_lanes in group_by_seat(_lanes(repo_root)).items():
        try:
            out[seat] = resolve_live_model(seat, seat_lanes)
        except ValueError as exc:
            # NOT SILENT. Best-effort metadata must not block a dispatch over a registry
            # defect that a dedicated gate (integrations.compiler.reviewers.check(), run
            # at push time) already owns catching -- but swallowing it with no trace at
            # all would be the exact defect-class this repo's own fail-open census
            # exists to find, one level up from the product code it scans.
            from core.telemetry.diagnostics import log_diagnostic

            log_diagnostic(
                category="failure",
                source="review_answers.lane_models",
                context={"seat": seat},
                details={"error_type": type(exc).__name__, "error_message": str(exc)},
            )
            continue
    return out


def lane_method_requirements(repo_root: Path | None = None) -> dict[str, list[str]]:
    """Which of the four techniques each lane requires of its answer, from the registry.

    Read fresh from `_lanes()`, same as `lane_ownership` above and for the same reason: a
    lane's `method_requirements` travels with the registry, not with whoever happens to be
    convening this round. A lane with no `method_requirements` key, or an empty one, is
    simply absent from the result -- `validate_answers` reads a missing lane here as
    "nothing required", which is what keeps this additive: every lane that never opted
    into a technique answers exactly as it did before this existed.
    """
    from core.gates.round_table import _lanes

    out: dict[str, list[str]] = {}
    for lane in _lanes(repo_root):
        required = lane.get("method_requirements") or []
        if isinstance(required, list) and required:
            out[str(lane.get("id"))] = [str(r) for r in required]
    return out


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


def _method_gaps(
    raw: dict[str, Any],
    *,
    verdict: str,
    required: set[str],
    reproduction: Any,
) -> list[str]:
    """Named gaps between the techniques *required* and what this raw answer evidences.

    SHAPE ONLY, same discipline as the rest of `validate_answers`: no container runs here,
    and no attempt is made to parse free text for "a citation" or "a mutation" -- a grep
    standing in for a drive is exactly the substitution `a-channel-outside-the-accounting`'s
    own `measurement` field (canonical/review_lanes.yml) exists to refuse. What this checks
    is that the reviewer filled in the STRUCTURED field each technique demands, not that its
    prose reads well -- the same division `evidence`/`why`/`declare` already draw.
    """
    gaps: list[str] = []

    if METHOD_ENUMERATE_PAIRED_SITES in required:
        sites = raw.get("paired_sites")
        named = [str(s).strip() for s in sites if str(s).strip()] if isinstance(sites, list) else []
        if len(named) < 2:
            gaps.append(
                "enumerate_paired_sites: `paired_sites` must list at least two specific"
                " sites actually inspected (a file:line or symbol each), not just the one"
                " site the diff touched -- checking siblings is the whole point"
            )

    if METHOD_PROVE_THE_BREAK in required and verdict == "pass":
        # A finding's own reproduction already demonstrates the break (it is a command
        # that fails); this is asked only of a pass, which otherwise only ever shows the
        # guard succeeding and never what its absence or a wrong value would look like.
        counterfactual = raw.get("counterfactual")
        if (
            not isinstance(counterfactual, dict)
            or not str(counterfactual.get("command", "") or "").strip()
        ):
            gaps.append(
                "prove_the_break: a pass needs `counterfactual` naming the command run"
                " against the mutated or bypassed guard and the exit_code it produced --"
                " a pass that only re-runs the happy path never showed what breaking the"
                " guard looks like"
            )
        else:
            code = counterfactual.get("exit_code")
            if not isinstance(code, int) or isinstance(code, bool):
                gaps.append("prove_the_break: `counterfactual.exit_code` must be an integer")
            elif isinstance(reproduction, dict) and code == reproduction.get("exit_code"):
                gaps.append(
                    "prove_the_break: `counterfactual.exit_code` is identical to the"
                    " reproduction's own exit_code -- a counterfactual that behaves the"
                    " same as the guarded case proves nothing broke"
                )

    if METHOD_FETCH_AUTHORITATIVE_DOCS in required:
        docs = raw.get("docs_consulted")
        named = [str(d).strip() for d in docs if str(d).strip()] if isinstance(docs, list) else []
        if not named:
            gaps.append(
                "fetch_authoritative_docs: `docs_consulted` must name at least one"
                " document or URL actually fetched for this lane, not reasoned from"
                " training-data memory"
            )

    if METHOD_VERIFY_CITED_RECORDS in required and str(raw.get("evidence", "") or "").strip():
        citations = raw.get("citations_verified")
        named = (
            [str(c).strip() for c in citations if str(c).strip()]
            if isinstance(citations, list)
            else []
        )
        if not named:
            gaps.append(
                "verify_cited_records: this answer's `evidence` cites a record, so"
                " `citations_verified` must name each one actually opened and confirmed --"
                " a citation taken on trust is exactly what this technique exists to refuse"
            )

    return gaps


def validate_answers(
    answers: list[dict[str, Any]],
    *,
    reviewer: str,
    assigned_lanes: list[str],
    method_requirements: dict[str, list[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a reviewer's answers into accepted and refused on SHAPE alone.

    No container is run here; `record_answers` verifies reproductions afterwards. Returns
    ``(accepted, refused)``, every refusal named -- a thrown-away answer would report a
    lane answered while the record shows it unanswered.

    *method_requirements* is lane id -> the techniques (`METHOD_VOCABULARY`) that lane's
    answer must evidence, as declared on the lane itself (`lane_method_requirements`
    reads it from the registry). Defaulting to ``{}`` rather than loading the registry
    here keeps this function a pure shape-check over its own arguments: every existing
    caller that does not pass this keyword enforces nothing new, which is the "no lane
    with no method_requirements regresses" guarantee the four techniques were added
    under -- `record_answers` is what wires the real registry in by default.
    """
    accepted: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    seen: set[str] = set()
    assigned = set(assigned_lanes)
    method_requirements = method_requirements or {}

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
        environment_gap = str(raw.get("environment_gap", "") or "").strip()
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

        required_methods = set(method_requirements.get(lane) or ())
        if required_methods:
            gaps = _method_gaps(
                raw, verdict=verdict, required=required_methods, reproduction=reproduction
            )
            if gaps:
                refused.append({"lane": lane, "reason": "; ".join(gaps)})
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
        if environment_gap:
            entry["environment_gap"] = environment_gap
        if isinstance(reproduction, dict):
            entry["reproduction"] = {
                "command": str(reproduction.get("command", "") or "").strip(),
                "exit_code": reproduction.get("exit_code"),
            }
        if isinstance(raw.get("paired_sites"), list):
            sites = [str(s).strip() for s in raw["paired_sites"] if str(s).strip()]
            if sites:
                entry["paired_sites"] = sites
        if isinstance(raw.get("counterfactual"), dict):
            cf_command = str(raw["counterfactual"].get("command", "") or "").strip()
            if cf_command:
                entry["counterfactual"] = {
                    "command": cf_command,
                    "exit_code": raw["counterfactual"].get("exit_code"),
                }
        if isinstance(raw.get("docs_consulted"), list):
            docs = [str(d).strip() for d in raw["docs_consulted"] if str(d).strip()]
            if docs:
                entry["docs_consulted"] = docs
        if isinstance(raw.get("citations_verified"), list):
            citations = [str(c).strip() for c in raw["citations_verified"] if str(c).strip()]
            if citations:
                entry["citations_verified"] = citations
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
    method_requirements: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Validate, verify and store a reviewer's answers for the current round.

    Refuses outright (``{"refused_submission": reason}``, nothing stored) when the work
    order does not exist, when no dispatch is recorded for it, or when Docker cannot run.
    Otherwise every answer is shape-checked, every reproduction re-run, and the
    submission APPENDED to that reviewer's history.

    ``complete`` requires the write to have landed: the first convening found `stored`
    returned False and read by nothing, so a failed write reported a complete review.

    *method_requirements* defaults to the real registry's own declarations
    (`lane_method_requirements(project_root)`) rather than to "nothing required" -- unlike
    `validate_answers`'s own conservative default, this is the door a live submission
    actually goes through, so it must see what the lane really demands. Injectable for
    the same reason `verify`/`ensure_image` are: a test can hand it a fixed mapping
    without needing a real lane in `canonical/review_lanes.yml` to exercise it.
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

    if method_requirements is None:
        method_requirements = lane_method_requirements(project_root)

    accepted, refused = validate_answers(
        answers,
        reviewer=reviewer,
        assigned_lanes=assigned,
        method_requirements=method_requirements,
    )

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

    # READ BACK FROM THE DISPATCH, not re-resolved live: the model that matters here is
    # the one THIS ROUND actually recorded (`resolve_round_content`'s own "model" key,
    # see lane_models()), not whatever a pin resolves to right now -- those two can
    # differ the moment an operator changes a pin without redispatching. Informational
    # only, same as the field it is read from: this says which model a seat was
    # configured to run on, never which model actually answered it.
    seat_models = {
        str(slot["seat"]): slot["model"]
        for slot in (dispatch or {}).get("assignments") or []
        if slot.get("seat") and slot.get("model")
    }

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
        "seat_models": seat_models,
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
