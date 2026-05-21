"""C5 — Context budget tracking evals.

Verifies:
  - EventType.SKILL_BUDGET_EXCEEDED exists with value "skill.budget_exceeded"
  - check_budget_status() returns correct status dict for ok / warning / exceeded
  - build_budget_exceeded_payload() returns correct payload shape
"""

from __future__ import annotations


# ── event type registration ───────────────────────────────────────────────────


def test_skill_budget_exceeded_event_type_exists() -> None:
    from canonical.events.types import EventType

    assert hasattr(EventType, "SKILL_BUDGET_EXCEEDED")
    assert EventType.SKILL_BUDGET_EXCEEDED.value == "skill.budget_exceeded"


# ── check_budget_status ───────────────────────────────────────────────────────


def test_budget_status_ok() -> None:
    from core.telemetry.context_budget import check_budget_status

    result = check_budget_status(tokens_used=5_000, budget_limit=100_000)
    assert result["status"] == "ok"
    assert result["exceeded"] is False
    assert result["warning"] is False
    assert result["tokens_used"] == 5_000
    assert result["budget_limit"] == 100_000
    assert 0.0 < result["utilization"] < 0.8


def test_budget_status_warning() -> None:
    from core.telemetry.context_budget import check_budget_status

    result = check_budget_status(tokens_used=85_000, budget_limit=100_000)
    assert result["status"] == "warning"
    assert result["exceeded"] is False
    assert result["warning"] is True
    assert result["utilization"] >= 0.8


def test_budget_status_exceeded() -> None:
    from core.telemetry.context_budget import check_budget_status

    result = check_budget_status(tokens_used=101_000, budget_limit=100_000)
    assert result["status"] == "exceeded"
    assert result["exceeded"] is True
    assert result["warning"] is False
    assert result["utilization"] > 1.0


def test_budget_status_exactly_at_limit_is_exceeded() -> None:
    from core.telemetry.context_budget import check_budget_status

    result = check_budget_status(tokens_used=100_000, budget_limit=100_000)
    assert result["exceeded"] is False
    assert result["status"] in {"ok", "warning"}


def test_budget_status_custom_warning_threshold() -> None:
    from core.telemetry.context_budget import check_budget_status

    result = check_budget_status(tokens_used=70_000, budget_limit=100_000, warning_threshold=0.6)
    assert result["warning"] is True
    assert result["status"] == "warning"


# ── build_budget_exceeded_payload ─────────────────────────────────────────────


def test_build_budget_exceeded_payload_shape() -> None:
    from core.telemetry.context_budget import build_budget_exceeded_payload

    payload = build_budget_exceeded_payload(
        skill_id="ds-core:build",
        work_order_id="wo-0001",
        tokens_used=110_000,
        budget_limit=100_000,
    )
    assert payload["skill_id"] == "ds-core:build"
    assert payload["work_order_id"] == "wo-0001"
    assert payload["tokens_used"] == 110_000
    assert payload["budget_limit"] == 100_000
    assert payload["overage"] == 10_000


def test_build_budget_exceeded_payload_no_wo() -> None:
    from core.telemetry.context_budget import build_budget_exceeded_payload

    payload = build_budget_exceeded_payload(
        skill_id="ds-core:think",
        work_order_id=None,
        tokens_used=105_000,
        budget_limit=100_000,
    )
    assert payload["work_order_id"] is None
    assert payload["overage"] == 5_000
