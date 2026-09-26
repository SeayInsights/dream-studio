"""In-process gate registry (C12): call a gate's own ``main()`` by import instead of
spawning a subprocess for it.

THE DEFECT THIS EXISTS FOR. ``pre_push.py`` shelled out to ``py -m core.gates.X`` for
every one of the 25 gates in the manifest, unconditionally -- even gates that do a few AST
walks and print a verdict. Measured on Windows: 55-150ms of interpreter-startup overhead
per gate, for gates whose own work is single-digit milliseconds. Every gate module already
exposes a clean ``main() -> int`` (or ``main(argv) -> int``) that does not touch global
process state beyond what its own docstring already documents (module-level ``REPO_ROOT``
constants, imported once) -- there is nothing a subprocess boundary was buying most of
these gates that an import does not already give them.

SCOPE, DELIBERATELY NARROW. Only a gate whose ``command:`` is a ``py -m <dotted.module>``
or ``py <script/path.py>`` invocation of code THIS REPOSITORY OWNS is eligible. Two classes
stay on subprocess on purpose:

* Third-party tools (``black``, ``pytest``) -- ``_FORCE_SUBPROCESS`` names them explicitly.
  Embedding pytest sessions in the SAME interpreter that just ran a different pytest
  session (or will run another gate after) risks cross-run state leakage (plugin
  registration, ``sys.modules`` caching of test modules, collected-item caches) that a
  fresh subprocess sidesteps for free -- and these three gates are already slow because
  they run real tests, not because of process-spawn overhead, so importing them would not
  even address the problem this registry exists to fix.
* A ``--repo <path>`` run against anything other than this repository's own checkout.
  These gate modules resolve their own ``REPO_ROOT`` from ``__file__`` at import time; a
  handful now also accept an explicit ``--repo-root`` override (D18), but not all of them
  do, and this repository's own gates are never the ones a FOREIGN project's manifest
  names in the first place (G27: a project declares its own gates or is refused, never
  Dream Studio's). So the one real scenario this matters for -- pointing ``--repo`` at
  ANOTHER Dream Studio checkout -- is rare enough, and the per-gate flag-injection it would
  need is inconsistent enough across the gates that added ``--repo-root`` (a flag) versus
  ``locale_decode_gate`` (a positional arg), that the honest choice is: fall back to the
  already-proven subprocess path whenever ``repo_root`` is not this module's own default.
  Nothing silently degrades -- ``run_in_process`` simply is not called for that case.
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import io
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Gates that must stay subprocess-run. See the module docstring for why.
FORCE_SUBPROCESS: frozenset[str] = frozenset(
    {"format-check", "test-suite", "pin-tests", "unit-collect"}
)


def module_name_from_command(command: list[str]) -> str | None:
    """A dotted, importable module name for ``command``, or None if it isn't one.

    Handles both manifest forms: ``[py, -m, dotted.module, ...]`` and
    ``[py, path/to/script.py, ...]`` (the latter translated to a dotted name the same way
    Python's own import system would resolve that path as a package member).
    """
    if len(command) < 2 or command[0] != "py":
        return None
    if command[1] == "-m":
        if len(command) < 3 or not command[2]:
            return None
        return str(command[2])
    script = str(command[1])
    if not script.endswith(".py"):
        return None
    dotted = script[: -len(".py")].replace("\\", "/").replace("/", ".")
    return dotted or None


def argv_after_module(command: list[str]) -> list[str]:
    """The extra arguments a manifest ``command:`` passes after the module/script itself."""
    if len(command) < 2 or command[0] != "py":
        return []
    if command[1] == "-m":
        return [str(part) for part in command[3:]]
    return [str(part) for part in command[2:]]


def importable_main(gate_id: str, command: list[str]):
    """The gate's ``main`` callable, or None when this gate must run as a subprocess."""
    if gate_id in FORCE_SUBPROCESS:
        return None
    module_name = module_name_from_command(command)
    if module_name is None:
        return None
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    main_fn = getattr(module, "main", None)
    if main_fn is None or not callable(main_fn):
        return None
    return main_fn


def run_in_process(
    gate_id: str, command: list[str], *, repo_root: Path
) -> tuple[int, str, str] | None:
    """Run this gate in-process. Returns ``(exit_code, stdout, stderr)``.

    Returns None (meaning: fall back to subprocess) when the gate is not eligible, when
    ``repo_root`` is not this module's own repository, or when the manifest passed extra
    argv to a ``main()`` that does not accept any (a shape this registry refuses to guess
    at rather than silently dropping arguments a gate needed).
    """
    if repo_root.resolve() != REPO_ROOT:
        return None
    main_fn = importable_main(gate_id, command)
    if main_fn is None:
        return None

    argv = argv_after_module(command)
    accepts_argv = len(inspect.signature(main_fn).parameters) > 0
    if argv and not accepts_argv:
        return None

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            result = main_fn(argv) if accepts_argv else main_fn()
        exit_code = result if isinstance(result, int) else 0
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else (1 if exc.code else 0)
    except Exception as exc:  # noqa: BLE001 - a crashing gate must fail the push, not the runner
        stderr_buf.write(
            f"\n[gate-registry] {gate_id} raised {type(exc).__name__} while running"
            f" in-process: {exc}"
        )
        exit_code = 1
    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()
