"""A git repository a test builds for itself, that no machine setting can change.

A test that runs ``git`` in a temporary directory still inherits the operator's global and
system configuration: the identity it commits as, ``init.defaultBranch``, ``core.autocrlf``,
signing, hooks templates, an ``includeIf`` that points at a sibling repository. The same
test then passes on the author's machine and fails on a runner with no ``user.name`` ("Please
tell me who you are"), or commits a different object id on every machine. The environment
below removes the operator from the equation: no global or system config, a fixed identity,
and fixed dates (callers may override a date to test a time-dependent rule).

Use this for any test that needs a repository. A test that needs THIS repository's history
should say so and build a fixture of it instead; ``origin/main``, tags and the branch the
checkout happens to be on are properties of one clone, not of the code.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

#: The instant every commit made through :func:`commit` carries unless a caller passes one.
FIXED_DATE = "2025-01-01T12:00:00+00:00"


def hermetic_env(**overrides: str) -> dict[str, str]:
    """``os.environ`` with git's machine-level configuration switched off.

    ``GIT_DIR`` and friends are removed too: under a git hook they point at the real
    repository (see the note at the top of ``tests/conftest.py``).
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") or k in {"GIT_EXEC_PATH", "GIT_ASKPASS"}
    }
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": "author@example.com",
            "GIT_COMMITTER_NAME": "Test Committer",
            "GIT_COMMITTER_EMAIL": "committer@example.com",
            "GIT_AUTHOR_DATE": FIXED_DATE,
            "GIT_COMMITTER_DATE": FIXED_DATE,
        }
    )
    env.update(overrides)
    return env


def git(repo: Path, *args: str, check: bool = True, **env: str) -> str:
    """Run ``git <args>`` in ``repo`` under :func:`hermetic_env`; return stripped stdout."""
    out = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=hermetic_env(**env),
        timeout=60,
    )
    if check:
        assert out.returncode == 0, f"git {' '.join(args)} failed in {repo}: {out.stderr}"
    return out.stdout.strip()


def init_repo(path: Path, *, branch: str = "main") -> Path:
    """Create ``path`` as an empty repository on ``branch``."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", branch)
    return path


def commit(repo: Path, message: str = "commit", *, files: dict[str, str] | None = None) -> str:
    """Write ``files`` (relative path -> text), commit everything, and return the new sha."""
    for rel, text in (files or {}).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def tag(repo: Path, *names: str) -> None:
    """Lightweight-tag HEAD with each name."""
    for name in names:
        git(repo, "tag", name)
