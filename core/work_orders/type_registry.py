"""The work-order type registry: the one place a work-order type is declared.

A work-order type used to be a closed, software-shaped tuple in ``models.py`` plus four
private subsets in four modules (the artifact class a type reviews as, the UI-bearing
pair, the brief-staling triple, the verification-exempt singleton). Adding a type meant
editing all of them, and nothing a pack ships could contribute one.

This module holds, per type, exactly the facts those subsets encoded:

- ``artifact_class``: what the type delivers, so review applies standards that fit it
  (``review_rules``).
- ``ui_bearing``: the type ships a page or component, so a locked design brief is read
  at start, and its milestone owes a design audit and a CWV result at close
  (``start_brief``, ``milestones.close``, ``milestones.queries``).
- ``stales_design_brief``: closing the type means the design surface moved
  (``gates.brief_currency``). A superset of ``ui_bearing``: ``saas_feature`` spans UI and
  API, so it stales a brief without owing a CWV result.
- ``exempt_from_verification``: independent review is not run by default at close
  (``close_main``).

Registration is a Python API only. Nothing here reads a pack manifest, touches a
database, or persists: the registry is rebuilt from the built-ins on every import, so a
type registered at runtime is process-local until a loader exists to re-register it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: What a work-order type delivers. ``review_rules`` selects its review standards by these.
CODE = "code"
CONFIG = "config"
DOCUMENT = "document"
DATA = "data"

ARTIFACT_CLASSES: frozenset[str] = frozenset({CODE, CONFIG, DOCUMENT, DATA})

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: A type name is stored in a TEXT column and printed in refusals and CLI choices; a bound
#: keeps a loader from registering a paragraph.
MAX_NAME_LENGTH = 64


@dataclass(frozen=True)
class WorkOrderType:
    """One declared work-order type and the facts the platform reads off it."""

    name: str
    artifact_class: str
    ui_bearing: bool = False
    stales_design_brief: bool = False
    exempt_from_verification: bool = False


# Insertion order is the declared order: it is what ``--type``'s choices and the refusal
# message list. The built-ins below keep the alphabetical order the old tuple had.
_REGISTRY: dict[str, WorkOrderType] = {}


def register_work_order_type(
    name: str,
    *,
    artifact_class: str,
    ui_bearing: bool = False,
    stales_design_brief: bool | None = None,
    exempt_from_verification: bool = False,
) -> WorkOrderType:
    """Declare a work-order type. Refuses, always with ValueError, a duplicate, a malformed
    or overlong name, a non-bool flag, an unknown artifact class, and a UI-bearing type that
    does not stale the design brief.

    ``stales_design_brief`` defaults to ``ui_bearing``: a type that ships a surface moves
    the design surface. Pass it explicitly to declare a type that moves the surface
    without owing a CWV result (as ``saas_feature`` does).
    """
    # `type(x) is str`, not isinstance: a str subclass can override __len__ (to slip past the
    # cap below) or __eq__ and __hash__ (to pose as a member of ARTIFACT_CLASSES). The
    # API is about to be fed manifest data, and a plain str is the only thing it declares.
    if type(name) is not str or not _NAME_RE.fullmatch(name):
        raise ValueError(
            f"work-order type name {name!r} must be lowercase letters, digits and underscores,"
            " starting with a letter (a plain str, not a subclass)"
        )
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(
            f"work-order type name {name[:20]!r}... is {len(name)} characters;"
            f" it must be at most {MAX_NAME_LENGTH}"
        )
    for flag, value in (
        ("ui_bearing", ui_bearing),
        ("stales_design_brief", stales_design_brief),
        ("exempt_from_verification", exempt_from_verification),
    ):
        # `type is bool`, not isinstance or truthiness: "no" is truthy and 1 is not a flag.
        # stales_design_brief alone may be None, meaning "follow ui_bearing".
        if type(value) is not bool and not (flag == "stales_design_brief" and value is None):
            raise ValueError(f"work-order type {name!r}: {flag} must be a bool, got {value!r}")
    if name in _REGISTRY:
        raise ValueError(f"work-order type {name!r} is already registered")
    if type(artifact_class) is not str or artifact_class not in ARTIFACT_CLASSES:
        raise ValueError(
            f"work-order type {name!r} names unknown artifact class {artifact_class!r}."
            f" Known: {', '.join(sorted(ARTIFACT_CLASSES))}."
        )
    stales = ui_bearing if stales_design_brief is None else stales_design_brief
    if ui_bearing and not stales:
        raise ValueError(
            f"work-order type {name!r} is ui_bearing but does not stale the design brief;"
            " a type that ships a surface moves the design surface"
        )
    declared = WorkOrderType(
        name=name,
        artifact_class=artifact_class,
        ui_bearing=ui_bearing,
        stales_design_brief=stales,
        exempt_from_verification=exempt_from_verification,
    )
    _REGISTRY[name] = declared
    return declared


def work_order_type_names() -> tuple[str, ...]:
    """Every declared type name, in declaration order."""
    return tuple(_REGISTRY)


def get_work_order_type(name: str | None) -> WorkOrderType | None:
    """The declaration for ``name``, or None when it is not declared."""
    if not name:
        return None
    return _REGISTRY.get(name)


def artifact_class_for(name: str | None) -> str | None:
    """The artifact class ``name`` reviews as, or None when ``name`` is not declared."""
    declared = get_work_order_type(name)
    return declared.artifact_class if declared else None


def is_ui_bearing(name: str | None) -> bool:
    declared = get_work_order_type(name)
    return bool(declared and declared.ui_bearing)


def is_verification_exempt(name: str | None) -> bool:
    declared = get_work_order_type(name)
    return bool(declared and declared.exempt_from_verification)


def design_brief_staling_types() -> tuple[str, ...]:
    """The declared types whose closing means the design surface moved, sorted."""
    return tuple(sorted(t.name for t in _REGISTRY.values() if t.stales_design_brief))


# The ten built-ins, in the alphabetical order the closed tuple declared them.
register_work_order_type("api_endpoint", artifact_class=CODE)
register_work_order_type("authentication", artifact_class=CODE)
register_work_order_type("data_pipeline", artifact_class=DATA)
register_work_order_type("deployment", artifact_class=CONFIG)
register_work_order_type("documentation", artifact_class=DOCUMENT, exempt_from_verification=True)
register_work_order_type("game_mechanic", artifact_class=CODE)
register_work_order_type("infrastructure", artifact_class=CONFIG)
register_work_order_type("saas_feature", artifact_class=CODE, stales_design_brief=True)
register_work_order_type("ui_component", artifact_class=CODE, ui_bearing=True)
register_work_order_type("ui_page", artifact_class=CODE, ui_bearing=True)
