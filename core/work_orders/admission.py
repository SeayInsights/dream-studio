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
from typing import Any, Iterable

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

#: Seats, spelled as the registry spells them. Not imported from `core.gates`: a work-order
#: mutation path must not depend on the gate package to file a task, and the registry gate
#: already refuses a seat outside its closed set, so a typo here fails there.
_WARDEN = "Gate-integrity engineer"
_SURVEYOR = "Merge-order steward"
_HERALD = "Claim and closure auditor"


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


def _warden(acceptance_criteria: str | None, why: str | None) -> dict[str, Any] | None:
    """Enforce-or-declare, the contract `canonical/rules.yml` already runs on."""
    if has_executable_criterion(acceptance_criteria):
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


def _herald(title: str, existing_titles: Iterable[str]) -> dict[str, Any] | None:
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
        }
    return None


def admit_task(
    *,
    title: str,
    acceptance_criteria: str | None = None,
    why: str | None = None,
    work_order_description: str = "",
    existing_titles: Iterable[str] = (),
    target_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Decide whether one proposed task may be filed. Never files, never deletes.

    Returns ``{"admitted": bool, "refusals": [...], "unknowns": [...]}`` where each entry
    names the seat that raised it and why, because "refused" with no attribution is the
    unreadable signal that gets a gate switched off.

    A lane that reports UNKNOWN does not refuse. That is not softness: an admission
    decision made on evidence the reviewer does not have is a guess wearing a verdict's
    clothes, and the unknown is returned so the caller can say so.
    """
    refusals: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []

    for finding in (
        _warden(acceptance_criteria, why),
        _herald(title, existing_titles),
    ):
        if finding:
            refusals.append(finding)

    refusal, unknown = _surveyor(target_paths, work_order_description)
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
