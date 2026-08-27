"""Where does a project's code actually live? (WO-MULTIROOT-REVIEW)

Dream Studio modelled a project as exactly one folder — ``business_projects.project_path``,
a single TEXT column read by a resolver returning a single ``Path``. Real development is
not shaped that way, and the cost was measured rather than argued:

    project_path for "Fulcrum Skill Library" = C:\\Users\\Dannis Seay\\Fulcrum
    that folder has NO .git of its own — it is a working folder holding, at one level:
      6 repositories   (demo, dogfood-appliances, fulcrum-gateway, planning, platform,
                        release-92)
      29 worktrees     (branches checked out as folders — db-755, db-756, …)

    _collect_git_commits(Fulcrum,          <wo>) -> None          nothing to grade
    _collect_git_commits(Fulcrum/platform, <wo>) -> found commits

So all 28 open Fulcrum work orders were graded with no diff at all. Verify fell through
to "independent review unverifiable — no diff provided", and the correctness grader —
holding only Dream Studio's own layer-map rules and no code — produced a work order whose
single task read "Fix N/A: independent review unverifiable — no diff provided in N/A".
The single-root model, the "reviews against Dream Studio" complaint, and that nonsense
work order are ONE defect with three symptoms.

A WORKTREE IS NOT A REPOSITORY, and conflating them turns 6 grading targets into 35.
Git marks the difference precisely: a repository has a ``.git`` DIRECTORY, a worktree has
a ``.git`` FILE reading ``gitdir: <repo>/.git/worktrees/<name>``. A worktree is one
branch of a repository checked out beside it — it shares that repository's history, so
grading it as a separate root would grade the same code many times over. They are
recorded as CHECKOUTS of their repository, which is also how you find which branch a
piece of work is on.

AND A ROOT NEED NOT BE A REPOSITORY AT ALL. Not everything is pushed to GitHub, and
plenty of work is never version-controlled. A declared folder that exists IS where the
code lives, git or no git; ``versioned`` says which, so a caller can choose an evidence
strategy instead of being handed nothing. Requiring ``.git`` here broke a real test
(``test_one_work_order_two_checkouts_one_verdict``) within minutes of being written.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# How deep to look beneath a declared root. Two levels covers the shapes seen in practice
# — repos directly under a working folder, and the `repos/<name>` layout tooling creates
# — without walking a whole disk.
_MAX_DISCOVERY_DEPTH = 2

_SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".idea", ".vscode"}
)


@dataclass
class ProjectRoots:
    """Every place a project's code lives.

    ``roots`` are the things worth grading independently: repositories, or — when the
    declared folder is not under version control — the folder itself. ``checkouts`` are
    additional working copies of a repository already in ``roots``; they are recorded
    because they say which branch work sits on, never graded as separate code.
    """

    declared: Path | None = None
    roots: list[Path] = field(default_factory=list)
    #: (worktree, the repository it belongs to) — branches checked out as folders.
    checkouts: list[tuple[Path, Path]] = field(default_factory=list)
    #: The declared path is not itself a root — it *holds* the roots below.
    is_container: bool = False
    #: False when a root is a plain folder with no version control.
    versioned: bool = True
    unreachable: list[tuple[str, str]] = field(default_factory=list)
    #: Why nothing resolved at all. None when at least one root was found.
    reason: str | None = None

    @property
    def primary(self) -> Path | None:
        """The one path a single-path caller should use.

        THREE ANSWERS, and the first two cuts each got one of them wrong.

        1. ONE root -> that root. Unchanged, and the common case.
        2. MANY roots -> the DECLARED container path, not a pick from among them. Cut one
           returned ``roots[0]``, handing every legacy caller Fulcrum's alphabetically
           first folder — an arbitrary wrong repo a TEST-CHECK would then RUN in.
        3. NONE -> None.

        CUT TWO RETURNED None FOR CASE 2, AND THAT WAS WORSE. Every caller does
        ``resolve_project_root(...) or source_root``, so None sent a Fulcrum work order to
        grade against the DREAM STUDIO repo — the operator's original "reviewing against
        dream studio" complaint, reintroduced by the fix meant to be careful. Verified:
        ``resolve_project_root`` returned None, ``_search_root`` became the DS repo, and
        ``run_executable_checks(project_root=None)`` documents its cwd as "the current
        process dir (the DS repo)".

        The declared path keeps every caller inside the RIGHT project. Git finds no
        commits there, so verify reports "no diff located" and a TEST-CHECK reports
        "could not run" — honestly unreviewable, rather than a confident verdict about
        somebody else's code. That is also exactly what the pre-multi-root resolver
        returned, so this is no regression on the old behaviour; the roots list is the new
        information, and grading their union is WO-MULTIROOT-REVIEW task 3.
        """
        if len(self.roots) == 1:
            return self.roots[0]
        if self.roots and self.declared is not None:
            return self.declared
        return None

    def describe(self) -> str:
        """One line a human or a grader can act on."""
        if not self.roots:
            return f"no code root resolved — {self.reason or 'reason unrecorded'}"
        if not self.versioned:
            return f"{self.roots[0]} (not under version control)"
        if self.is_container:
            names = ", ".join(p.name for p in self.roots)
            extra = (
                f", plus {len(self.checkouts)} branch checkout(s) of them" if self.checkouts else ""
            )
            noun = "repository" if len(self.roots) == 1 else "repositories"
            return (
                f"{self.declared} is not itself a repository; it holds "
                f"{len(self.roots)} {noun}: {names}{extra}"
            )
        return str(self.roots[0])


def git_kind(path: Path) -> str | None:
    """``"repository"``, ``"worktree"``, or None.

    A repository has a ``.git`` DIRECTORY. A worktree has a ``.git`` FILE pointing into
    its repository's ``worktrees/`` — the distinction that keeps 6 repositories from
    being counted as 35.
    """
    marker = path / ".git"
    try:
        if marker.is_dir():
            return "repository"
        if marker.is_file():
            return "worktree"
    except OSError:
        return None
    return None


def worktree_repository(path: Path) -> Path | None:
    """The repository a worktree belongs to, read from its ``.git`` file.

    The file reads ``gitdir: <repo>/.git/worktrees/<name>``, so the repository root is
    the path above that ``.git``.
    """
    try:
        text = (path / ".git").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.split(":", 1)[1].strip())
    for parent in gitdir.parents:
        if parent.name == ".git":
            return parent.parent
    return None


def _discover(
    root: Path, *, depth: int = _MAX_DISCOVERY_DEPTH
) -> tuple[list[Path], list[tuple[Path, Path]]]:
    """``(repositories, checkouts)`` beneath ``root``, breadth-first to ``depth``."""
    repos: list[Path] = []
    checkouts: list[tuple[Path, Path]] = []
    frontier = [(root, 0)]
    while frontier:
        current, level = frontier.pop(0)
        if level >= depth:
            continue
        try:
            children = sorted(p for p in current.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            if child.name in _SKIP_DIRS:
                continue
            kind = git_kind(child)
            if kind == "repository":
                repos.append(child)
                continue  # a repository's subdirectories are part of it
            if kind == "worktree":
                # A branch checked out as a folder. Its repository may or may not be
                # inside this project; record what we can and never treat it as a root.
                checkouts.append((child, worktree_repository(child) or child))
                continue
            frontier.append((child, level + 1))
    return repos, checkouts


def resolve_project_roots(
    work_order_id: str, db_path: Path, *, discover: bool = True
) -> ProjectRoots:
    """Every code root for the work order's project.

    A single-repo project resolves exactly as it always did. A container resolves to the
    repositories it holds, with worktrees recorded as checkouts. A folder under no
    version control resolves to itself with ``versioned=False`` — because a root need not
    be a repository for work to live in it.
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as exc:  # noqa: BLE001 - a resolver must not raise into verify
        return ProjectRoots(reason=f"authority unavailable: {exc}")
    try:
        row = conn.execute(
            "SELECT p.project_path FROM business_work_orders w"
            " JOIN business_projects p ON w.project_id = p.project_id"
            " WHERE w.work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    except Exception as exc:  # noqa: BLE001
        return ProjectRoots(reason=f"authority query failed: {exc}")
    finally:
        conn.close()

    if not row or not row[0]:
        return ProjectRoots(reason="the project declares no project_path")

    declared = Path(row[0])
    if not declared.is_dir():
        return ProjectRoots(
            declared=declared,
            unreachable=[(str(declared), "declared project_path does not exist on disk")],
            reason=f"declared project_path is not a directory: {declared}",
        )

    kind = git_kind(declared)
    if kind == "repository":
        return ProjectRoots(declared=declared, roots=[declared])
    if kind == "worktree":
        # The declared path is itself a branch checkout. Grade it — that IS the code the
        # operator pointed at — while recording the repository it came from.
        repo = worktree_repository(declared)
        return ProjectRoots(
            declared=declared,
            roots=[declared],
            checkouts=[(declared, repo)] if repo else [],
        )

    repos: list[Path] = []
    checkouts: list[tuple[Path, Path]] = []
    if discover:
        repos, checkouts = _discover(declared)

    if repos:
        return ProjectRoots(declared=declared, roots=repos, checkouts=checkouts, is_container=True)

    # NOT A REPOSITORY AND HOLDS NONE — still where the code lives. Returning nothing
    # here broke test_one_work_order_two_checkouts_one_verdict and would have broken
    # every project that is not in git, which the operator called out explicitly: not
    # everything gets pushed to GitHub.
    return ProjectRoots(declared=declared, roots=[declared], versioned=False)
