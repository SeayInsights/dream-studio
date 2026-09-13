"""The gate that maps a changed module to the suite named after it.

This file's own name is the convention under test: `core/gates/changed_module_suites.py`
is covered by `tests/unit/test_changed_module_suites.py`. The acceptance criterion filed
for this work originally pointed at `test_task_criteria_baseline.py`, which would have put
the gate's test in the suite of a different module -- contradicting the mapping the gate
exists to enforce, in the change that added it.
"""

from __future__ import annotations

import subprocess

from core.gates import changed_module_suites as cms


def test_a_changed_module_names_the_suite_that_covers_it():
    """The mapping is literal, and an absent suite is not a passing one.

    Driven on `suite_for` directly because the claim is about the mapping, not about git:
    a module under a source root maps to `tests/unit/test_<stem>.py` WHEN THAT FILE EXISTS,
    and to nothing when it does not. The second half is the one that matters -- a mapper
    that returned a path whether or not it existed would hand pytest a missing file and
    report the change uncovered for the wrong reason.
    """
    # The exact miss that motivated this gate: the module was edited, its suite was not run.
    assert (
        cms.suite_for("core/gates/task_criteria_baseline.py")
        == "tests/unit/test_task_criteria_baseline.py"
    )
    # And this gate covers itself.
    assert (
        cms.suite_for("core/gates/changed_module_suites.py")
        == "tests/unit/test_changed_module_suites.py"
    )

    # A real module under a source root with NO same-named suite maps to nothing rather
    # than to a path that does not exist.
    assert cms.suite_for("interfaces/cli/commands/work_order_query.py") is None

    # Not every .py file is a module with behaviour of its own.
    assert cms.suite_for("tests/unit/test_admission.py") is None, "a test is not a module"
    assert cms.suite_for("core/gates/__init__.py") is None
    assert cms.suite_for("docs/DATABASE.md") is None
    assert cms.suite_for("canonical/review_lanes.yml") is None


def test_an_unreadable_diff_fails_rather_than_reporting_clean(monkeypatch):
    """ "I could not look" and "nothing changed" have different remedies.

    A gate that cannot read the diff and reports OK is the compared-nothing-reported-clean
    shape this repo names. `measure` returns unknown, and `run` turns that into ok=False.
    """
    monkeypatch.setattr(cms, "changed_files", lambda base: [])
    report = cms.run("origin/main")
    assert report["status"] == "unknown", report
    assert report["ok"] is False, (
        "the gate could not read a diff and reported success, so a broken git invocation "
        f"would clear the check it exists to run: {report}"
    )
    assert "changed-module-suites: UNKNOWN" in cms._render(report)


def test_a_module_with_no_suite_is_reported_not_silently_covered(monkeypatch):
    """An unmapped module is named, because silence reads as coverage."""
    monkeypatch.setattr(
        cms,
        "changed_files",
        lambda base: [
            "core/gates/task_criteria_baseline.py",
            "interfaces/cli/commands/work_order_query.py",
            "docs/DATABASE.md",
        ],
    )
    report = cms.measure("origin/main")
    assert report["suites"] == ["tests/unit/test_task_criteria_baseline.py"], report
    assert report["unmapped_modules"] == ["interfaces/cli/commands/work_order_query.py"], report
    # The documentation file is neither mapped nor reported as an uncovered module.
    assert "docs/DATABASE.md" not in report["unmapped_modules"]

    rendered = cms._render(dict(report, ok=True))
    assert "work_order_query.py" in rendered, rendered


def test_a_red_mapped_suite_fails_the_gate(monkeypatch, tmp_path):
    """The gate RUNS the suite; it does not merely name it.

    Naming the suite an author should have run is advice, and this repo has said where
    advice with no mechanism goes. Asserted by making the pytest invocation come back
    non-zero and requiring the report to say so, rather than by shipping a red test.
    """
    monkeypatch.setattr(cms, "changed_files", lambda base: ["core/gates/task_criteria_baseline.py"])

    class _Proc:
        returncode = 1
        stdout = "F\n1 failed, 2 passed in 0.4s\n"
        stderr = ""

    monkeypatch.setattr(cms.subprocess, "run", lambda *a, **k: _Proc())
    report = cms.run("origin/main")

    assert report["ok"] is False, report
    assert report["pytest_returncode"] == 1
    assert "1 failed" in str(report["reason"]), report
    assert "OK" not in cms._render(report)


def test_the_gate_is_registered_in_the_pre_push_chain():
    """A gate no chain invokes is a mechanism with no caller.

    That family is the reason this gate exists, so it would be a poor joke to ship it
    unwired. Reads the canonical chain rather than a copy of it.
    """
    from pathlib import Path

    chain = (Path(cms.REPO_ROOT) / "canonical" / "workflows" / "pre-push.yaml").read_text(
        encoding="utf-8"
    )
    assert "changed-module-suites" in chain, (
        "the gate is not in canonical/workflows/pre-push.yaml, so nothing runs it and the "
        "miss it was written for would happen again unchanged"
    )
    assert (
        "core.gates.changed_module_suites" in chain
    ), "the chain names the gate but does not invoke its module"


def test_it_would_have_caught_the_miss_that_motivated_it():
    """The specific failure, replayed end to end.

    `core/gates/task_criteria_baseline.py` was edited and its suite was never run; five
    tests there were red and the gate they cover would have refused every push. This
    asserts the mapping puts that suite in front of that edit -- the one thing that had to
    be true for the miss to have been caught.
    """
    edited = "core/gates/task_criteria_baseline.py"
    suite = cms.suite_for(edited)
    assert suite is not None, f"{edited} maps to no suite, so the miss recurs"

    # And the suite it names genuinely exists and collects, or the mapping points at a file
    # pytest cannot run -- which would report the change covered by nothing.
    proc = subprocess.run(
        ["py", "-m", "pytest", suite, "--collect-only", "-q"],
        cwd=cms.REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, (
        f"the mapped suite {suite} does not collect, so the gate would hand pytest a file "
        f"it cannot run: {proc.stdout[-400:]}"
    )


def test_a_same_named_module_in_another_package_is_not_claimed_as_covered():
    """The stem is not a unique key, and treating it as one produced a false PASS.

    Constructed by an independent review against the live tree, not hypothesised:
    `core/release/repo_publication_readiness.py` and
    `interfaces/cli/repo_publication_readiness.py` both mapped to
    `tests/unit/test_repo_publication_readiness.py`, which imports only the former. So
    editing the CLI wrapper made this gate run a suite that cannot exercise it and report
    the change covered -- the exact shape the gate's own docstring says it exists to catch.

    Driven against the real repository rather than a fixture, because the claim is about
    THIS tree: a fixture would prove the branch works on invented files and say nothing
    about whether the collision it was written for is handled.
    """
    siblings = cms._modules_sharing_stem("repo_publication_readiness")
    if len(siblings) < 2:
        # The collision is what the test is about. If the repo no longer has it, this test
        # is asserting nothing and should say so rather than passing quietly.
        raise AssertionError(
            "the repository no longer has two modules named repo_publication_readiness, so "
            "this test no longer exercises the ambiguity it was written for. Repoint it at "
            f"another colliding stem or delete it. Found: {siblings}"
        )

    suite = "tests/unit/test_repo_publication_readiness.py"
    owner = cms.suite_for("core/release/repo_publication_readiness.py")
    other = cms.suite_for("interfaces/cli/repo_publication_readiness.py")

    assert owner == suite, (
        "the module the suite actually imports lost its mapping, so resolving the "
        f"ambiguity traded a false pass for a false alarm: {owner}"
    )
    assert other is None, (
        "a module the suite never imports is still claimed as covered by it. Running that "
        "suite cannot exercise this file, so reporting it green is the false pass this "
        "gate exists to refuse"
    )


def test_an_unambiguous_stem_keeps_its_mapping_without_proving_itself():
    """The common case must not be made to justify itself.

    Requiring every module to prove its suite reaches it would report UNMAPPED wherever an
    import is spelled in a form the check does not understand -- `from core.gates import
    task_criteria_baseline` never spells the dotted path contiguously. Trading a false pass
    for a false alarm is how a gate gets switched off, so the evidence requirement engages
    only where a stem is genuinely shared.
    """
    assert len(cms._modules_sharing_stem("task_criteria_baseline")) == 1
    assert (
        cms.suite_for("core/gates/task_criteria_baseline.py")
        == "tests/unit/test_task_criteria_baseline.py"
    ), "an unambiguous module lost its mapping, so the disambiguation is over-reaching"
