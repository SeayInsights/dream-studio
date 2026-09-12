"""WO-FIX-VERIFY-GATE: independent_review certifies from authority+diff, not
commit-message grep.

The verify gate greps git for the WO id/title. A squash merge never carries the
id into the merged commit, so grep-by-id finds nothing and every squash-merged
WO was forced to close with force=True (or a wo-<shortid> branch-pointer hack).
The fix: when _collect_git_commits finds nothing, fall back to the WO's own
executable AC results (SQL/TEST/API-CHECK) as objective authority proof — a
WO-scoped signal that does not depend on commit messages. Only genuinely-no-
evidence (no commits AND no passing executable check) stays unreviewable
(no false-done). When the `claude` grader CLI is absent (Popen raises
FileNotFoundError), that grader is treated as unreviewable rather than crashing
the whole verify — the post-merge main-red this WO's follow-up repaired.
"""

from __future__ import annotations

import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify import _authority_evidence

NOW = "2026-01-01T00:00:00.000000Z"


def _make_git_repo(tmp_path: Path, messages: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = dict(cwd=str(repo), capture_output=True, text=True, check=True)
    subprocess.run(["git", "init", "-q"], **env)
    subprocess.run(["git", "config", "user.email", "t@t"], **env)
    subprocess.run(["git", "config", "user.name", "t"], **env)
    for i, msg in enumerate(messages):
        (repo / f"f{i}.txt").write_text(msg, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], **env)
        subprocess.run(["git", "commit", "-q", "-m", msg], **env)
    return repo


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield


def _seed_wo(db_path: Path, *, work_order_id: str, title: str, ac: str | None) -> None:
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
        " description, work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, title, "desc", "infrastructure", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, description,"
        " status, created_at, updated_at, acceptance_criteria)"
        " VALUES (?,?,?,?,?,'complete',?,?,?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T1", "do it", NOW, NOW, ac),
    )
    conn.commit()
    conn.close()


class TestUnitHelpers:
    def test_authority_evidence_has_passing_when_ac_passes(self):
        tasks = [{"title": "T1", "status": "complete"}]
        ac_results = {"T1": [{"kind": "SQL-CHECK", "expr": "SELECT 1", "passed": True}]}
        text, has_passing = _authority_evidence("abcd1234-0000", tasks, ac_results)
        assert has_passing is True
        assert "SQL-CHECK PASS" in text
        assert "abcd1234" in text

    def test_authority_evidence_no_passing_without_checks(self):
        tasks = [{"title": "T1", "status": "complete"}]
        text, has_passing = _authority_evidence("abcd1234-0000", tasks, {})
        assert has_passing is False  # nothing objective to certify

    def test_authority_evidence_failing_check_is_not_passing(self):
        tasks = [{"title": "T1", "status": "complete"}]
        ac_results = {"T1": [{"kind": "TEST-CHECK", "expr": "tests/x.py", "passed": False}]}
        _, has_passing = _authority_evidence("wo", tasks, ac_results)
        assert has_passing is False


class TestAuthorityCertification:
    def test_squash_merged_wo_with_passing_ac_certifies_from_authority(self, tmp_path, monkeypatch):
        """No commit references the WO id (squash) and no branch diff (post-merge),
        but a passing SQL-CHECK certifies from authority — NOT unreviewable."""
        monkeypatch.setenv("DREAM_STUDIO_VERIFY_MOCK", "1")  # canned graders
        repo = _make_git_repo(tmp_path, ["chore: unrelated squash commit (#999)"])
        db_path = _make_db(tmp_path)
        wo_id = str(uuid.uuid4())
        _seed_wo(db_path, work_order_id=wo_id, title="WO-SQUASHED - x", ac="SQL-CHECK: SELECT 1")
        # Force both git sources empty so only authority evidence remains.
        monkeypatch.setattr(
            "core.work_orders.verify_git._collect_git_commits", lambda *a, **k: None
        )

        with _patch_db(db_path):
            from core.work_orders.verify import verify_work_order

            result = verify_work_order(
                work_order_id=wo_id,
                source_root=repo,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )

        assert result["ok"] is True
        assert not result.get("unreviewable"), "passing AC should certify, not go unreviewable"
        assert result["certification_basis"] == "authority_evidence"

    def test_no_evidence_at_all_stays_unreviewable(self, tmp_path, monkeypatch):
        """No commit, no branch diff, and NO executable AC → still unreviewable
        (the no-false-done invariant: nothing objective to certify)."""
        monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
        repo = _make_git_repo(tmp_path, ["chore: unrelated"])
        db_path = _make_db(tmp_path)
        wo_id = str(uuid.uuid4())
        _seed_wo(db_path, work_order_id=wo_id, title="WO-NOPE - nothing", ac=None)
        monkeypatch.setattr(
            "core.work_orders.verify_git._collect_git_commits", lambda *a, **k: None
        )

        with _patch_db(db_path):
            from core.work_orders.verify import verify_work_order

            result = verify_work_order(
                work_order_id=wo_id,
                source_root=repo,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )

        assert result["ok"] is True
        assert result["unreviewable"] is True
        assert result["spawned_work_orders"] == []

    def test_grader_cli_absent_is_unreviewable_not_crash(self, tmp_path, monkeypatch):
        """When the `claude` grader CLI is missing (CI), _spawn_grader raises
        FileNotFoundError. Verify must degrade to an unreviewable verdict instead
        of letting the exception abort the whole run — the regression that turned
        main red on the WO-FIX-VERIFY-GATE merge. A passing AC routes into grading
        via the authority-evidence fallback; a missing grader = unreviewable."""

        def _spawn_grader_missing_cli(_prompt, _profile=None):
            # Mirror the real _spawn_grader(prompt, profile) seam: _run_graders_parallel
            # now passes the role's resolved provider profile as the 2nd arg.
            raise FileNotFoundError("[Errno 2] No such file or directory: 'grader-cli'")

        monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
        monkeypatch.setattr(
            "core.work_orders.verify_graders._spawn_grader", _spawn_grader_missing_cli
        )
        repo = _make_git_repo(tmp_path, ["chore: unrelated"])
        db_path = _make_db(tmp_path)
        wo_id = str(uuid.uuid4())
        _seed_wo(db_path, work_order_id=wo_id, title="WO-X - y", ac="SQL-CHECK: SELECT 1")
        monkeypatch.setattr(
            "core.work_orders.verify_git._collect_git_commits", lambda *a, **k: None
        )

        with _patch_db(db_path):
            from core.work_orders.verify import verify_work_order

            result = verify_work_order(
                work_order_id=wo_id,
                source_root=repo,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )

        assert result["ok"] is True  # did not crash
        assert result["unreviewable"] is True
        # A missing CLI surfaces every grader as unreviewable (grader_cli_unavailable).
        assert result["unreviewable_graders"]


# ── WO 654a54d7: a verdict says which commits it could not see ─────────────────


def test_the_verdict_names_the_commits_it_could_not_see(tmp_path, monkeypatch):
    """The number that separates a bad fix from an unread one.

    Three verify runs on WO 20796691 re-reported two findings that were false at HEAD,
    because the graded range ended four commits behind it. One grader noticed in prose;
    nothing computed it, and the stored verdict recorded only `evidence_layer`. A failed
    verdict whose range excluded the fix was indistinguishable from a failed verdict
    about the fix.

    Asserted on the STORED verdict, not just the return value, because close and
    merge-check read the artifact rather than the CLI output.
    """
    import json as _json

    monkeypatch.setenv("DREAM_STUDIO_VERIFY_MOCK", "1")
    repo = _make_git_repo(tmp_path, ["chore: unrelated"])
    db_path = _make_db(tmp_path)
    wo_id = str(uuid.uuid4())
    _seed_wo(db_path, work_order_id=wo_id, title="WO-RANGE - x", ac="SQL-CHECK: SELECT 1")
    monkeypatch.setattr("core.work_orders.verify_git._collect_git_commits", lambda *a, **k: None)

    with _patch_db(db_path):
        from core.work_orders.artifacts import get_wo_artifact
        from core.work_orders.verify import verify_work_order

        result = verify_work_order(
            work_order_id=wo_id,
            source_root=repo,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
        )
        stored = _json.loads(get_wo_artifact(wo_id, "review_verdict", db_path=db_path))

    for where, verdict in (("returned", result), ("stored", stored)):
        described = verdict.get("graded_range")
        assert described is not None, f"the {where} verdict does not say what range it graded"
        assert "range" in described, described
        assert "stops_short_of_head" in described or "unavailable" in described, (
            f"the {where} verdict reports a range without saying whether it reaches HEAD, "
            "which is the fact that distinguishes a finding from an unread tree"
        )


# ── WO 654a54d7: the trailer is derived at commit time, not remembered ─────────


def test_a_commit_under_an_open_work_order_carries_its_trailer(tmp_path, monkeypatch):
    """Derive the trailer from the staged files, so nobody has to remember it.

    THE COST OF REMEMBERING IT LATE, measured 2026-09-11: four commits on this branch had
    to be rebuilt through cherry-pick to add trailers after a verdict had already graded
    the wrong range. The attribution was computable the whole time -- the on-edit
    enforcement hook calls `in_progress_work_order` on every edit to decide whether the
    edit is allowed at all.

    Driven through the real `trailer_for` with a stubbed authority, so the assertions are
    about the rule and not about whichever work orders happen to be open today.
    """
    import scripts.work_order_trailer as wot

    monkeypatch.setattr(wot, "staged_files", lambda repo_root: ["core/work_orders/verify_git.py"])
    import runtime.lib.enforcement as enforcement

    monkeypatch.setattr(
        enforcement, "match_registered_project", lambda p: {"project_id": "p", "project_path": "."}
    )
    monkeypatch.setattr(
        enforcement,
        "in_progress_work_order",
        lambda pid, **kw: {
            "work_order_id": "654a54d7-1a44-49a0-8851-3c1f7a763904",
            "attribution": "module_boundary",
            "claimants": ["654a54d7-1a44-49a0-8851-3c1f7a763904"],
        },
    )

    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("fix(verify): a real change\n", encoding="utf-8")

    assert wot.apply(msg, repo_root=tmp_path) is True
    body = msg.read_text(encoding="utf-8")
    assert body.endswith("Work-Order: 654a54d7-1a44-49a0-8851-3c1f7a763904\n")
    assert body.startswith("fix(verify): a real change"), "the author's message is preserved"


def test_an_ambiguous_attribution_writes_no_trailer(tmp_path, monkeypatch):
    """Two work orders both declaring this path means there is no single right answer.

    Measured on the live authority while building this: `core/work_orders/verify_main.py`
    fell inside FOUR in-progress boundaries at once. Writing either id would make one work
    order look responsible for another's diff, which is worse than an absent trailer --
    the same rule `in_progress_work_order` already applies by returning every claimant
    instead of picking one.
    """
    import scripts.work_order_trailer as wot
    import runtime.lib.enforcement as enforcement

    monkeypatch.setattr(wot, "staged_files", lambda repo_root: ["core/work_orders/x.py"])
    monkeypatch.setattr(
        enforcement, "match_registered_project", lambda p: {"project_id": "p", "project_path": "."}
    )
    monkeypatch.setattr(
        enforcement,
        "in_progress_work_order",
        lambda pid, **kw: {
            "work_order_id": "aaaa",
            "attribution": "module_boundary",
            "claimants": ["aaaa", "bbbb"],
        },
    )

    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("fix: something\n", encoding="utf-8")

    assert wot.apply(msg, repo_root=tmp_path) is False
    assert "Work-Order:" not in msg.read_text(encoding="utf-8")


def test_recency_attribution_is_not_good_enough_for_a_trailer(tmp_path, monkeypatch):
    """`most_recently_started` is the guess the boundary rule exists to replace.

    Stamping it into a commit would make a guess permanent and citable.
    """
    import scripts.work_order_trailer as wot
    import runtime.lib.enforcement as enforcement

    monkeypatch.setattr(wot, "staged_files", lambda repo_root: ["anything.py"])
    monkeypatch.setattr(
        enforcement, "match_registered_project", lambda p: {"project_id": "p", "project_path": "."}
    )
    monkeypatch.setattr(
        enforcement,
        "in_progress_work_order",
        lambda pid, **kw: {"work_order_id": "aaaa", "attribution": "most_recently_started"},
    )

    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("fix: something\n", encoding="utf-8")

    assert wot.apply(msg, repo_root=tmp_path) is False


def test_an_authors_own_trailer_is_never_overwritten(tmp_path, monkeypatch):
    """A tool that rewrites a deliberate attribution is worse than one that adds none."""
    import scripts.work_order_trailer as wot

    monkeypatch.setattr(wot, "staged_files", lambda repo_root: ["core/work_orders/x.py"])
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("fix: x\n\nWork-Order: deliberate-choice\n", encoding="utf-8")

    assert wot.apply(msg, repo_root=tmp_path) is False
    assert "deliberate-choice" in msg.read_text(encoding="utf-8")


def test_the_trailer_hook_never_blocks_a_commit(tmp_path):
    """Advisory by construction: a missing authority must not stop work.

    `main()` returns 0 on every path, including a message file that does not exist.
    """
    import scripts.work_order_trailer as wot

    assert wot.main([str(tmp_path / "nope.txt")]) == 0
    assert wot.main([]) == 0
