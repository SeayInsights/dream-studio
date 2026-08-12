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


# ── gap 9227c560: coverage for run_generation + grader_provider_available ─────


def test_run_generation_with_stub_profile(tmp_path):
    stub = tmp_path / "gen.py"
    stub.write_text("import sys; sys.stdin.read(); print('GEN-OK')", encoding="utf-8")
    profile = {"command": sys.executable, "base_args": [str(stub)], "prompt_via": "stdin"}
    cp = grader_runner.run_generation("hello", profile=profile, timeout=30)
    assert cp.returncode == 0
    assert "GEN-OK" in cp.stdout


def test_run_generation_argv_mode_passes_prompt(tmp_path):
    stub = tmp_path / "gen.py"
    stub.write_text("import sys; print('ARGS:' + '|'.join(sys.argv[1:]))", encoding="utf-8")
    profile = {"command": sys.executable, "base_args": [str(stub)], "prompt_via": "argv"}
    cp = grader_runner.run_generation("the-prompt", profile=profile, timeout=30)
    assert "the-prompt" in cp.stdout


def test_grader_provider_available_true_for_present_probe(tmp_path):
    stub = tmp_path / "g.py"
    stub.write_text("", encoding="utf-8")
    profile = {"command": sys.executable, "availability_probe": sys.executable}
    assert grader_runner.grader_provider_available(profile) is True


def test_grader_provider_available_false_for_missing():
    profile = {
        "command": "definitely-not-a-real-binary-xyz-123",
        "availability_probe": "definitely-not-a-real-binary-xyz-123",
    }
    assert grader_runner.grader_provider_available(profile) is False
