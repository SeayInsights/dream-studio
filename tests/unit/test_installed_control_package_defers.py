"""WO becfca00: a PARTIAL installed package must defer to the repo's, never hide it.

THE DEFECT THIS EXISTS FOR, measured on the operator's live install. The installer copied
the repo's ``control/__init__.py`` into ``~/.claude/hooks/control/`` while shipping only
``control/execution/dispatch_tracking.py``. That made a complete-LOOKING regular package.
The dispatcher inserts the plugin root at ``sys.path[0]``, so Python bound ``control`` to
the partial copy, fixed its ``__path__``, and never searched the repo:

    load_module(on_skill_metrics)   ModuleNotFoundError: control.execution.models
    load_module(on_skill_complete)  ModuleNotFoundError: control.skills

**12 handlers** import ``control.*`` submodules the install does not carry --
``control.skills.*``, ``control.context``, ``control.review.engine``, ``control.analysis``,
``control.research.memory``, ``control.execution.workflow``,
``control.execution.dispatch_helpers`` and ``control.execution.models.*``. Handlers that
import ``core.*`` were unaffected for one reason only: no ``core`` package is installed to
shadow, which is why ``on-tool-activity`` kept working beside handlers that had never run.

The fix is a GENERATED ``__init__.py`` that appends the repo's matching directory to
``__path__``. These tests drive it the way production does -- the partial copy FIRST on
``sys.path`` -- because with the repo first the bug cannot reproduce and the test would
prove nothing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from integrations.installer.claude_code_fileops import _package_shim

REPO_ROOT = Path(__file__).resolve().parents[2]

#: (relative package, parents between its __init__ and the hooks dir)
_SHIMMED = (("control", 2), ("control/execution", 3))


def _partial_install(tmp_path: Path) -> Path:
    """A hooks dir carrying ONLY dispatch_tracking, plus the generated shims."""
    hooks = tmp_path / "hooks"
    (hooks / "control" / "execution").mkdir(parents=True)
    (hooks / ".ds-source-root").write_text(str(REPO_ROOT), encoding="utf-8")
    (hooks / "control" / "execution" / "dispatch_tracking.py").write_text(
        (REPO_ROOT / "control" / "execution" / "dispatch_tracking.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for rel, depth in _SHIMMED:
        (hooks.joinpath(*rel.split("/")) / "__init__.py").write_text(
            _package_shim(rel, depth), encoding="utf-8"
        )
    return hooks


def _import_under(hooks: Path, modules: list[str]) -> dict[str, str]:
    """Import each module in a subprocess with the PARTIAL install first on sys.path."""
    script = (
        "import sys, json\n"
        f"sys.path.insert(0, r'{hooks}')\n"
        f"sys.path.append(r'{REPO_ROOT}')\n"
        "out = {}\n"
        f"for m in {modules!r}:\n"
        "    try:\n"
        "        __import__(m); out[m] = 'ok'\n"
        "    except BaseException as e:\n"
        "        out[m] = type(e).__name__ + ': ' + str(e)\n"
        "print(json.dumps(out))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    import json as _json

    return _json.loads(proc.stdout.strip().splitlines()[-1])


def test_partial_install_still_resolves_repo_only_submodules(tmp_path: Path) -> None:
    """The submodules that were dying on every dispatch now import."""
    hooks = _partial_install(tmp_path)
    got = _import_under(
        hooks,
        [
            "control.execution.dispatch_tracking",  # shipped
            "control.skills.calibration",  # repo-only, on-skill-complete
            "control.skills.metrics",  # repo-only, on-skill-metrics
            "control.execution.models.selector",  # repo-only, NESTED partial
            "control.context",  # repo-only, 3 more handlers
        ],
    )
    assert all(v == "ok" for v in got.values()), got


def test_without_the_shim_the_partial_install_hides_the_repo(tmp_path: Path) -> None:
    """The positive control: prove the shim is what fixes it.

    Without this, a test suite that never reproduced the defect would pass against any
    implementation -- including one that silently did nothing.
    """
    hooks = _partial_install(tmp_path)
    # replace the shims with what the installer used to do: copy the repo's __init__
    for rel, _ in _SHIMMED:
        (hooks.joinpath(*rel.split("/")) / "__init__.py").write_text(
            (REPO_ROOT.joinpath(*rel.split("/")) / "__init__.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    got = _import_under(hooks, ["control.skills.calibration", "control.execution.models.selector"])
    assert all("ModuleNotFoundError" in v for v in got.values()), (
        "the copied __init__ must reproduce the shadowing this shim exists to fix; " f"got {got}"
    )


def test_shim_survives_a_missing_sidecar(tmp_path: Path) -> None:
    """No .ds-source-root is a repo-less install, not a crash.

    It cannot import repo-only submodules -- nothing could, since `core` is never
    installed either -- but the shipped one must still load, so the dispatcher boots and
    can report rather than dying at import.
    """
    hooks = _partial_install(tmp_path)
    (hooks / ".ds-source-root").unlink()
    got = _import_under(hooks, ["control.execution.dispatch_tracking"])
    assert got["control.execution.dispatch_tracking"] == "ok", got


def test_installer_generates_the_shim_rather_than_copying(tmp_path: Path) -> None:
    """The plan must not copy the repo's control __init__ files back in.

    Pinned because the defect was reintroduced by a one-line convenience: copying the
    repo file is the obvious thing to write, and it is what shadowed the package.
    """
    shim = _package_shim("control", 2)
    assert "__path__.append" in shim, "the shim must extend __path__ toward the repo"
    assert ".ds-source-root" in shim, "it must resolve the repo from the sidecar"

    repo_init = (REPO_ROOT / "control" / "__init__.py").read_text(encoding="utf-8")
    assert shim != repo_init, "the installed __init__ must be generated, not the repo's copy"
