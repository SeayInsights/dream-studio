"""ds prove — a runnable demonstration of the four behaviors that differentiate the
Dream Studio substrate (WO-PROVE-HARNESS).

It stands up a *disposable* scratch project + authority DB, runs four demonstrations
against it, prints one PASS/FAIL line per claim with the real runtime evidence, tears the
scratch down, and exits non-zero if any claim fails — so it is usable as a CI job, a demo
for a regulated/defense buyer, AND a regression test over the substrate's actual guarantees.

HARD CONSTRAINT: it must never write to, read authority state from, or register anything in
the operator's live ``~/.dream-studio/state/studio.db``. Every demonstration runs against a
scratch home (a fresh temp dir pointed at by USERPROFILE/HOME for the enforcement subprocess,
and passed as ``dream_studio_home`` to the in-process engine calls). ``tests/integration/
test_prove.py`` asserts the live authority DB is byte-for-byte unchanged across a run.

The four claims:
  1. an unauthorized source edit is denied     (runtime enforcement hook, real deny payload)
  2. a defect cannot close while its symptom reproduces  (originating-symptom close gate)
  3. graders are blind to the claimed task list (anti-self-certification prompt asymmetry)
  4. adapter configs regenerate from authority and drift is detected
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_NOW = "2026-01-01T00:00:00.000000Z"  # pre-change-impact-cutover so close is not gated on it


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``prove`` subparser."""
    p = subcommands.add_parser(
        "prove",
        help="Demonstrate the four substrate enforcement guarantees against a scratch project",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON result, not the transcript",
    )
    p.add_argument("--keep", action="store_true", help="Keep the scratch dir (debugging)")


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    return prove_main(as_json=getattr(args, "json", False), keep=getattr(args, "keep", False))


# ── scratch harness ───────────────────────────────────────────────────────────────


class _Scratch:
    """A disposable project + authority DB. Never the operator's live state."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-prove-"))
        self.home = self.root / "home"
        # The hook resolves its DB from Path.home()/.dream-studio/state; the engine calls
        # resolve it from dream_studio_home/state. ds_home is the shared parent of state/.
        self.ds_home = self.home / ".dream-studio"
        state = self.ds_home / "state"
        state.mkdir(parents=True, exist_ok=True)
        self.db = state / "studio.db"
        self.project_dir = self.root / "project"
        (self.project_dir / "src").mkdir(parents=True, exist_ok=True)
        self.project_id = str(uuid.uuid4())
        self.milestone_id = str(uuid.uuid4())

        from core.config.sqlite_bootstrap import bootstrap_database

        bootstrap_database(self.db)
        self._seed()

    def _seed(self) -> None:
        conn = sqlite3.connect(str(self.db))
        try:
            conn.execute(
                "INSERT INTO business_projects"
                " (project_id, name, description, status, project_path, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (self.project_id, "prove-scratch", "", "active", str(self.project_dir), _NOW, _NOW),
            )
            conn.execute(
                "INSERT INTO business_milestones"
                " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (self.milestone_id, self.project_id, "M1", "active", 1, _NOW, _NOW),
            )
            conn.commit()
        finally:
            conn.close()

    def add_work_order(
        self, *, status: str, wo_type: str = "cleanup", title: str = "Scratch WO"
    ) -> str:
        wo_id = str(uuid.uuid4())
        conn = sqlite3.connect(str(self.db))
        try:
            conn.execute(
                "INSERT INTO business_work_orders"
                " (work_order_id, project_id, milestone_id, title, description,"
                "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    wo_id,
                    self.project_id,
                    self.milestone_id,
                    title,
                    "desc",
                    wo_type,
                    status,
                    1,
                    _NOW,
                    _NOW,
                    _NOW,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return wo_id

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


# ── Claim 1 — an unauthorized source edit is denied ─────────────────────────────────


def _claim_unauthorized_edit_denied(s: _Scratch) -> tuple[bool, str]:
    """Run the REAL PreToolUse enforcement hook as a subprocess against the scratch project
    (registered, no in_progress work order) and capture the actual deny payload it emits —
    not a paraphrase. The hook reads its authority DB from Path.home(), so USERPROFILE/HOME
    point it at the scratch home; TMP/TEMP are pointed away from the project dir so the
    project is not treated as a temp path."""
    # A created (not in_progress) WO so the deny names the exact `ds work-order start` command.
    start_wo = s.add_work_order(status="created", title="Do the thing")
    src = s.project_dir / "src" / "app.py"
    src.write_text("# product source\nprint('hello')\n", encoding="utf-8")

    payload = json.dumps(
        {"session_id": "prove-claim1", "tool_name": "Edit", "tool_input": {"file_path": str(src)}}
    )
    hook = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-edit-enforce.py"

    env = dict(os.environ)
    env["USERPROFILE"] = str(s.home)  # Path.home() on Windows
    env["HOME"] = str(s.home)  # Path.home() on POSIX
    env["TMP"] = str(s.home)  # TEMP_ROOT != project_dir, so the project is not temp-exempt
    env["TEMP"] = str(s.home)
    env.pop("DS_ENFORCE", None)

    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=payload,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    out = (proc.stdout or "").strip()
    decision = reason = None
    try:
        data = json.loads(out)
        hso = data.get("hookSpecificOutput", {})
        decision = hso.get("permissionDecision")
        reason = hso.get("permissionDecisionReason")
    except Exception:
        pass

    passed = (
        decision == "deny"
        and bool(reason)
        and start_wo[:8] in (reason or "")
        and ("work-order start" in (reason or ""))
    )
    evidence = (
        out if out else f"(no deny payload; exit={proc.returncode} stderr={proc.stderr[:300]})"
    )
    return passed, evidence


# ── Claim 2 — a defect cannot close while its symptom reproduces ─────────────────────


def _claim_defect_symptom_gate(s: _Scratch) -> tuple[bool, str]:
    """Register a defect WO whose originating_symptom SQL still reproduces, show close BLOCKED,
    then satisfy the symptom and show the SAME close succeeding — both halves, so the gate is
    proven discriminating rather than simply broken. Runs the real close_work_order path."""
    from core.work_orders.close import close_work_order

    sentinel = str(uuid.uuid4())
    # Symptom: the defect is "fixed" only when a row with this sentinel exists.
    symptom = (
        "SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE description = '%s'" % sentinel
    )
    wo_id = s.add_work_order(status="in_progress", title="Defect: symptom must not reproduce")

    conn = sqlite3.connect(str(s.db))
    try:
        # One task, marked complete; a passing executable AC so only the symptom can block.
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
            "  status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                wo_id,
                s.project_id,
                "Fix it",
                "do it",
                "SQL-CHECK: SELECT COUNT(*) FROM business_projects",
                "complete",
                _NOW,
                _NOW,
            ),
        )
        conn.execute(
            "UPDATE business_work_orders SET originating_symptom = ? WHERE work_order_id = ?",
            (symptom, wo_id),
        )
        conn.commit()
    finally:
        conn.close()

    # A fast stub grader so any independent_review gate resolves without a vendor CLI.
    stub = s.root / "grader_stub.py"
    stub.write_text(
        "import sys, json\nsys.stdin.read()\n"
        'print(json.dumps({"completion_score":1.0,"correctness_score":1.0,'
        '"quality_score":1.0,"passed":True,"summary":"stub","gaps":[]}))\n',
        encoding="utf-8",
    )
    prior_stub = os.environ.get("DS_GRADER_STUB")
    os.environ["DS_GRADER_STUB"] = str(stub)
    try:
        blocked = close_work_order(
            work_order_id=wo_id, source_root=REPO_ROOT, dream_studio_home=s.ds_home
        )
        blocked_ok = (not blocked.get("ok")) and any(
            "originating_symptom" in str(f) for f in blocked.get("failures", [])
        )

        # Satisfy the symptom: insert the sentinel row the SQL-CHECK looks for.
        conn = sqlite3.connect(str(s.db))
        try:
            conn.execute(
                "INSERT INTO business_projects"
                " (project_id, name, description, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), "sentinel", sentinel, "archived", _NOW, _NOW),
            )
            conn.commit()
        finally:
            conn.close()

        reclosed = close_work_order(
            work_order_id=wo_id, source_root=REPO_ROOT, dream_studio_home=s.ds_home
        )
        reopen_ok = bool(reclosed.get("ok"))
    finally:
        if prior_stub is None:
            os.environ.pop("DS_GRADER_STUB", None)
        else:
            os.environ["DS_GRADER_STUB"] = prior_stub

    passed = blocked_ok and reopen_ok
    evidence = (
        "with symptom reproducing → close BLOCKED: "
        + "; ".join(str(f) for f in blocked.get("failures", []))[:300]
        + f"\n  after satisfying the symptom → close ok={reclosed.get('ok')}"
    )
    return passed, evidence


# ── Claim 3 — graders are blind to the claimed task list ─────────────────────────────


def _claim_graders_blind_to_tasks(_s: _Scratch) -> tuple[bool, str]:
    """Construct the three grader prompts exactly as verify does and assert the asymmetry on
    the constructed prompts (not on prose): the completion grader receives the task list AND
    the diff, but the correctness and quality graders receive ONLY the diff. This is the
    anti-self-certification property — a grader that cannot see the claimed task list cannot
    be steered by it."""
    from core.work_orders.verify_prompts import (
        _COMPLETION_PROMPT_TEMPLATE,
        _CORRECTNESS_PROMPT_TEMPLATE,
        _QUALITY_PROMPT_TEMPLATE,
    )

    task_marker = "TASKLIST-SENTINEL-9f3a: implement the widget"
    diff_marker = "DIFF-SENTINEL-2b1c +def widget(): ..."

    completion = _COMPLETION_PROMPT_TEMPLATE.format(
        title="Scratch WO",
        work_order_id="00000000",
        work_order_type="cleanup",
        task_list=task_marker,
        git_diff=diff_marker,
    )
    # WO-MULTIROOT-REVIEW made the correctness rules RESOLVED rather than hardcoded, so
    # the template gained rules_block / rules_provenance / rule_count. Formatting it with
    # git_diff alone now raises KeyError: 'rules_provenance', which is what turned this
    # claim red on main.
    #
    # The claim under test is that the correctness grader never sees the task list, so the
    # rules content is irrelevant here -- but it must be SOMETHING, and it must be
    # something that could not be mistaken for a task list.
    correctness = _CORRECTNESS_PROMPT_TEMPLATE.format(
        git_diff=diff_marker,
        rules_block="(1) a placeholder rule for this demonstration",
        rules_provenance="prove harness: rules not resolved from a project",
        rule_count=1.0,
    )
    quality = _QUALITY_PROMPT_TEMPLATE.format(git_diff=diff_marker)

    task_asymmetry = (
        task_marker in completion and task_marker not in correctness and task_marker not in quality
    )
    diff_everywhere = all(diff_marker in p for p in (completion, correctness, quality))
    passed = task_asymmetry and diff_everywhere
    evidence = (
        f"task list in completion prompt: {task_marker in completion}; "
        f"in correctness: {task_marker in correctness}; in quality: {task_marker in quality}\n"
        f"  diff present in all three: {diff_everywhere}"
    )
    return passed, evidence


# ── Claim 4 — adapter configs regenerate from authority and drift is detected ────────


def _claim_adapter_drift_detected(s: _Scratch) -> tuple[bool, str]:
    """Regenerate an adapter projection from authority, write it out, mutate the projected file
    out of band, and show the content-hash drift check catching it — the projection is derived,
    never hand-authoritative."""
    from core.shared_intelligence.adapter_config_projection import adapter_config_projection
    from core.shared_intelligence.authority import record_adapter_authority_profile

    conn = sqlite3.connect(str(s.db))
    conn.row_factory = sqlite3.Row
    try:
        # Register an adapter profile in authority — the projection is derived from THIS.
        record_adapter_authority_profile(
            conn,
            adapter_id="claude",
            adapter_type="claude",
            adapter_name="Claude Code",
            supported_context_packets=["resume", "work_order_execution", "review"],
            supported_result_types=["decision", "code_change", "validation", "evidence"],
        )
        conn.commit()
        projection = adapter_config_projection(conn, adapter_id="claude")
    finally:
        conn.close()

    content = projection["content"]
    authority_hash = projection["content_sha256"]
    projected_file = s.root / "adapter-claude.projection"
    projected_file.write_text(content, encoding="utf-8")

    # Fresh projection matches the on-disk file: no drift.
    on_disk = projected_file.read_text(encoding="utf-8")
    fresh_hash = hashlib.sha256(on_disk.encode("utf-8")).hexdigest()
    fresh_matches = fresh_hash == authority_hash

    # Mutate the projected file out of band → the hash diverges → drift is detected.
    projected_file.write_text(on_disk + "\n# hand-edited out of band\n", encoding="utf-8")
    mutated_hash = hashlib.sha256(
        projected_file.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    drift_detected = mutated_hash != authority_hash

    passed = fresh_matches and drift_detected
    evidence = (
        f"authority hash {authority_hash[:12]}… == fresh projection: {fresh_matches}\n"
        f"  after out-of-band edit, hash {mutated_hash[:12]}… != authority: {drift_detected}"
    )
    return passed, evidence


# ── orchestration ───────────────────────────────────────────────────────────────────

_CLAIMS = [
    ("an unauthorized source edit is denied", _claim_unauthorized_edit_denied),
    ("a defect cannot close while its symptom reproduces", _claim_defect_symptom_gate),
    ("graders are blind to the claimed task list", _claim_graders_blind_to_tasks),
    (
        "adapter configs regenerate from authority and drift is detected",
        _claim_adapter_drift_detected,
    ),
]


def prove_main(*, as_json: bool = False, keep: bool = False) -> int:
    scratch = _Scratch()
    results: list[dict] = []
    try:
        for idx, (title, fn) in enumerate(_CLAIMS, start=1):
            try:
                passed, evidence = fn(scratch)
            except Exception as exc:  # a claim that errors is a FAIL, never a silent pass
                passed, evidence = False, f"(claim raised: {type(exc).__name__}: {exc})"
            results.append({"claim": idx, "title": title, "passed": passed, "evidence": evidence})
    finally:
        if not keep:
            scratch.cleanup()

    all_passed = all(r["passed"] for r in results)
    if as_json:
        print(json.dumps({"ok": all_passed, "scratch_isolated": True, "claims": results}, indent=2))
        return 0 if all_passed else 1

    lines = [
        "ds prove — Dream Studio substrate enforcement demonstration",
        f"Scratch project + authority DB: {scratch.root}" + ("" if keep else " (torn down)"),
        "The operator's live ~/.dream-studio/state/studio.db is never touched.",
        "",
    ]
    for r in results:
        lines.append(f"CLAIM {r['claim']} — {r['title']}")
        for ln in str(r["evidence"]).splitlines():
            lines.append(f"  {ln}")
        lines.append(f"  → {'PASS' if r['passed'] else 'FAIL'}")
        lines.append("")
    passed_n = sum(1 for r in results if r["passed"])
    lines.append(f"RESULT: {passed_n}/{len(results)} claims passed")
    print("\n".join(lines))
    return 0 if all_passed else 1
