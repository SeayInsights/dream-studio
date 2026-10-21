"""An explicit `--domain` request that cannot be honoured fails; it is never answered with
the general analysis.

WHY. `repo-analyzer.py` used to print a one-line warning when the domain analyzers failed
to load and then, for `--domain finance`, run the general SKILL.md-pattern analysis and
print it. The report read as the domain analysis that was asked for (issue #891). A run
with no `--domain` is the general analysis by design and must not change.

Every test runs the entry points from an installed-style copy of the pack in a temp
directory -- no repository around it, the way `dist/plugin` installs it -- with the
`domains` package made unimportable in the copy. The real pack is never modified.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "canonical" / "skills" / "analyze"

BREAKS = ("missing", "raises")


def _install_copy(dest: Path, break_domains: str | None) -> Path:
    """Copy the pack to `dest`; optionally make `domains` unimportable there."""
    shutil.copytree(
        PACK,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test_*.py"),
    )
    if break_domains == "missing":
        shutil.rmtree(dest / "domains")
    elif break_domains == "raises":
        (dest / "domains" / "__init__.py").write_text(
            "raise ImportError('simulated: domains cannot load')\n", encoding="utf-8"
        )
    return dest


def _subject_repo(root: Path) -> Path:
    repo = root / "subject-repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("# Subject\n\nA skill.\n", encoding="utf-8")
    return repo


def _run(script: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def _report_from(stdout: str) -> dict:
    """The JSON report on stdout, after the import-time warning line if there is one."""
    return json.JSONDecoder().raw_decode(stdout, stdout.index("{"))[0]


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("analyze-degradation")


@pytest.fixture(scope="module")
def healthy(workdir: Path) -> Path:
    return _install_copy(workdir / "healthy" / "analyze", None)


@pytest.fixture(scope="module")
def subject(workdir: Path) -> Path:
    return _subject_repo(workdir)


@pytest.fixture(params=BREAKS, scope="module")
def broken(request: pytest.FixtureRequest, workdir: Path) -> Path:
    return _install_copy(workdir / f"broken-{request.param}" / "analyze", request.param)


ENTRY_POINTS = (
    pytest.param("repo-analyzer.py", id="repo-analyzer"),
    pytest.param("modes/repo/analyze-repos.py", id="analyze-repos"),
)


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_domain_request_with_domains_unloadable_fails_and_reports_nothing(
    entry: str, broken: Path, subject: Path, workdir: Path
):
    proc = _run(
        broken / entry, str(subject), "--domain", "finance", "--format", "json", cwd=workdir
    )

    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "--domain finance" in proc.stderr
    assert "did not load" in proc.stderr
    assert "Nothing was analyzed" in proc.stderr
    # The failure names why the analyzers did not load.
    assert "Error" in proc.stderr
    # No report on stdout: nothing a caller could mistake for a domain analysis.
    assert "{" not in proc.stdout, proc.stdout


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_domain_request_succeeds_when_domains_load(
    entry: str, healthy: Path, subject: Path, workdir: Path
):
    proc = _run(
        healthy / entry, str(subject), "--domain", "finance", "--format", "json", cwd=workdir
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = _report_from(proc.stdout)
    assert report["domain"] == "finance"
    assert "capability_matrix" in report


def test_auto_detect_with_domains_unloadable_fails(broken: Path, subject: Path, workdir: Path):
    proc = _run(broken / "repo-analyzer.py", str(subject), "--auto-detect", cwd=workdir)

    assert proc.returncode != 0
    assert "--auto-detect" in proc.stderr
    assert "did not load" in proc.stderr


def test_list_domains_with_domains_unloadable_exits_nonzero(
    broken: Path, subject: Path, workdir: Path
):
    proc = _run(broken / "repo-analyzer.py", "--list-domains", str(subject), cwd=workdir)

    assert proc.returncode != 0
    assert "not available" in proc.stderr


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_no_domain_request_is_unchanged_when_domains_are_unloadable(
    entry: str, healthy: Path, broken: Path, subject: Path, workdir: Path
):
    """Without --domain the general analysis runs, with or without the domain package.

    The pre-existing import-time warning is the only difference, and it stays on
    stdout exactly as before; everything after it is byte-identical.
    """
    args = (str(subject), "--format", "json")
    ok = _run(healthy / entry, *args, cwd=workdir)
    degraded = _run(broken / entry, *args, cwd=workdir)

    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert degraded.returncode == 0, degraded.stdout + degraded.stderr
    assert "[WARN] Domain analyzers not available" in degraded.stdout
    assert "[WARN] Domain analyzers not available" not in ok.stdout

    def body(out: str) -> dict:
        report = _report_from(out)
        # repository paths differ between copies only if the subject differs; it does not.
        return report

    assert body(degraded.stdout) == body(ok.stdout)
    assert "domain" not in body(ok.stdout)


def test_domain_general_is_the_general_analysis_and_needs_no_domain_package(
    broken: Path, subject: Path, workdir: Path
):
    """`--domain general` names the general analysis; it is not a domain request."""
    proc = _run(
        broken / "repo-analyzer.py",
        str(subject),
        "--domain",
        "general",
        "--format",
        "json",
        cwd=workdir,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
