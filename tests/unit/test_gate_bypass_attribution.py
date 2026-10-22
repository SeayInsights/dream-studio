"""The gate-bypass ledger can say WHICH run a bypass belongs to (#927).

A `gate.bypassed` event is one run of the gate that took the hatch; every pre-push retry
and every stacked branch inheriting an earlier trailer is another. The payload used to
carry no branch, sha, base or launcher, so the runs could not be told apart.

These run the real emitters against a real git repository and read the real payload off
the spool writer.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

from core.gates import bypass_event, migration_risk  # noqa: E402
from core.gates.bypass_event import INVOCATION_ENV, invocation, run_context  # noqa: E402

DOMAIN = "sqlite_schema_authority"  # impacted by a change to core/config/database.py
RISK_FILE = "core/event_store/migrations/083_new.sql"


# -- a real repository ----------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, rel: str, message: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{message}\n{uuid.uuid4()}", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    """main + a feature branch of four commits: two trailers naming DOMAIN, one naming
    another domain, and one with no trailer. Returns the repo path and the shas."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    base = _commit(root, "base.txt", "base")
    _git(root, "checkout", "-q", "-b", "feature/attribution")
    first = _commit(
        root, "core/config/database.py", f"first\n\nDocs-Reviewed-No-Change: {DOMAIN}\n"
    )
    other = _commit(root, "b.txt", "other\n\nDocs-Reviewed-No-Change: some_other_domain\n")
    plain = _commit(root, "c.txt", "plain")
    second = _commit(root, "d.txt", f"second\n\nDocs-Reviewed-No-Change: {DOMAIN}\n")
    return {
        "root": root,
        "base": base,
        "first": first,
        "other": other,
        "plain": plain,
        "second": second,
        "head": second,
    }


@pytest.fixture
def written(monkeypatch) -> list[dict]:
    """Every envelope the emitter writes to the spool, captured at the writer."""
    events: list[dict] = []
    monkeypatch.setattr("spool.writer.write_event", lambda ev: events.append(ev))
    for var in (
        INVOCATION_ENV,
        "GITHUB_ACTIONS",
        "GITHUB_BASE_REF",
        "DREAM_STUDIO_BASE_REF",
        "DREAM_STUDIO_CHANGED_FILES",
        "DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE",
        "MIGRATION_RISK_ACKNOWLEDGED",
    ):
        monkeypatch.delenv(var, raising=False)
    return events


# -- invocation -------------------------------------------------------------------------


@pytest.mark.parametrize("declared", ["pre_push_hook", "pre_push_runner", "ci_gate"])
def test_a_declared_launcher_is_reported_as_declared(monkeypatch, declared):
    monkeypatch.setenv(INVOCATION_ENV, declared)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert invocation() == declared


def test_a_declaration_outranks_what_the_environment_shows(monkeypatch):
    """ci_gate sets GITHUB_ACTIONS itself; it must still be named, not 'github_actions'."""
    monkeypatch.setenv(INVOCATION_ENV, "ci_gate")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert invocation() == "ci_gate"


def test_undeclared_invocation_says_only_what_can_be_seen(monkeypatch):
    monkeypatch.delenv(INVOCATION_ENV, raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert invocation() == "direct"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert invocation() == "github_actions"


@pytest.mark.parametrize("stray", ["manual", "", "PRE_PUSH_HOOK", "work_order_check"])
def test_a_value_that_is_not_a_known_launcher_is_never_recorded(monkeypatch, stray):
    monkeypatch.setenv(INVOCATION_ENV, stray)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert invocation() == "direct"


# -- run_context ------------------------------------------------------------------------


def test_run_context_is_true_to_the_repository(repo, monkeypatch):
    monkeypatch.delenv(INVOCATION_ENV, raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    ctx = run_context(repo["root"], "main")
    assert ctx == {
        "branch": "feature/attribution",
        "head_sha": repo["head"],
        "base_ref": "main",
        "base_sha": repo["base"],
        "invocation": "direct",
    }


def test_run_context_on_a_detached_head_has_no_branch(repo):
    _git(repo["root"], "checkout", "-q", "--detach", repo["first"])
    ctx = run_context(repo["root"], "main")
    assert ctx["branch"] is None
    assert ctx["head_sha"] == repo["first"]


def test_run_context_never_invents_what_git_cannot_answer(repo, tmp_path):
    ctx = run_context(repo["root"], "origin/does-not-exist")
    assert ctx["base_ref"] == "origin/does-not-exist"
    assert ctx["base_sha"] is None
    assert run_context(repo["root"], None)["base_ref"] is None
    assert run_context(repo["root"], None)["base_sha"] is None

    elsewhere = tmp_path / "not-a-repo"
    elsewhere.mkdir()
    ctx = run_context(elsewhere, "main")
    assert (ctx["branch"], ctx["head_sha"], ctx["base_sha"]) == (None, None, None)


def test_a_failing_git_command_is_absent_even_when_it_printed_something(tmp_path):
    """On a repository with no commits `git rev-parse HEAD` prints the word HEAD to stdout
    and exits non-zero. That is a failure, not a sha."""
    root = tmp_path / "unborn"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    ctx = run_context(root, "main")
    assert ctx["head_sha"] is None
    assert ctx["base_sha"] is None


def test_a_successful_command_that_printed_nothing_is_absent(repo, monkeypatch):
    """Empty output is no answer: it must not become an empty or placeholder string."""

    class _Silent:
        returncode = 0
        stdout = "  \n"

    monkeypatch.setattr(bypass_event.subprocess, "run", lambda *a, **k: _Silent())
    ctx = run_context(repo["root"], "main")
    assert ctx["branch"] is None and ctx["head_sha"] is None and ctx["base_sha"] is None


def test_run_context_survives_a_missing_git_binary(repo, monkeypatch):
    def _no_git(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(bypass_event.subprocess, "run", _no_git)
    ctx = run_context(repo["root"], "main")
    assert ctx["branch"] is None and ctx["head_sha"] is None and ctx["base_sha"] is None


# -- the trailer commits ------------------------------------------------------------------


def test_trailer_commits_names_exactly_the_commits_that_cleared_the_domain(repo):
    from interfaces.cli._gate_review_context import trailer_commits

    shas = trailer_commits(repo_root=repo["root"], base_ref="main", domains=[DOMAIN])
    assert shas == [repo["first"], repo["second"]]  # oldest first; not `other`, not `plain`

    assert trailer_commits(
        repo_root=repo["root"], base_ref="main", domains=["some_other_domain"]
    ) == [repo["other"]]
    assert trailer_commits(repo_root=repo["root"], base_ref="main", domains=["nobody"]) == []


def test_a_commit_naming_the_domain_twice_is_listed_once(repo):
    from interfaces.cli._gate_review_context import trailer_commits

    twice = _commit(
        repo["root"],
        "e.txt",
        f"twice\n\nDocs-Reviewed-No-Change: {DOMAIN}\nDocs-Reviewed-No-Change: {DOMAIN}, x\n",
    )
    shas = trailer_commits(repo_root=repo["root"], base_ref="main", domains=[DOMAIN])
    assert shas == [repo["first"], repo["second"], twice]


def test_reviewed_no_change_domains_still_reads_every_trailer(repo):
    """The shared parser feeds both gates; its domain answer must not move."""
    from interfaces.cli._gate_review_context import reviewed_no_change_domains

    assert reviewed_no_change_domains(
        cli_domains=[], repo_root=repo["root"], base_ref="main"
    ) == sorted({DOMAIN, "some_other_domain"})


# -- docs-drift payload -------------------------------------------------------------------


def _run_docs_drift(repo: dict, monkeypatch, capsys, *argv: str) -> None:
    from interfaces.cli import contract_docs_drift_gate as gate

    monkeypatch.setattr(gate, "REPO_ROOT", repo["root"])
    with pytest.raises(SystemExit):
        gate.main(list(argv))
    capsys.readouterr()


def test_docs_drift_bypass_names_the_run(repo, written, monkeypatch, capsys):
    _run_docs_drift(repo, monkeypatch, capsys, "--base-ref", "main")

    assert len(written) == 1
    ev = written[0]
    assert ev["event_type"] == "gate.bypassed"
    payload = ev["payload"]
    assert payload["gate"] == "docs_drift_reviewed_no_change"
    assert DOMAIN in payload["domains"]
    assert payload["branch"] == "feature/attribution"
    assert payload["head_sha"] == repo["head"]
    assert payload["base_ref"] == "main"
    assert payload["base_sha"] == repo["base"]
    assert payload["trailer_commits"] == [repo["first"], repo["second"]]
    assert payload["invocation"] == "direct"
    assert payload["reason"].isascii()


def test_docs_drift_bypass_reports_the_launcher_that_declared_itself(
    repo, written, monkeypatch, capsys
):
    monkeypatch.setenv(INVOCATION_ENV, "pre_push_hook")
    _run_docs_drift(repo, monkeypatch, capsys, "--base-ref", "main")
    assert written[0]["payload"]["invocation"] == "pre_push_hook"


def test_the_same_commit_run_twice_is_two_events_with_one_head(repo, written, monkeypatch, capsys):
    """Duplicates are accepted at emission (a retry IS another execution); what makes them
    countable is that both carry the same head_sha, which `bypass_audit` groups on."""
    _run_docs_drift(repo, monkeypatch, capsys, "--base-ref", "main")
    _run_docs_drift(repo, monkeypatch, capsys, "--base-ref", "main")
    assert len(written) == 2
    assert {e["payload"]["head_sha"] for e in written} == {repo["head"]}


def test_a_domain_cleared_without_a_trailer_has_no_trailer_commit(
    repo, written, monkeypatch, capsys
):
    """Cleared through the CLI flag: no commit accounts for it, and none is invented."""
    _git(repo["root"], "checkout", "-q", "-b", "no-trailer", repo["base"])
    _commit(repo["root"], "core/config/database.py", "no trailer here")
    _run_docs_drift(
        repo, monkeypatch, capsys, "--base-ref", "main", "--docs-reviewed-no-change", DOMAIN
    )
    payload = written[0]["payload"]
    assert DOMAIN in payload["domains"]
    assert payload["trailer_commits"] == []
    assert payload["branch"] == "no-trailer"


# -- migration-risk payload and acknowledgement -----------------------------------------


@pytest.fixture
def migration_gate(repo, written, monkeypatch):
    monkeypatch.setattr(migration_risk, "REPO_ROOT", repo["root"])
    monkeypatch.setattr(migration_risk, "_changed_files", lambda base_ref: [RISK_FILE])
    # Rollback pairing and DROP safety are not bypassable and have their own tests.
    monkeypatch.setattr(
        "core.gates.migration_rollback_pairing.find_unpaired_migrations", lambda: []
    )
    monkeypatch.setattr(migration_risk, "_changed_forward_migration_drops", lambda files: [])
    monkeypatch.setenv("DREAM_STUDIO_BASE_REF", "main")
    return written


def test_migration_risk_bypass_names_the_run(repo, migration_gate, monkeypatch):
    monkeypatch.setenv("MIGRATION_RISK_ACKNOWLEDGED", "1")
    monkeypatch.setenv(INVOCATION_ENV, "pre_push_runner")

    assert migration_risk.main() == 0

    assert len(migration_gate) == 1
    payload = migration_gate[0]["payload"]
    assert payload["gate"] == "migration_risk"
    assert payload["risk_files"] == [RISK_FILE]
    assert payload["branch"] == "feature/attribution"
    assert payload["head_sha"] == repo["head"]
    assert payload["base_ref"] == "main"
    assert payload["base_sha"] == repo["base"]
    assert payload["invocation"] == "pre_push_runner"
    assert payload["reason"].isascii(), payload["reason"]


# -- the launchers declare themselves ------------------------------------------------------


def test_the_git_hook_declares_itself_on_the_command_it_runs():
    text = (REPO_ROOT / "hooks" / "git" / "pre-push").read_text(encoding="utf-8")
    match = re.search(
        rf"^{INVOCATION_ENV}=(\w+) \"\$PY\" -m interfaces\.cli\.ds workflow run pre-push",
        text,
        re.MULTILINE,
    )
    assert match, "the hook must set the invocation on the very command that runs the gates"
    assert match.group(1) == "pre_push_hook"
    assert match.group(1) in bypass_event.DECLARED_INVOCATIONS


def test_ci_gate_declares_itself_to_every_check_it_starts(monkeypatch, tmp_path):
    import tempfile

    from interfaces.cli import ci_gate

    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(tmp_path / prefix))
    monkeypatch.delenv(INVOCATION_ENV, raising=False)
    assert ci_gate._isolated_check_env()[INVOCATION_ENV] == "ci_gate"


def _manifest(tmp_path: Path) -> Path:
    probe = "import os; print('invocation=' + os.environ.get('" + INVOCATION_ENV + "', 'UNSET'))"
    manifest = tmp_path / "gates.yaml"
    manifest.write_text(
        "gates:\n"
        "  - id: probe\n"
        "    tier: blocking\n"
        f"    command: [{json.dumps(sys.executable)}, '-c', {json.dumps(probe)}]\n",
        encoding="utf-8",
    )
    return manifest


def test_the_runner_names_itself_for_the_run_and_leaves_nothing_behind(monkeypatch, tmp_path):
    from core.gates.pre_push import run_pre_push_gates

    monkeypatch.delenv(INVOCATION_ENV, raising=False)
    report = run_pre_push_gates(
        manifest_path=_manifest(tmp_path), repo_root=tmp_path, emit_events=False
    )
    assert report.overall_passed
    assert "invocation=pre_push_runner" in report.gates[0].stdout_tail
    import os

    assert INVOCATION_ENV not in os.environ


def test_the_runner_does_not_overwrite_what_the_hook_declared(monkeypatch, tmp_path):
    from core.gates.pre_push import run_pre_push_gates

    monkeypatch.setenv(INVOCATION_ENV, "pre_push_hook")
    report = run_pre_push_gates(
        manifest_path=_manifest(tmp_path), repo_root=tmp_path, emit_events=False
    )
    assert "invocation=pre_push_hook" in report.gates[0].stdout_tail
    import os

    assert os.environ[INVOCATION_ENV] == "pre_push_hook"
