"""Compute what can be computed, before anyone is asked to judge it.

Operator directive 2026-08-21: *anything that can be verified deterministically
should be.* A claim with an exact answer must never be put to a language model — not
because judgement is bad, but because spending it on facts leaves less of it for the
claims that genuinely need reading, and because computation is available when judgement
is not.

THE EVIDENCE, all measured in this repo on 2026-08-20/21.

1. JUDGEMENT IS UNAVAILABLE MORE OFTEN THAN COMPUTATION IS. Six consecutive grader
   timeouts blocked three complete work orders (befde290, 59c69b58, 6a4c21d1) — 4/4
   tasks, pushed, gates green, unclosable. ``claude --print`` timed out at 360s again
   the next night. A computed check does not time out.

2. GRADERS WERE ASKED QUESTIONS WITH EXACT ANSWERS. Verbatim from passing verdicts:
   "all three named TEST-CHECK node IDs exist verbatim"; "the dist/plugin copy matches
   canonical"; "the skill text names the check". Each is one function call.

3. THEY SOMETIMES CANNOT COMPUTE, AND SAY SO. "running pytest was denied by the
   sandbox, so the tests are not confirmed green by execution." "I could not execute
   pytest in this session (command approval denied), so the TEST-CHECK results are
   unexecuted." Both honest, both degraded. Making the degradation visible was
   WO-SEPARATE-TEST-RUNNER; removing the dependence is this.

THE PATTERN THIS EXTENDS, RATHER THAN INVENTS. ``verify_prompts`` already tells the
completion grader that SQL-CHECK results "are ground truth — they take precedence over
diff inference", for one fact class. This module produces the rest in the same shape.

AND THE BOUNDARY, stated because it would be easy to overclaim. Building the
reachability gate produced six defects: two were caught by RUNNING it, four by READING
it — a task spec contradicting its implementation behind a misleading test name, a
function parameter that changed no answer, a comment asserting a superseded rule, and a
guard test incapable of failing. All four sat behind a green suite. Execution proves
behaviour; it cannot notice that an argument is inert or that a name misdescribes what
it proves. So: compute everything computable so judgement is spent only where judgement
is the sole available tool — and never let a computed layer imply coverage it lacks,
which is why every fact here can be ``unknown`` WITH a reason and never a silent pass.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.gates.reachability import SourceUnreadable

REPO_ROOT = Path(__file__).resolve().parents[2]

# pytest --collect-only exit codes that mean "this node id does not resolve here".
# 5 = nothing collected, 4 = usage error (a malformed or non-existent path).
_COLLECT_UNRESOLVED = frozenset({4, 5})
_COLLECT_TIMEOUT_SECONDS = 120

_TEST_CHECK_LINE = re.compile(r"^\s*TEST-CHECK:\s*(.+)$", re.IGNORECASE)
# pytest prints one of these per unresolvable target during collection.
# Captures to END OF LINE, not the first whitespace: pytest echoes an absolute path
# and this repo lives under "C:\Users\Dannis Seay\...", so a \S+ capture
# reported the missing target as "C:\Users\Dannis".
_NOT_FOUND = re.compile(r"ERROR:\s+(?:file or directory )?not found:\s*(.+?)\s*$", re.M)
# WHAT COUNTS AS EXECUTABLE IS NOT DECIDED HERE.
#
# The Warden's lane, asked of this module before it was pushed: two sites decided
# "is this acceptance criterion executable", and this report is worthless if it
# disagrees with the thing that actually runs them. A first cut named three kinds and
# allowed a space before the colon; measured against the executor it disagreed in BOTH
# directions -- `PERF-CHECK:` reported prose though the executor detects it (and then
# fails it closed), `TEST-CHECK :` reported executable though the executor never sees
# it. Retyping the executor's regex here would have produced two copies that merely
# agree today, so the predicate is imported from the executor instead: there is one
# definition, and this report cannot describe a rule the executor does not run.
#
# AND THE APPLIER IS WHAT IS IMPORTED, not the pattern. An audit mutated only this
# module -- deleting the `.strip()` it applied before matching -- and all 30 tests
# stayed green while an indented `  TEST-CHECK: x` became a criterion the executor
# runs and this report calls prose. Sharing a constant cannot stop a caller from
# applying it differently, so `check_token` strips and matches in one place and
# there is no per-caller step left to drift.

# The value that means "this could not be determined". Never omitted and never
# collapsed into False: "we could not tell" and "no" have different remedies, the same
# distinction the unverified-risk ledger and the verdict reader already make.
UNKNOWN = "unknown"


def _unknown(reason: str) -> dict[str, Any]:
    return {"status": UNKNOWN, "reason": reason}


def collect_test_check_expressions(tasks: list[dict[str, Any]]) -> list[str]:
    """Every TEST-CHECK expression across a work order's task acceptance criteria.

    NOT named ``test_*``: pytest collects any module-level ``test_``-prefixed callable it
    imports, and that exact mistake produced a collection ERROR ("fixture 'tasks' not
    found") from a production module earlier in this milestone. A production helper in a
    repo with a test suite has one naming constraint, and this is it.
    """
    found: list[str] = []
    for task in tasks:
        for line in (task.get("acceptance_criteria") or "").splitlines():
            match = _TEST_CHECK_LINE.match(line)
            if match:
                found.append(match.group(1).strip())
    return found


def resolve_node_ids(expressions: list[str], *, project_root: Path | None = None) -> dict[str, Any]:
    """Do these TEST-CHECK node ids exist in this checkout? One subprocess, not N.

    RESOLUTION IS NOT PASSING, and conflating them sent a real diagnosis down the wrong
    path on 2026-08-19: three TEST-CHECKs read as FAILED for merged, green work purely
    because the working tree was on another branch. ``--collect-only`` answers the
    cheaper, more diagnostic question — is the check pointed at anything here — without
    running the suite.

    BATCHED DELIBERATELY. The first cut spawned one pytest per node id: at ~2-5s each,
    a six-task work order with two checks apiece would have added 30-60s to EVERY
    verify. A deterministic layer that makes verification slower gets switched off, and
    then it verifies nothing. pytest names each unresolvable id on its own
    ``ERROR: not found:`` line, so one call answers for all of them.

    ``cmd:`` expressions are the target repo's own command, not pytest node ids, and are
    reported as undetermined rather than guessed at.
    """
    node_ids = [e.strip() for e in expressions if e.strip()[:4].lower() != "cmd:"]
    undetermined: list[dict[str, str]] = [
        {
            "expr": e,
            "reason": "a 'cmd:' expression is the target repo's own command, not a pytest node id",
        }
        for e in expressions
        if e.strip()[:4].lower() == "cmd:"
    ]
    if not node_ids:
        return {
            "status": "computed",
            "checked": 0,
            "unresolved": [],
            "undetermined": undetermined,
        }

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header", *node_ids],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_COLLECT_TIMEOUT_SECONDS,
            cwd=str(project_root) if project_root else None,
        )
    except subprocess.TimeoutExpired:
        return _unknown(f"pytest collection timed out after {_COLLECT_TIMEOUT_SECONDS}s")
    except OSError as exc:
        return _unknown(f"pytest unavailable: {exc}")

    code = result.returncode
    if not isinstance(code, int):
        return _unknown("pytest returned no exit code")

    output = (result.stdout or "") + (result.stderr or "")
    if code == 0:
        return {
            "status": "computed",
            "checked": len(node_ids),
            "unresolved": [],
            "undetermined": undetermined,
        }
    if code in _COLLECT_UNRESOLVED:
        # pytest names each missing target explicitly; anything it does not name
        # collected fine, so only the named ones are reported unresolved.
        named = _NOT_FOUND.findall(output)
        unresolved = [n for n in node_ids if any(n in item or item in n for item in named)]
        if not unresolved and named:
            unresolved = named
        if not unresolved:
            # Exit said "nothing collected" but named nothing — do not guess which.
            return {
                "status": "computed",
                "checked": len(node_ids),
                "unresolved": [],
                "undetermined": undetermined
                + [
                    {
                        "expr": ", ".join(node_ids),
                        "reason": f"pytest exited {code} without naming a missing target",
                    }
                ],
            }
        return {
            "status": "computed",
            "checked": len(node_ids),
            "unresolved": unresolved,
            "undetermined": undetermined,
        }
    return _unknown(f"pytest collection exited {code}")


def acceptance_criteria_determinism(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Which tasks carry an executable criterion, and which rest on prose.

    A REPORT, NOT A VERDICT. Some claims genuinely cannot be computed — a design
    judgement, an operator attestation — and a gate that demands the impossible is a
    gate people route around. What this makes visible is whether prose-only was a
    CHOICE: an author who sees the count can decide, and a reader can tell how much of
    a close rested on reading.
    """
    # Function-level, as every other gate reaching into core.work_orders does -- a gate
    # module is imported by the pre-push chain and should not pay for the executor's
    # import graph to answer a question that may not be asked.
    from core.work_orders.verify_executor import check_token

    executable: list[str] = []
    prose_only: list[str] = []
    for task in tasks:
        title = str(task.get("title") or "(untitled task)")
        criteria = task.get("acceptance_criteria") or ""
        if any(check_token(line) for line in criteria.splitlines()):
            executable.append(title)
        else:
            prose_only.append(title)
    total = len(executable) + len(prose_only)
    return {
        "total": total,
        "executable": len(executable),
        "prose_only": prose_only,
        "coverage": round(len(executable) / total, 3) if total else None,
    }


def projection_parity(repo_root: Path | None = None) -> dict[str, Any]:
    """Is every projected skill file byte-identical to its canonical source?

    Asked of a grader repeatedly ("the dist/plugin copy matches canonical") and answered
    here by comparing bytes. Newlines are normalised so a CRLF checkout compares equal.
    """
    root = repo_root or REPO_ROOT
    canonical_root = root / "canonical" / "skills"
    projected_root = root / "dist" / "plugin" / "skills"
    if not canonical_root.is_dir():
        return _unknown(f"no canonical skills tree at {canonical_root}")
    if not projected_root.is_dir():
        return _unknown(f"no projected skills tree at {projected_root}")

    # The projection prefixes bare pack names with "ds-" (canonical/skills/core ->
    # dist/plugin/skills/ds-core) and leaves already-prefixed ones alone. DERIVED, not
    # listed: the first cut hardcoded three of eleven packs, so 54 canonical files read
    # as "not projected at all" — a false alarm in the one field whose whole point is
    # that missing is not fresh.
    def _projected_pack(pack: str) -> list[str]:
        return [pack] if pack.startswith("ds-") else [f"ds-{pack}", pack]

    compared = 0
    stale: list[str] = []
    unmatched: list[str] = []
    for path in sorted(canonical_root.rglob("SKILL.md")):
        rel = path.relative_to(canonical_root)
        pack = rel.parts[0]
        candidates = [
            projected_root / name / Path(*rel.parts[1:]) for name in _projected_pack(pack)
        ]
        projected = next((c for c in candidates if c.is_file()), None)
        if projected is None:
            unmatched.append(rel.as_posix())
            continue
        compared += 1
        try:
            canon = path.read_bytes().replace(b"\r\n", b"\n")
            proj = projected.read_bytes().replace(b"\r\n", b"\n")
        except OSError as exc:
            unmatched.append(f"{rel.as_posix()} ({exc})")
            continue

        # TWO DIFFERENT CONTRACTS, measured rather than assumed. A mode file
        # (modes/<mode>/SKILL.md) is copied verbatim, so byte equality is the right
        # question. A top-level pack SKILL.md has generated YAML frontmatter PREPENDED
        # by the projection (name:, description:), so byte equality reports all ten pack
        # routers stale — which the first cut did, on a repo where none of them were.
        # A parity check that cries wolf on every router is one nobody consults, so the
        # pack files are asked what is actually true of them: is the canonical body
        # still present, unmodified, inside the projected file.
        if len(rel.parts) > 1 and rel.parts[1] == "modes":
            if canon != proj:
                stale.append(rel.as_posix())
        elif canon not in proj:
            stale.append(rel.as_posix())
    return {
        "status": "computed",
        "compared": compared,
        "stale": stale,
        # A canonical file with no projected counterpart is NOT fresh; it is undeployed,
        # which the hook-freshness check learned the hard way by reporting clean on 42
        # of 45 paths while three were simply absent.
        "unprojected": unmatched,
    }


def deterministic_facts(
    *,
    tasks: list[dict[str, Any]],
    project_root: Path | None = None,
    repo_root: Path | None = None,
    check_node_ids: bool = True,
) -> dict[str, Any]:
    """Everything about this work order that can be established by computation.

    ``check_node_ids=False`` skips the pytest collection subprocess and records why,
    for callers that cannot afford them — an omission with a stated reason, never a
    silent gap.
    """
    facts: dict[str, Any] = {
        "acceptance_criteria": acceptance_criteria_determinism(tasks),
        "projection_parity": projection_parity(repo_root),
    }
    expressions = collect_test_check_expressions(tasks)
    if not check_node_ids:
        facts["node_ids"] = _unknown("node-id resolution was not requested by this caller")
    else:
        facts["node_ids"] = resolve_node_ids(expressions, project_root=project_root)
    return facts


def facts_prompt_block(facts: dict[str, Any]) -> str:
    """The computed facts, phrased for a grader as established rather than asked.

    Modelled on the SQL-CHECK paragraph already in ``_COMPLETION_PROMPT_TEMPLATE``,
    which tells the grader those results "are ground truth — they take precedence over
    diff inference". Same contract, more facts: state it, say it is ground truth, and
    say what the grader must conclude — including that an ``unknown`` is not a pass.
    """
    lines = [
        "IMPORTANT — COMPUTED FACTS (ground truth, established before you were asked):",
        "The following were measured directly, not inferred from the diff. They take",
        "precedence over your reading of the diff. Do NOT re-derive them, and do not",
        "treat any 'could not determine' below as a pass — it means unknown.",
        "",
    ]

    node_ids = facts.get("node_ids") or {}
    if node_ids.get("status") == "computed":
        unresolved = node_ids.get("unresolved") or []
        undetermined = node_ids.get("undetermined") or []
        lines.append(
            f"- TEST-CHECK node ids: {node_ids.get('checked', 0)} checked by pytest collection;"
            f" {len(unresolved)} do NOT resolve in this checkout."
        )
        for expr in unresolved:
            lines.append(
                f"    UNRESOLVED: {expr!r} — this is NOT a test failure. The criterion is"
                " misaddressed or this checkout lacks the work."
            )
        for item in undetermined:
            lines.append(f"    UNDETERMINED: {item['expr']!r} — {item['reason']}")
    else:
        lines.append(
            f"- TEST-CHECK node ids: not determined ({node_ids.get('reason', 'no reason')})."
        )

    parity = facts.get("projection_parity") or {}
    if parity.get("status") == "computed":
        stale, unprojected = parity.get("stale") or [], parity.get("unprojected") or []
        lines.append(
            f"- Skill projection parity: {parity.get('compared', 0)} file(s) byte-compared;"
            f" {len(stale)} stale, {len(unprojected)} canonical file(s) not projected at all."
        )
        for rel in stale[:5]:
            lines.append(f"    STALE PROJECTION: {rel}")
        for rel in unprojected[:5]:
            lines.append(f"    NOT PROJECTED: {rel} (missing is not fresh)")
    else:
        lines.append(f"- Skill projection parity: not determined ({parity.get('reason', '')}).")

    criteria = facts.get("acceptance_criteria") or {}
    if criteria.get("total"):
        lines.append(
            f"- Acceptance criteria: {criteria['executable']} of {criteria['total']} task(s)"
            f" carry an executable check (coverage {criteria.get('coverage')})."
        )
        for title in (criteria.get("prose_only") or [])[:8]:
            lines.append(f"    PROSE-ONLY: {title}")
        lines.append(
            "    A prose-only criterion is not a defect by itself — some claims cannot be"
            " computed — but its task's completion rests on your reading alone."
        )
    return "\n".join(lines)


# ── A grep standing in for a drive ────────────────────────────────────────────
#
# Caught by judgement twice on 2026-08-20/21 and it will be missed a third time:
#   - the project-state test asserted "work_order_execution_caveat" in queries.py source
#     instead of driving get_project_state, and its verify said so: "a grep proves the
#     line was typed, not that the payload carries the key";
#   - tests/unit/test_merge_readiness.py asserts '"merge-check"' in src where the task
#     demanded an end-to-end drive of the surface.
# Both are mechanically detectable, which makes them exactly the wrong thing to keep
# asking a grader about.

# NARROWED BY MEASUREMENT, NOT BY REASONING. The first cut treated any file read plus
# an assertion as a suspect and reported 154 tests across tests/unit — overwhelmingly
# legitimate: reading back a JSON output, a temp file the test just wrote, a generated
# launcher, an install script, a .md doc. A report that size is unreadable, and an
# unreadable report is the signal-nobody-reads failure this milestone keeps finding.
#
# So the detector is confined to what is unambiguous: `inspect.getsource` and
# `getsourcelines` can only be applied to IMPORTABLE PYTHON. If a test can call
# getsource on it, the test could have called the thing instead. That narrows the same
# corpus to a handful, and it catches both real cases: test_merge_readiness's
# `'"merge-check"' in src` and the project-state grep its verify rejected.
#
# `read_text` is deliberately NOT included. Statically distinguishing "reads a
# production .py" from "reads the JSON it just wrote" needs data-flow analysis, and a
# detector that guesses produces the noise measured above.
_SOURCE_READERS = frozenset({"getsource", "getsourcelines"})

# A structural assertion over code that genuinely has no drivable surface says so
# inline, and the report PRINTS every exemption — an exemption nobody can see is the
# same shape as the defect it exempts.
GREP_EXEMPT_MARKER = "deterministic-first: structural assertion"


def source_reading_tests(source: str, *, path: str) -> list[dict[str, Any]]:
    """Test functions whose evidence is the source TEXT of importable Python.

    Returns one entry per suspect: ``{test, line, reads, exempt, exempt_reason, reason}``.

    A grep proves the line was typed; only a drive proves it runs. Judgement caught this
    twice — the project-state test asserting ``work_order_execution_caveat`` appeared in
    ``queries.py`` instead of driving ``get_project_state``, and ``test_merge_readiness``
    asserting ``'"merge-check"' in src`` where the task demanded an end-to-end drive.
    Both are mechanically detectable, which makes them the wrong thing to keep asking a
    grader about.

    REPORTED, NEVER BLOCKED. Some structural claims have no drivable surface (that a
    module does NOT import something; that a fallback is a chain rather than a
    concatenation). Those are declared with ``GREP_EXEMPT_MARKER`` and still listed, so
    the exemption is visible rather than silent.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SourceUnreadable(f"{path}: {exc}") from exc

    suspects: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue

        body_text = ast.get_source_segment(source, node) or ""
        readers: list[str] = []
        asserts = 0
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assert):
                asserts += 1
            elif isinstance(inner, ast.Call):
                name = getattr(inner.func, "attr", None) or getattr(inner.func, "id", None)
                if name in _SOURCE_READERS:
                    readers.append(str(name))
        if not (readers and asserts):
            continue

        exempt = GREP_EXEMPT_MARKER in body_text
        reason = ""
        if exempt:
            after = body_text.split(GREP_EXEMPT_MARKER, 1)[1]
            reason = after.splitlines()[0].strip(" #:-") or "(no reason given)"
        suspects.append(
            {
                "test": node.name,
                "line": node.lineno,
                "reads": sorted(set(readers)),
                "exempt": exempt,
                "exempt_reason": reason,
                "reason": (
                    "asserts over the SOURCE TEXT of importable Python — a grep proves the"
                    " line was typed, not that it runs. Drive the surface instead, or declare"
                    f" the structural claim with '# {GREP_EXEMPT_MARKER}: <why>'."
                ),
            }
        )
    return suspects


def main() -> int:
    """Advisory sweep: which tests in this change set offer source text as evidence?

    WIRED BECAUSE THE REACHABILITY GATE BLOCKED THE PUSH THAT ADDED
    ``source_reading_tests`` with no call site. Task 4 said "report it"; the first cut
    built the reporter and gave it no reporting surface — the fifth instance of
    mechanism-without-wiring in this milestone, and the first one caught by a machine
    before the push rather than by a grader after the merge. The gate shipped an hour
    earlier caught its author.

    ADVISORY, always exit 0. Some structural claims have no drivable surface, the
    judgement is contextual, and a blocking gate on a contextual judgement is one people
    route around — the same reason ``leanness`` is advisory. Diff-scoped so the report
    stays about what this change set added.
    """
    if os.environ.get("GITHUB_ACTIONS"):
        return 0

    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF", "origin/main")
    changed = _changed_test_files(base_ref)
    if not changed:
        print("deterministic-first: no test files changed — nothing to sweep")
        return 0

    suspects: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    for rel in changed:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            found = source_reading_tests(
                path.read_text(encoding="utf-8", errors="replace"), path=rel
            )
        except SourceUnreadable as exc:
            print(f"deterministic-first: could not parse {rel} — {exc}")
            continue
        for item in found:
            item["file"] = rel
            (exempted if item["exempt"] else suspects).append(item)

    for item in exempted:
        print(
            f"deterministic-first: DECLARED {item['file']}:{item['line']} {item['test']}"
            f" — {item['exempt_reason']}"
        )
    if not suspects:
        print(f"deterministic-first: OK — {len(changed)} changed test file(s) swept")
        return 0

    print()
    print("deterministic-first: these tests offer SOURCE TEXT as their evidence:")
    for item in suspects:
        print(
            f"  {item['file']}:{item['line']}  {item['test']}  (reads {', '.join(item['reads'])})"
        )
    print()
    print("  A grep proves the line was typed; only a drive proves it runs. Import the")
    print("  thing and call it, or — if the claim genuinely has no drivable surface —")
    print(f"  declare it inline: # {GREP_EXEMPT_MARKER}: <why>")
    print("  Advisory: this never blocks a push.")
    return 0


def _changed_test_files(base_ref: str) -> list[str]:
    """Test files this change set touched, including ones git does not track yet."""
    diff = _git(["diff", "--name-only", f"{base_ref}...HEAD"]) or _git(
        ["diff", "--name-only", "HEAD"]
    )
    untracked = _git(["ls-files", "--others", "--exclude-standard"])
    seen: list[str] = []
    for line in (diff + "\n" + untracked).splitlines():
        rel = line.strip().replace("\\", "/")
        if rel.endswith(".py") and "/test_" in f"/{rel}" and rel not in seen:
            seen.append(rel)
    return seen


def _git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO_ROOT,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if not isinstance(result.returncode, int) or result.returncode != 0:
        return ""
    return result.stdout or ""


if __name__ == "__main__":
    raise SystemExit(main())
