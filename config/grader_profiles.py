"""Grader provider profile registry (WO-GRADER-PROFILE-REGISTRY + gap follow-ups).

Per-grader-role provider profiles for the provider-neutral grader runner
(``core.adapters.grader_runner``). A profile describes HOW to invoke a grader provider
(NOT model capabilities — that was the retired model_provider_profiles registry).

Minimum profile shape (every resolved profile carries all of these):
  - ``provider_id``       — stable id for the provider (e.g. "claude-cli")
  - ``command`` + argv    — the invocation argv template (command / base_args / print_flag)
  - ``model_id``          — the model to request (None = let the provider default), fed to
                            the runner argv via ``model_flag``
  - ``availability_probe``— what ``grader_provider_available`` checks (PATH name / abs path)
  - ``prompt_via``        — "stdin" (default) | "argv"

Resolution precedence (highest first) — one place, documented alongside DS_ENFORCE in
docs/HOOK_RUNTIME.md and CLAUDE.md:
  1. an explicit CLI flag value (``cli_override``, a shlex argv string)
  2. the per-role env override ``DS_GRADER_PROFILE_<ROLE>`` (shlex argv)
  3. a per-role (or ``default``) entry in the config file at ``DS_GRADER_PROFILE_CONFIG``
  4. a per-role (or ``default``) entry in the built-in registry table
  5. fail closed — raise ``UnresolvableGraderProfile`` naming the exact keys to set
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

_ROLE_ENV_PREFIX = "DS_GRADER_PROFILE_"
_CONFIG_ENV = "DS_GRADER_PROFILE_CONFIG"
_STUB_ENV = "DS_GRADER_STUB"

#: The grader roles the verify plane runs, in a stable order.
GRADER_ROLES: tuple[str, ...] = ("completion", "correctness", "quality", "migration")

# Built-in registry table. ``default`` is the fallback for any role without an entry.
_DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "provider_id": "claude-cli",
        "command": "claude",
        "print_flag": "--print",
        "model_flag": "--model",
        "model_id": None,
        "prompt_via": "stdin",
        "availability_probe": "claude",
    },
}


# Named real (non-stub) provider profiles. The registry must contain at least two real
# providers so "the verification plane is portable across providers" is more than a claim
# about one vendor (gap 930ea6df). A profile DEFINITION here does not assert the binary is
# installed or that it emits a conformant verdict on this host — that is a runtime question
# answered by grader_provider_available + run_grader_conformance.
PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "claude-cli": _DEFAULT_PROFILES["default"],
    # OpenAI Codex CLI, non-interactive: `codex exec "<prompt>"`. Registered so the
    # registry holds a second real provider; whether it can act as a one-shot JSON grader
    # on a given host is checked at runtime (it needs login and is agentic, so it may not).
    "codex-cli": {
        "provider_id": "codex-cli",
        "command": "codex",
        "base_args": ["exec"],
        "model_flag": "--model",
        "model_id": None,
        "prompt_via": "argv",
        "availability_probe": "codex",
    },
}


def real_provider_profiles() -> dict[str, dict[str, Any]]:
    """Return the named real (non-stub) provider profiles the registry knows about."""
    return {name: _normalize(p) for name, p in PROVIDER_PROFILES.items()}


def resolve_named_provider(name: str) -> dict[str, Any]:
    """Resolve a named real provider profile by id (bypasses the stub/env precedence).

    Used to run conformance against a specific real provider (gap 930ea6df). Raises
    ``UnresolvableGraderProfile`` for an unknown provider.
    """
    if name not in PROVIDER_PROFILES:
        raise UnresolvableGraderProfile(
            f"Unknown grader provider {name!r}. Known real providers: {sorted(PROVIDER_PROFILES)}."
        )
    return _normalize(PROVIDER_PROFILES[name])


class UnresolvableGraderProfile(RuntimeError):
    """Raised when no profile can be resolved for a role (fail closed)."""


def _normalize(profile: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``profile`` guaranteed to carry the minimum shape fields."""
    p = dict(profile)
    p.setdefault("command", p.get("provider_id", "unknown"))
    p.setdefault("provider_id", p["command"])
    p.setdefault("model_id", None)
    p.setdefault("prompt_via", "stdin")
    p.setdefault("availability_probe", p.get("command"))
    return p


def _argv_to_profile(argv_str: str) -> dict[str, Any]:
    parts = shlex.split(argv_str)
    return {
        "provider_id": parts[0] if parts else "unknown",
        "command": parts[0] if parts else "unknown",
        "base_args": parts[1:],
        "prompt_via": "stdin",
        "availability_probe": parts[0] if parts else None,
        "model_id": None,
    }


def _load_config_file() -> dict[str, dict[str, Any]]:
    path = os.environ.get(_CONFIG_ENV)
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_grader_profile(
    role: str | None = None,
    *,
    cli_override: str | None = None,
    profiles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve the grader provider profile for ``role`` (see module precedence).

    Pure: reads only the CLI override, env, an optional config file, and the given/static
    registry table — never the network or a DB. Raises ``UnresolvableGraderProfile``,
    naming the exact keys to set, when nothing resolves (fail closed).
    """
    # 0. headless/CI stub override (DS_GRADER_STUB) — must dominate so verify + the
    # conformance suite run with no vendor CLI present (CI, or any host without it).
    stub = os.environ.get(_STUB_ENV)
    if stub:
        return _normalize(
            {
                "provider_id": "stub",
                "command": sys.executable,
                "base_args": [stub],
                "prompt_via": "stdin",
                "availability_probe": stub,
                "is_stub": True,
            }
        )

    # 1. explicit CLI flag
    if cli_override:
        return _normalize(_argv_to_profile(cli_override))

    # 2. per-role env override
    if role:
        env = os.environ.get(_ROLE_ENV_PREFIX + role.upper())
        if env:
            return _normalize(_argv_to_profile(env))

    # 3. config file (per-role, then default)
    cfg = _load_config_file()
    if role and role in cfg:
        return _normalize(cfg[role])
    if "default" in cfg:
        return _normalize(cfg["default"])

    # 4. built-in registry table (per-role, then default)
    table = profiles if profiles is not None else _DEFAULT_PROFILES
    if role and role in table:
        return _normalize(table[role])
    if "default" in table:
        return _normalize(table["default"])

    # 5. fail closed — name the exact keys
    role_key = (role or "ROLE").upper()
    raise UnresolvableGraderProfile(
        f"No grader provider profile resolved for role {role!r}. Set one of (highest "
        f"precedence first): the --grader-profile CLI flag; the env var "
        f"{_ROLE_ENV_PREFIX}{role_key}; a '{role}' or 'default' entry in the config file "
        f"named by {_CONFIG_ENV}; or a registry default in config/grader_profiles.py."
    )


def describe_grader_selection(
    *, cli_override: str | None = None, roles: tuple[str, ...] = GRADER_ROLES
) -> dict[str, dict[str, Any]]:
    """Return, for each grader role, the provider that will grade it under the current
    env + config — so an operator can inspect the mapping BEFORE running verify.

    Never raises: an unresolvable role is reported as ``{"error": <message>}`` rather than
    aborting the whole mapping.
    """
    mapping: dict[str, dict[str, Any]] = {}
    for role in roles:
        try:
            profile = resolve_grader_profile(role, cli_override=cli_override)
            mapping[role] = {
                "provider_id": profile["provider_id"],
                "command": profile["command"],
                "model_id": profile.get("model_id"),
            }
        except UnresolvableGraderProfile as exc:
            mapping[role] = {"error": str(exc)}
    return mapping
