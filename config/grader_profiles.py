"""Grader provider profile registry (WO-GRADER-PROFILE-REGISTRY).

Per-grader-role provider profiles for the provider-neutral grader runner
(``core.adapters.grader_runner``). These describe HOW to invoke a grader provider
(the runner's profile shape: command / print_flag / prompt_via / model_flag / …),
NOT model capabilities (that was the retired model_provider_profiles registry).

Design constraints from the work order:
  - Resolves purely from static config + operator env overrides — no network, no DB
    call (the verification plane must not depend on a live provider lookup to decide
    which provider to spawn).
  - Per-role selection with fallback to a ``default`` profile.
  - Operator override precedence, and an unresolvable role fails CLOSED (raises) rather
    than silently spawning nothing.

Precedence, highest first:
  1. a per-role operator env override ``DS_GRADER_PROFILE_<ROLE>`` (shlex argv)
  2. a per-role entry in the profile table
  3. the ``default`` entry in the profile table
  4. fail closed — raise ``UnresolvableGraderProfile``
"""

from __future__ import annotations

import os
import shlex
from typing import Any

_ROLE_ENV_PREFIX = "DS_GRADER_PROFILE_"

# Built-in profile table. ``default`` is the fallback for any role without a specific
# entry. The default profile is the vendor CLI (matching grader_runner's default), but a
# role or the operator can override it to any provider — that is the whole point.
_DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "default": {"command": "claude", "print_flag": "--print", "prompt_via": "stdin"},
}


class UnresolvableGraderProfile(RuntimeError):
    """Raised when no profile can be resolved for a role and there is no default."""


def _profile_from_env(role: str) -> dict[str, Any] | None:
    raw = os.environ.get(_ROLE_ENV_PREFIX + role.upper())
    if not raw:
        return None
    parts = shlex.split(raw)
    if not parts:
        return None
    return {"command": parts[0], "base_args": parts[1:], "prompt_via": "stdin"}


def resolve_grader_profile(
    role: str | None = None,
    *,
    profiles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve the grader provider profile for ``role`` (see module precedence).

    Pure: reads only the given/static profile table and env — never the network or a DB.
    Raises ``UnresolvableGraderProfile`` when the role has no entry and there is no
    ``default`` (fail closed).
    """
    table = profiles if profiles is not None else _DEFAULT_PROFILES

    if role:
        env_profile = _profile_from_env(role)
        if env_profile is not None:
            return env_profile
        if role in table:
            return dict(table[role])

    if "default" in table:
        return dict(table["default"])

    raise UnresolvableGraderProfile(
        f"No grader provider profile for role {role!r} and no 'default' entry — "
        "refusing to spawn an unresolved provider (fail closed)."
    )
