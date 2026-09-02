"""Score computation and the ``verify_work_order`` entry point.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
composite-score computation and the main orchestrator that reads a work
order's tasks, collects git/authority evidence, runs the parallel graders,
computes scores, spawns gap work orders, and persists the verdict. No logic
changes — extracted verbatim from the original module.

Entry point: ``verify_work_order(work_order_id=, source_root=, dream_studio_home=)``.

Architecture (T4c/T4d/T4e):
Four independent graders run in parallel via subprocess.Popen. Each grader is
blind to the other graders' domain — no shared context between prompts:

  Grader 1 — Completion: task list + git diff.
    Returns: {passed, tasks_verified, summary, gaps, completion_score}

  Grader 2 — Correctness: architectural rules + git diff only (NO task list).
    Returns: {correctness_passed, correctness_score, violations, coverage_gaps,
              migration_gaps}

  Grader 3 — Quality: quality best-practice rules + git diff only (NO task list).
    Returns: {quality_passed, quality_score, issues}

  Grader 4 — Migration (only when diff contains migration files): migration SQL
    file contents only (NO task list, NO other diff).
    Returns: {migration_safe, migration_score, risks}

Overall pass = completion_passed AND correctness_passed AND composite >= 0.70
  AND migration_safe (when applicable).

Composite score = (completion * 0.5) + (correctness * 0.3) + (quality * 0.2).

Thresholds:
  >= 0.85: auto-continue to next WO
  0.70-0.84: auto-continue with logged warning
  < 0.70: register remediation WO, do NOT auto-continue

Set DREAM_STUDIO_VERIFY_MOCK=1 to substitute deterministic fixtures for CI.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

from .verify_db import (
    _read_tasks,
    _read_work_order,
    _require_db,
    _run_sql_checks,
    _format_sql_checks,
)
from .verify_executor import resolve_project_root, record_test_execution, run_executable_checks
from .verify_git import evidence_layer_note
from .verify_gaps import (
    _falsification_to_gaps,
    normalise_falsification_scenarios,
    _filter_invented_threshold_gaps,
    _insert_gap_work_orders,
    _migration_risks_to_gaps,
    _quality_issues_to_gaps,
    _violations_to_gaps,
)
from .verify_git import _authority_evidence, _find_migration_files
from .verify_persist import (
    _persist_review_verdict,
    _persist_unverified_ledger,
    _write_eval_run,
)
from .scenario_taxonomy import SCENARIO_TAXONOMY
from .verify_prompts import (
    _COMPLETION_PROMPT_TEMPLATE,
    _CORRECTNESS_PROMPT_TEMPLATE,
    _FALSIFICATION_PROMPT_TEMPLATE,
    _MIGRATION_PROMPT_TEMPLATE,
    _QUALITY_PROMPT_TEMPLATE,
)
from .verify_shared import _MOCK_COMPLETION, _MOCK_CORRECTNESS, _MOCK_ENV, _MOCK_QUALITY

# ── Falsification diff budget (WO-FALSIFY-TIMEOUT) ─────────────────────────────
#
# The falsification analyst reasons over the WHOLE diff (every surface × every
# scenario class), so its cost grows with diff size — its first live run timed
# out on an ordinary multi-file change. A longer per-role window is half the fix;
# the other half is not handing it unbounded input. Newest commits first, because
# the most recent work is what the operator is about to declare done.

_FALSIFICATION_DIFF_BUDGET = 60_000


def budget_falsification_diff(
    git_diff: str, *, budget: int = _FALSIFICATION_DIFF_BUDGET
) -> tuple[str, bool]:
    """Return ``(diff_for_analysis, truncated)`` within ``budget`` characters.

    Splits on the ``=== commit <sha> ===`` markers ``_collect_git_commits`` writes
    and keeps NEWEST-first whole sections until the budget is spent, then restores
    chronological order so the analyst reads the change as it happened. A diff with
    no markers (authority-evidence text) is head-truncated. ``truncated`` is
    recorded in the verdict so a partial analysis is never mistaken for a complete
    enumeration.
    """
    if len(git_diff) <= budget:
        return git_diff, False

    import re as _re

    parts = _re.split(r"(?=^=== (?:commit|remediation evidence) )", git_diff, flags=_re.MULTILINE)
    sections = [p for p in parts if p.strip()]
    if len(sections) <= 1:
        return git_diff[:budget], True

    # THE WO'S OWN COMMITS COME FIRST (falsification analyst finding,
    # empty_absent_state on this function): closed-child remediation evidence is
    # APPENDED after the commits, so a plain newest-first walk kept the evidence
    # and could spend the entire budget on it — the analyst would then enumerate
    # worst cases for a change set whose actual diff it never saw. Commits are
    # budgeted first (newest-first within their group), then evidence gets what
    # remains.
    def _is_evidence(section: str) -> bool:
        return section.lstrip().startswith("=== remediation evidence")

    commits = [s for s in sections if not _is_evidence(s)]
    evidence = [s for s in sections if _is_evidence(s)]

    kept: list[str] = []
    used = 0
    for group in (commits, evidence):
        for section in reversed(group):  # newest-first within the group
            if used + len(section) > budget and kept:
                continue  # this one does not fit; a smaller later one still might
            kept.append(section)
            used += len(section)
    # Restore the original order so the analyst reads the change as it happened.
    order = {id(s): i for i, s in enumerate(sections)}
    kept.sort(key=lambda s: order[id(s)])
    return "".join(kept), True


# ── Score computation ───────────────────────────────────────────────────────────


def _compute_scores(
    completion: dict[str, Any],
    correctness: dict[str, Any],
    quality: dict[str, Any],
    total_tasks: int,
) -> dict[str, float]:
    # Completion score — grader may return it directly or we compute from tasks_verified.
    raw_completion = completion.get("completion_score")
    if raw_completion is not None:
        completion_score = float(raw_completion)
    elif total_tasks > 0:
        tasks_passed = sum(
            1 for t in completion.get("tasks_verified", []) if t.get("verdict") == "pass"
        )
        completion_score = tasks_passed / total_tasks
    else:
        completion_score = 1.0 if completion.get("passed", True) else 0.0

    # Correctness score.
    raw_correctness = correctness.get("correctness_score")
    if raw_correctness is not None:
        correctness_score = float(raw_correctness)
    else:
        violations = correctness.get("violations", [])
        correctness_score = max(0.0, 1.0 - len(violations) / 7.0) if violations else 1.0

    # Quality score — returned directly by grader.
    quality_score = float(quality.get("quality_score", 1.0))

    composite = (completion_score * 0.5) + (correctness_score * 0.3) + (quality_score * 0.2)

    return {
        "completion_score": round(completion_score, 4),
        "correctness_score": round(correctness_score, 4),
        "quality_score": round(quality_score, 4),
        "composite_score": round(composite, 4),
    }


# ── Protocol resolution ─────────────────────────────────────────────────────────


def _resolve_protocol(protocol_dir: Path, name: str) -> Path | None:
    """Resolve a named verification protocol to its file.

    Accepts either the full filename stem
    (``PROTOCOL-0001-three-store-architecture``) or the short protocol id
    (``PROTOCOL-0001``) — the id matches the file whose stem is exactly the id or
    begins with ``<id>-``. This is what the skill text and the protocols themselves
    document (``--protocol PROTOCOL-0001``), where the on-disk file carries a
    descriptive suffix. Returns None when nothing matches; raises ValueError only
    when a short id is ambiguous (matches more than one file).
    """
    exact = protocol_dir / f"{name}.md"
    if exact.is_file():
        return exact
    matches = sorted(p for p in protocol_dir.glob(f"{name}-*.md") if p.is_file())
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous verification protocol id {name!r}: matches "
            + ", ".join(m.name for m in matches)
        )
    return None


# ── Main entry point ────────────────────────────────────────────────────────────


def verify_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
    protocol: str | None = None,
) -> dict[str, Any]:
    """Run parallel independent verification for a work order.

    Returns::

        {
            "ok": bool,
            "work_order_id": str,
            "passed": bool,
            "summary": str,
            "completion": {...},        # grader 1 result
            "correctness": {...},       # grader 2 result
            "quality": {...},           # grader 3 result
            "migration": {...} | None,  # grader 4 result (migration-class only)
            "scores": {
                "completion_score": float,
                "correctness_score": float,
                "quality_score": float,
                "composite_score": float,
            },
            "gaps": [...],              # all combined gaps
            "spawned_work_orders": [...],
            "verdict_path": str,
            "auto_continue_warning": str | None,
        }
    """
    started_at = datetime.now(UTC).isoformat()
    p_root = planning_root or Path.cwd() / ".planning"
    db_path = _require_db(source_root, dream_studio_home)

    # WO-MULTIROOT-REVIEW task 3: which roots the review read. Initialised here, at
    # function scope, because the result dict references them and this function returns
    # early in several places -- the same scoping bug attachment_pressure had.
    _root_provenance: list[dict[str, object]] = []
    _union_summary: str = "not determined"
    _rules_provenance: str = "not determined"
    # WO-MULTIROOT-REVIEW task 7: which rung of the evidence ladder answered.
    # Function-scope, before any early return, because the result dict reads it --
    # the scoping bug attachment_pressure had.
    _evidence_layer: str = "none"

    with _connect(db_path) as conn:
        wo = _read_work_order(conn, work_order_id)
        if wo is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        tasks = _read_tasks(conn, work_order_id)
        if not tasks:
            return {"ok": False, "error": f"No tasks found for work order: {work_order_id}"}

        # R7: a named verification protocol constrains HOW the fresh-context review looks
        # (scope, anti-bias, conflict rule) — its text is prepended to every grader prompt
        # below. Gap→WO behavior is unchanged. A named-but-missing protocol fails fast.
        protocol_preamble = ""
        if protocol:
            proto_dir = source_root / "docs" / "verification-protocols"
            try:
                proto_path = _resolve_protocol(proto_dir, protocol)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            if proto_path is None:
                return {
                    "ok": False,
                    "error": (
                        f"Verification protocol not found: {protocol} "
                        f"(expected docs/verification-protocols/{protocol}.md "
                        f"or {protocol}-*.md)"
                    ),
                }
            protocol_preamble = (
                f"## VERIFICATION PROTOCOL: {protocol}\n"
                "Conduct this review strictly under the protocol below: inspect ONLY the "
                "sources it names, reconstruct the intended shape BEFORE comparing to the "
                "code, and let spec/intent win on conflict.\n\n"
                f"{proto_path.read_text(encoding='utf-8')}\n\n---\n\n"
            )

        sql_check_results = _run_sql_checks(tasks, db_path)

        task_list_str = "\n".join(
            "{n}. [{st}] {title}: {desc}{ac}{sql}".format(
                n=i + 1,
                st=t["status"],
                title=t["title"],
                desc=t["description"],
                ac=(
                    f"\n   Acceptance criteria: {t['acceptance_criteria']}"
                    if t.get("acceptance_criteria")
                    else ""
                ),
                sql=_format_sql_checks(sql_check_results.get(t["title"], [])),
            )
            for i, t in enumerate(tasks)
        )
        # Lazy import (not module-level): keeps `_collect_git_commits` a bare-name
        # call resolved against verify_git's live globals on every invocation, so
        # `patch("core.work_orders.verify_git._collect_git_commits", ...)` in tests
        # intercepts it — a static top-level import would freeze the reference at
        # verify_main import time and silently bypass the patch.
        from .verify_git import _collect_git_commits

        # WO cef6ddaa — evidence model fixes:
        # (A) Search the WO's TARGET repo (its project's project_path), not always the DS
        #     source_root, so external-repo work is findable — parallels the
        #     executable_ac repo-aware fix (WO 2c751184). Falls back to source_root.
        # (B) A gap-spawned WO carries a "[gap-key: <originating-wo-id>::<category>]" marker;
        #     its work was committed under that ORIGINATING id, so when the WO's own id finds
        #     no commits, fall back to the originating id. This is why the per-gap-id review
        #     could never trace already-committed work and re-spawned endlessly.
        import re as _re

        # The originating id is the token before "::" in the marker — match any id shape
        # (UUIDs in production, but do not assume hex), up to the "::category" separator.
        _gap_marker = _re.search(r"\[gap-key:\s*([^\s:\]]+)::", wo.get("description") or "")
        originating_wo_id = _gap_marker.group(1) if _gap_marker else None

        # WO-MULTIROOT-REVIEW task 3: a project resolves to every root its code lives
        # in, so evidence is collected from all of them and the verdict records which
        # ones answered. _search_root remains the single anchor for the recorded
        # delivery boundary (a boundary is stamped against one repo), while the commit
        # search spans the union.
        from .project_roots import resolve_project_roots

        _project_roots = resolve_project_roots(work_order_id, db_path)
        _search_root = _project_roots.primary or source_root

        # WO-MULTIROOT-REVIEW tasks 5-6: which rulebook this review grades against.
        # folder > project > Dream Studio baseline; nothing declared means the baseline.
        # Resolved HERE because a folder profile is per root, so it needs the roots.
        from .review_rules import render_rules_block, resolve_review_rules

        # THE PROJECT TIER MUST READ THE PROJECT'S OWN PATH, not a repository inside it.
        #
        # This passed project_root=_search_root, which is _project_roots.primary -- and
        # for a container declaring a single repo, primary is that REPO, not the declared
        # container. So a project-level .ds-review-rules.md at the container was never
        # read and the "project" tier of folder > project > baseline was unreachable in
        # production, while every test passed because they declare the container directly.
        #
        # Found by the correctness grader on this work order's own close, phrased as a
        # NO DEAD CODE violation: an advertised layer that no path can reach.
        _declared_root = _project_roots.declared or (Path(_search_root) if _search_root else None)
        _ruleset = resolve_review_rules(
            project_root=_declared_root,
            folders=list(_project_roots.roots),
            # WO-MULTIROOT-REVIEW task 8: the type selects which standards can fairly
            # judge what was delivered. A documentation work order stops being told its
            # tests are missing and starts being judged on completeness, accuracy against
            # the system, and stale description -- narrower on code rules, not weaker.
            work_order_type=wo.get("work_order_type"),
        )
        _rules_provenance = _ruleset.provenance

        # WO-MULTIROOT-REVIEW task 9: the milestone, open siblings and declared edges, so
        # "concise" and "addresses the issue" have a referent beyond one diff. Bounded,
        # and any truncation is carried on the verdict rather than silently elided.
        from .direction_context import build_direction_context

        _direction_text, _direction_note = build_direction_context(work_order_id, db_path=db_path)
        # THE CAVEAT MUST TRAVEL WITH THE CONTEXT. This discarded _direction_note, so the
        # truncation the module deliberately computes ("N further open sibling(s) not
        # listed") reached neither the prompt nor the verdict, and a truncated sibling
        # list was presented to the grader as complete. Found by this work order's own
        # review -- the computed-but-unreached defect, inside the module whose docstring
        # says an unmarked partial list reads as a complete one.
        if _direction_note:
            _prefix = _direction_text + chr(10) * 2 if _direction_text else ""
            _direction_text = _prefix + "  INCOMPLETE: " + _direction_note

        # WO-VERIFY-GRADES-DELIVERY: the RECORDED boundary is the locator; the
        # commit-message grep below is reinforcement. Grepping history for the WO's
        # uuid or title fails for a squash merge, a reworded title, unpushed work,
        # no remote, a commit naming the WO by its human tag, or a non-git target —
        # and none of those mean nothing was delivered. Observed live on 758fbedd:
        # "no commits found referencing 758fbedd", for work merged and green on all
        # three platforms.
        #
        # The recorded boundary is the locator and the grep is the FALLBACK, not an
        # addition. The first cut made them additive (reasoning: a rebase can move
        # work outside the recorded range, so both together see more). That is a
        # universal cost for a conditional benefit: for any WO whose commits DO
        # mention it, both layers return the same commits and the grader input
        # roughly doubles, charged to a budget WO-FALSIFY-TIMEOUT already showed to
        # be tight. So: range when it has content, else the grep. The rare rebase
        # case degrades to exactly what it was before this WO.
        #
        # HONEST CORRECTION: this change was first committed blaming a completion-
        # grader timeout on 2206774f's own verify. That attribution was wrong and
        # measurement disproved it — that WO predates boundary stamping, so this
        # layer contributed ZERO characters to its prompt (5,785 chars total). The
        # timeout was provider-side, exactly as the grader-failure message said
        # before I reached past it for a better story. The fallback design stands on
        # the cost/benefit argument above; it fixed nothing about that timeout.
        from .delivery_boundary import boundary_diff_text

        _boundary_diff, _boundary_note = boundary_diff_text(
            work_order_id, repo_root=Path(_search_root), db_path=db_path
        )
        # WO-BOUNDARY-OPEN-END review finding: the range-replaces-grep choice now
        # lives in choose_locator, where a test can drive it. The guard that used to
        # protect it grepped this function's source, broke on a refactor that changed
        # nothing it cared about, and its replacement could never fail.
        from .verify_git import (
            choose_locator,
            collect_union_evidence,
            union_evidence_summary,
        )

        git_diff, _root_provenance, _evidence_layer = choose_locator(
            _boundary_diff,
            lambda: collect_union_evidence(
                work_order_id,
                _project_roots,
                title=wo["title"],
                fallback_root=_search_root,
            ),
        )
        _union_summary = (
            f"recorded delivery boundary in {_search_root} (roots not searched: the "
            "stamped boundary is the locator when it has content)"
            if _evidence_layer == "recorded_delivery_boundary"
            else union_evidence_summary(_root_provenance)
        )
        if git_diff is None and originating_wo_id:
            git_diff = _collect_git_commits(_search_root, originating_wo_id)

        # WO-GAP-EVIDENCE: remediation for THIS WO's review gaps is committed under
        # the spawned gap WOs' own ids — invisible to the parent-id collection above,
        # so the completion grader re-failed already-remediated tasks forever (and
        # grader-phrasing-dependent gap keys made the closed-spawn discount unable to
        # converge). Append each CLOSED child gap WO's diff as labeled remediation
        # evidence: the grader then grades the full picture and passes on merits.
        if originating_wo_id is None:
            try:
                _child_rows = conn.execute(
                    "SELECT work_order_id FROM business_work_orders"
                    " WHERE instr(description, ?) > 0 AND status = 'closed'"
                    " AND work_order_id != ?",
                    (f"[gap-key: {work_order_id}::", work_order_id),
                ).fetchall()
                _remediation_parts: list[str] = []
                for _child_row in _child_rows:
                    _child_id = _child_row[0]
                    _child_diff = _collect_git_commits(_search_root, _child_id)
                    if _child_diff:
                        _remediation_parts.append(
                            f"=== remediation evidence (closed gap WO {_child_id}) ===\n"
                            f"{_child_diff}"
                        )
                if _remediation_parts:
                    _remediation_text = "\n\n".join(_remediation_parts)
                    git_diff = (
                        f"{git_diff}\n\n{_remediation_text}" if git_diff else _remediation_text
                    )
            except Exception:
                pass  # evidence enrichment is best-effort; the parent diff stands alone

        # WO-FIX-VERIFY-GATE: commit-grep by WO id/title fails for every
        # squash-merged WO (the id never survives the squash), forcing force=True
        # or a wo-<shortid> branch-pointer hack. When _collect_git_commits finds
        # nothing, fall back to the WO's executable AC results (SQL/TEST/API-CHECK)
        # as objective, authority-recorded proof — the certification basis that
        # does not depend on commit messages. This is WO-scoped (the WO's own
        # tasks' checks), unlike a whole-repo working diff which would pick up
        # ambient changes. Only when there is NO commit evidence AND no passing
        # executable check is the work genuinely unreviewable (no-false-done).
        #
        # An escalated WO (its originating symptom regressed) must not certify from
        # its own executable AC alone — that is the same check that may have passed
        # before the regression. Escalated work demands a genuine re-review, so the
        # authority-evidence fallback is suppressed and it stays unreviewable until a
        # real (diff-backed or human) verdict clears it.
        from core.work_orders.escalation import read_escalation

        _is_escalated = read_escalation(work_order_id, db_path=db_path) is not None

        authority_certified = False
        # WO-SEPARATE-TEST-RUNNER: only the authority-evidence path runs the checks, so
        # this stays None on the git-diff path and the verdict records `not_run_at_verify`
        # rather than implying execution it did not do.
        ac_results: dict[str, list[dict[str, Any]]] | None = None
        if git_diff is None and not _is_escalated:
            ac_results = run_executable_checks(
                tasks, db_path, project_root=resolve_project_root(work_order_id, db_path)
            )
            evidence_text, has_passing = _authority_evidence(work_order_id, tasks, ac_results)
            if has_passing:
                git_diff = evidence_text
                authority_certified = True
                _evidence_layer = "authority_executable_checks"

        if git_diff is None and not os.environ.get(_MOCK_ENV):
            # WO-VERIFY-GRADES-DELIVERY task 5: NO FALSE-UNREVIEWABLE. Reaching here
            # now means every layer was empty — the recorded commit range, the
            # boundary-scoped working tree, the boundary files themselves, the
            # commit-message grep, and the WO's own executable checks. That is a
            # finding about the WORK (a work order that delivered nothing findable),
            # not the metadata artifact this message used to describe.
            #
            # The old wording blamed the work for a bookkeeping miss: "no commits
            # found referencing <id> or '<title>'" told an operator to go looking
            # for commits when the real problem was often that nothing had recorded
            # where to look. It must now say what was actually tried, so the reader
            # can tell "nothing was delivered" from "the boundary was never
            # stamped" — which have opposite remedies.
            token = wo["title"].split(" - ")[0].strip()
            _why = _boundary_note or "no delivery boundary recorded for this work order"
            warning = (
                "independent review unreviewable: no delivered change could be located"
                f" for {work_order_id[:8]}. Tried: recorded delivery boundary"
                f" ({_why}); commit-message search for {work_order_id[:8]} or"
                f" '{token}'; and this work order's own executable checks."
                " Work is NOT certified — if the work exists, verify from the"
                " branch/commit where it landed; if the boundary was never stamped,"
                " re-start the work order so it is."
            )
            scores = {
                "completion_score": 0.0,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "composite_score": 0.0,
            }
            completed_at = datetime.now(UTC).isoformat()
            _write_eval_run(
                conn,
                work_order_id=work_order_id,
                scores=scores,
                passed=False,
                failure_reasons=["unreviewable_no_commits_found"],
                started_at=started_at,
                completed_at=completed_at,
                status="unreviewable",
            )
            verdict_path = _persist_review_verdict(
                work_order_id,
                {
                    "work_order_id": work_order_id,
                    "passed": False,
                    "unreviewable": True,
                    "unreviewable_reason": warning,
                    "scores": scores,
                    "auto_continue_warning": warning,
                    "completion": {},
                    "correctness": {},
                    "quality": {},
                    "gaps": [],
                    "spawned_work_orders": [],
                    "verified_at": completed_at,
                },
                planning_root=p_root,
                db_path=db_path,
                project_root=_search_root,
            )
            return {
                "ok": True,
                "work_order_id": work_order_id,
                "passed": False,
                "unreviewable": True,
                "summary": warning,
                "completion": {},
                "correctness": {},
                "quality": {},
                "migration": None,
                "scores": scores,
                "auto_continue_warning": warning,
                "gaps": [],
                "spawned_work_orders": [],
                "verdict_path": str(verdict_path) if verdict_path else None,
            }
        if git_diff is None:
            git_diff = f"(no commits found referencing {work_order_id[:8]})"

        # WO-FALSIFY-TIMEOUT: budget the falsification analyst's input before
        # building its prompt; the other roles keep the full diff.
        _falsification_diff, _falsification_truncated = budget_falsification_diff(git_diff)

        # Build grader prompts.
        prompts: dict[str, str] = {
            "completion": _COMPLETION_PROMPT_TEMPLATE.format(
                direction_context=_direction_text
                or "  (nothing recorded: no milestone, no open siblings, no declared "
                "dependency edges)",
                title=wo["title"],
                work_order_id=work_order_id,
                work_order_type=wo.get("work_order_type", "infrastructure"),
                task_list=task_list_str,
                git_diff=git_diff,
            ),
            "correctness": _CORRECTNESS_PROMPT_TEMPLATE.format(
                git_diff=git_diff,
                rules_block=render_rules_block(_ruleset),
                rules_provenance=_ruleset.provenance,
                rule_count=float(max(1, len(_ruleset.rules))),
            ),
            "quality": _QUALITY_PROMPT_TEMPLATE.format(git_diff=git_diff),
            # WO-FALSIFY-FIRST-PASS: the only grader that asks what SHOULD have
            # been tested and wasn't. Runs on every verify alongside the others.
            # WO-FALSIFY-TIMEOUT: on a budgeted diff (newest commits first) so a
            # large change set yields an analysis instead of a timeout.
            "falsification": _FALSIFICATION_PROMPT_TEMPLATE.format(
                title=wo["title"],
                task_list=task_list_str,
                git_diff=_falsification_diff,
                scenario_taxonomy=SCENARIO_TAXONOMY,
            ),
        }

        # Grader 4: migration — only when diff includes migration SQL files.
        migration_files = _find_migration_files(source_root, git_diff)
        if migration_files:
            mf = migration_files[0]
            try:
                migration_sql = mf.read_text(encoding="utf-8")
            except Exception:
                migration_sql = "(could not read migration file)"
            prompts["migration"] = _MIGRATION_PROMPT_TEMPLATE.format(
                migration_file=mf.name,
                migration_sql=migration_sql,
            )

        # R7: run every grader under the named protocol's scope constraints.
        if protocol_preamble:
            prompts = {name: protocol_preamble + body for name, body in prompts.items()}

        # Run all graders in parallel.
        # Lazy import (not module-level) — see the `_collect_git_commits` note above;
        # keeps `patch("core.work_orders.verify_graders._run_graders_parallel", ...)`
        # able to intercept this call.
        from .verify_graders import _run_graders_parallel

        grader_results = _run_graders_parallel(prompts)

        completion = grader_results.get("completion", _MOCK_COMPLETION.copy())
        correctness = grader_results.get("correctness", _MOCK_CORRECTNESS.copy())
        quality = grader_results.get("quality", _MOCK_QUALITY.copy())
        migration: dict[str, Any] | None = grader_results.get("migration")
        falsification: dict[str, Any] | None = grader_results.get("falsification")

        # T1/T3: Detect unreviewable graders (empty LLM output after retry).
        # Record and surface a warning instead of scoring — there is nothing to
        # remediate and spawning gap WOs for an empty diff would be unactionable.
        # Mock mode bypasses this so CI fixtures keep exercising the grader path.
        # WO-GRADER-ERROR-UNREVIEWABLE: a grader that could not RUN is not evidence
        # in either direction. Empty output was already treated as unreviewable; a
        # non-JSON HARD ERROR (provider quota/auth failure, crash) was not — it fell
        # through to _compute_scores, which read a missing completion_score as
        # tasks_passed/total = 0.0 and produced a FAILED verdict with an empty
        # summary. That converts an infrastructure failure into a substantive
        # negative verdict: a false-fail, the mirror of false-done.
        _grader_errors = {
            name: grader_results[name]["_grader_error"]
            for name in ("completion", "correctness", "quality", "migration")
            if name in grader_results and grader_results[name].get("_grader_error")
        }
        unreviewable_graders = [
            name
            for name in ("completion", "correctness", "quality", "migration")
            if name in grader_results
            and (
                grader_results[name].get("unreviewable")
                or grader_results[name].get("_grader_error")
            )
        ]
        if unreviewable_graders and not os.environ.get(_MOCK_ENV):
            reason_str = ", ".join(unreviewable_graders)
            if _grader_errors:
                _err_detail = "; ".join(
                    f"{name}: {str(err).strip()[:300]}" for name, err in _grader_errors.items()
                )
                warning = (
                    f"independent review unreviewable: grader(s) [{reason_str}] did not produce a"
                    f" verdict — {_err_detail}. This is a GRADER failure (e.g. provider quota or"
                    f" auth), NOT a finding about the work. Work is NOT certified — re-run verify"
                    f" once the provider is available, or review manually."
                )
            else:
                warning = (
                    f"independent review unreviewable: grader(s) [{reason_str}] returned empty"
                    f" output. Work is NOT certified — review manually."
                )
            scores = {
                "completion_score": 0.0,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "composite_score": 0.0,
            }
            completed_at = datetime.now(UTC).isoformat()
            _write_eval_run(
                conn,
                work_order_id=work_order_id,
                scores=scores,
                passed=False,
                failure_reasons=["unreviewable_grader_no_summary"],
                started_at=started_at,
                completed_at=completed_at,
                status="unreviewable",
            )
            verdict_path = _persist_review_verdict(
                work_order_id,
                {
                    "work_order_id": work_order_id,
                    "passed": False,
                    "unreviewable": True,
                    "unreviewable_graders": unreviewable_graders,
                    "unreviewable_reason": warning,
                    "grader_errors": _grader_errors,
                    "scores": scores,
                    "auto_continue_warning": warning,
                    "completion": completion,
                    "correctness": correctness,
                    "quality": quality,
                    "gaps": [],
                    "spawned_work_orders": [],
                    "verified_at": completed_at,
                },
                planning_root=p_root,
                db_path=db_path,
                project_root=_search_root,
            )
            return {
                "ok": True,
                "work_order_id": work_order_id,
                "passed": False,
                "unreviewable": True,
                "unreviewable_graders": unreviewable_graders,
                "summary": warning,
                "completion": completion,
                "correctness": correctness,
                "quality": quality,
                "migration": migration,
                "scores": scores,
                "auto_continue_warning": warning,
                "gaps": [],
                "spawned_work_orders": [],
                "verdict_path": str(verdict_path) if verdict_path else None,
            }

        # Compute scores.
        scores = _compute_scores(completion, correctness, quality, total_tasks=len(tasks))
        composite = scores["composite_score"]

        # Determine individual pass/fail signals.
        completion_passed = completion.get("passed", False)
        correctness_passed = correctness.get("correctness_passed", True)
        migration_safe = migration.get("migration_safe", True) if migration else True

        # Collect all gaps from all graders.
        all_gaps: list[dict[str, Any]] = []
        all_gaps.extend(completion.get("gaps", []))

        if not correctness_passed:
            all_gaps.extend(
                _violations_to_gaps(
                    correctness.get("violations", []),
                    correctness.get("coverage_gaps", []),
                    correctness.get("migration_gaps", []),
                )
            )

        if composite < 0.70:
            quality_errors = [i for i in quality.get("issues", []) if i.get("severity") == "error"]
            all_gaps.extend(_quality_issues_to_gaps(quality_errors))

        if migration and not migration_safe:
            all_gaps.extend(_migration_risks_to_gaps(migration.get("risks", [])))

        # WO-FALSIFY-FIRST-PASS: an error-severity scenario the analyst says is
        # TESTABLE BUT UNTESTED (PROPOSED) becomes tracked work, not a note —
        # this is what turns "what should have been tested" into a work order.
        # UNVERIFIED scenarios do NOT spawn (there is nothing to write yet); they
        # land in the ledger below so the residual risk is named, never silent.
        # MALFORMED GRADER REPLY, second surface (gap WO 66e7ebc8 task 2, caught by
        # that WO's own verify): _falsification_to_gaps was hardened against a
        # grader returning prose or a bare object, but this comprehension was left
        # calling .get() on every element — so the very reply the task describes
        # still raised AttributeError here, INSIDE verify's open authority
        # transaction, taking down the whole verify. Hardening one of two readers of
        # the same untrusted payload leaves the failure exactly where it was, so the
        # shape contract now lives in ONE shared normaliser both readers call.
        _fals_scenarios, _fals_malformed = normalise_falsification_scenarios(
            falsification.get("scenarios") if falsification else None
        )
        all_gaps.extend(_falsification_to_gaps(_fals_scenarios))
        _unverified = [s for s in _fals_scenarios if s.get("status") == "UNVERIFIED"]

        # Overall pass/fail. Falsification is ADDITIVE evidence: it spawns gap WOs
        # and records residual risk, but it does not gate certification — an
        # analyst that flags an untestable deploy-only risk must not permanently
        # block a WO whose declared work is complete and correct.
        passed = completion_passed and correctness_passed and composite >= 0.70 and migration_safe

        auto_continue_warning: str | None = None
        if passed and composite < 0.85:
            auto_continue_warning = (
                f"Quality warning: composite score {composite:.2f} is below 0.85. "
                "Auto-continuing but recommend addressing quality issues."
            )

        # Collect failure reasons for eval_runs.
        failure_reasons: list[str] = []
        if not completion_passed:
            failure_reasons.append(f"completion_failed (score={scores['completion_score']:.2f})")
        if not correctness_passed:
            failure_reasons.append(f"correctness_failed (score={scores['correctness_score']:.2f})")
        if composite < 0.70:
            failure_reasons.append(f"composite_below_threshold ({composite:.2f} < 0.70)")
        if not migration_safe:
            failure_reasons.append("migration_unsafe")

        # T2: reject gaps that invent a numeric threshold absent from the AC text.
        acceptance_text = " ".join(
            f"{t.get('title', '')} {t.get('description', '')} {t.get('acceptance_criteria', '')}"
            for t in tasks
        )
        all_gaps = _filter_invented_threshold_gaps(all_gaps, acceptance_text)

        # Register gap WOs. milestone_id is no longer required (T3): null-milestone
        # gaps still spawn and dedup, scoped by project_id.
        #
        # WO cef6ddaa (C) — break the gap-spawn recursion: a WO that is ITSELF a
        # gap-spawned remediation WO must not breed further gap WOs. Previously the
        # re-review keyed new gaps by the gap WO's own id (dedup key
        # reviewed_wo_id::category), so each generation escaped the parent's dedup and
        # spawned a fresh WO — the 17->28 cascade. A remediation WO's findings now
        # surface advisory-only in the verdict (all_gaps) but spawn nothing.
        spawned: list[dict[str, Any]] = []
        if all_gaps and wo.get("project_id") and originating_wo_id is None:
            spawned = _insert_gap_work_orders(
                conn,
                gaps=all_gaps,
                project_id=wo["project_id"],
                milestone_id=wo.get("milestone_id"),
                reviewed_work_order_id=work_order_id,
                reviewed_wo_title=wo["title"],
                reviewed_wo_sequence=wo.get("sequence_order"),
                # WO-GAP-FANOUT: a FAILED verdict means the reviewed work order is not
                # done, so its gaps are its own remaining work and belong on it as
                # tasks. A passing verdict's advisory gaps must not block the close it
                # just approved.
                reviewed_wo_incomplete=not passed,
            )

        # WO-GAP-FANOUT: a work order absorbing gaps review after review is the
        # inflation problem wearing a blocking face. The bound is visible or it is not a
        # bound — surface it on the result and the verdict rather than letting one work
        # order grow silently.
        _pressure = [s["attachment_pressure"] for s in spawned if s.get("attachment_pressure")]
        attachment_pressure = _pressure[0] if _pressure else None

        # WO-VERIFY-GAP-RESOLUTION: a gap whose remediation WO is already CLOSED is
        # resolved, not open. Verify grades only WO-attributed commits, so remediation
        # committed under a spawned gap WO's own id is invisible to this diff — without
        # this pass an already-remediated-and-closed gap fails the original WO forever.
        # WO-GAP-RES-COMPLETION: completion-driven gaps discount too — a closed
        # (gate-checked, independently verified) remediation WO IS the completion
        # evidence the parent diff cannot carry, so completion_passed is not required.
        # Rule violations, migration gaps, and non-closed spawns never discount
        # (no-false-done preserved; the status=='closed' check is below).
        # An attached gap is not a spawned work order. Splitting here, once, keeps
        # every downstream consumer honest -- close_gates prints spawned_work_orders as
        # "Gap WOs", and an attached record put the reviewed work order's own id in that
        # list.
        _genuine_spawns = [s for s in spawned if not s.get("attached_to_reviewed")]
        _attached_gaps = [s for s in spawned if s.get("attached_to_reviewed")]

        resolved_gap_wos: list[str] = []
        if (
            not passed
            and spawned
            and all(s.get("respawn_suppressed") for s in spawned)
            and migration_safe
            and composite >= 0.70
            and not correctness.get("violations")
            and not correctness.get("migration_gaps")
        ):
            # respawn_suppressed fires for ANY non-open prior spawn — including
            # 'blocked' and 'cancelled', where the remediation was never done.
            # Only a WO whose status is exactly 'closed' (gate-checked completion)
            # may discount (gap WO d6e7b4c0, caught by verify's own review of
            # WO-VERIFY-GAP-RESOLUTION).
            _gap_ids = [s["work_order_id"] for s in spawned]
            _ph = ",".join("?" for _ in _gap_ids)
            _closed = {
                r[0]
                for r in conn.execute(
                    "SELECT work_order_id FROM business_work_orders"
                    f" WHERE work_order_id IN ({_ph}) AND status = 'closed'",
                    _gap_ids,
                ).fetchall()
            }
            if all(g in _closed for g in _gap_ids):
                resolved_gap_wos = _gap_ids
                passed = True
                failure_reasons = [f"resolved_by_closed_gap_wos: {', '.join(resolved_gap_wos)}"]

        completed_at = datetime.now(UTC).isoformat()

        # Write eval run.
        _write_eval_run(
            conn,
            work_order_id=work_order_id,
            scores=scores,
            passed=passed,
            failure_reasons=failure_reasons,
            started_at=started_at,
            completed_at=completed_at,
        )

        # WO-FILESDB-C2: DB-first verdict persistence (authority, kind=review_verdict);
        # .planning disk only as the unreleased-migration fallback. Supersedes the
        # WO-FILESDB-P1 disk+DB dual-write.
        # WO-VERIFY-PROVENANCE: record which commits were actually graded; the
        # provenance envelope (via _persist_review_verdict) records the repo HEAD.
        _graded_commits: list[str] = []
        if not authority_certified and git_diff:
            import re as _re_commits

            _graded_commits = _re_commits.findall(r"=== commit ([0-9a-f]{7,40}) ===", git_diff)
        full_verdict: dict[str, Any] = {
            "work_order_id": work_order_id,
            "passed": passed,
            "scores": scores,
            "auto_continue_warning": auto_continue_warning,
            "completion": completion,
            "correctness": correctness,
            "quality": quality,
            "gaps": all_gaps,
            "spawned_work_orders": _genuine_spawns,
            # WO-GAP-FANOUT: gaps that became TASKS on the reviewed work order. Kept
            # separate because a consumer reading spawned_work_orders is looking for a
            # sibling work order to chase, and an attached gap has none.
            "attached_gap_tasks": _attached_gaps,
            "certification_basis": "authority_evidence" if authority_certified else "git_diff",
            "graded_commits": _graded_commits,
            "resolved_gaps": resolved_gap_wos,
            "verified_at": completed_at,
            # WO-SEPARATE-TEST-RUNNER: whether this certification rests on running the
            # work order's tests or on reading its code. Merge consults the verdict
            # before close ever executes anything, so the distinction has to ride here.
            "test_execution": record_test_execution(tasks, ac_results),
            # WO-GAP-FANOUT: named when this work order has absorbed gaps across
            # several reviews, so the honest exit (carry the remainder) is visible
            # instead of the work order quietly growing.
            "attachment_pressure": attachment_pressure,
            # WO-MULTIROOT-REVIEW task 3: which roots this verdict actually read.
            # "no violations found" and "nothing was read" are indistinguishable in a
            # score, so the ratio rides the verdict: all 28 open Fulcrum work orders
            # were graded against 1 of 6 repositories and nothing said so.
            "roots_examined": _root_provenance,
            "roots_summary": _union_summary,
            # WO-MULTIROOT-REVIEW tasks 5-6: the rulebook this verdict used, named.
            "rules_provenance": _rules_provenance,
            # WO-MULTIROOT-REVIEW task 7: WHICH rung answered, and what that rung means.
            # certification_basis has two values for four rungs, so it cannot tell a diff
            # from the current contents of some files -- very different strengths.
            "evidence_layer": _evidence_layer,
            "evidence_layer_note": evidence_layer_note(_evidence_layer),
        }
        # WO-FALSIFY-FIRST-PASS: the falsification section and the UNVERIFIED
        # ledger ride the verdict. A falsification grader that could not run is
        # recorded as unavailable rather than silently omitted — an absent
        # analysis must never read as "no worst cases found".
        if falsification is not None:
            full_verdict["falsification"] = falsification
            if _falsification_truncated:
                # A partial enumeration must never read as a complete one.
                full_verdict["falsification_diff_truncated"] = (
                    f"diff exceeded the {_FALSIFICATION_DIFF_BUDGET}-char falsification budget;"
                    " the analyst saw the newest commits only — surfaces in older commits of"
                    " this work order may be unenumerated."
                )
            if _fals_malformed:
                # A grader reply that partly failed to parse narrows the enumeration.
                # Skipping the unparseable entries silently would make a degraded
                # analysis indistinguishable from a clean one.
                full_verdict["falsification_malformed_entries"] = (
                    f"{_fals_malformed} scenario entr(ies) were not objects and could not be"
                    " classified — the enumeration may be incomplete."
                )
            if falsification.get("_grader_error") or falsification.get("unreviewable"):
                full_verdict["falsification_unavailable"] = str(
                    falsification.get("_grader_error") or "grader returned empty output"
                )[:300]
            else:
                full_verdict["unverified_risks"] = _unverified
                _persist_unverified_ledger(
                    work_order_id,
                    _unverified,
                    planning_root=p_root,
                    db_path=db_path,
                    project_root=_search_root,
                    # Carry the partial-analysis caveat and the run stamp into the
                    # ledger itself, so every downstream reader (close, project
                    # state) knows the enumeration was partial and can detect a
                    # ledger/verdict pair from different runs.
                    truncated=full_verdict.get("falsification_diff_truncated"),
                    verified_at=completed_at,
                )
        else:
            full_verdict["falsification_unavailable"] = "falsification grader produced no result"
        if migration is not None:
            full_verdict["migration"] = migration
        verdict_path = _persist_review_verdict(
            work_order_id,
            full_verdict,
            planning_root=p_root,
            db_path=db_path,
            project_root=_search_root,
        )

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": passed,
        "summary": completion.get("summary", ""),
        # WO-GAP-FANOUT: the attach-loop bound reaches the CLI, not just the stored
        # verdict — a bound nobody can see is not a bound.
        "attachment_pressure": attachment_pressure,
        # WO-MULTIROOT-REVIEW task 3: same rule for root coverage.
        "roots_summary": _union_summary,
        "roots_examined": _root_provenance,
        "rules_provenance": _rules_provenance,
        "evidence_layer": _evidence_layer,
        "evidence_layer_note": evidence_layer_note(_evidence_layer),
        "completion": completion,
        "correctness": correctness,
        "quality": quality,
        "migration": migration,
        "scores": scores,
        "auto_continue_warning": auto_continue_warning,
        "gaps": all_gaps,
        "spawned_work_orders": _genuine_spawns,
        "attached_gap_tasks": _attached_gaps,
        "certification_basis": "authority_evidence" if authority_certified else "git_diff",
        "resolved_gaps": resolved_gap_wos,
        "falsification": falsification,
        "unverified_risks": full_verdict.get("unverified_risks", []),
        "falsification_unavailable": full_verdict.get("falsification_unavailable"),
        "falsification_diff_truncated": full_verdict.get("falsification_diff_truncated"),
        "verdict_path": str(verdict_path) if verdict_path else None,
    }


def attest_work_order(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Record an operator attestation as a PASSING review verdict (WO cef6ddaa, residual (ii)).

    The residual path for a work order whose done work has NO machine-traceable evidence —
    no commit under its own or its originating id (repo-aware search A/B exhausted) and no
    executable AC for the authority-evidence fallback. Rather than fabricate a WO-id-referenced
    artifact just to satisfy the gate, the operator attests completion; that attestation is
    persisted as the review_verdict (certification_basis='operator_attested', passed=True,
    with the reason + timestamp) so the independent_review close gate is satisfied.

    This is NOT force: force bypasses a gate silently; this records an auditable human
    certification. It is the operator's explicit "this is done" — categorically distinct from
    forcing UNdone work, which no-false-done forbids.
    """
    if not (reason and reason.strip()):
        return {"ok": False, "error": "attestation reason is required (record why it is done)"}
    now = datetime.now(UTC).isoformat()
    p_root = planning_root or Path.cwd() / ".planning"
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo = _read_work_order(conn, work_order_id)
        if wo is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}
        verdict: dict[str, Any] = {
            "work_order_id": work_order_id,
            "passed": True,
            "certification_basis": "operator_attested",
            "attestation": reason.strip(),
            "attested_at": now,
            "summary": f"Operator-attested complete: {reason.strip()}",
            "scores": {},
            "gaps": [],
            "spawned_work_orders": [],
            "verified_at": now,
        }
        verdict_path = _persist_review_verdict(
            work_order_id,
            verdict,
            planning_root=p_root,
            db_path=db_path,
            project_root=resolve_project_root(work_order_id, db_path) or source_root,
            generator="ds work-order attest",
        )
    return {
        "ok": True,
        "work_order_id": work_order_id,
        "certification_basis": "operator_attested",
        "attestation": reason.strip(),
        "verdict_path": str(verdict_path) if verdict_path else None,
    }
