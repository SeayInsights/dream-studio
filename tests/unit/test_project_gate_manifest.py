"""A project's gates are ITS gates, and the CLI can finally reach them.

`run_pre_push_gates` has accepted `manifest_path` and `repo_root` all along. The only
door that called it — `ds workflow run pre-push --non-interactive`, which is what the git
pre-push hook runs — passed neither. So every gate run measured Dream Studio whatever
repository the operator was standing in, and no other project could be gated at all: a
capability built, and nothing able to use it.

THE REFUSAL IS THE DESIGN. A repository with no manifest of its own is refused rather
than judged by Dream Studio's gates, because those gates measure Dream Studio — skill-sync
compares canonical skills to their projections, `pin-tests` compares `dist/plugin` to its
generator, `migration-risk` watches this repo's DDL sites. Against another repository they
pass vacuously or fail for reasons about this one, and a green result that means nothing
is worse than a refusal because only one of the two gets fixed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interfaces.cli.ds_workflow import PROJECT_GATE_MANIFEST, _resolve_gate_manifest

MANIFEST = "gates:\n  - id: noop\n    tier: advisory\n    command: [py, -c, pass]\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    d = tmp_path / "a-project"
    (d / PROJECT_GATE_MANIFEST.parent).mkdir(parents=True)
    (d / PROJECT_GATE_MANIFEST).write_text(MANIFEST, encoding="utf-8")
    return d


# --------------------------------------------------------------------------
# The convention
# --------------------------------------------------------------------------


def test_a_project_manifest_is_found_by_convention(project):
    resolved = _resolve_gate_manifest(repo_root=str(project), manifest_path=None)
    assert "error" not in resolved
    assert resolved["manifest_path"] == project / PROJECT_GATE_MANIFEST
    assert resolved["repo_root"] == project


def test_the_convention_is_one_documented_path(project):
    """An operator who has onboarded a project must be able to find where the manifest
    goes without reading the source, so the path is a module constant and the refusal
    below prints it."""
    assert PROJECT_GATE_MANIFEST.as_posix() == ".dream-studio/pre-push.yaml"


def test_no_repo_root_still_means_dream_studios_own(project):
    """The default path must not change: the git pre-push hook in THIS repo passes no
    --repo-root, and `None` is what `run_pre_push_gates` already reads as its own."""
    resolved = _resolve_gate_manifest(repo_root=None, manifest_path=None)
    assert resolved == {"manifest_path": None, "repo_root": None}


# --------------------------------------------------------------------------
# The refusal
# --------------------------------------------------------------------------


def test_a_project_with_no_manifest_is_refused_not_judged_by_dream_studios_gates(tmp_path):
    bare = tmp_path / "bare-project"
    bare.mkdir()
    resolved = _resolve_gate_manifest(repo_root=str(bare), manifest_path=None)
    assert "error" in resolved
    assert "manifest_path" not in resolved, "a refusal must not also hand back a manifest"


def test_the_refusal_says_where_to_put_the_manifest_and_why_there_is_no_fallback(tmp_path):
    """A refusal that does not say how to satisfy it is a wall, and one that does not say
    why it refuses invites somebody to add the fallback back."""
    bare = tmp_path / "bare-project"
    bare.mkdir()
    error = _resolve_gate_manifest(repo_root=str(bare), manifest_path=None)["error"]
    assert PROJECT_GATE_MANIFEST.as_posix() in error
    assert "--manifest" in error
    assert "measure Dream Studio" in error


def test_a_repo_root_that_is_not_a_directory_is_refused(tmp_path):
    resolved = _resolve_gate_manifest(repo_root=str(tmp_path / "nope"), manifest_path=None)
    assert "not a directory" in resolved["error"].lower()


# --------------------------------------------------------------------------
# The explicit override
# --------------------------------------------------------------------------


def test_an_explicit_manifest_overrides_the_convention(tmp_path, project):
    elsewhere = tmp_path / "somewhere-else.yaml"
    elsewhere.write_text(MANIFEST, encoding="utf-8")
    resolved = _resolve_gate_manifest(repo_root=str(project), manifest_path=str(elsewhere))
    assert resolved["manifest_path"] == elsewhere
    assert resolved["repo_root"] == project, "the tree under test is still the named one"


def test_an_explicit_manifest_that_does_not_exist_is_refused(tmp_path):
    resolved = _resolve_gate_manifest(repo_root=None, manifest_path=str(tmp_path / "missing.yaml"))
    assert "no gate manifest at" in resolved["error"]


# --------------------------------------------------------------------------
# The door actually passes it through
# --------------------------------------------------------------------------


def test_the_cli_hands_both_values_to_the_runner(project, monkeypatch, capsys):
    """The whole defect was a door that opened onto nothing. Asserted by driving
    `cmd_run` and capturing what the runner was actually called with."""
    import interfaces.cli.ds_workflow as wf

    seen = {}

    class _Report:
        overall_passed = True

    def _fake_run(*, manifest_path=None, repo_root=None):
        seen["manifest_path"] = manifest_path
        seen["repo_root"] = repo_root
        return _Report()

    import core.gates.pre_push as pp

    monkeypatch.setattr(pp, "run_pre_push_gates", _fake_run)
    monkeypatch.setattr(pp, "format_report", lambda r: "ok")

    import argparse

    args = argparse.Namespace(
        wf_key="pre-push",
        non_interactive=True,
        dry_run=False,
        repo_root=str(project),
        manifest_path=None,
    )
    assert wf.cmd_run(args) == 0
    assert seen["manifest_path"] == project / PROJECT_GATE_MANIFEST
    assert seen["repo_root"] == project


def test_the_cli_exposes_both_flags():
    """A capability is not done until the CLI exposes it — the rule this whole change
    exists to satisfy, asserted on the parser rather than on the help text."""
    import argparse

    from interfaces.cli.ds_workflow import add_workflow_subcommand

    parser = argparse.ArgumentParser()
    add_workflow_subcommand(parser.add_subparsers(dest="command"))
    args = parser.parse_args(
        ["workflow", "run", "pre-push", "--non-interactive", "--repo-root", ".", "--manifest", "m"]
    )
    assert args.repo_root == "."
    assert args.manifest_path == "m"
