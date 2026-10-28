"""etl_home.home_dir() is core.config.paths.home_dir(), run without `core`.

WHY. The Dream Studio home is spelled in one place, core.config.paths, and
tests/unit/test_home_means_home.py fails on any other spelling. The security ETL scripts ship
standalone into a skill directory with no `core` package, so they carry a stdlib mirror
(templates/security/etl/etl_home.py), listed in that test as a reasoned exception. A mirror
that drifts from the original is the defect the rule exists to stop, so this runs both under
the SAME environment and requires the same path:

  * the etl side is a fresh `py -I` interpreter with `core` blocked (sys.modules['core'] =
    None), importing etl_home from its own directory only: it proves the module stays
    standalone, and that nothing in it reaches for the platform;
  * the core side is a fresh `py -I` interpreter importing core.config.paths.

The matrix is the environment the resolver reads: DREAM_STUDIO_HOME unset, empty, blank,
absolute, with a trailing separator, with `..`, relative, `~` and `~/x`; the home a
self-installed app records under sys.prefix (present, empty, blank, padded, relative); both
together (the variable wins); and variables that must be ignored (DS_DREAM_STUDIO_HOME,
DS_HOME). Each is one subprocess pair, so no state leaks between cases.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ETL = REPO_ROOT / "templates" / "security" / "etl"

ETL_SIDE = """
import sys
sys.modules["core"] = None          # `import core` now raises: the module must not need it
sys.path.insert(0, {etl!r})
import etl_home
if {prefix!r}:
    sys.prefix = {prefix!r}
print(str(etl_home.home_dir()))
"""

CORE_SIDE = """
import sys
sys.path.insert(0, {repo!r})
from core.config import paths
if {prefix!r}:
    sys.prefix = {prefix!r}
print(str(paths.home_dir()))
"""

#: DREAM_STUDIO_HOME values (None = unset) and what the venv marker holds (None = no marker).
#: Paths are relative to a per-test scratch directory unless they start with a marker token.
CASES = [
    ("unset", None, None),
    ("empty", "", None),
    ("blank", "   ", None),
    ("absolute", "<tmp>/home", None),
    ("trailing-separator", "<tmp>/home/", None),
    ("trailing-backslash-style", "<tmp>/home\\\\", None),
    ("dotdot", "<tmp>/a/../home", None),
    ("dot", "<tmp>/./home/.", None),
    ("relative", "rel/home", None),
    ("relative-dotdot", "../elsewhere", None),
    ("tilde", "~", None),
    ("tilde-path", "~/x/y", None),
    ("upper-case-segment", "<tmp>/HOME/Mixed", None),
    ("unicode", "<tmp>/hôme", None),
    ("with-space", "<tmp>/my home", None),
    ("marker-only", None, "<tmp>/installed-home"),
    ("marker-padded", None, "  <tmp>/installed-home  \n"),
    ("marker-empty", None, ""),
    ("marker-blank", None, " \n\t "),
    ("marker-relative", None, "installed/rel"),
    ("marker-tilde-is-not-expanded", None, "~/installed"),
    ("variable-beats-marker", "<tmp>/home", "<tmp>/installed-home"),
    ("empty-variable-falls-to-marker", "", "<tmp>/installed-home"),
    ("blank-variable-is-a-value-not-empty", "   ", "<tmp>/installed-home"),
]


def _expand(value: str | None, tmp: Path) -> str | None:
    return None if value is None else value.replace("<tmp>", str(tmp).replace("\\", "/"))


def _env(tmp: Path, home_value: str | None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("DREAM_STUDIO", "DS_", "PYTHON"))
        and k not in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")
    }
    user = tmp / "os-user"
    user.mkdir(parents=True, exist_ok=True)
    env["HOME"] = env["USERPROFILE"] = str(user)
    env["DS_DREAM_STUDIO_HOME"] = str(tmp / "ignored-1")  # not read by either resolver
    env["DS_HOME"] = str(tmp / "ignored-2")
    if home_value is not None:
        env["DREAM_STUDIO_HOME"] = home_value
    return env


def _run(code: str, env: dict[str, str], cwd: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=cwd,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.rstrip("\r\n")


def _answers(tmp: Path, home_value: str | None, marker: str | None) -> tuple[str, str]:
    prefix = ""
    if marker is not None:
        prefix_dir = tmp / "app-venv"
        prefix_dir.mkdir(parents=True, exist_ok=True)
        (prefix_dir / "dream-studio-home").write_text(_expand(marker, tmp) or "", encoding="utf-8")
        prefix = str(prefix_dir)
    env = _env(tmp, _expand(home_value, tmp))
    work = tmp / "cwd"
    work.mkdir(parents=True, exist_ok=True)
    etl = _run(ETL_SIDE.format(etl=str(ETL), prefix=prefix), env, work)
    core = _run(CORE_SIDE.format(repo=str(REPO_ROOT), prefix=prefix), env, work)
    return etl, core


@pytest.mark.parametrize("case, home_value, marker", CASES, ids=[c[0] for c in CASES])
def test_etl_home_answers_what_core_answers(tmp_path: Path, case, home_value, marker):
    etl, core = _answers(tmp_path, home_value, marker)
    assert etl == core, f"{case}: etl_home says {etl!r}, core.config.paths says {core!r}"
    assert etl, "an empty answer is not a home"


def test_the_matrix_exercises_every_branch_of_the_resolver(tmp_path: Path):
    """The cases above are only worth anything if they reach each of the three answers (and
    the marker's padding), so say what the distinct answers are."""
    env_answer = _answers(tmp_path / "a", "<tmp>/home", None)[0]
    marker_answer = _answers(tmp_path / "b", None, "<tmp>/installed-home")[0]
    default_answer = _answers(tmp_path / "c", None, None)[0]
    assert env_answer.endswith("home") and "installed-home" not in env_answer
    assert marker_answer.endswith("installed-home")
    assert default_answer.endswith(".dream-studio") and "os-user" in default_answer
    assert len({env_answer, marker_answer, default_answer}) == 3


def test_etl_home_imports_nothing_but_the_standard_library():
    import ast

    tree = ast.parse((ETL / "etl_home.py").read_text(encoding="utf-8"))
    modules = {
        alias.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import)
        for alias in n.names
    } | {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert modules <= {"__future__", "os", "sys", "pathlib"}, modules


def test_it_is_the_only_templates_file_that_spells_the_default() -> None:
    """The exception in test_home_means_home.py is for this one file; a second spelling under
    templates/ would be a second mirror with no parity test."""
    offenders = []
    for path in (REPO_ROOT / "templates").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if ('".dream-studio"' in text or "'.dream-studio'" in text) and path.name != "etl_home.py":
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []
