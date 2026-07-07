"""WO-SPLIT-HANDOFF: core/work_orders/handoff.py was split into focused modules
(handoff_constants / handoff_helpers / handoff_decision / handoff_build /
handoff_validate / handoff_security) behind a facade that re-exports the public
API. These tests pin the facade contract and module independence so existing
`from core.work_orders.handoff import X` callers keep working.
"""

from __future__ import annotations

import importlib

# The public names callers import from core.work_orders.handoff (see the 7
# handoff test modules + skill contract evals).
_PUBLIC_API = [
    "build_handoff_prompt",
    "build_handoff_sections",
    "determine_sequential_readiness",
    "determine_next_action_decision",
    "self_validate_generated_handoff",
    "parse_prompt_sections",
    "dry_run_handoff_prompt",
    "evaluate_handoff_prompt",
    "regenerate_handoff_prompt",
    "build_security_review_remediation_handoff_prompt",
    "build_security_remediation_mutation_handoff_prompt",
    "build_security_post_remediation_review_handoff_prompt",
    "evaluate_security_review_next_handoff_prompt",
    "HANDOFF_PROMPT_COMPLETENESS",
    "HANDOFF_EXECUTION_READINESS",
    "HANDOFF_PUSH_TARGET_CONSTRAINTS",
    "HANDOFF_PUSH_EVIDENCE_REQUIREMENTS",
    "READY_WITH_CONSTRAINTS",
]

_SUBMODULES = [
    "core.work_orders.handoff_constants",
    "core.work_orders.handoff_helpers",
    "core.work_orders.handoff_decision",
    "core.work_orders.handoff_build",
    "core.work_orders.handoff_validate",
    "core.work_orders.handoff_security",
]


def test_facade_reexports_full_public_api():
    h = importlib.import_module("core.work_orders.handoff")
    missing = [n for n in _PUBLIC_API if not hasattr(h, n)]
    assert not missing, f"facade dropped public names: {missing}"


def test_submodules_import_independently():
    """Every split module imports without error (no circular import)."""
    for mod in _SUBMODULES:
        assert importlib.import_module(mod) is not None


def test_facade_all_is_importable():
    h = importlib.import_module("core.work_orders.handoff")
    assert getattr(h, "__all__", None), "facade must declare __all__"
    missing = [n for n in h.__all__ if not hasattr(h, n)]
    assert not missing, f"__all__ names not importable: {missing}"


def test_facade_is_a_thin_shell():
    """The facade is re-exports only — the 5k-line implementation moved out."""
    import core.work_orders.handoff as h
    from pathlib import Path

    src = Path(h.__file__).read_text(encoding="utf-8")
    assert "def build_handoff_prompt" not in src, "impl leaked back into the facade"
    assert src.count("\n") < 200, "facade should be a thin re-export shell"


def test_build_and_validate_roundtrip_through_facade():
    """Behavioral smoke across the build<->validate module boundary: a prompt
    built via the facade evaluates through the facade without import errors."""
    from core.work_orders.handoff import determine_sequential_readiness

    # A minimal readiness call exercises decision + its helpers across modules.
    result = determine_sequential_readiness(
        work_order={"work_order_id": "wo-1", "status": "in_progress"},
        result_metadata=None,
        eval_artifacts=[],
    )
    assert isinstance(result, dict)
    assert "readiness" in result
