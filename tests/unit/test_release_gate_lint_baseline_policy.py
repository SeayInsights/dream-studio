from __future__ import annotations

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
    assert all(command != ["make", "fmt"] for command in checks.values())


def test_code_history_and_lint_policy_docs_exist() -> None:
    history_policy = REPO_ROOT / "docs" / "operations" / "code-history-impact-guardrail.md"
    lint_policy = REPO_ROOT / "docs" / "operations" / "lint-format-baseline-policy.md"

    assert history_policy.is_file()
    assert lint_policy.is_file()
    assert "recent git history" in history_policy.read_text(encoding="utf-8")
    assert "runtime/config/release-gates/flake8-baseline.txt" in lint_policy.read_text(
        encoding="utf-8"
    )
