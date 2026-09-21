"""Skill model tier resolution, with one documented precedence chain.

WHY THIS EXISTS. 52 mode cards declare ``model_preference`` and nothing read it. The only
reader, ``core.skills.queries.list_skills``, took ``model_tier`` from the mode's
``config.yml`` and fell back to the literal ``"sonnet"``, so a card's declared tier was
inert. Measured 2026-09-18: 34 modes declare a tier in both places and **11 of them
disagree** (core:think says opus in config.yml and sonnet on its card); 18 more declare a
tier only on the card and were silently resolving to sonnet regardless.

``config/grader_profiles.py`` already solved this shape for grader roles -- an explicit
precedence chain, documented in one place, inspectable. That pattern was confined to
grading. This is the same chain for skill modes.

PRECEDENCE, highest first:

  1. ``DS_SKILL_MODEL_STUB`` -- pins every mode to one tier. For headless and CI runs, where
     a matrix should not fan out across tiers. Mirrors ``DS_GRADER_STUB``.
  2. an explicit ``override`` argument (a caller that already knows what it wants)
  3. the per-mode env var ``DS_SKILL_MODEL_<PACK>_<MODE>`` (non-alphanumerics become
     underscores, so quality:pr-security-scan reads DS_SKILL_MODEL_QUALITY_PR_SECURITY_SCAN)
  4. a per-specifier or ``default`` entry in the JSON file at ``DS_SKILL_MODEL_CONFIG``
  5. the mode's ``config.yml`` ``model_tier``
  6. the card's ``model_preference``
  7. ``sonnet``

Levels 5 and 6 are in that order deliberately. config.yml is what resolution reads today, so
putting the card above it would silently re-tier the 11 modes that disagree -- core:think
would drop from opus to sonnet, which is a downgrade nobody asked for. Keeping config.yml
first leaves all 34 of those modes resolving exactly as they do now, and gives the card a
job for the 18 modes that have nothing else. One mode's resolved tier changes as a result:
website:critique moves from the hardcoded sonnet to the opus its card asks for.

UNLIKE grader_profiles, this resolves rather than failing closed. A grader role with no
provider cannot run at all, so refusing is the only honest answer; a mode with no declared
tier has a sane default. What it does refuse is a tier value it does not recognise, from any
source -- that is a typo in an override or a card, and silently swallowing it would put the
mode on a tier nobody chose.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

#: Tiers a mode may resolve to, cheapest first. Mirrors the card schema's enum.
SKILL_MODEL_TIERS: tuple[str, ...] = ("haiku", "sonnet", "opus")

DEFAULT_TIER = "sonnet"

_STUB_ENV = "DS_SKILL_MODEL_STUB"
_MODE_ENV_PREFIX = "DS_SKILL_MODEL_"
_CONFIG_ENV = "DS_SKILL_MODEL_CONFIG"

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


class UnknownSkillModelTier(ValueError):
    """A tier value came from somewhere that is not one of SKILL_MODEL_TIERS."""


def mode_env_var(specifier: str) -> str:
    """The per-mode override variable name for ``pack:mode``.

    ``quality:pr-security-scan`` -> ``DS_SKILL_MODEL_QUALITY_PR_SECURITY_SCAN``.
    """
    normalized = _NON_ALNUM.sub("_", specifier.upper()).strip("_")
    return _MODE_ENV_PREFIX + normalized


def _checked(value: Any, source: str, key: str) -> str:
    text = str(value).strip()
    if text not in SKILL_MODEL_TIERS:
        raise UnknownSkillModelTier(
            f"{source} set the tier to {text!r} for {key}; expected one of "
            f"{', '.join(SKILL_MODEL_TIERS)}"
        )
    return text


def _from_config_file(specifier: str) -> tuple[str, str] | None:
    path_str = os.environ.get(_CONFIG_ENV)
    if not path_str:
        return None
    try:
        data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in (specifier, "default"):
        if key in data:
            return _checked(data[key], f"{_CONFIG_ENV}[{key}]", specifier), f"config-file:{key}"
    return None


def resolve_skill_model(
    specifier: str,
    *,
    card_preference: str | None = None,
    config_tier: str | None = None,
    override: str | None = None,
) -> dict[str, str]:
    """Resolve the model tier for ``pack:mode``, and say which level decided it.

    The ``source`` is returned so an operator can see why a mode landed on a tier instead of
    guessing which of six places won.
    """
    stub = os.environ.get(_STUB_ENV)
    if stub:
        return {"tier": _checked(stub, _STUB_ENV, specifier), "source": "stub-env"}

    if override:
        return {"tier": _checked(override, "override", specifier), "source": "override"}

    env_name = mode_env_var(specifier)
    from_env = os.environ.get(env_name)
    if from_env:
        return {"tier": _checked(from_env, env_name, specifier), "source": f"env:{env_name}"}

    from_file = _from_config_file(specifier)
    if from_file:
        return {"tier": from_file[0], "source": from_file[1]}

    if config_tier:
        return {
            "tier": _checked(config_tier, "config.yml model_tier", specifier),
            "source": "config-yml",
        }

    if card_preference:
        return {
            "tier": _checked(card_preference, "card model_preference", specifier),
            "source": "card",
        }

    return {"tier": DEFAULT_TIER, "source": "default"}
