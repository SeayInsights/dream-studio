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


def test_ci_gate_uses_format_check_and_lint_baseline_not_mutating_format_target() -> None:
    checks = {name: command for name, command in ci_gate.CHECKS}

    assert checks["format"] == [ci_gate._PYTHON, "-m", "black", "--check", "."]
    assert checks["lint-baseline"] == [
        ci_gate._PYTHON,
        "interfaces/cli/lint_baseline.py",
        "check",
    ]
    assert checks["contract-docs-drift"] == [
        ci_gate._PYTHON,
        "interfaces/cli/contract_docs_drift_gate.py",
    ]
    assert checks["contract-atlas-lifecycle"] == [
        ci_gate._PYTHON,
        "interfaces/cli/contract_atlas_lifecycle_gate.py",
    ]
    assert all(command != ["make", "fmt"] for command in checks.values())


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
    isolated_db = Path(env["DREAM_STUDIO_DB_PATH"])
    isolated_home = isolated_db.parents[2]

    assert isolated_home.name.startswith("dream-studio-ci-home-")
    assert "DREAM_STUDIO_HOME" not in env
    assert env["GITHUB_ACTIONS"] == "true"
    assert env["HOME"] == str(isolated_home)
    assert env["USERPROFILE"] == str(isolated_home)
    assert env["DREAM_STUDIO_DB_PATH"] == str(
        isolated_home / ".dream-studio" / "state" / "studio.db"
    )


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
    ) -> subprocess.CompletedProcess[str]:
        captured.update(
            {
                "cmd": cmd,
                "capture_output": capture_output,
                "text": text,
                "cwd": cwd,
                "env": env,
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
