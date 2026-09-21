from __future__ import annotations

import os
import subprocess
from pathlib import Path

from interfaces.cli import ci_gate, lint_baseline

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_flake8_finding_identity_ignores_line_number_drift() -> None:
    before = lint_baseline.normalized_findings(
        ".\\core\\example.py:10:4: F401 'json' imported but unused"
    )
    after = lint_baseline.normalized_findings(
        ".\\core\\example.py:99:4: F401 'json' imported but unused"
    )

    comparison = lint_baseline.compare_to_baseline(current=after, baseline=before)

    assert comparison["status"] == "pass"
    assert comparison["new_finding_count"] == 0


def test_flake8_baseline_detects_new_findings() -> None:
    baseline = lint_baseline.normalized_findings(
        ".\\core\\example.py:10:4: F401 'json' imported but unused"
    )
    current = baseline + lint_baseline.normalized_findings(
        ".\\core\\example.py:20:8: F841 local variable 'item' is assigned to but never used"
    )

    comparison = lint_baseline.compare_to_baseline(current=current, baseline=baseline)

    assert comparison["status"] == "fail"
    assert comparison["new_finding_count"] == 1
    assert "F841" in comparison["new_findings"][0]


def test_no_check_anywhere_uses_a_mutating_format_target() -> None:
    """The property this test was always about: check formatting, never rewrite it.

    A gate that runs `make fmt` does not report a verdict, it edits the tree and
    then agrees with itself.
    """
    checks = {name: command for name, command in ci_gate.CHECKS}
    assert all(command != ["make", "fmt"] for command in checks.values())


def test_each_check_has_exactly_one_home() -> None:
    """format and lint-baseline live in the pre-push gate, and nowhere else.

    They used to run in THREE places -- the pre-push gate, pr-smoke, and here in
    full-ci -- three runs for one answer. This copy is the worst of the three: it
    runs POST-MERGE, so a formatting failure is discovered after it is already on
    main, having burned a 3-platform matrix to say "run black".

    They now run once, in pre-push, where the fix is `black .` before you push.
    What is left here is the full test suite, which nothing else runs.
    """
    import pathlib

    checks = {name for name, _ in ci_gate.CHECKS}
    assert "test" in checks, "full-ci must still run the suite; nothing else does"
    assert "format" not in checks, "format runs in pre-push; this is the third copy"
    assert "lint-baseline" not in checks, "lint runs in pre-push; this is the third copy"

    repo = pathlib.Path(__file__).resolve().parents[2]
    prepush = (repo / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    assert "id: format-check" in prepush, "format lost its one home"
    assert "id: lint-check" in prepush, "lint lost its one home"

    ci = (repo / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "black --check" not in ci, "pr-smoke is running format again"


def test_ci_gate_env_uses_isolated_runtime_state() -> None:
    env = ci_gate._isolated_check_env()
    isolated_db = Path(env["DREAM_STUDIO_DB_PATH"])
    isolated_home = isolated_db.parents[2]
    dream_studio_home = isolated_home / ".dream-studio"

    assert isolated_home.name.startswith("dream-studio-ci-home-")
    assert env["DREAM_STUDIO_HOME"] == str(dream_studio_home)
    assert env["GITHUB_ACTIONS"] == "true"
    assert env["HOME"] == str(isolated_home)
    assert env["USERPROFILE"] == str(isolated_home)
    assert env["DREAM_STUDIO_DB_PATH"] == str(dream_studio_home / "state" / "studio.db")


def test_ci_gate_test_env_lets_test_fixtures_control_dream_studio_home() -> None:
    env = ci_gate._isolated_test_env()
    isolated_home = Path(env["HOME"])
    isolated_db = Path(env["DREAM_STUDIO_DB_PATH"])

    assert isolated_home.name.startswith("dream-studio-ci-home-")
    assert "DREAM_STUDIO_HOME" not in env
    assert env["GITHUB_ACTIONS"] == "true"
    assert env["HOME"] == str(isolated_home)
    assert env["USERPROFILE"] == str(isolated_home)
    # DB must NOT live under HOME — if it did, conftest.guard_real_homedir's
    # _db_redirected check would be False and any test DB write would trigger
    # the FATAL abort (the bug this change fixes).
    assert not str(isolated_db).startswith(str(isolated_home))


def test_ci_gate_run_check_uses_isolated_env_for_non_test_checks(monkeypatch) -> None:
    isolated_env = {
        **os.environ,
        "DREAM_STUDIO_HOME": "sentinel-dream-studio-home",
        "DREAM_STUDIO_DB_PATH": "sentinel-studio.db",
    }
    captured: dict[str, object] = {}

    def fake_isolated_env() -> dict[str, str]:
        return isolated_env

    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        cwd: Path,
        env: dict[str, str] | None,
        # WO-LOCALE-DECODE-SILENT-LOSS: the call under test now names its codec
        # explicitly. **kwargs rather than two more named parameters, because this
        # stub exists to capture cmd/cwd/env — pinning the full kwarg list makes it
        # fail on any unrelated addition to the call, which is what happened here.
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        captured.update(
            {
                "cmd": cmd,
                "capture_output": capture_output,
                "text": text,
                "cwd": cwd,
                "env": env,
                **kwargs,
            }
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(ci_gate, "_isolated_check_env", fake_isolated_env)
    monkeypatch.setattr(ci_gate.subprocess, "run", fake_run)

    result = ci_gate.run_check("format", [ci_gate._PYTHON, "--version"])

    assert result["passed"] is True
    assert captured["env"] is isolated_env
    assert captured["cwd"] == ci_gate.REPO_ROOT


def test_code_history_and_lint_policy_docs_exist() -> None:
    history_policy = REPO_ROOT / "docs" / "operations" / "code-history-impact-guardrail.md"
    lint_policy = REPO_ROOT / "docs" / "operations" / "lint-format-baseline-policy.md"

    assert history_policy.is_file()
    assert lint_policy.is_file()
    assert "recent git history" in history_policy.read_text(encoding="utf-8")
    assert "runtime/config/release-gates/flake8-baseline.txt" in lint_policy.read_text(
        encoding="utf-8"
    )
