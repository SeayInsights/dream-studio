"""Admission: the round table decides whether a proposed task may be filed at all.

OPERATOR DIRECTIVE, 2026-09-10: "no stubs, only real registered work ... there needs to be
an independent reviewer of whether or not something can be added. we can use the round
table to review proposed tasks or work orders coming in and determine whether or not they
can even be filed."

WHAT WAS MEASURED FIRST, because the numbers decided the design:

    1766 of 3278 tasks in the live authority carry NO acceptance criterion       (53%)
    `_attach_gap_tasks` hardcoded `"acceptance_criteria": None`      verify_gaps.py
    `ds work-order add-task --acceptance` is OPTIONAL           nothing required it
    the `executable_ac` close gate needs ONE executable check per WORK ORDER,
        so every other task on it may be prose and the work order still closes
    20 of 175 open work orders carry a parseable `Module boundary:` clause       (11%)

So the rules an author would reasonably assume existed did not. They lived in CLI help
text ("Executable AC: TEST-CHECK / SQL-CHECK / API-CHECK") and in a nudge printed after
create -- guidance, with no mechanism, which is where the operator has already said
guidance goes to die. This module is the mechanism.

THE ONE HARD CONSTRAINT: A REFUSED FINDING STILL SURVIVES. Dropping a real finding because
nobody wrote it a criterion is strictly worse than the stub it replaces -- the stub is at
least visible. So this returns refusals to its caller with the seat and the reason, for the
caller to surface. `admit_task` decides; it does not delete.

WHY THE SEATS ARE REUSED RATHER THAN A NEW VOCABULARY INVENTED: the questions are the ones
already registered in `canonical/review_lanes.yml`, asked at intake instead of at review.
The Warden asks whether the predicate that admits is the predicate that delivers, and here
the predicate is literally shared -- `check_token` is imported from the module that RUNS
acceptance criteria, because two sites deciding "is this executable" is the defect this
milestone already paid for twice (WO eac7f657, 2 of 6 criteria disagreeing in both
directions).
"""

from __future__ import annotations

import re as _re
from pathlib import Path
from typing import Any, Iterable, Mapping

#: Minimum characters for a declared reason. Mirrors the `security-scan` exemption
#: contract deliberately: one repo, one shape for "I cannot enforce this, and here is why",
#: so an author who has met one has met them all. A shrug is an escape hatch becoming the
#: norm, and 20 characters is roughly the length at which a reason stops being one.
_MIN_WHY = 20

#: HOW A DECLARED REASON IS RECORDED. The schema has no column for it, so it is
#: composed into the task description behind this marker -- the same way
#: `compose_module_boundary` carries the boundary clause. DEFINED ONCE HERE because two
#: sites read it: the CLI that writes the declaration, and
#: `core/gates/task_criteria_baseline.py`, which must not count a declared task as a
#: stub. They agreed on a hardcoded phrase for about ten minutes, which is the Warden's
#: lane, so the phrase lives here and both import it.
DECLARED_PREFIX = "Filed with no executable criterion, on a declared reason:"


def compose_declared_reason(description: str | None, why: str | None) -> str:
    """Fold a declared reason into a task description, where the ratchet reads it.

    WO 82f608ca. The `--why` a reviewer supplies is what ADMITS a criterion-less task, and
    for the gap paths it was used to grant admission and then dropped -- a bare bypass
    with a nicer spelling, which is what #706 fixed for the CLI and what this function
    exists to stop recurring elsewhere. `task_criteria_baseline` counts a task as declared
    only when `DECLARED_PREFIX` appears in its description, so a reason that never reaches
    the description is a reason nobody can audit and a row the blocking ceiling counts.

    One composer beside the marker, because the writer and the reader agreed on a
    hardcoded phrase once already and the Warden's lane was asked of it.
    """
    declared = " ".join((why or "").split())
    if not declared:
        return description or ""
    body = (description or "").rstrip()
    separator = chr(10) + chr(10) if body else ""
    return body + separator + DECLARED_PREFIX + " " + declared


#: Seats, spelled as the registry spells them. Not imported from `core.gates`: a work-order
#: mutation path must not depend on the gate package to file a task, and the registry gate
#: already refuses a seat outside its closed set, so a typo here fails there.
_WARDEN = "Gate-integrity engineer"
_SURVEYOR = "Merge-order steward"
# Renamed with the bench: the Herald became the Claim and closure auditor, and that
# seat now answers under "Claim integrity" alongside the contract and canon lanes. The
# value is a display label on a refusal record -- never matched or queried -- so this
# keeps admission speaking the roster's vocabulary rather than a name it retired.
_HERALD = "Claim integrity"


#: A path-shaped token: at least one "/" and a file extension. Deliberately narrow.
_PATH_TOKEN = _re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.[A-Za-z0-9]+")


def paths_named(text: str, *, repo_root: "Path | None" = None) -> list[str]:
    """Repo paths a finding's prose names, kept only when they EXIST.

    A HEURISTIC, AND BOUNDED SO IT CANNOT INVENT ATTRIBUTION. Grader findings arrive as
    prose, so the file a finding is about has to be recovered from the text. Guessing wrong
    would make attribution confidently incorrect, which is worse than unknown -- so a token
    is kept only if it resolves to a file that actually exists in the repo. A path that
    cannot be resolved cannot be attributed, and this returns [] rather than a guess.

    The consequence is deliberate asymmetry: this can establish that a finding names files
    OUTSIDE a work order's boundary, and never that a finding belongs INSIDE one on the
    strength of prose alone.
    """
    from pathlib import Path as _Path

    root = _Path(repo_root) if repo_root is not None else _Path.cwd()
    found: list[str] = []
    for token in _PATH_TOKEN.findall(str(text or "")):
        candidate = token.replace("\\", "/").lstrip("./")
        if candidate in found:
            continue
        if (root / candidate).is_file():
            found.append(candidate)
    return found


def _normalised(title: str) -> str:
    return " ".join(str(title or "").split()).strip().lower()


def has_executable_criterion(acceptance_criteria: str | None) -> bool:
    """True when at least one line names a check the executor will actually run.

    THE PREDICATE IS IMPORTED, NOT RESTATED. `check_token` strips a line and matches the
    executor's own token pattern, and it is the function `run_executable_checks` calls at
    its detection site. A second predicate here -- even one that agreed today -- is the
    exact shape that made `acceptance_criteria_determinism` report `PERF-CHECK:` as prose
    while the executor detected it, and `TEST-CHECK :` as executable while the executor
    never saw it. One definition, three readers now.

    Note what "executable" means and does not mean: the executor will ADJUDICATE the line,
    not that it will pass. An unknown `*-CHECK` token is detected and fails closed, which
    is a criterion someone can run -- and a misspelled kind therefore blocks a close rather
    than being silently ignored.
    """
    from core.work_orders.verify_executor import check_token

    return any(
        check_token(line) is not None for line in str(acceptance_criteria or "").splitlines()
    )


def unrunnable_target(acceptance_criteria: str | None) -> str | None:
    """The first TEST-CHECK target that names a file which does not exist, if any.

    `has_executable_criterion` above answers "does a line carry a check TOKEN". It
    never asked whether the thing named can be run, and nothing else did either.

    Measured on the live authority 2026-09-21: of 1,387 tasks carrying a
    TEST-CHECK, 930 named a file that exists and 457 -- ONE IN THREE -- named
    something that cannot be run at all. The corpus includes `a`, `cargo`, `cmd:`
    and a bare `TEST-CHECK:` with nothing after it.

    That is what made this ceremony rather than a check: a third of the time a
    close either blocks or passes for a reason about the CRITERION, telling the
    author nothing about the code. A criterion written against a file that does
    not exist can never fail for the right reason.

    Returns the offending target (for the message) or None when every TEST-CHECK
    resolves. Deliberately only TEST-CHECK: SQL-CHECK and API-CHECK name a query
    and an endpoint, which are not paths and cannot be checked this cheaply.
    """
    import re
    from pathlib import Path as _Path

    for line in str(acceptance_criteria or "").splitlines():
        m = re.search(r"TEST-CHECK\s*:\s*(\S*)", line)
        if not m:
            continue
        raw = m.group(1).strip().strip("`\"'")
        if not raw:
            return "(nothing after TEST-CHECK:)"
        # `::test_name` with no path is a legitimate shape -- the executor resolves it
        # against the whole suite.
        if raw.startswith("::"):
            continue
        target = raw.split("::")[0].strip().strip("`\"'")
        if not target:
            return "(nothing after TEST-CHECK:)"
        looks_like_a_path = "/" in target or "\\" in target or target.endswith(".py")
        if not looks_like_a_path:
            # Not a path and not a node id. The live corpus holds `a`, `cargo` and
            # `cmd:` in this position -- words that name nothing the executor can run.
            return target
        if not _Path(target).is_file():
            return target
    return None


def declared_reason(description: str | None) -> str:
    """The reason `compose_declared_reason` folded into a description, or "".

    The composer had no reader outside the ratchet, so a task filed on a declared reason
    could not be re-admitted from its own row -- only from the `--why` that was passed
    once, at the CLI, and nowhere else. Paired with the composer here so the marker keeps
    one definition and two users.
    """
    text = str(description or "")
    marker = text.rfind(DECLARED_PREFIX)
    if marker < 0:
        return ""
    start = marker + len(DECLARED_PREFIX)
    return " ".join(text[start:].split())


def criterion_refusal(
    acceptance_criteria: str | None,
    *,
    why: str | None = None,
    description: str | None = None,
) -> dict[str, Any] | None:
    """The Warden's lane, asked of ANY door rather than only the one the CLI opens.

    `admit_task` runs the whole round table and needs a work order's description, its
    sibling titles and the repo to do it. That is the right check for an operator filing
    by hand and the wrong dependency for `create_task`, which is the door
    `core/work_orders/mutations.py` tells skills, workflows and hooks to import directly.
    So the one lane that needs no context at all -- whether a criterion exists and can be
    run, which is a property of the text -- is available on its own.

    `why` is the reason an author passes now; `description` is where a reason passed
    EARLIER was folded by `compose_declared_reason`, which is how a task already admitted
    on a declared reason stays admitted when its row is re-read.
    """
    return _warden(acceptance_criteria, why or declared_reason(description))


def _warden(acceptance_criteria: str | None, why: str | None) -> dict[str, Any] | None:
    """Enforce-or-declare, the contract `canonical/rules.yml` already runs on."""
    if has_executable_criterion(acceptance_criteria):
        # A TOKEN IS NOT A CHECK. The criterion carries TEST-CHECK, so the door used
        # to open here -- without anyone asking whether the thing it names can be run.
        # One in three could not: 457 of 1,387 on the live authority, including `a`,
        # `cargo`, `cmd:` and a bare `TEST-CHECK:`.
        #
        # This is the difference between a check and ceremony. A criterion pointed at
        # a file that does not exist can never fail for the right reason, so a close
        # that turns on it tells the author about the paperwork, not the code.
        #
        # Refused at the WRITE door, which is the only place it is cheap: at close
        # time the author has finished the work and the criterion is someone else's
        # mistake from weeks ago.
        bad = unrunnable_target(acceptance_criteria)
        if bad:
            return {
                "seat": _WARDEN,
                "lane": "a-criterion-nobody-can-run",
                "reason": (
                    f"TEST-CHECK names {bad!r}, which is not a file that exists and not"
                    " a `::node_id`. A criterion nothing can run cannot fail for the"
                    " right reason, so a close that turns on it reports the paperwork"
                    " rather than the code. Point it at a test file that exists, or use"
                    " SQL-CHECK / API-CHECK, or declare a reason with --why."
                ),
            }
        return None
    declared = " ".join(str(why or "").split())
    if len(declared) >= _MIN_WHY:
        return None
    if declared:
        return {
            "seat": _WARDEN,
            "lane": "a-criterion-nobody-can-run",
            "reason": (
                f"no executable criterion, and the declared reason is {len(declared)}"
                f" characters -- {_MIN_WHY} are required, because a reason shorter than that"
                " is a shrug, and an escape hatch that costs nothing becomes the norm"
            ),
        }
    return {
        "seat": _WARDEN,
        "lane": "a-criterion-nobody-can-run",
        "reason": (
            "no executable criterion and no declared reason. A task nobody can check is a"
            " claim that gets marked done by reading -- name a TEST-CHECK / SQL-CHECK /"
            " API-CHECK, or declare in at least"
            f" {_MIN_WHY} characters why this claim cannot be computed"
        ),
    }


def _surveyor(
    target_paths: Iterable[str], work_order_description: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Is this finding attributable to THIS work order? Returns ``(refusal, unknown)``.

    THREE STATES, AND THE THIRD IS WHY `path_in_boundary` IS NOT USED HERE. That helper
    returns True when no boundary is declared -- a sensible default for an advisory edit
    check, and a fail-open for an admission decision, because "no boundary" would read as
    "in boundary" and admit everything. Measured on the live authority: only 20 of 175 open
    work orders carry a parseable clause, so that default would decide 89% of cases by
    accident. Unknown is reported instead, and reported is not admitted-quietly: the caller
    surfaces it, which is what creates pressure to declare a boundary.

    The clause is parsed by the shared `boundary_globs` so the producer of the clause
    (`compose_module_boundary`) and every consumer keep reading one format.
    """
    paths = [str(p) for p in target_paths if str(p or "").strip()]
    if not paths:
        return None, None

    from runtime.lib.enforcement import boundary_globs

    globs = boundary_globs(work_order_description or "")
    if not globs:
        return None, {
            "seat": _SURVEYOR,
            "lane": "a-finding-filed-on-the-wrong-work-order",
            "reason": (
                "this work order declares no `Module boundary:` clause, so whether"
                f" {', '.join(paths[:3])} belongs to it cannot be judged. Attribution is"
                " UNKNOWN, not confirmed -- declare a boundary with"
                " `ds work-order create --module-boundary` to have it checked"
            ),
        }

    inside = [p for p in paths if any(p.replace("\\", "/").startswith(g) for g in globs)]
    if inside:
        return None, None
    return {
        "seat": _SURVEYOR,
        "lane": "a-finding-filed-on-the-wrong-work-order",
        "reason": (
            f"none of {', '.join(paths[:3])} falls inside this work order's boundary"
            f" ({', '.join(globs[:3])}). A finding about another module's code filed here"
            " makes this work order un-closable for work it never owned -- register it"
            " against the work order whose boundary contains the file"
        ),
    }, None


def _herald(
    title: str,
    existing_titles: Iterable[str],
    acceptance_criteria: str | None = None,
    existing_criteria: Iterable[str] | Mapping[str, str] = (),
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Is this finding already filed on this work order? Returns ``(refusal, unknown)``.

    THE TITLE WAS THE WRONG FIELD TO ASK ALONE. This lane's question has always been
    "already filed?"; it answered it from free text, which a grader rewords between verify
    rounds without meaning anything by it. Measured on the live authority: 4 groups
    covering 9 OPEN tasks share a work order and an acceptance criterion, and in every one
    of the 35 same-key duplicate groups the titles DIFFER -- so title dedup caught none of
    them. Two are confirmed restatements of one item, filed on WO 1364e05e and WO 66069823
    as "Add the instrument assertion to the docstring test" and "Add the instrument
    assertion to the MIRROR-DECISION docstring test".

    A SHARED CRITERION REPORTS UNKNOWN AND DOES NOT REFUSE, and the first cut of this lane
    had it as a refusal. What changed it was a counter-example in the same measurement it
    was built from. WO 20796691 carries "Fold the producibility column into the
    measured-overlap table" and "Add the absence assertion the node was named for" under
    one node: the first edits the docstring, the second strengthens the assertion that
    reads it, and the node only passes once BOTH are done. That is two genuine pieces of
    work one check legitimately covers, and a refusal would have called it a duplicate.

    So the two cases are indistinguishable from here. A restatement and a
    one-node-two-changes pair look identical in the fields this lane can see, and the
    difference is whether the check actually exercises both -- which nothing at admission
    time knows. `_surveyor` already had this shape for the boundary it cannot resolve, and
    the module docstring already says why: a decision made on evidence the reviewer does
    not have is a guess wearing a verdict's clothes. Reported, and reported is not
    admitted-quietly -- the caller surfaces it, which is what creates the pressure to
    either distinguish the criteria or merge the tasks.

    WHY NOT THE GAP KEY, which was the obvious candidate. The gap key names a CATEGORY, not
    an item: `advisory::add-missing-adversarial-tests-for-durable-reachable-failure-modes`
    legitimately covers nine different functions. Deduping there would drop real work. The
    criterion is the level at which two tasks are plausibly the same claim -- plausibly,
    which is why this reports rather than decides.

    Only a criterion something can RUN is compared. A declared-reason task carries no
    criterion, and treating two absent criteria as equal would flag every second declared
    task on a work order -- a report about a shared blank, which is no signal at all.
    """
    existing = {_normalised(t) for t in existing_titles}
    if _normalised(title) in existing:
        return {
            "seat": _HERALD,
            "lane": "a-finding-already-filed",
            "reason": (
                "a task with this title is already on this work order. Re-filing it adds a"
                " second row for one finding, and the count of open work stops meaning"
                " anything"
            ),
        }, None

    if has_executable_criterion(acceptance_criteria):
        mine = _normalised(acceptance_criteria or "")
        # THE SIBLING IS NAMED, NOT JUST ITS CRITERION (second review round on this work
        # order). The first cut plumbed bare criterion strings, so the observation could
        # quote the shared check and could not say WHICH open task already held it -- an
        # operator told a duplicate exists with nowhere to look is told nothing actionable.
        # A mapping of criterion -> task title is accepted, and a plain iterable still
        # works: callers that have only the strings keep their current behaviour and get
        # the observation without the name, rather than the lane going silent for them.
        if isinstance(existing_criteria, Mapping):
            already = {
                _normalised(c or ""): str(t or "")
                for c, t in existing_criteria.items()
                if has_executable_criterion(c)
            }
        else:
            already = {
                _normalised(c or ""): "" for c in existing_criteria if has_executable_criterion(c)
            }
        if mine in already:
            holder = already.get(mine) or ""
            held_by = f' It is carried by the open task "{holder[:80]}".' if holder else ""
            return None, {
                "seat": _HERALD,
                "lane": "a-finding-already-filed",
                # TWO KINDS OF UNKNOWN, AND ONLY ONE IS WORTH INTERRUPTING SOMEONE WITH.
                # The Surveyor's unknown means "I could not look" -- it fires wherever no
                # boundary is declared, which is 155 of 175 open work orders, so surfacing
                # it on every filing would be noise an operator learns to scroll past.
                # This one means "I looked, and here is the specific thing I found." A
                # caller that wants to print unknowns can tell them apart by this flag
                # instead of by matching a seat name, which would bind the surface to the
                # roster.
                "observed": True,
                "holder": holder or None,
                "reason": (
                    "an open task on this work order already carries this exact acceptance"
                    f" criterion ({str(acceptance_criteria or '').strip()[:120]}).{held_by}"
                    " One check run will mark both done, so neither can fail independently"
                    " of the other. That is correct when the check genuinely exercises both"
                    " changes and wrong when this is the earlier finding reworded -- and"
                    " which one it is cannot be told from a title and a criterion, so it is"
                    " reported rather than decided. Confirm the check covers both, or give"
                    " this one a criterion that distinguishes it"
                ),
            }
    return None, None


def admit_task(
    *,
    title: str,
    acceptance_criteria: str | None = None,
    why: str | None = None,
    work_order_description: str = "",
    existing_titles: Iterable[str] = (),
    existing_criteria: Iterable[str] | Mapping[str, str] = (),
    target_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Decide whether one proposed task may be filed. Never files, never deletes.

    Returns ``{"admitted": bool, "refusals": [...], "unknowns": [...]}`` where each entry
    names the seat that raised it and why, because "refused" with no attribution is the
    unreadable signal that gets a gate switched off.

    A lane that reports UNKNOWN does not refuse. That is not softness: an admission
    decision made on evidence the reviewer does not have is a guess wearing a verdict's
    clothes, and the unknown is returned so the caller can say so.

    `existing_criteria` carries the acceptance criteria of the work order's OPEN tasks.
    The Herald was handed the candidate's criterion and the existing TITLES, so it could
    compare a new title against old titles and could not compare a new criterion against
    old criteria -- the comparison that spots a possible restatement. Defaults to empty so
    every existing caller keeps its current behaviour rather than silently gaining a
    finding it was never given the evidence for.
    """
    refusals: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []

    if warden := _warden(acceptance_criteria, why):
        refusals.append(warden)

    for refusal, unknown in (
        _herald(title, existing_titles, acceptance_criteria, existing_criteria),
        _surveyor(target_paths, work_order_description),
    ):
        if refusal:
            refusals.append(refusal)
        if unknown:
            unknowns.append(unknown)

    return {"admitted": not refusals, "refusals": refusals, "unknowns": unknowns}


def attribution_reach(db_path: "Path | None" = None) -> dict[str, Any]:
    """How many open work orders the Surveyor lane can actually judge.

    THE LANE'S REACH IS A NUMBER, NOT AN IMPRESSION. Attribution needs a declared
    `Module boundary:` clause, and measured on the live authority only 20 of 175 open work
    orders carry a parseable one -- so the lane judges 11% of cases and reports UNKNOWN for
    the rest. Stating that is the difference between a lane with known reach and one that
    looks like enforcement.

    NOT BACKFILLED BY GUESSING. A boundary inferred from a description would make
    attribution confidently wrong, which is worse than unknown -- so this reports the gap
    and names the work orders, and someone who knows the scope declares it.
    """
    import sqlite3

    from runtime.lib.enforcement import boundary_globs

    if db_path is None:
        from core.config.database import _default_db_path

        db_path = Path(_default_db_path())
    if not Path(db_path).is_file():
        return {"status": "unknown", "reason": f"no authority database at {db_path}"}
    try:
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"status": "unknown", "reason": f"authority could not be opened ({exc})"}
    try:
        rows = conn.execute(
            "SELECT work_order_id, COALESCE(description, '') FROM business_work_orders"
            " WHERE status IN ('created', 'in_progress', 'blocked')"
        ).fetchall()
    except sqlite3.Error as exc:
        return {"status": "unknown", "reason": f"business_work_orders unreadable ({exc})"}
    finally:
        conn.close()

    declared = [wo for wo, description in rows if boundary_globs(description)]
    undeclared = [wo for wo, description in rows if not boundary_globs(description)]
    return {
        "status": "computed",
        "open_work_orders": len(rows),
        "with_boundary": len(declared),
        "without_boundary": len(undeclared),
        "reach": round(len(declared) / len(rows), 3) if rows else None,
        "undeclared_ids": sorted(undeclared),
    }
