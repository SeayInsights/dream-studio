"""A gate outcome says which repository it judged.

THE DEFECT, found by reading the live spool after `--repo` shipped. `pre_push --repo
<path>` runs another project's own gates, and the telemetry landed in Dream Studio's
spool carrying `gate_id` and nothing else:

    {"gate_id": "says-hello", "outcome": "passed", "passed": true, ...}

`says-hello` exists only in a throwaway test project. It sat in the authority beside 23
real gates with nothing to tell them apart. Any later question of the form "how often
does this gate fail" silently mixes two populations, and the answer is wrong in a
direction nobody would notice — which is worse than no telemetry, because it looks like
an answer.
"""

from __future__ import annotations

import pathlib

from core.gates.pre_push import REPO_ROOT, GateResult, _judged_repo


def _result(gate_id: str = "g", passed: bool = True) -> GateResult:
    return GateResult(
        gate_id=gate_id,
        passed=passed,
        exit_code=0 if passed else 1,
        duration_seconds=0.0,
    )


def test_this_repository_is_recorded_as_itself():
    attribution = _judged_repo(None)
    assert attribution["repo"] == str(REPO_ROOT)
    assert attribution["repo_is_self"] is True


def test_another_project_is_recorded_as_not_self(tmp_path):
    attribution = _judged_repo(tmp_path)
    assert attribution["repo"] == str(pathlib.Path(tmp_path).resolve())
    assert (
        attribution["repo_is_self"] is False
    ), "a foreign project's gate outcome is indistinguishable from this repository's"


def test_the_same_path_spelled_differently_is_still_self():
    """`--repo .` and the default must not split one repository into two populations."""
    assert _judged_repo(REPO_ROOT)["repo_is_self"] is True
    assert _judged_repo(str(REPO_ROOT))["repo_is_self"] is True


def test_both_emitters_accept_the_repository():
    """The failure event carries it too. Attributing only the outcome event would leave
    the failure rows — the ones anyone actually queries — unattributed."""
    import inspect

    from core.gates.pre_push import emit_gate_failure_event, emit_gate_outcome_event

    for fn in (emit_gate_outcome_event, emit_gate_failure_event):
        assert "repo_root" in inspect.signature(fn).parameters, fn.__name__
        assert "_judged_repo" in inspect.getsource(
            fn
        ), f"{fn.__name__} takes repo_root and does not put it in the payload"


def test_the_run_loop_passes_the_root_it_actually_used():
    """The wiring. A signature that accepts attribution proves nothing about whether the
    caller supplies it — the gap that let a mutant survive twenty-six tests earlier in
    this series."""
    import inspect

    from core.gates.pre_push import run_pre_push_gates

    source = inspect.getsource(run_pre_push_gates)
    assert "emit_gate_outcome_event(result, repo_root=root)" in source
    assert "emit_gate_failure_event(result, repo_root=root)" in source
