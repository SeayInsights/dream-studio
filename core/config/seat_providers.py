"""Per-seat AI provider/model/effort pins, stored in config.json.

A round-table seat (canonical/review_lanes.yml) compiles onto whatever tool an
`ds integrate install` targets, with a model resolved by
integrations.compiler.reviewers._model_for_seat(). An operator can pin one seat to a
DIFFERENT provider than the rest of the install -- e.g. keep everything on
claude_code but dispatch the security-review seat to codex specifically -- and
optionally override that seat's model or reasoning effort too. This module is the
storage for that pin: read-modify-write against config.json's own `seat_providers`
key, the same shape get_quiet_mode/set_quiet_mode already use for a different key.

    {"seat_providers": {"<seat_name>": {"provider": "codex", "model": "opus"}}}

`model` and `effort` are both optional. An unset model falls back to whatever
_model_for_seat() would have resolved anyway; an unset effort means "that tool's own
default", never a literal default string, since not every tool declares
effort_levels (most don't yet -- see TargetSpec.effort_levels).

TWO CONSUMERS READ A PIN'S MODEL, NOT ONE. `integrations.compiler.reviewers.
resolve_seat_assignment()` is the compile-time reader -- an installer bakes the
resolved model into a static subagent file. `resolve_live_model()` in that same module
is the live-dispatch-time reader: `core.work_orders.review_answers.dispatch_review_round`
has no subagent file to bake anything into, only a dispatch record to annotate, so a pin
set here is informational metadata on that record (which model a seat was configured to
run on when the round was dispatched), never a claim this module or either reader can
verify was actually honored.
"""

from __future__ import annotations

from typing import Any

from core.config.state import read_config, write_config

_KEY = "seat_providers"

#: The one provider id with no TargetSpec -- Claude Code uses its own dedicated
#: installer (ClaudeCodeInstaller), not the generic multitool registry.
_CLAUDE_CODE = "claude_code"


def _valid_providers() -> frozenset[str]:
    from integrations.targets.registry import TARGET_SPECS

    return frozenset(TARGET_SPECS) | {_CLAUDE_CODE}


def _validate_model(provider: str, model: str) -> None:
    if provider == _CLAUDE_CODE:
        from integrations.compiler.agents import ALLOWED_MODEL_ALIASES

        if model not in ALLOWED_MODEL_ALIASES:
            raise ValueError(
                f"claude_code: unknown model alias {model!r};"
                f" valid: {sorted(ALLOWED_MODEL_ALIASES)}"
            )
        return
    from integrations.targets.registry import translate_model

    translate_model(provider, model)  # raises KeyError/ValueError naming what's wrong


def _validate_effort(provider: str, model: str | None, effort: str) -> None:
    """Raises naming what's wrong. *model*, when given in the SAME pin, additionally
    enforces that provider's per-model effort floor (see TargetSpec.effort_floor_by_model)
    -- codex's astra cannot run below "low" the way its luna/sol siblings can. Without an
    explicit *model*, only membership in the tool's own effort_levels is checked: the
    floor is a property of the MODEL this seat ends up on, and a pin that leaves model
    unset defers that resolution to _model_for_seat() at compile time, not here -- this
    is a deliberately bounded gap, not a silent one: pin --model alongside --effort to
    get the precise check.
    """
    if provider == _CLAUDE_CODE:
        raise ValueError("claude_code has no reasoning-effort concept for a seat to pin")
    from integrations.targets.registry import get_target_spec

    spec = get_target_spec(provider)
    if not spec.effort_levels:
        raise ValueError(
            f"{provider}: declares no effort_levels yet -- this tool's reasoning-effort"
            " vocabulary has not been verified against its own docs, so there is"
            " nothing valid to pin an effort override to"
        )
    if effort not in spec.effort_levels:
        raise ValueError(
            f"{provider}: unknown effort {effort!r}; valid: {list(spec.effort_levels)}"
        )
    if model is not None and spec.effort_floor_by_model:
        floor = spec.effort_floor_by_model.get(model)
        if floor is not None and spec.effort_levels.index(effort) < spec.effort_levels.index(floor):
            raise ValueError(
                f"{provider}: model {model!r} cannot run below effort {floor!r}"
                f" (asked for {effort!r})"
            )


def get_seat_provider(seat: str) -> dict[str, Any] | None:
    """The pinned override for *seat*, or None if it has none."""
    return read_config().get(_KEY, {}).get(seat)


def all_seat_providers() -> dict[str, dict[str, Any]]:
    """Every pinned seat name -> its override, exactly as stored."""
    return dict(read_config().get(_KEY, {}))


def set_seat_provider(
    seat: str, *, provider: str, model: str | None = None, effort: str | None = None
) -> None:
    """Pin *seat* to *provider*, replacing any existing pin for that seat.

    Raises ValueError naming what's wrong for an unknown seat name, provider, model,
    or effort -- never silently stores a pin that would later fail to compile.
    """
    if not seat or not seat.strip():
        raise ValueError("seat must be non-empty")
    valid = _valid_providers()
    if provider not in valid:
        raise ValueError(f"unknown provider {provider!r}; valid: {sorted(valid)}")
    if model is not None:
        _validate_model(provider, model)
    if effort is not None:
        _validate_effort(provider, model, effort)

    cfg = read_config()
    seats = dict(cfg.get(_KEY, {}))
    entry: dict[str, Any] = {"provider": provider}
    if model is not None:
        entry["model"] = model
    if effort is not None:
        entry["effort"] = effort
    seats[seat] = entry
    cfg[_KEY] = seats
    write_config(cfg)


def clear_seat_provider(seat: str) -> None:
    """Remove *seat*'s pin. A no-op, not an error, if it had none."""
    cfg = read_config()
    seats = dict(cfg.get(_KEY, {}))
    seats.pop(seat, None)
    cfg[_KEY] = seats
    write_config(cfg)
