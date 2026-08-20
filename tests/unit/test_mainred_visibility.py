"""WO-MAINRED-VISIBILITY: post-merge full-ci status is surfaced, not assumed.

Operator-caught 2026-08-19: main sat RED across eight merges and nothing
reported it. The merge rule is satisfied by the 3-platform pr-smoke matrix (11
focused files); the FULL suite runs post-merge, ubuntu-only — so a merge can be
correctly authorized and still break main. An unwatched signal is an invisible
signal, the same class as the enforcement bypasses this milestone made visible.

Advisory by design: a red main never blocks (someone else's red must not stop
unrelated work), and an unreadable signal is reported as unknown — never as a
pass, never as a failure.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.health.main_ci import main_ci_status, main_ci_warning


def _gh(runs: list[dict]) -> MagicMock:
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps(runs)
    proc.stderr = ""
    return proc


def _run(runs: list[dict]) -> dict:
    with patch("subprocess.run", return_value=_gh(runs)):
        return main_ci_status(repo_root=Path("."))


# ── status reading ──────────────────────────────────────────────────────────────


def test_red_main_surfaces_in_doctor(tmp_path):
    """The doctor reports a failing post-merge run with the commit and run URL."""
    runs = [
        {
            "conclusion": "failure",
            "status": "completed",
            "headSha": "ab929c8a1111",
            "url": "https://github.com/x/y/actions/runs/1",
            "displayTitle": "feat(verify): falsification analyst",
        }
    ]
    status = _run(runs)
    assert status["status"] == "failure"
    assert status["red"] is True
    assert status["head_sha"].startswith("ab929c8a")

    warning = main_ci_warning(status)
    assert warning and "main is RED" in warning
    assert "ab929c8a" in warning
    assert "actions/runs/1" in warning
    # The lesson that caused this WO is stated where an operator will read it.
    assert "not proof main is green" in warning

    # And it genuinely lands on the doctor's checks payload — run_doctor_checks
    # is read-only, so this drives the real composition rather than asserting on
    # a hand-built dict.
    with patch("core.health.main_ci.main_ci_status", return_value=status):
        from core.health.doctor import run_doctor_checks

        report = run_doctor_checks(source_root=Path("."), dream_studio_home=tmp_path)
    main_ci_check = report["checks"]["main_ci"]
    assert main_ci_check["red"] is True
    assert main_ci_check["head_sha"].startswith("ab929c8a")
    assert main_ci_check["warning"].startswith("main is RED")
    # Advisory: a red main must not turn the doctor's own verdict into a failure.
    assert report["status"] in ("pass", "warn", "attention_required", "fail")


def test_green_and_running_produce_no_warning():
    """Only a definite failure warns — crying wolf on in-progress runs would
    train operators to ignore the line that matters."""
    green = _run(
        [
            {
                "conclusion": "success",
                "status": "completed",
                "headSha": "aaa",
                "url": "u",
                "displayTitle": "t",
            }
        ]
    )
    assert green["status"] == "success" and green["red"] is False
    assert main_ci_warning(green) is None

    running = _run(
        [
            {
                "conclusion": None,
                "status": "in_progress",
                "headSha": "bbb",
                "url": "u",
                "displayTitle": "t",
            }
        ]
    )
    assert running["status"] == "running" and running["red"] is False
    assert main_ci_warning(running) is None

    queued = _run(
        [
            {
                "conclusion": None,
                "status": "queued",
                "headSha": "ccc",
                "url": "u",
                "displayTitle": "t",
            }
        ]
    )
    assert queued["status"] == "running"


def test_cancelled_is_unknown_not_a_pass_or_a_failure():
    """A cancelled/skipped run is neither evidence of health nor of a defect."""
    for conclusion in ("cancelled", "skipped", "neutral", "action_required"):
        status = _run(
            [
                {
                    "conclusion": conclusion,
                    "status": "completed",
                    "headSha": "d",
                    "url": "u",
                    "displayTitle": "t",
                }
            ]
        )
        assert status["status"] == "unknown", conclusion
        assert status["red"] is False, conclusion
        assert main_ci_warning(status) is None


@pytest.mark.parametrize(
    "failure_mode",
    [
        FileNotFoundError("gh"),
        subprocess.TimeoutExpired(cmd="gh", timeout=25),
        OSError("boom"),
    ],
)
def test_unavailable_gh_yields_unknown_never_a_fabricated_verdict(failure_mode):
    """No gh, a timeout, or an OS error must never be reported as success."""
    with patch("subprocess.run", side_effect=failure_mode):
        status = main_ci_status(repo_root=Path("."))
    assert status["status"] == "unknown"
    assert status["red"] is False
    assert status["reason"], "an unknown status must say WHY"
    assert main_ci_warning(status) is None


def test_gh_error_exit_and_non_json_are_unknown_with_reason():
    proc = MagicMock()
    proc.returncode = 1
    proc.stdout = ""
    proc.stderr = "gh: not authenticated\nrun gh auth login"
    with patch("subprocess.run", return_value=proc):
        status = main_ci_status(repo_root=Path("."))
    assert status["status"] == "unknown"
    assert "not authenticated" in status["reason"]

    proc2 = MagicMock()
    proc2.returncode = 0
    proc2.stdout = "not json at all"
    proc2.stderr = ""
    with patch("subprocess.run", return_value=proc2):
        status2 = main_ci_status(repo_root=Path("."))
    assert status2["status"] == "unknown"
    assert "non-JSON" in status2["reason"]


def test_no_runs_found_is_unknown_with_reason():
    status = _run([])
    assert status["status"] == "unknown"
    assert "no Full CI runs" in status["reason"]


def test_non_text_gh_output_degrades_to_unknown():
    """WO-MAINRED-GH-NONSTR — the defect that took main red for a day.

    A bare ``MagicMock(returncode=0)`` is what a caller patching
    ``subprocess.run`` for some OTHER subprocess call hands back, and it is a
    legitimate shape: ``.stdout`` is an auto-created attribute that happens to be
    truthy and is not a string. ``stdout or "[]"`` passed it to ``json.loads``,
    which raises TypeError — not a JSONDecodeError and not a ValueError, so the
    guard here never caught it.
    """
    with patch("subprocess.run", return_value=MagicMock(returncode=0)):
        status = main_ci_status(repo_root=Path("."))
    assert status["status"] == "unknown"
    assert status["red"] is False
    assert "non-text" in status["reason"]


def test_advisory_reader_never_raises_into_its_caller():
    """The class, not the instance.

    This reader is documented as advisory: it never blocks a close, never fails
    the doctor, never alters a gate outcome. An exception escaping it violates
    that whatever the trigger, so every malformed shape must come back as a
    well-formed unknown rather than propagate.
    """
    shapes: list[tuple[str, object, object, object]] = [
        ("non-str stdout", 0, b"bytes not str", ""),
        ("non-str stderr on failure", 1, "", b"bytes not str"),
        ("stdout is a list", 0, ["already", "parsed"], ""),
        ("stdout is None", 0, None, ""),
        ("returncode is not an int", MagicMock(), "[]", ""),
    ]
    for label, code, out, err in shapes:
        proc = MagicMock()
        proc.returncode = code
        proc.stdout = out
        proc.stderr = err
        with patch("subprocess.run", return_value=proc):
            status = main_ci_status(repo_root=Path("."))  # must not raise
        assert status["status"] == "unknown", label
        assert status["red"] is False, label
        assert status["reason"], f"{label}: an unknown must always say why"
        # And the advisory renderer stays silent rather than inventing an alarm.
        assert main_ci_warning(status) is None, label


def test_empty_gh_output_is_not_confused_with_unreadable_output():
    """An empty string means "gh answered, there were no runs"; a non-string means
    "we could not read the answer". Collapsing them would report a real absence as
    a malfunction, or worse, the reverse."""
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = ""
    proc.stderr = ""
    with patch("subprocess.run", return_value=proc):
        status = main_ci_status(repo_root=Path("."))
    assert status["status"] == "unknown"
    assert "no Full CI runs" in status["reason"], "empty output is an absence, not a read failure"


# ── Is the failing run MINE? (gap WO ebbd529c) ─────────────────────────────────


def _red_run(sha: str = "deadbeef1234") -> list[dict]:
    return [
        {
            "conclusion": "failure",
            "status": "completed",
            "headSha": sha,
            "url": "https://github.com/x/y/actions/runs/9",
            "displayTitle": "some merge",
        }
    ]


@pytest.mark.parametrize(
    ("includes", "reason", "expect"),
    [
        (True, None, "INCLUDES your local HEAD"),
        (False, None, "PREDATES your local HEAD"),
        (None, "git not installed", "unknown (git not installed)"),
    ],
)
def test_local_head_relationship_is_reported(includes, reason, expect):
    """'main is RED' prompts different action depending on whether the operator's
    own merge is in that run. An advisory that cannot say which just adds noise to
    a close that may have been entirely correct."""
    with patch("subprocess.run", return_value=_gh(_red_run())):
        with patch("core.health.main_ci._local_head_includes", return_value=(includes, reason)):
            status = main_ci_status(repo_root=Path("."))
    assert status["local_head_includes_run"] is includes
    assert status["local_head_reason"] == reason
    warning = main_ci_warning(status)
    assert warning and expect in warning


def test_local_head_ancestry_is_computed_against_a_real_repository(tmp_path):
    """Driven against a real git repo rather than a mocked exit code — the value of
    this check is that it answers correctly, and a mocked returncode would only
    prove the branching, not the question."""
    from core.health.main_ci import _local_head_includes

    repo = tmp_path / "r"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }

    def git(*args: str) -> str:
        out = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )
        assert out.returncode == 0, f"git {args}: {out.stderr}"
        return out.stdout.strip()

    git("init", "-q")
    (repo / "a.txt").write_text("1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "first")
    first = git("rev-parse", "HEAD")
    (repo / "a.txt").write_text("2", encoding="utf-8")
    git("commit", "-aqm", "second")

    # An ancestor of HEAD is included.
    assert _local_head_includes(first, repo) == (True, None)
    # HEAD itself counts as included (merge-base --is-ancestor is inclusive).
    assert _local_head_includes(git("rev-parse", "HEAD"), repo) == (True, None)

    # A commit on a divergent branch is NOT in HEAD.
    git("checkout", "-qb", "side", first)
    (repo / "b.txt").write_text("x", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "side")
    side = git("rev-parse", "HEAD")
    git("checkout", "-q", "-")
    assert _local_head_includes(side, repo) == (False, None)

    # A sha this repo has never heard of is UNKNOWN, not False — absence of the
    # object is not evidence about ancestry.
    answer, why = _local_head_includes("0" * 40, repo)
    assert answer is None and why


def test_local_head_is_unknown_when_git_cannot_answer():
    from core.health.main_ci import _local_head_includes

    assert _local_head_includes(None, Path(".")) == (None, "run sha unknown")
    with patch("subprocess.run", side_effect=FileNotFoundError("git")):
        assert _local_head_includes("abc", Path(".")) == (None, "git not installed")
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)):
        answer, why = _local_head_includes("abc", Path("."))
    assert answer is None and "timed out" in why


def test_the_relationship_is_only_asked_when_main_is_red():
    """A green or unknown main needs no "was it mine", so the subprocess is not
    spent on it. Advisory checks earn their keep by being cheap."""
    green = [{**_red_run()[0], "conclusion": "success"}]
    with patch("subprocess.run", return_value=_gh(green)):
        with patch("core.health.main_ci._local_head_includes") as probe:
            status = main_ci_status(repo_root=Path("."))
    assert probe.call_count == 0
    assert status["local_head_includes_run"] is None


# ── Adversarial: worst cases the falsification analyst named (gap WO 094f3c12) ──


@pytest.mark.parametrize(
    "body",
    [
        {"message": "Not Found"},  # a gh/GitHub API error object
        {"runs": []},  # a differently-shaped payload
        [1, 2, 3],  # a list, but not of objects
        ["a string"],
        "just a quoted string",
        42,
        None,
    ],
)
def test_malformed_runs_payload_never_raises(body):
    """gh can exit 0 with valid JSON that is not a list of run objects — an API
    error object, or another command's output when a caller blanket-patches
    subprocess.run (the exact trigger of WO-MAINRED-GH-NONSTR). ``runs[0]`` and
    ``latest.get`` raise KeyError/TypeError/AttributeError on those."""
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps(body)
    proc.stderr = ""
    with patch("subprocess.run", return_value=proc):
        status = main_ci_status(repo_root=Path("."))  # must not raise
    # This assertion was originally `status in ("unknown","success","failure",
    # "running")` — every possible value, so it could not fail and proved nothing.
    # 094f3c12's own verify flagged it. A payload that is not a list of runs is
    # unknown, full stop: any other verdict would be fabricated from data the
    # reader could not parse.
    assert status["status"] == "unknown", f"a non-run payload must be unknown: {body!r}"
    assert status["red"] is False, "an unparseable payload is never a definite failure"
    assert status["reason"], "an unknown must always say why"


def test_doctor_survives_a_raising_main_ci_read(tmp_path):
    """run_doctor_checks completes every prior check and then reads main's CI. If
    that advisory step can abort the report, the operator gets a traceback instead
    of a partial payload — which is precisely how main stayed red for a day."""
    from core.health.doctor import run_doctor_checks

    with patch("core.health.main_ci.main_ci_status", side_effect=RuntimeError("gh exploded")):
        report = run_doctor_checks(source_root=Path("."), dream_studio_home=tmp_path)
    assert report["status"] in ("pass", "warn", "attention_required", "fail")
    main_ci = report["checks"].get("main_ci")
    assert main_ci is not None, "the key must still be present"
    assert main_ci.get("status") == "unknown"
    assert main_ci.get("red") is False
    assert main_ci.get("reason"), "a failed advisory read must say why, not vanish"


def test_the_workflow_name_matches_the_ci_workflow_file():
    """version_skew: this module finds runs by the workflow's DISPLAY NAME. Rename
    `name:` in full-ci.yml and `gh run list --workflow "Full CI"` returns [] forever
    — the reader reports "no Full CI runs found", which is indistinguishable from a
    repo that has simply never run it, and post-merge red goes silently invisible
    again. Two files, one string, no compiler to tie them together: so a test does.
    """
    from core.health.main_ci import _WORKFLOW

    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "full-ci.yml"
    assert workflow.is_file(), f"the workflow this module reads is missing: {workflow}"
    declared = None
    for line in workflow.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            declared = line.split(":", 1)[1].strip().strip("\"'")
            break
    assert declared == _WORKFLOW, (
        f"main_ci.py looks for workflow {_WORKFLOW!r} but full-ci.yml declares "
        f"{declared!r} — post-merge red would become invisible. Update both together."
    )


def test_the_branch_matches_the_workflow_trigger():
    """The OTHER unpinned string in the same `gh run list` call.

    094f3c12's verify caught that pinning `--workflow` while leaving `--branch`
    unpinned covers half of one invocation. `full-ci.yml` runs `on: push:
    branches: [main]`, so if that trigger changes and `_BRANCH` does not, the
    query asks for runs on a branch the workflow never runs on and gets `[]`
    forever — reported as "no Full CI runs found", which is indistinguishable
    from a repo that has simply never run it. Identical failure mode to the
    workflow-name skew, identical invisibility.
    """
    import re

    from core.health.main_ci import _BRANCH

    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "full-ci.yml"
    text = workflow.read_text(encoding="utf-8")
    match = re.search(r"^\s*branches:\s*\[([^\]]*)\]", text, flags=re.MULTILINE)
    assert match, "full-ci.yml no longer declares a push-branches list — re-pin this test"
    declared = [b.strip().strip("\"'") for b in match.group(1).split(",") if b.strip()]
    assert _BRANCH in declared, (
        f"main_ci.py reads branch {_BRANCH!r} but full-ci.yml only runs on {declared!r} — "
        "the query would return no runs forever and post-merge red would go invisible. "
        "Update both together."
    )


# ── close-ceremony advisory ─────────────────────────────────────────────────────


def test_close_surfaces_main_red_advisory(tmp_path):
    """close_work_order carries a main_ci_warning when main is red — a WO must
    not be declared done while its own merge has main red without the operator
    seeing it. Advisory: the close still succeeds."""
    import sqlite3
    import uuid

    from core.config.sqlite_bootstrap import bootstrap_database

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','cleanup','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()

    red = {
        "status": "failure",
        "red": True,
        "head_sha": "deadbeef1234",
        "run_url": "https://example/run/9",
        "title": "some merge",
        "conclusion": "failure",
        "reason": None,
    }
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        with patch("core.health.main_ci.main_ci_status", return_value=red):
            from core.work_orders.close import close_work_order

            result = close_work_order(
                work_order_id=wo_id,
                force=True,  # gates are not under test; the advisory is
                source_root=tmp_path,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )
    assert result["ok"] is True, result
    assert "main is RED" in result["main_ci_warning"]
    assert result["main_ci"]["head_sha"] == "deadbeef1234"


def test_close_is_silent_when_main_is_green(tmp_path):
    """A green (or unknown) main adds no noise to the close output."""
    import sqlite3
    import uuid

    from core.config.sqlite_bootstrap import bootstrap_database

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','cleanup','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()

    green = {
        "status": "success",
        "red": False,
        "head_sha": "a",
        "run_url": "u",
        "title": "t",
        "conclusion": "success",
        "reason": None,
    }
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        with patch("core.health.main_ci.main_ci_status", return_value=green):
            from core.work_orders.close import close_work_order

            result = close_work_order(
                work_order_id=wo_id,
                force=True,
                source_root=tmp_path,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )
    assert result["ok"] is True, result
    assert "main_ci_warning" not in result
