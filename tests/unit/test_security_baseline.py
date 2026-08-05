"""R4 — automated security baseline: scheduled secret scan + single-source lint pin.

The scheduled workflow (.github/workflows/security-baseline.yml) runs the native
full-history secret scanner on a cron; the linter/format pin has exactly one source
(runtime/config/release-gates/flake8-baseline.txt) read by BOTH pre-push and CI. See
core/gates/secret_scan.py and docs/operations/lint-format-baseline-policy.md.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.gates.secret_scan import find_secrets

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "security-baseline.yml"
PRE_PUSH = REPO / "canonical" / "workflows" / "pre-push.yaml"
CI = REPO / ".github" / "workflows" / "ci.yml"
BASELINE = REPO / "runtime" / "config" / "release-gates" / "flake8-baseline.txt"


def test_scheduled_scan_and_single_source_config():
    # (a) The scheduled workflow PARSES as YAML and declares a cron schedule + a
    # secret-scan job that runs the native scanner.
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses the bare key `on` as the boolean True (YAML 1.1) — accept either.
    on_cfg = doc.get("on", doc.get(True))
    assert on_cfg and "schedule" in on_cfg, "workflow must declare on.schedule"
    assert any("cron" in entry for entry in on_cfg["schedule"]), "schedule must be a cron"

    jobs = doc["jobs"]
    assert "secret-scan" in jobs, "workflow must have a secret-scan job"
    assert "core.gates.secret_scan" in yaml.dump(
        jobs["secret-scan"]
    ), "the secret-scan job must run the native scanner"

    # (b) Single-source linter/format pin: exactly one baseline file, and BOTH the local
    # pre-push gate and CI consume it via lint_baseline.py — no duplicate pin to drift.
    assert BASELINE.is_file(), "the single lint baseline must exist"
    others = [
        p for p in REPO.glob("**/flake8-baseline*.txt") if ".git" not in p.parts and p != BASELINE
    ]
    assert not others, f"duplicate lint baseline pin(s) found: {others}"

    pre_push = PRE_PUSH.read_text(encoding="utf-8")
    ci = CI.read_text(encoding="utf-8")
    assert (
        "lint_baseline.py" in pre_push and "lint_baseline.py" in ci
    ), "pre-push and CI must both read the single lint_baseline.py pin"

    # The flake8 *config* pin is single-sourced too: `.flake8` is the only flake8 config.
    # pyproject.toml must not carry a second, divergent (and — without flake8-pyproject —
    # inert) `[tool.flake8]` block that silently drifts from `.flake8`.
    assert (REPO / ".flake8").is_file(), ".flake8 is the single flake8 config"
    assert "[tool.flake8]" not in (REPO / "pyproject.toml").read_text(
        encoding="utf-8"
    ), "duplicate flake8 config in pyproject.toml — `.flake8` is the single source"


def test_secret_scanner_detects_high_confidence_credentials():
    assert find_secrets("k = 'AKIA" + "A" * 16 + "'")[0]["rule"] == "aws_access_key_id"
    assert find_secrets("t=ghp_" + "a" * 36)[0]["rule"] == "github_token"
    assert find_secrets("-----BEGIN RSA PRIVATE KEY-----")[0]["rule"] == "private_key_block"
    # The redacted match never contains the full credential.
    finding = find_secrets("t=ghp_" + "a" * 36)[0]
    assert "a" * 36 not in finding["match"]


def test_secret_scanner_no_false_positives_or_pragma_waives():
    assert find_secrets("def f(): return 42") == []
    assert find_secrets("comment about AKIA prefixes") == []
    # An inline pragma waives a line.
    assert find_secrets("token = ghp_" + "a" * 36 + "  # allowlist secret") == []
    # Rule/template files are excluded by path.
    assert find_secrets("-----BEGIN RSA PRIVATE KEY-----", source="templates/security/x.j2") == []


def test_scan_history_parses_diff_and_honors_path_exclusion(monkeypatch):
    """scan_history tracks commit + file across the git-log diff, scans added lines, and
    skips excluded paths."""
    from core.gates import secret_scan

    fake = "\n".join(
        [
            "a" * 40,  # commit hash line
            "+++ b/src/app.py",
            "+token = ghp_" + "a" * 36,  # secret in a real file → found
            "+++ b/templates/security/rules.j2",
            "+-----BEGIN RSA PRIVATE KEY-----",  # excluded path → ignored
        ]
    )
    monkeypatch.setattr(secret_scan, "_git", lambda args: fake)
    findings = secret_scan.scan_history()
    assert len(findings) == 1
    assert findings[0]["rule"] == "github_token"
    assert findings[0]["source"] == "src/app.py@" + "a" * 12


def test_main_exit_codes_and_fail_closed(monkeypatch, capsys):
    """main: 0 = clean, 1 = credentials found, 2 = scan could not run (fail CLOSED)."""
    from core.gates import secret_scan

    monkeypatch.setattr(secret_scan, "scan_tree", lambda: [])
    assert secret_scan.main([]) == 0

    monkeypatch.setattr(
        secret_scan, "scan_tree", lambda: [{"rule": "x", "match": "…", "source": "f"}]
    )
    assert secret_scan.main([]) == 1

    # A git failure must NOT read as "no credentials found" — it fails closed with exit 2.
    def _boom():
        raise secret_scan.SecretScanError("git missing")

    monkeypatch.setattr(secret_scan, "scan_tree", _boom)
    assert secret_scan.main([]) == 2
    assert "could not run" in capsys.readouterr().out


def test_git_helper_fails_closed_on_error(monkeypatch):
    """_git raises SecretScanError on a non-zero git exit instead of returning ''."""
    import subprocess

    from core.gates import secret_scan

    class _R:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    import pytest

    with pytest.raises(secret_scan.SecretScanError):
        secret_scan._git(["log"])
