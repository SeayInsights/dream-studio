"""The single-read-path gate, and the closability answer it protects.

The defect, twice reported to the operator as fact: a survey asked whether thirteen work
orders could be closed, read ``result["gates"]`` instead of ``gates_pass`` /
``gate_failures``, got ``None``, and reported all thirteen CLOSABLE. Every one was blocked
on ``independent_review``.

Two halves are tested here. The gate refuses a caller that re-derives the answer. And
``closability`` itself is asserted to resolve every ambiguity toward NOT closable, because
the whole point of a single read is that a mistake stops producing an optimistic answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.gates import single_read_path as srp

_REDERIVES = """
def survey(work_order_id):
    result = check_close_gates(work_order_id=work_order_id, source_root=".")
    failures = [g for g, v in (result.get("gate_failures") or {}).items() if not v]
    return not failures
"""

_SUBSCRIPT = """
def survey(result):
    return result["gates_pass"]
"""

_USES_THE_SUPPORTED_READ = """
from core.work_orders.close import closability


def survey(work_order_id):
    can_close, reasons = closability(work_order_id=work_order_id, source_root=".")
    return can_close, reasons
"""

_HARDCODED_VOCABULARY = """
def count_done(tasks):
    return sum(1 for t in tasks if t["status"] in ("done", "completed"))
"""

_IMPORTED_VOCABULARY = """
from core.work_orders.task_status import is_done


def count_done(tasks):
    return sum(1 for t in tasks if is_done(t["status"]))
"""

# A status word in prose, or a pair that names no finished state, is not the vocabulary.
_INNOCENT = """
MESSAGES = ("complete the form", "please try again")
PHASES = ("created", "in_progress")
"""


def _tree(tmp_path: Path, source: str, *, rel: str = "core/survey_site.py") -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


def test_catches_a_caller_that_rederives_close_readiness(tmp_path):
    result = srp.run(repo_root=_tree(tmp_path, _REDERIVES))
    assert result["status"] == "fail"
    assert result["offenders"][0]["contract"] == "close-readiness"


def test_catches_a_subscript_read_too_not_only_dot_get(tmp_path):
    # `.get()` returns None silently; `[...]` raises. Both are re-derivation, and a gate
    # that caught only one would send the next author to the other.
    result = srp.run(repo_root=_tree(tmp_path, _SUBSCRIPT))
    assert result["status"] == "fail"
    assert result["offenders"][0]["contract"] == "close-readiness"


def test_the_supported_read_is_not_a_finding(tmp_path):
    result = srp.run(repo_root=_tree(tmp_path, _USES_THE_SUPPORTED_READ))
    assert result["status"] == "pass", result["offenders"]


def test_catches_a_hardcoded_task_status_vocabulary(tmp_path):
    result = srp.run(repo_root=_tree(tmp_path, _HARDCODED_VOCABULARY))
    assert result["status"] == "fail"
    assert result["offenders"][0]["contract"] == "task-done-vocabulary"


def test_the_imported_vocabulary_is_not_a_finding(tmp_path):
    result = srp.run(repo_root=_tree(tmp_path, _IMPORTED_VOCABULARY))
    assert result["status"] == "pass", result["offenders"]


def test_prose_and_unrelated_status_pairs_are_not_findings(tmp_path):
    result = srp.run(repo_root=_tree(tmp_path, _INNOCENT))
    assert result["status"] == "pass", result["offenders"]


def test_a_declared_owner_may_read_the_raw_fields(tmp_path):
    # The module that BUILDS the answer, and the tests of that module, necessarily touch
    # the fields. An owner list is how the contract stays enforceable instead of being
    # switched off the first time it fires on its own producer.
    tree = _tree(tmp_path, _SUBSCRIPT, rel="core/work_orders/close_main.py")
    assert srp.run(repo_root=tree)["status"] == "pass"


def test_every_contract_states_its_supported_read_and_its_reason():
    for contract in srp.CONTRACTS:
        assert contract.supported_read, f"{contract.name} names no supported read"
        assert len(contract.why) > 60, (
            f"{contract.name} states no real reason. A contract whose rationale is a"
            " shrug gets deleted by the next person who trips over it."
        )
        assert contract.owners, f"{contract.name} declares no owner"


def test_the_real_repository_honours_every_contract():
    result = srp.run()
    assert result["status"] == "pass", result["offenders"]
    assert result["files_scanned"] > 500, "the scan found almost nothing -- roots are wrong"


# --------------------------------------------------------------------------------------
# closability: the answer the gate protects. Every ambiguity must resolve to NOT closable.
# --------------------------------------------------------------------------------------


def _patched_preview(monkeypatch, payload: dict) -> None:
    from core.work_orders import close_main

    monkeypatch.setattr(close_main, "check_close_gates", lambda **_: payload)


def test_closability_reports_not_closable_when_the_work_order_is_unreadable(monkeypatch):
    _patched_preview(monkeypatch, {"ok": False, "error": "Work order not found: x"})
    from core.work_orders.close_main import closability

    can_close, reasons = closability(work_order_id="x", source_root=Path.cwd())
    assert can_close is False
    assert "not found" in reasons[0]


def test_closability_never_returns_true_with_reasons(monkeypatch):
    # A preview that contradicts itself is not evidence of a pass.
    _patched_preview(
        monkeypatch, {"ok": True, "gates_pass": True, "gate_failures": ["independent_review"]}
    )
    from core.work_orders.close_main import closability

    can_close, reasons = closability(work_order_id="x", source_root=Path.cwd())
    assert can_close is False
    assert any("contradicts itself" in r for r in reasons)


def test_closability_refuses_a_failure_with_no_stated_reason(monkeypatch):
    _patched_preview(monkeypatch, {"ok": True, "gates_pass": False, "gate_failures": []})
    from core.work_orders.close_main import closability

    can_close, reasons = closability(work_order_id="x", source_root=Path.cwd())
    assert can_close is False
    assert reasons, "a refusal with no reason is still a refusal, and must say something"


def test_closability_passes_only_on_an_unambiguous_pass(monkeypatch):
    _patched_preview(monkeypatch, {"ok": True, "gates_pass": True, "gate_failures": []})
    from core.work_orders.close_main import closability

    can_close, reasons = closability(work_order_id="x", source_root=Path.cwd())
    assert can_close is True
    assert reasons == []


def test_closability_reasons_are_empty_exactly_when_it_can_close(monkeypatch):
    """The invariant a caller is allowed to rely on, so nobody has to check both."""
    for payload in (
        {"ok": True, "gates_pass": True, "gate_failures": []},
        {"ok": True, "gates_pass": False, "gate_failures": ["a"]},
        {"ok": False, "error": "gone"},
    ):
        _patched_preview(monkeypatch, payload)
        from core.work_orders.close_main import closability

        can_close, reasons = closability(work_order_id="x", source_root=Path.cwd())
        assert can_close == (not reasons)


def test_a_missing_gates_pass_key_is_not_an_optimistic_pass(monkeypatch):
    """The exact mistake, at the source. A preview missing the field must not read as yes."""
    _patched_preview(monkeypatch, {"ok": True})
    from core.work_orders.close_main import closability

    can_close, _ = closability(work_order_id="x", source_root=Path.cwd())
    assert can_close is False


@pytest.mark.parametrize("field", ["gates_pass", "gate_failures"])
def test_the_gate_watches_both_close_readiness_fields(field):
    contract = next(c for c in srp.CONTRACTS if c.name == "close-readiness")
    assert field in contract.fields
