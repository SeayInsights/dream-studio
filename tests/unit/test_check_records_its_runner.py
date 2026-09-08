"""Every check result records WHO ran it, not only whether it ran.

WO-SEPARATE-TEST-RUNNER shipped the operator directive -- tests and evals are always run by
a different agent than the one that authored them -- as canonical skill text, made the gate
EXECUTE rather than read a report, and made every result record whether it ran (``executed``
/ ``not_executed_reason``). What it did not do is record WHO. With no runner identity on a
check result, an author-run suite is indistinguishable from an independent runner's report
in every stored artifact, so the rule sat in ``canonical/rules.yml`` as pure ``guidance`` on
the stated grounds that no check inside the repo could observe it.

A check CAN observe it once the identity is written down. This is that half.

WHAT IS STILL OWED, and why the rule is registered as PARTIALLY enforced rather than
satisfied: comparing the runner against the AUTHOR requires author identity, and
``mark_task_done`` emits ``task.completed`` with ``session_id=None``, so the authority
records no author for a task. Until that lands, the substrate can say who ran a check and
cannot yet say it was someone else. That gap is named in the registry's ``residual_risk``
instead of being left to a reader to notice.
"""

from __future__ import annotations

from core.work_orders.verify_executor import _runner_identity


def test_the_identity_names_the_session_the_adapter_the_host_and_the_process():
    identity = _runner_identity()
    assert set(identity) == {"session", "adapter", "host", "pid"}
    assert all(isinstance(v, str) and v for v in identity.values())


def test_an_absent_session_is_recorded_as_unknown_not_omitted(monkeypatch):
    """An absent field reads as "nobody asked"; an explicit unknown reads as "asked, and
    the answer was not available". Every other honesty fix in this module turns on that
    distinction, and a runner field that vanished when the environment was bare would make
    a CI run and an author run look identical again."""
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("DS_ADAPTER_ID", raising=False)

    identity = _runner_identity()
    assert identity["session"] == "unknown"
    assert identity["adapter"] == "unknown"


def test_a_present_session_is_captured(monkeypatch):
    monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-abc-123")
    monkeypatch.setenv("DS_ADAPTER_ID", "claude")

    identity = _runner_identity()
    assert identity["session"] == "sess-abc-123"
    assert identity["adapter"] == "claude"


def test_two_processes_are_distinguishable():
    """The pid is what separates two runs on one host when neither carries a session."""
    import os

    assert _runner_identity()["pid"] == str(os.getpid())


def test_every_check_result_carries_a_runner(tmp_path):
    """Driven through the real runner, so the field cannot silently stop being attached.

    A TEST-CHECK naming a node that does not exist still produces a RESULT -- misaddressed
    is not failed -- and that result must carry a runner too, otherwise the identity would
    be present only on the happy path.
    """
    from core.work_orders.verify_executor import run_executable_checks

    tasks = [
        {
            "task_id": "t1",
            "title": "a check that cannot resolve",
            "acceptance_criteria": "TEST-CHECK: tests/unit/test_does_not_exist.py::test_nope",
        }
    ]
    # The return is `task_title -> [check, ...]`, not a flat list. Read from the signature
    # rather than assumed: assuming a shape is how the previous verdict-shape defect got in.
    results = run_executable_checks(tasks, tmp_path / "studio.db")
    assert results, "the runner returned no results at all"
    checks = [c for per_task in results.values() for c in per_task]
    assert checks, f"no check results under any task: {results}"
    for check in checks:
        assert "runner" in check, f"a check result carries no runner: {check}"
        assert check["runner"].get("session"), "the runner records no session field"
        assert "executed" in check, "the pre-existing executed field must survive"
