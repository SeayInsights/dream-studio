"""WO-MULTIROOT-REVIEW: review the code that actually exists.

Dream Studio modelled a project as exactly one folder. Real development is not shaped
that way, and the cost was measured on the live authority rather than argued:

    project_path for "Fulcrum Skill Library" = <operator home>/Fulcrum  (a container)
    that folder has NO .git of its own — it is a working folder holding many repos

    _collect_git_commits(Fulcrum,          <wo>) -> None          nothing to grade
    _collect_git_commits(Fulcrum/platform, <wo>) -> found commits

So all 28 open Fulcrum work orders were graded with no diff at all. Verify fell through
to "independent review unverifiable — no diff provided", and the correctness grader —
holding only Dream Studio's own layer-map rules and no code — produced a work order whose
single task read "Fix N/A: independent review unverifiable — no diff provided in N/A".

The single-root model, the "reviews against Dream Studio" complaint, and that nonsense
work order are ONE defect with three symptoms.

TWO THINGS MEASUREMENT CORRECTED WHILE THIS WAS BUILT, both recorded in the tests below:
a worktree's ``.git`` is a FILE, so a shell check for a ``.git`` directory saw six repos
where there are thirty-five; and returning the first of many roots handed every legacy
caller an arbitrary worktree, which is worse than returning nothing.
"""

from __future__ import annotations

import sqlite3
import subprocess
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.project_roots import ProjectRoots, resolve_project_roots
from core.work_orders.review_rules import (
    PROFILE_NAME,
    SDLC_BASELINE,
    parse_profile,
    render_rules_block,
    resolve_review_rules,
)

NL = chr(10)

_NOW = "2026-08-26T00:00:00+00:00"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def _make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "file.txt").write_text("x", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _project_with_path(db: Path, project_path: Path) -> str:
    """A project whose code lives at ``project_path``, and one open work order."""
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at, project_path)"
        " VALUES (?,?,?,?,?,?,?)",
        (project_id, "P", "", "active", _NOW, _NOW, str(project_path)),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, _NOW, _NOW),
    )
    conn.commit()
    conn.close()
    return wo_id


# ── Task 1: a project resolves to MULTIPLE roots ──────────────────────────────


def test_a_single_repo_project_is_unchanged(db, tmp_path):
    """The four single-repo projects in the live authority must resolve exactly as they
    did. A multi-root change that moves them is a regression, not a feature."""
    repo = _make_repo(tmp_path / "solo")
    wo = _project_with_path(db, repo)

    roots = resolve_project_roots(wo, db)
    assert roots.roots == [repo]
    assert roots.is_container is False
    assert roots.primary == repo
    assert roots.reason is None


def test_a_container_root_resolves_to_its_nested_repos(db, tmp_path):
    """The Fulcrum shape: a working folder holding repos, with no .git of its own."""
    container = tmp_path / "workspace"
    (container / "notes").mkdir(parents=True)
    (container / "README.md").write_text("docs", encoding="utf-8")
    alpha = _make_repo(container / "alpha")
    beta = _make_repo(container / "beta")

    wo = _project_with_path(db, container)
    roots = resolve_project_roots(wo, db)

    assert roots.is_container is True
    assert set(roots.roots) == {alpha, beta}
    assert roots.declared == container


def test_a_worktree_is_a_checkout_of_a_repository_not_a_root(db, tmp_path):
    """A WORKTREE IS NOT A REPOSITORY, and conflating them turns 6 grading targets into
    35. Measured on the live layout: Fulcrum holds 6 repositories and 29 worktrees —
    branches checked out as folders, each sharing its repository's history. Grading them
    as roots would grade the same code many times over.

    Git marks the difference exactly: a repository has a ``.git`` DIRECTORY, a worktree
    has a ``.git`` FILE reading ``gitdir: <repo>/.git/worktrees/<name>``. An earlier
    shell check that tested only for a ``.git`` directory therefore saw 6 where there
    are 35 objects — the count that first told me the model was wrong.
    """
    container = tmp_path / "workspace"
    container.mkdir()
    main = _make_repo(container / "main")
    worktree = container / "task-branch"
    _git(main, "worktree", "add", "-q", "-b", "task", str(worktree))

    assert (worktree / ".git").is_file(), "precondition: a worktree's .git is a FILE"
    assert (main / ".git").is_dir(), "precondition: a repository's .git is a DIRECTORY"

    wo = _project_with_path(db, container)
    roots = resolve_project_roots(wo, db)

    assert roots.roots == [main], f"only the repository is a root; got {roots.roots}"
    assert worktree not in roots.roots
    assert [c[0] for c in roots.checkouts] == [worktree], "the branch is recorded as a checkout"
    assert roots.checkouts[0][1] == main, "and mapped to the repository it belongs to"


def test_git_kind_and_worktree_repository_read_the_real_markers(tmp_path):
    """The two primitives the whole count depends on, driven against a real worktree
    rather than a described one — the repo/worktree distinction is exactly the thing an
    invented fixture would get wrong."""
    from core.work_orders.project_roots import git_kind, worktree_repository

    repo = _make_repo(tmp_path / "repo")
    worktree = tmp_path / "branch-as-a-folder"
    _git(repo, "worktree", "add", "-q", "-b", "feature", str(worktree))

    assert git_kind(repo) == "repository"
    assert git_kind(worktree) == "worktree"
    assert git_kind(tmp_path) is None, "an ordinary folder is neither"

    assert worktree_repository(worktree) == repo, "a checkout resolves to its repository"
    assert worktree_repository(repo) is None, "a repository is not a checkout of anything"


def test_a_declared_worktree_is_graded_as_the_code_it_is(db, tmp_path):
    """If the operator points a project AT a branch checkout, that IS the code they mean.
    Grade it, and record which repository it came from."""
    container = tmp_path / "workspace"
    container.mkdir()
    main = _make_repo(container / "main")
    worktree = container / "task-branch"
    _git(main, "worktree", "add", "-q", "-b", "task", str(worktree))

    wo = _project_with_path(db, worktree)
    roots = resolve_project_roots(wo, db)
    assert roots.roots == [worktree]
    assert roots.checkouts == [(worktree, main)]


def test_discovery_does_not_descend_into_a_repo(db, tmp_path):
    """A repo's own subdirectories are part of it, not sibling roots. Descending would
    turn one repo into many and multiply everything downstream."""
    container = tmp_path / "workspace"
    container.mkdir()
    repo = _make_repo(container / "alpha")
    (repo / "vendor").mkdir()

    wo = _project_with_path(db, container)
    assert resolve_project_roots(wo, db).roots == [repo]


# ── Task 2: a container is DESCRIBED, never returned as nothing ───────────────


def test_a_container_root_is_described_not_null(db, tmp_path):
    """``None`` is what became "Fix N/A in N/A": answering "nothing here" for a folder
    holding repos reports absence where the truth is "you are looking one level too
    high". Those have different remedies."""
    container = tmp_path / "workspace"
    container.mkdir()
    _make_repo(container / "alpha")
    _make_repo(container / "beta")

    wo = _project_with_path(db, container)
    described = resolve_project_roots(wo, db).describe()

    assert "not itself a repository" in described
    assert "2 repositories" in described
    assert "alpha" in described and "beta" in described, "name them, so a caller can traverse"


def test_an_unreachable_root_is_reported_not_silently_skipped(db, tmp_path):
    """A declared path that does not exist is a stated fact with a reason, never an
    empty answer that reads like 'no code here'."""
    wo = _project_with_path(db, tmp_path / "does-not-exist")
    roots = resolve_project_roots(wo, db)

    assert roots.roots == []
    assert roots.reason and "not a directory" in roots.reason
    assert roots.unreachable, "the path must be named as unreachable"
    assert "does-not-exist" in roots.unreachable[0][0]


def test_a_folder_under_no_version_control_is_still_a_root(db, tmp_path):
    """NOT EVERYTHING IS PUSHED TO GITHUB, and plenty of work is never version-controlled
    at all. An earlier cut required ``.git`` for a root, which resolved such a project to
    nothing — and broke test_one_work_order_two_checkouts_one_verdict within minutes,
    because its checkouts are plain directories.

    The folder IS where the code lives. ``versioned`` says git evidence is unavailable so
    a caller can pick a different evidence strategy, rather than being handed nothing.
    """
    plain = tmp_path / "just-work"
    (plain / "sub").mkdir(parents=True)
    (plain / "notes.md").write_text("x", encoding="utf-8")

    wo = _project_with_path(db, plain)
    roots = resolve_project_roots(wo, db)

    assert roots.roots == [plain], "the folder itself is the root"
    assert roots.versioned is False
    assert roots.primary == plain, "and a single-path caller still gets it"
    assert "not under version control" in roots.describe()


def test_a_project_with_no_declared_path_states_that(db):
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    roots = resolve_project_roots(wo_id, db)
    assert roots.reason == "the project declares no project_path"


# ── The regression a single `primary` would have shipped ──────────────────────


def test_primary_never_guesses_between_many_roots(db, tmp_path):
    """THE REGRESSION MEASUREMENT CAUGHT. The first cut returned ``roots[0]``, so every
    legacy single-path caller got Fulcrum's alphabetically first worktree — an arbitrary
    wrong repo. That is worse than the useless-but-honest folder the old resolver
    returned, because a TEST-CHECK would then RUN there and report a result about the
    wrong code.

    One root means one answer; many means the caller must say which.
    """
    container = tmp_path / "workspace"
    container.mkdir()
    _make_repo(container / "aaa-first-alphabetically")
    _make_repo(container / "zzz-the-one-you-wanted")

    wo = _project_with_path(db, container)
    roots = resolve_project_roots(wo, db)

    assert len(roots.roots) == 2
    # UPDATED: primary is the DECLARED path, not None and not one of the repositories.
    # Asserting None here was correct about the guessing and wrong about the remedy —
    # every caller does `resolve_project_root(...) or source_root`, so None sent a Fulcrum
    # work order to grade against the Dream Studio repo. The declared path keeps the
    # caller inside the right project; see
    # test_a_container_project_never_resolves_to_the_dream_studio_repo.
    assert roots.primary not in roots.roots, "still no guessing between the repositories"
    assert roots.primary == container, "and it stays inside the declared project"


def test_the_legacy_resolver_is_unchanged_for_single_repo_projects(db, tmp_path):
    """resolve_project_root now delegates here, so its contract for the common case is
    asserted through the real function every existing caller uses."""
    from core.work_orders.verify_executor import resolve_project_root

    repo = _make_repo(tmp_path / "solo")
    wo = _project_with_path(db, repo)
    assert resolve_project_root(wo, db) == repo


def test_a_broken_authority_yields_a_reason_not_an_exception(tmp_path):
    """A resolver that raises takes verify down with it. Every failure is a stated
    reason."""
    roots = resolve_project_roots(str(uuid.uuid4()), tmp_path / "absent.db")
    assert isinstance(roots, ProjectRoots)
    assert roots.roots == []
    assert roots.reason


# ── Adversarial: primary must never send a caller to the wrong project ────────


def test_a_container_project_never_resolves_to_the_dream_studio_repo(db, tmp_path):
    """reachability_vs_config, and the operator's original complaint reintroduced by my
    own fix.

    Every caller does ``resolve_project_root(...) or source_root``. Returning None for a
    container therefore sent a Fulcrum work order to grade against the DREAM STUDIO repo,
    and ``run_executable_checks(project_root=None)`` documents its cwd as "the current
    process dir (the DS repo)". Verified on the live authority before the fix:
    resolve_project_root returned None and _search_root became the DS repo.

    The declared path keeps the caller inside the right project. Git finds no commits
    there, so verify reports "no diff located" and a TEST-CHECK reports "could not run" —
    honestly unreviewable, rather than a confident verdict about someone else's code.
    """
    from core.work_orders.verify_executor import resolve_project_root

    container = tmp_path / "workspace"
    container.mkdir()
    _make_repo(container / "alpha")
    _make_repo(container / "beta")
    wo = _project_with_path(db, container)

    roots = resolve_project_roots(wo, db)
    assert len(roots.roots) == 2, "precondition: ambiguous, several repositories"

    resolved = resolve_project_root(wo, db)
    assert resolved is not None, "None would make every caller fall back to the DS repo"
    assert resolved == container, "the declared path — inside the right project"
    assert resolved not in roots.roots, "and not a guess between the repositories"


def test_primary_still_returns_the_one_root_when_there_is_only_one(db, tmp_path):
    """The common case must be untouched by the ambiguity handling."""
    repo = _make_repo(tmp_path / "solo")
    wo = _project_with_path(db, repo)
    assert resolve_project_roots(wo, db).primary == repo


def test_primary_is_none_only_when_there_is_genuinely_nothing(db, tmp_path):
    """A project with no usable path is the ONLY case where falling back to the caller's
    own root is defensible — a Dream-Studio-self work order."""
    wo = _project_with_path(db, tmp_path / "absent")
    roots = resolve_project_roots(wo, db)
    assert roots.roots == []
    assert roots.primary is None


# -- Task 3: grade the union of roots, and say which contributed ---------------


def _fake_collector(found_in: set[str]):
    """A collector that reports commits only for the named root basenames."""

    def _collect(root, work_order_id, title=None):
        return f"diff from {Path(root).name}" if Path(root).name in found_in else None

    return _collect


def test_the_verdict_records_which_roots_contributed(db, tmp_path):
    """MEASURED on the live authority: Fulcrum resolves to 6 repositories and exactly
    ONE of them (platform) holds the commits. Before this, verify collected from a single
    root, found nothing, and graded all 28 open Fulcrum work orders with no diff at all.

    A verdict that silently graded 1 of 6 repositories is worse than one that says so,
    because "no violations found" and "nothing was read" are indistinguishable in a
    score. So the ratio is recorded, per root, with a reason for every empty one.
    """
    from core.work_orders.verify_git import collect_union_evidence, union_evidence_summary

    container = tmp_path / "workspace"
    container.mkdir()
    for name in ("alpha", "beta", "gamma"):
        _make_repo(container / name)
    wo = _project_with_path(db, container)

    roots = resolve_project_roots(wo, db)
    assert len(roots.roots) == 3, f"precondition: three repositories, got {len(roots.roots)}"

    diff, provenance = collect_union_evidence(wo, roots, collector=_fake_collector({"beta"}))

    assert diff is not None, "the one root with commits must still produce evidence"
    assert "diff from beta" in diff

    by_name = {Path(str(p["root"])).name: p for p in provenance}
    assert set(by_name) == {"alpha", "beta", "gamma"}, "every root must be accounted for"
    assert by_name["beta"]["contributed"] is True
    assert by_name["alpha"]["contributed"] is False
    assert by_name["gamma"]["contributed"] is False

    # An empty root must say WHY it was empty. "read fine, no commits" and "could not be
    # read" are different facts and only one of them is a problem.
    assert by_name["alpha"]["reason"], "an empty root with no reason is unattributable"
    assert "no commits reference" in str(by_name["alpha"]["reason"])

    assert "1 of 3" in union_evidence_summary(provenance)
    assert "beta" in union_evidence_summary(provenance)


def test_a_root_that_contributed_nothing_is_not_reported_as_a_failure(db, tmp_path):
    """Most roots of a multi-repo project legitimately hold nothing for a given work
    order. Reporting those as errors would make the summary useless noise."""
    from core.work_orders.verify_git import collect_union_evidence

    container = tmp_path / "workspace"
    container.mkdir()
    _make_repo(container / "one")
    _make_repo(container / "two")
    wo = _project_with_path(db, container)

    _diff, provenance = collect_union_evidence(
        wo, resolve_project_roots(wo, db), collector=_fake_collector(set())
    )

    for entry in provenance:
        reason = str(entry["reason"])
        assert "could not be read" not in reason, f"a readable empty root called an error: {reason}"


def test_no_root_producing_evidence_returns_none_not_an_empty_string(db, tmp_path):
    """The existing contract: None means "no evidence", and callers must treat it as
    neither a certified pass nor an auto-zero. An empty string would read as "a diff was
    collected and it was empty", which is a different and wrong claim.
    """
    from core.work_orders.verify_git import collect_union_evidence

    container = tmp_path / "workspace"
    container.mkdir()
    _make_repo(container / "solo")
    wo = _project_with_path(db, container)

    diff, provenance = collect_union_evidence(
        wo, resolve_project_roots(wo, db), collector=_fake_collector(set())
    )
    assert diff is None, "no evidence must be None, never an empty string"
    assert provenance, "and it must still say which roots were examined"


def test_a_root_that_raises_does_not_lose_the_readable_ones(db, tmp_path):
    """One unreadable repository in a six-repository project must not cost the evidence
    from the other five -- that would turn a partial read into a total blackout."""
    from core.work_orders.verify_git import collect_union_evidence

    container = tmp_path / "workspace"
    container.mkdir()
    _make_repo(container / "good")
    _make_repo(container / "broken")
    wo = _project_with_path(db, container)

    def _collect(root, work_order_id, title=None):
        if Path(root).name == "broken":
            raise OSError("git exploded")
        return "diff from good"

    diff, provenance = collect_union_evidence(wo, resolve_project_roots(wo, db), collector=_collect)

    assert diff and "diff from good" in diff, "the readable root's evidence was lost"
    broken = next(p for p in provenance if Path(str(p["root"])).name == "broken")
    assert broken["contributed"] is False
    assert "could not be read" in str(broken["reason"])
    assert "OSError" in str(broken["reason"]), "name the failure so it can be fixed"


def test_a_single_root_project_is_not_labeled_per_root(db, tmp_path):
    """The common case must read exactly as it did before. Labeling a lone root's diff
    with "=== evidence from root ... ===" would add noise to every single-repo verdict
    and change the grader's input for no reason."""
    from core.work_orders.verify_git import collect_union_evidence

    repo = _make_repo(tmp_path / "solo")
    wo = _project_with_path(db, repo)

    diff, provenance = collect_union_evidence(
        wo, resolve_project_roots(wo, db), collector=_fake_collector({"solo"})
    )
    assert diff == "diff from solo", f"a single root must not be relabeled; got {diff!r}"
    assert len(provenance) == 1


def test_an_unversioned_root_says_git_evidence_is_unavailable(db, tmp_path):
    """Operator: "not everything will always be pushed to a github."

    A root with no .git is not a failure and not an absence of work -- it is an absence
    of THIS evidence layer. Saying so is what lets a later task pick a different layer
    instead of scoring zero.
    """
    from core.work_orders.verify_git import collect_union_evidence

    plain = tmp_path / "no_git_here"
    plain.mkdir()
    (plain / "main.py").write_text("print('real work, never pushed')\n", encoding="utf-8")
    wo = _project_with_path(db, plain)

    roots = resolve_project_roots(wo, db)
    if not roots.roots:
        pytest.skip("an unversioned declared path resolves to no root in this build")

    _diff, provenance = collect_union_evidence(wo, roots, collector=_fake_collector(set()))
    reasons = " ".join(str(p["reason"]) for p in provenance)
    assert "not a git repository" in reasons
    assert "not the same as no work" in reasons, "absence of git must not read as absence of work"


# -- Task 4: an executable check names the root it ran in ----------------------


def test_a_check_result_names_its_root(db, tmp_path):
    """With six roots, "1 failed" cannot be located without knowing which repository ran
    it. Extends the executed/not_executed_reason provenance already on each check."""
    from core.work_orders.verify_executor import run_executable_checks

    repo = _make_repo(tmp_path / "target")
    tasks = [{"title": "T", "acceptance_criteria": "SQL-CHECK: SELECT 1"}]

    results = run_executable_checks(tasks, db, repo)
    check = results["T"][0]
    assert "ran_in" in check, "every check result must say where it executed"
    assert check["ran_in"], "an empty ran_in is the same as not having it"


def test_a_test_check_names_the_repo_it_ran_in(db, tmp_path):
    """The kind that actually has a root. A TEST-CHECK runs with the project root as cwd,
    so that path is the locator for a failure."""
    from core.work_orders.verify_executor import run_executable_checks

    repo = _make_repo(tmp_path / "target")
    tasks = [{"title": "T", "acceptance_criteria": "TEST-CHECK: cmd: python -c pass"}]

    check = run_executable_checks(tasks, db, repo)["T"][0]
    assert str(repo) == check["ran_in"], f"expected the repo path, got {check['ran_in']!r}"


def test_a_test_check_with_no_resolved_root_says_it_ran_in_the_ds_repo(db, tmp_path):
    """The dangerous case, stated plainly. project_root=None runs in the current process
    directory -- the Dream Studio repo -- which is how a Fulcrum work order came to be
    graded against Dream Studio. Silence here is what made that invisible.
    """
    from core.work_orders.verify_executor import run_executable_checks

    tasks = [{"title": "T", "acceptance_criteria": "TEST-CHECK: cmd: python -c pass"}]
    check = run_executable_checks(tasks, db, None)["T"][0]

    assert "Dream Studio repo" in check["ran_in"]
    assert (
        "did NOT run in the work order" in check["ran_in"]
    ), "it must say the work order's own repo was not used, not merely name a directory"


def test_a_sql_check_does_not_claim_to_have_run_in_a_repo(db, tmp_path):
    """Stamping project_root on all three kinds would be convenient and false: a
    SQL-CHECK runs against the authority database, not a repository."""
    from core.work_orders.verify_executor import run_executable_checks

    repo = _make_repo(tmp_path / "target")
    tasks = [{"title": "T", "acceptance_criteria": "SQL-CHECK: SELECT 1"}]

    check = run_executable_checks(tasks, db, repo)["T"][0]
    assert str(repo) != check["ran_in"], "a SQL-CHECK must not claim the repo as its context"
    assert "authority database" in check["ran_in"]
    assert "not a repository root" in check["ran_in"]


def test_an_unknown_check_kind_still_carries_a_context(db, tmp_path):
    """Fail-closed results are consumed by the same readers. A missing key there means a
    consumer has to branch on kind before it can read provenance."""
    from core.work_orders.verify_executor import run_executable_checks

    tasks = [{"title": "T", "acceptance_criteria": "UNKNOWN-CHECK: whatever"}]
    check = run_executable_checks(tasks, db, None)["T"][0]

    assert check["passed"] is False
    assert "ran_in" in check
    assert "nothing was executed" in check["ran_in"]


# -- Tasks 5-6: the rules layer ------------------------------------------------


def _write_profile(root: Path, body: str) -> Path:
    path = root / PROFILE_NAME
    path.write_text(body, encoding="utf-8")
    return path


def test_nothing_declared_gets_the_dream_studio_default(tmp_path):
    """Operator: "out of the box it works with ours and until otherwise stated that will
    remain." A project that declares nothing is graded against the DS baseline -- not
    against nothing, and not against a guess."""
    plain = tmp_path / "some_project"
    plain.mkdir()

    ruleset = resolve_review_rules(project_root=plain)

    assert ruleset.mode == "default"
    assert list(ruleset.rules) == list(SDLC_BASELINE), "the baseline, unmodified"
    assert "no project or folder profile declared" in ruleset.provenance


def test_a_project_profile_can_add(tmp_path):
    """ADD is the common case: keep the industry baseline, layer this project's own
    rules on top."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_profile(root, "mode: add\n\n- HOUSE RULE: no raw SQL outside the dal module.\n")

    ruleset = resolve_review_rules(project_root=root)

    assert ruleset.mode == "add"
    assert len(ruleset.rules) == len(SDLC_BASELINE) + 1
    assert any("HOUSE RULE" in r for r in ruleset.rules)
    assert all(b in ruleset.rules for b in SDLC_BASELINE), "adding must not drop a baseline rule"
    assert "PLUS 1 rule(s) added by" in ruleset.provenance


def test_a_project_profile_can_replace(tmp_path):
    """Operator: "they should be able to replace per project or folder if they choose as
    well." REPLACE means the baseline is gone -- that is the point of the word."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_profile(root, "mode: replace\n\n- ONLY RULE: ship it.\n")

    ruleset = resolve_review_rules(project_root=root)

    assert ruleset.mode == "replace"
    assert ruleset.rules == ["ONLY RULE: ship it."]
    for baseline_rule in SDLC_BASELINE:
        assert baseline_rule not in ruleset.rules
    assert "REPLACED the Dream Studio baseline" in ruleset.provenance


def test_a_folder_profile_outranks_its_project(tmp_path):
    """Per-FOLDER granularity is why multi-root needed this: six repositories under one
    project may not want one rulebook, and the repository that declares its own rules is
    nearer the code than the project is."""
    project = tmp_path / "workspace"
    folder = project / "special_repo"
    folder.mkdir(parents=True)
    _write_profile(project, "mode: add\n\n- PROJECT RULE: something.\n")
    _write_profile(folder, "mode: replace\n\n- FOLDER RULE: only this.\n")

    ruleset = resolve_review_rules(project_root=project, folders=[folder])

    assert ruleset.mode == "replace"
    assert ruleset.rules == ["FOLDER RULE: only this."]
    assert not any("PROJECT RULE" in r for r in ruleset.rules), "the folder replace must win"


def test_a_folder_add_layers_onto_a_project_replace(tmp_path):
    """A replace at the project level and an add in one folder: the folder is nearer, so
    its rules apply ON TOP of what the project replaced the baseline with, rather than
    being discarded along with it."""
    project = tmp_path / "workspace"
    folder = project / "repo_a"
    folder.mkdir(parents=True)
    _write_profile(project, "mode: replace\n\n- PROJECT ONLY: a.\n")
    _write_profile(folder, "mode: add\n\n- FOLDER EXTRA: b.\n")

    ruleset = resolve_review_rules(project_root=project, folders=[folder])

    assert any("PROJECT ONLY" in r for r in ruleset.rules)
    assert any("FOLDER EXTRA" in r for r in ruleset.rules)
    for baseline_rule in SDLC_BASELINE:
        assert baseline_rule not in ruleset.rules, "a replace still discards the baseline"


def test_a_profile_with_no_mode_adds_rather_than_replaces(tmp_path):
    """The safe default. Someone writing a profile without reading the docs should EXTEND
    the industry baseline, never silently discard it -- discarding has to be deliberate."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_profile(root, "- A RULE WITH NO MODE DECLARED: check something.\n")

    ruleset = resolve_review_rules(project_root=root)

    assert ruleset.mode == "add"
    assert all(b in ruleset.rules for b in SDLC_BASELINE)


def test_an_unreadable_or_empty_profile_falls_back_to_the_baseline(tmp_path):
    """A typo in a profile must not silently disarm the review. Zero rules parsed means
    the profile is ignored and the baseline stands -- failing toward MORE checking."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_profile(root, "mode: replace\n\nthis file has prose but no bullet rules at all\n")

    ruleset = resolve_review_rules(project_root=root)

    assert ruleset.mode == "default", "a ruleless profile must not disarm the review"
    assert list(ruleset.rules) == list(SDLC_BASELINE)


def test_the_baseline_states_sdlc_standards_not_ds_paths():
    """RULING 2. Seven of the old prompt's eight rules named Dream Studio files by path,
    so the universal standards were never stated at all and every other project was
    graded against one project's file layout.

    The test for whether a rule belongs in the baseline: could it be applied to a
    repository nobody on this team has ever seen?
    """
    joined = " ".join(SDLC_BASELINE)

    for ds_token in (
        "business_*",
        "studio.db",
        "DuckDB",
        "files.db",
        "spool/ingestor",
        "runtime/hooks/",
        "core/projections/",
        "interfaces/cli/",
        "released_version",
        "canonical_events",
        "aspirational-schema-debt",
    ):
        assert ds_token not in joined, f"baseline names a Dream Studio specific: {ds_token!r}"

    # And it must actually STATE the standards, not merely omit DS's map.
    for standard in ("TEST COVERAGE", "SECRET", "LAYERING", "DEAD CODE", "DATA SAFETY"):
        assert standard in joined, f"baseline is missing the {standard} standard"


def test_ds_layer_map_is_scoped_to_the_dream_studio_project():
    """DS's own rules ship as a PROFILE in the DS repo, making Dream Studio the first
    customer of the extension point rather than a hardcoded special case. If this file
    cannot carry these rules, the mechanism cannot carry anyone else's.
    """
    ds_profile = Path(PROFILE_NAME)
    assert ds_profile.is_file(), f"Dream Studio's own profile is missing at {ds_profile}"

    # AND GIT MUST ACTUALLY SHIP IT. The first location was under .dream-studio/, which
    # .gitignore excludes -- so this file existed locally, this test passed locally, and
    # every other checkout would have silently fallen back to the bare SDLC baseline.
    # Asserting is_file() alone cannot tell those apart.
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(ds_profile)],
        capture_output=True,
        text=True,
        # text=True with no encoding decodes as cp1252 on Windows, so a single non-cp1252
        # byte in git's output raises UnicodeDecodeError in the reader thread. The
        # locale-decode gate exists for exactly this and caught this line.
        encoding="utf-8",
        errors="replace",
    )
    assert tracked.returncode == 0, (
        f"{ds_profile} exists on disk but git does not track it, so it will not ship: "
        f"{tracked.stderr.strip()}"
    )

    mode, rules = parse_profile(ds_profile.read_text(encoding="utf-8"))
    assert mode == "add", "DS's map extends the baseline; it does not replace it"
    joined = " ".join(rules)
    assert "LAYER-MAP Rule 4" in joined, "the layer map must survive the move into a profile"
    assert "spool/ingestor.py" in joined


def test_a_project_without_a_profile_is_never_graded_against_ds_rules(tmp_path):
    """THE OPERATOR'S COMPLAINT, DIRECTLY: "the reviewer attempts to review against dream
    studio when the code is addressing other work ... this is just bogus."

    Verified as an absence, because that is what was wrong: the rules were present when
    they had no business being present.
    """
    other = tmp_path / "someone_elses_project"
    other.mkdir()

    block = render_rules_block(resolve_review_rules(project_root=other))

    for ds_token in ("LAYER-MAP", "business_*", "spool/ingestor", "studio.db", "DuckDB"):
        assert ds_token not in block, f"a foreign project was handed a DS rule: {ds_token!r}"
    assert "TEST COVERAGE FOR CHANGED BEHAVIOUR" in block, "but it still gets the baseline"


def test_the_correctness_prompt_carries_the_resolved_rules_and_says_which(tmp_path):
    """A ruleset resolved and then not used would be the attachment_pressure defect
    again: computed, stored nowhere, reaching nothing. And a review that cannot say which
    rulebook it used is not auditable."""
    from core.work_orders.verify_prompts import _CORRECTNESS_PROMPT_TEMPLATE

    root = tmp_path / "proj"
    root.mkdir()
    _write_profile(root, "mode: add\n\n- DISTINCTIVE HOUSE RULE: xyzzy.\n")
    ruleset = resolve_review_rules(project_root=root)

    prompt = _CORRECTNESS_PROMPT_TEMPLATE.format(
        git_diff="<diff>",
        rules_block=render_rules_block(ruleset),
        rules_provenance=ruleset.provenance,
        rule_count=float(len(ruleset.rules)),
    )

    assert "DISTINCTIVE HOUSE RULE: xyzzy." in prompt, "the resolved rules must reach the grader"
    assert ruleset.provenance in prompt, "the prompt must name the rulebook in force"
    assert "/ 7.0" not in prompt, "the score divisor must follow the rule count, not a constant"


def test_the_prompt_tells_the_grader_its_inability_is_not_a_violation():
    """WO-GAP-FANOUT found work order 58e21003 carrying the task "Fix N/A: independent
    review unverifiable - no diff provided in N/A" -- the grader's own inability laundered
    into scheduled work. The filter that drops those is downstream; this stops the grader
    emitting them."""
    from core.work_orders.verify_prompts import _CORRECTNESS_PROMPT_TEMPLATE

    # Case-insensitive: the template writes "NOT a violation" for emphasis, and this
    # asserted the lowercase form. My own check confirmed the OTHER half of the phrase
    # ("never become scheduled work") and passed, so the mismatch survived -- verifying
    # the half that matched is the same shortcut this whole work order is about.
    lowered = _CORRECTNESS_PROMPT_TEMPLATE.lower()
    assert "not a violation" in lowered
    assert "never become scheduled work" in lowered


def test_a_project_with_no_declared_root_still_gets_its_own_diff(db, tmp_path):
    """THE FALLBACK THIS WORK ORDER DROPPED AND PUT BACK.

    The single-root code read ``resolve_project_root(...) or source_root``, and that
    ``or`` was load-bearing. A work order whose project declares no path resolves to ZERO
    roots, so iterating roots.roots collected nothing and the parent's own diff vanished
    from the grader input.

    Caught by test_closed_child_diffs_join_parent_evidence, which failed in the worst
    possible shape: the CHILD's remediation evidence still arrived while the parent's own
    change did not. A verdict built on remediation alone looks substantive, so nothing in
    the output would have said the parent was never read.
    """
    from core.work_orders.verify_git import collect_union_evidence

    wo = _project_with_path(db, tmp_path / "declared-nothing-usable")
    roots = resolve_project_roots(wo, db)
    assert roots.roots == [], "precondition: the project resolves to no root"

    caller_root = _make_repo(tmp_path / "callers-own-repo")
    diff, provenance = collect_union_evidence(
        wo, roots, fallback_root=caller_root, collector=lambda r, w, title=None: "the diff"
    )

    assert diff == "the diff", "with no declared root, the caller's root must still be read"
    assert provenance, "and the fallback must be recorded, not silent"
    assert provenance[0].get("fallback") is True
    assert "declared none" in str(
        provenance[0]["kind"]
    ), "a reader must be able to tell a fallback from a declared root"


def test_no_fallback_offered_means_the_absence_is_reported(db, tmp_path):
    """The converse: a caller that offers no fallback gets an honest empty result with a
    reason, never a silent None."""
    from core.work_orders.verify_git import collect_union_evidence

    wo = _project_with_path(db, tmp_path / "nothing-here")
    roots = resolve_project_roots(wo, db)

    diff, provenance = collect_union_evidence(wo, roots)
    assert diff is None
    assert provenance, "the absence must still be described"
    assert not provenance[0].get("fallback")


def test_a_declared_root_is_preferred_over_the_fallback(db, tmp_path):
    """The fallback must not shadow real roots -- offering one must change nothing when
    the project resolves properly."""
    from core.work_orders.verify_git import collect_union_evidence

    repo = _make_repo(tmp_path / "real")
    wo = _project_with_path(db, repo)
    other = _make_repo(tmp_path / "unrelated")

    _diff, provenance = collect_union_evidence(
        wo,
        resolve_project_roots(wo, db),
        fallback_root=other,
        collector=lambda r, w, title=None: f"from {Path(r).name}",
    )
    roots_seen = {Path(str(p["root"])).name for p in provenance}
    assert roots_seen == {"real"}, f"the fallback leaked in: {roots_seen}"


# -- The verdict itself, not the helpers under it ------------------------------


def test_the_project_tier_reads_the_declared_path_not_a_repo_inside_it(db, tmp_path):
    """MEASURED: for a container declaring a single repository, ``primary`` is that
    REPOSITORY, not the container. resolve_review_rules was handed ``primary``, so a
    project-level ``.ds-review-rules.md`` at the declared container was never read and the
    "project" tier of folder > project > baseline could not be reached in production.

    Every rules test passed anyway, because they declare the container path directly and
    never went through the resolution verify actually uses. Found by the correctness
    grader on this work order's own close, phrased as NO DEAD CODE: an advertised layer no
    path can reach.
    """
    container = tmp_path / "workspace"
    container.mkdir()
    _make_repo(container / "only-repo")
    (container / PROFILE_NAME).write_text(
        "mode: add" + NL * 2 + "- PROJECT TIER RULE: reachable." + NL, encoding="utf-8"
    )
    wo = _project_with_path(db, container)

    roots = resolve_project_roots(wo, db)
    assert roots.primary != container, (
        "precondition: primary is the single repo, not the container -- if this ever "
        "changes, the bug this test guards has moved rather than gone"
    )
    assert roots.declared == container

    # What verify does now: the DECLARED path is the project tier.
    from core.work_orders.review_rules import resolve_review_rules

    ruleset = resolve_review_rules(project_root=roots.declared, folders=list(roots.roots))
    assert any(
        "PROJECT TIER RULE" in r for r in ruleset.rules
    ), "a project-level profile at the declared root must be read"

    # And the old behaviour is genuinely broken, so this test can fail.
    missed = resolve_review_rules(project_root=roots.primary, folders=list(roots.roots))
    assert not any("PROJECT TIER RULE" in r for r in missed.rules), (
        "passing primary must MISS the container profile -- otherwise this test proves "
        "nothing about the fix"
    )


def _declare_boundary(db: Path, work_order_id: str, boundary: str) -> None:
    """Give a work order a declared module boundary, the way a real one carries it."""
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE business_work_orders SET description = ? WHERE work_order_id = ?",
        (f"Module boundary: {boundary}.", work_order_id),
    )
    conn.commit()
    conn.close()


# -- Task 7: evidence must not require git, and must name the layer -------------


def test_a_project_with_no_git_still_yields_evidence(db, tmp_path):
    """ "No git" is an ORDINARY SUPPORTED CASE, not a fallback. Operator: "not everything
    will always be pushed to a github. End users will use claude for anything."

    A folder that was never a repository still contains the work. The boundary-file rung
    reads it directly, needing no VCS at all -- which is why the ladder's last usable rung
    is file contents rather than a git operation.
    """
    from core.work_orders.delivery_boundary import boundary_file_contents

    plain = tmp_path / "never_a_repo"
    plain.mkdir()
    (plain / "deliverable.py").write_text(
        "def the_thing():" + NL + "    return 'real work, never pushed'" + NL,
        encoding="utf-8",
    )
    assert not (plain / ".git").exists(), "precondition: no VCS here at all"

    wo = _project_with_path(db, plain)
    _declare_boundary(db, wo, "deliverable.py")

    text, reason = boundary_file_contents(wo, repo_root=plain, db_path=db)

    assert text, f"a non-git folder must still yield evidence; reason was {reason!r}"
    assert "real work, never pushed" in text, "the delivered content itself is the evidence"


def test_the_verdict_names_which_evidence_layer_answered():
    """certification_basis has TWO values -- "authority_evidence" and "git_diff" -- for
    FOUR rungs. So it cannot distinguish a real diff from the current contents of some
    files, and those are very different strengths: a diff shows what this work order DID,
    file contents show only what the code IS.

    A verdict grading the second while reading like the first is the absent-looks-clean
    shape this milestone exists to remove, so the rung is named and explained.
    """
    from core.work_orders.verify_git import EVIDENCE_LAYERS, evidence_layer_note

    names = [name for name, _ in EVIDENCE_LAYERS]
    assert names == [
        "recorded_delivery_boundary",
        "commit_search_union",
        "authority_executable_checks",
        "none",
    ], f"the ladder's stated order changed: {names}"

    for name, note in EVIDENCE_LAYERS:
        assert note and len(note) > 20, f"{name} has no usable explanation"
        assert evidence_layer_note(name) == note

    # The reader must be told when the evidence is the weaker kind.
    boundary = evidence_layer_note("recorded_delivery_boundary")
    assert "needs no VCS" in boundary
    assert (
        "current state rather than the change" in boundary
    ), "the weaker rung must SAY it is weaker -- that is the whole point of naming it"

    # And 'none' must not read like a pass.
    none_note = evidence_layer_note("none")
    assert "unreviewable" in none_note
    assert "never a certified pass" in none_note


def test_an_unrecognised_layer_is_named_rather_than_swallowed():
    """A layer value the vocabulary does not know must surface as itself. Returning a
    bland default would hide a wiring mistake behind plausible prose."""
    from core.work_orders.verify_git import evidence_layer_note

    note = evidence_layer_note("something_new")
    assert "unrecognised" in note
    assert "something_new" in note, "the unknown value must appear so it can be traced"


def test_the_verdict_and_result_both_carry_the_layer():
    """A layer computed and recorded nowhere is the attachment_pressure defect again:
    calculated, stored nowhere, reaching no reader."""
    source = Path("core/work_orders/verify_main.py").read_text(encoding="utf-8")

    # Once in the verdict dict (12-space indent) and once in the result dict (8-space).
    verdict = [ln for ln in source.splitlines() if ln.startswith('            "evidence_layer"')]
    result = [
        ln
        for ln in source.splitlines()
        if ln.startswith('        "evidence_layer"') and not ln.startswith("            ")
    ]
    assert len(verdict) == 1, f"verdict occurrences: {len(verdict)}"
    assert len(result) == 1, f"result occurrences: {len(result)}"


# -- Task 8: the type selects the standards ------------------------------------


def test_a_documentation_work_order_is_not_graded_on_code_standards():
    """Operator: "End users will use claude for anything and everything not just SDLC."

    Telling a documentation work order its tests are missing is the same category error as
    grading Fulcrum against Dream Studio's tables, and it is how a reviewer earns the
    reputation of surfacing nonsense.
    """
    from core.work_orders.review_rules import resolve_review_rules

    rules = resolve_review_rules(work_order_type="documentation").rules
    joined = " ".join(rules)

    for inapplicable in (
        "TEST COVERAGE FOR CHANGED BEHAVIOUR",
        "NO DEAD CODE",
        "LAYERING AND DEPENDENCY DISCIPLINE",
        "CONCURRENCY AND RESOURCE SAFETY",
    ):
        assert inapplicable not in joined, f"a document was graded on {inapplicable}"


def test_a_documentation_work_order_is_reviewed_MORE_not_less():
    """THE DISTINCTION THAT MATTERS. The previous handling was
    ``_VERIFY_EXEMPT_TYPES = {"documentation"}`` in close_main -- documentation skipped
    independent review altogether. THAT is weaker review.

    Narrowing the code rules is only legitimate because document-specific standards
    replace them. A documentation work order that ships a false statement about the system
    has failed, and before this nothing was checking.
    """
    from core.work_orders.review_rules import DOCUMENT_STANDARDS, resolve_review_rules

    doc = resolve_review_rules(work_order_type="documentation").rules
    code = resolve_review_rules(work_order_type="api_endpoint").rules

    gained = [r for r in doc if r not in code]
    assert len(gained) == len(DOCUMENT_STANDARDS), f"document standards missing: {gained}"

    joined = " ".join(doc)
    assert "COMPLETENESS" in joined
    assert "ACCURACY AGAINST THE SYSTEM" in joined
    # The one this session kept finding in Dream Studio's own docs: a workflow node still
    # described a selector that had been replaced.
    assert "NO STALE DESCRIPTION" in joined


def test_a_document_is_still_held_to_the_standards_that_do_apply():
    """A document can leak a credential, and a document change can be unreviewable. Those
    rules are not code-specific and must survive the narrowing."""
    from core.work_orders.review_rules import resolve_review_rules

    joined = " ".join(resolve_review_rules(work_order_type="documentation").rules)
    assert "INPUT AND SECRET HANDLING" in joined
    assert "CHANGE CONTROL AND REVIEWABILITY" in joined


def test_a_code_work_order_still_gets_the_full_baseline():
    """The common case must be untouched -- narrowing for documents must not narrow for
    code."""
    from core.work_orders.review_rules import SDLC_BASELINE, resolve_review_rules

    for wo_type in ("api_endpoint", "ui_component", "authentication", "saas_feature"):
        rules = resolve_review_rules(work_order_type=wo_type).rules
        for baseline_rule in SDLC_BASELINE:
            assert baseline_rule in rules, f"{wo_type} lost {baseline_rule.split(':')[0]}"


def test_an_unknown_type_is_graded_as_code():
    """Unknown-means-code errs toward MORE standards. Defaulting to DOCUMENT would
    silently drop test-coverage and data-safety for any type added later without touching
    the map -- a quiet weakening triggered by someone else's unrelated change."""
    from core.work_orders.review_rules import (
        CODE,
        SDLC_BASELINE,
        artifact_kind,
        resolve_review_rules,
    )

    assert artifact_kind("some_type_nobody_has_added_yet") == CODE
    assert artifact_kind(None) == CODE
    assert artifact_kind("") == CODE
    assert len(resolve_review_rules(work_order_type="brand_new_type").rules) == len(SDLC_BASELINE)


def test_a_data_pipeline_gains_schema_and_replay_standards():
    """A pipeline is not code and not a document. Its failure modes -- a contract change
    with unnotified readers, a re-run that double-counts -- are named by neither."""
    from core.work_orders.review_rules import resolve_review_rules

    joined = " ".join(resolve_review_rules(work_order_type="data_pipeline").rules)
    assert "SCHEMA AND CONTRACT" in joined
    assert "IDEMPOTENCE AND REPLAY" in joined
    # And it keeps the code standards that do apply to a transform.
    assert "TEST COVERAGE FOR CHANGED BEHAVIOUR" in joined
    assert "DATA SAFETY" in joined


def test_a_project_profile_still_layers_on_top_of_the_selected_baseline():
    """Type selection picks the BASELINE; a project or folder profile still adds to or
    replaces whatever was selected. The two mechanisms have to compose, or declaring a
    profile would silently re-widen a document's rules."""
    from core.work_orders.review_rules import PROFILE_NAME, resolve_review_rules

    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / PROFILE_NAME).write_text(
            "mode: add" + NL * 2 + "- HOUSE DOC RULE: every page names its owner." + NL,
            encoding="utf-8",
        )
        rules = resolve_review_rules(project_root=root, work_order_type="documentation").rules
        joined = " ".join(rules)

        assert "HOUSE DOC RULE" in joined, "the profile must still apply"
        assert "NO STALE DESCRIPTION" in joined, "and the document standards must survive"
        assert "NO DEAD CODE" not in joined, "a profile must not re-widen the code rules"
