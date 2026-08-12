"""WO-GRADER-PROVIDER-NEUTRAL: the grader runner resolves the spawn argv from a
provider profile / env override / default, instead of a hardcoded vendor CLI.
"""

from __future__ import annotations

import sys

from core.adapters import grader_runner


def test_spawn_argv_resolved_from_profile():
    assert grader_runner.resolve_grader_argv({"command": "foo", "print_flag": "-p"}) == [
        "foo",
        "-p",
    ]
    argv = grader_runner.resolve_grader_argv(
        {"command": "x", "base_args": ["a"], "model_flag": "-m"}, model="mm"
    )
    assert argv == ["x", "a", "-m", "mm"]


def test_default_profile_is_the_vendor_cli(monkeypatch):
    monkeypatch.delenv("DS_GRADER_STUB", raising=False)
    monkeypatch.delenv("DS_GRADER_ARGV", raising=False)
    assert grader_runner.resolve_grader_argv() == ["claude", "--print"]


def test_stub_env_overrides_to_current_interpreter(monkeypatch, tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text("", encoding="utf-8")
    monkeypatch.setenv("DS_GRADER_STUB", str(stub))
    argv = grader_runner.resolve_grader_argv()
    assert argv[0] == sys.executable
    assert str(stub) in argv


def test_argv_env_override(monkeypatch):
    monkeypatch.delenv("DS_GRADER_STUB", raising=False)
    monkeypatch.setenv("DS_GRADER_ARGV", "mytool --grade")
    assert grader_runner.resolve_grader_argv() == ["mytool", "--grade"]


def test_prompt_via_argv_appends_prompt():
    argv = grader_runner.resolve_grader_argv({"command": "c", "prompt_via": "argv"}, prompt="hello")
    assert argv[-1] == "hello"


def test_prompt_via_stdin_never_puts_prompt_in_argv():
    argv = grader_runner.resolve_grader_argv(
        {"command": "c", "prompt_via": "stdin"}, prompt="hello"
    )
    assert "hello" not in argv
