"""C12 — the in-process gate registry.

WHY THIS EXISTS. ``pre_push.py`` used to shell out to ``py -m core.gates.X`` for every
one of 25 gates, unconditionally — 55-150ms of interpreter startup on Windows for gates
whose own work is single-digit milliseconds. Every gate module already exposes a clean
``main() -> int`` that does not depend on subprocess isolation, so this registry imports
and calls it directly instead.

Each test here proves something the mechanism could get wrong silently: a real gate's
verdict must survive the switch from subprocess to import BYTE FOR BYTE (same exit code),
a crashing gate must fail the push rather than crash the runner, black/pytest must never
be routed through import (there is no safe embed story for either), and a foreign
``repo_root`` must fall back to the already-proven subprocess path rather than guess at
per-gate flag conventions this registry does not control.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core.gates import registry
from core.gates.pre_push import run_gate

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── command parsing ──────────────────────────────────────────────────────────


def test_module_form_resolves_to_its_dotted_name():
    assert (
        registry.module_name_from_command(["py", "-m", "core.gates.agent_coverage"])
        == "core.gates.agent_coverage"
    )


def test_script_form_resolves_to_its_dotted_name():
    assert (
        registry.module_name_from_command(["py", "interfaces/cli/lint_baseline.py", "check"])
        == "interfaces.cli.lint_baseline"
    )


def test_a_command_not_shaped_like_py_dash_m_or_a_script_is_not_importable():
    assert registry.module_name_from_command(["black", "--check", "."]) is None
    assert registry.module_name_from_command(["py", "-m"]) is None
    assert registry.module_name_from_command(["py"]) is None


def test_argv_after_module_strips_the_module_reference():
    assert registry.argv_after_module(["py", "-m", "core.gates.dependency_rules", "rule1"]) == [
        "rule1"
    ]
    assert registry.argv_after_module(["py", "interfaces/cli/lint_baseline.py", "check"]) == [
        "check"
    ]


# ── scope boundaries ─────────────────────────────────────────────────────────


def test_black_and_pytest_gates_are_never_imported():
    """No safe embed story for either — see the module docstring."""
    for gate_id, command in (
        ("format-check", ["py", "-m", "black", "--check", "."]),
        ("test-suite", ["py", "-m", "pytest", "tests/evals", "-q"]),
        ("pin-tests", ["py", "-m", "pytest", "tests/unit/test_x.py", "-q"]),
        ("unit-collect", ["py", "-m", "pytest", "tests/unit", "--collect-only", "-q"]),
    ):
        assert registry.importable_main(gate_id, command) is None
        assert registry.run_in_process(gate_id, command, repo_root=REPO_ROOT) is None, gate_id


def test_a_foreign_repo_root_falls_back_to_subprocess(tmp_path):
    """The one case this registry refuses to guess at (see module docstring)."""
    result = registry.run_in_process(
        "agent-coverage",
        ["py", "-m", "core.gates.agent_coverage"],
        repo_root=tmp_path,
    )
    assert result is None


def test_extra_argv_to_a_no_argv_main_falls_back_rather_than_dropping_it():
    """agent_coverage's main() takes no argv at all; a manifest that somehow passed one
    must not have it silently discarded."""
    result = registry.run_in_process(
        "agent-coverage",
        ["py", "-m", "core.gates.agent_coverage", "--unexpected"],
        repo_root=REPO_ROOT,
    )
    assert result is None


# ── behavior preservation: same verdict, in-process vs subprocess ───────────


def test_in_process_matches_subprocess_for_a_real_cheap_gate():
    """The actual C12 claim: importing a real gate must not change its verdict.

    agent-coverage is deterministic and fast either way, which is what makes this a fair
    comparison rather than a race against gate state changing between the two calls.
    """
    command = ["py", "-m", "core.gates.agent_coverage"]

    in_process = registry.run_in_process("agent-coverage", command, repo_root=REPO_ROOT)
    assert in_process is not None, "agent-coverage should be registry-eligible"
    in_process_exit, in_process_stdout, _ = in_process

    subprocess_result = subprocess.run(
        [sys.executable, "-m", "core.gates.agent_coverage"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert in_process_exit == subprocess_result.returncode
    assert in_process_stdout.strip() == (subprocess_result.stdout or "").strip()


def test_run_gate_uses_the_registry_for_a_real_manifest_style_entry(monkeypatch):
    """End to end through pre_push.run_gate(), the way the manifest actually calls it.

    Round-1 review finding: the original version of this test only checked the gate's
    OWN output, which the subprocess fallback reproduces identically for a currently-
    passing gate -- it never proved the registry path was actually taken, so disabling
    the registry entirely left this test green. Spies on registry.run_in_process itself
    to confirm it was called and returned non-None, not just that the final verdict
    happens to match what subprocess would also have produced.
    """
    import core.gates.pre_push as pre_push_module

    calls: list[tuple[str, list[str]]] = []
    real_run_in_process = registry.run_in_process

    def _spy(gate_id, command, *, repo_root):
        result = real_run_in_process(gate_id, command, repo_root=repo_root)
        calls.append((gate_id, command, result is not None))
        return result

    monkeypatch.setattr(pre_push_module._registry, "run_in_process", _spy)

    result = run_gate(
        {"id": "agent-coverage", "command": ["py", "-m", "core.gates.agent_coverage"]},
        repo_root=REPO_ROOT,
    )

    assert len(calls) == 1, "run_gate did not consult the registry at all"
    gate_id, command, took_in_process_path = calls[0]
    assert gate_id == "agent-coverage"
    assert took_in_process_path, "the registry was consulted but declined, so this ran subprocess"
    assert result.passed is True
    assert "mode(s)" in result.stdout_tail


def test_a_gate_env_override_still_forces_subprocess():
    """A gate declaring env: overrides a real behavior difference the in-process path
    cannot honor without leaking that env into every gate run after it — so it must keep
    using the subprocess path regardless of registry eligibility."""
    result = run_gate(
        {
            "id": "agent-coverage",
            "command": ["py", "-m", "core.gates.agent_coverage"],
            "env": {"SOME_VAR": "1"},
        },
        repo_root=REPO_ROOT,
    )
    assert result.passed is True


# ── a crashing gate fails the push, not the runner ───────────────────────────


def test_a_gate_that_raises_is_reported_as_a_failure_not_a_crash(monkeypatch):
    import types

    fake = types.ModuleType("core.gates._fake_crashing_gate")

    def _boom():
        raise RuntimeError("synthetic gate crash")

    fake.main = _boom
    monkeypatch.setitem(sys.modules, "core.gates._fake_crashing_gate", fake)

    result = registry.run_in_process(
        "fake-gate",
        ["py", "-m", "core.gates._fake_crashing_gate"],
        repo_root=REPO_ROOT,
    )
    assert result is not None
    exit_code, _stdout, stderr = result
    assert exit_code == 1
    assert "synthetic gate crash" in stderr


def test_a_gate_calling_sys_exit_directly_is_read_correctly(monkeypatch):
    """contract_docs_drift_gate's main() raises SystemExit itself rather than returning an
    int — the registry must read .code, not treat this as an uncaught crash."""
    import types

    fake = types.ModuleType("core.gates._fake_sysexit_gate")

    def _exits():
        raise SystemExit(1)

    fake.main = _exits
    monkeypatch.setitem(sys.modules, "core.gates._fake_sysexit_gate", fake)

    result = registry.run_in_process(
        "fake-gate",
        ["py", "-m", "core.gates._fake_sysexit_gate"],
        repo_root=REPO_ROOT,
    )
    assert result is not None
    exit_code, _stdout, _stderr = result
    assert exit_code == 1


def test_an_unimportable_module_falls_back_to_subprocess():
    result = registry.run_in_process(
        "nonexistent",
        ["py", "-m", "core.gates.this_module_does_not_exist"],
        repo_root=REPO_ROOT,
    )
    assert result is None


def test_a_module_that_raises_at_import_time_falls_back_rather_than_crashing(monkeypatch):
    """Round-1 review finding: only ImportError was caught around the import step, so a
    module raising ANYTHING ELSE while being imported (a real bug in its top-level code,
    not a missing dependency) propagated uncaught through pre_push.run_gate() and crashed
    the whole pre-push run instead of falling back to subprocess for just that gate."""
    import importlib

    def _boom(name, *a, **kw):
        if name == "core.gates._fake_broken_at_import":
            raise ValueError("synthetic import-time crash, not an ImportError")
        return _real_import_module(name, *a, **kw)

    _real_import_module = importlib.import_module
    monkeypatch.setattr(registry.importlib, "import_module", _boom)

    result = registry.run_in_process(
        "fake-gate",
        ["py", "-m", "core.gates._fake_broken_at_import"],
        repo_root=REPO_ROOT,
    )
    assert result is None
