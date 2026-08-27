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
