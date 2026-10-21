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
- ``dashboard_truth_gated``: closing the type is held to the live-authority dashboard
  invariants (``close_main``).
- ``description`` and ``order``: the sentence on when to use the type and the position it
  takes in a presentation, which the generated operator AGENTS.md renders.

WHERE A PACK'S TYPES COME FROM. A pack declares them in ``packs.yaml`` under
``contributes.work_order_types`` and ``type_manifest.load_pack_work_order_types`` registers
them. Nothing persists a registration: it is process-local, rebuilt from the built-ins and the
manifest of the running checkout or installed app in every process.

The manifest is read lazily, by ``ensure_loaded``, which every accessor and
``register_work_order_type`` calls first. That is the call site, and it is chosen over three
alternatives on purpose:

- Not at import. An import that reads a file and mutates a global makes the answer depend on
  import order and on the working directory of whoever imported first, and a failing manifest
  would break unrelated imports. The built-ins are constants and are registered at import; the
  manifest is not.
- Not by a loader every entry point must remember to call. The CLI, the MCP server, the
  hooks and the tests each read the registry; one that forgot would see only the built-ins
  and refuse a pack's type as undeclared. Here the first read does it.
- Not a write to the database. A row holds a snapshot; the manifest is the declaration.

``ensure_loaded`` is idempotent, thread-safe, and raises ``PackManifestError`` (naming the
file and the pack) when the manifest cannot be read or declares something invalid, on every
call until it is fixed: a registry that silently fell back to the built-ins would refuse the
pack's type as "not declared" with no hint that a manifest was the cause.

A type declared by a manifest that is later removed is simply undeclared again. Work orders
of that type stay readable (nothing on the read path asks the registry), and close treats them
as an undeclared type (strictest default: independent review required, reviewed as code);
start refuses them with a message that says why.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

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

#: A description is one row of a markdown table in the generated AGENTS.md.
MAX_DESCRIPTION_LENGTH = 200

#: Names core itself writes into ``business_work_orders.work_order_type`` without going through
#: the declared set, or has written, and so cannot be declared by anything else. A name here is
#: not a declared type (``create_work_order`` still refuses it); it is a name nobody else may
#: take, because declaring it would retroactively change how EXISTING work orders of that type
#: are reviewed and closed: a pack declaring ``cleanup`` as an exempt document type would turn
#: every spawned cleanup work order into one that closes with no independent review.
#:
#: DERIVED, not remembered: ``cleanup`` is what core's writers file (``verify_gaps`` spawns gap
#: work orders as cleanup and reads that default back; ``ds prove`` formats it into the review
#: prompts, whose schema also lists it), found by a scan of production code that
#: ``tests/unit/test_work_order_type_names_core_writes.py`` re-runs and fails on if a writer
#: files a name that is neither built in nor listed here. The other three are values live
#: authorities hold from earlier versions, which no scan of today's code can find: they are
#: listed from a census of a real authority's distinct ``work_order_type`` values (UNVERIFIED
#: from this repository, which holds no authority) and cannot be re-derived, only extended.
RESERVED_WORK_ORDER_TYPES: dict[str, str] = {
    "cleanup": (
        "core files it: verify_gaps spawns gap work orders as cleanup (and defaults a gap"
        " with no type to it), and the review prompts list it; live authorities hold many"
    ),
    "migration": "held by live authorities from earlier versions of the work-order surface",
    "investigation": "held by live authorities from earlier versions of the work-order surface",
    "chore": "held by live authorities from earlier versions of the work-order surface",
}

#: Longest fragment of a caller-supplied value an error message will quote. A manifest is data
#: from outside this process, and a message that repr()s it whole is a way to make this process
#: build a huge string.
_QUOTE_LIMIT = 40


def quote(value: object) -> str:
    """A bounded, safe rendering of a caller-supplied value for an error message.

    A string is quoted up to ``_QUOTE_LIMIT`` characters; anything else is named by its type
    only, never ``repr()``-ed, so a nested or self-multiplying structure costs nothing.
    """
    if isinstance(value, str):
        shown = value[:_QUOTE_LIMIT]
        return repr(shown) + ("..." if len(value) > _QUOTE_LIMIT else "")
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)[:_QUOTE_LIMIT]
    return f"<{type(value).__name__}>"


@dataclass(frozen=True)
class WorkOrderType:
    """One declared work-order type and the facts the platform reads off it."""

    name: str
    artifact_class: str
    ui_bearing: bool = False
    stales_design_brief: bool = False
    exempt_from_verification: bool = False
    dashboard_truth_gated: bool = False
    description: str = ""
    #: Position in a presentation (the generated AGENTS.md table), ascending.
    order: int = 0
    #: The pack key whose manifest declared this type; None for a built-in or an API call.
    declared_by: str | None = None

    @property
    def label(self) -> str:
        """A human label derived from the name, for a type that has no seeded row to carry one."""
        return self.name.replace("_", " ").title()


class PackManifestError(ValueError):
    """A pack manifest could not be read or declares something the registry refuses.

    A ValueError, like every refusal the registry itself makes, so a caller catches one thing.
    """


# Insertion order is the declared order: it is what ``--type``'s choices and the refusal
# message list. The built-ins below keep the alphabetical order the old tuple had.
_REGISTRY: dict[str, WorkOrderType] = {}

#: The built-in names, in declaration order. Filled once, below, and never changed.
_BUILTIN_NAMES: list[str] = []
_BUILTIN: dict[str, WorkOrderType] = {}

#: Process-local: has the running checkout's manifest been applied, and is a load in progress
#: (so the registrations the loader itself makes do not recurse into ensure_loaded).
_STATE: dict[str, object] = {"loaded": False, "loading": False}
_LOCK = threading.RLock()


def _build(
    name: object,
    *,
    artifact_class: object,
    ui_bearing: object = False,
    stales_design_brief: object = None,
    exempt_from_verification: object = False,
    dashboard_truth_gated: object = False,
    description: object = "",
    order: object = None,
    declared_by: str | None = None,
) -> WorkOrderType:
    """Validate one declaration and return it, touching no registry state.

    Every refusal is a ValueError. See ``register_work_order_type`` for the rules.
    """
    # `type(x) is str`, not isinstance: a str subclass can override __len__ (to slip past the
    # cap below) or __eq__ and __hash__ (to pose as a member of ARTIFACT_CLASSES). The
    # API is fed manifest data, and a plain str is the only thing it declares.
    if type(name) is not str or not _NAME_RE.fullmatch(name):
        raise ValueError(
            f"work-order type name {quote(name)} must be lowercase letters, digits and underscores,"
            " starting with a letter (a plain str, not a subclass)"
        )
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(
            f"work-order type name {name[:20]!r}... is {len(name)} characters;"
            f" it must be at most {MAX_NAME_LENGTH}"
        )
    if name in RESERVED_WORK_ORDER_TYPES:
        raise ValueError(
            f"work-order type name {name!r} is reserved: {RESERVED_WORK_ORDER_TYPES[name]}."
            " Declaring it would change how existing work orders of that type are reviewed"
            " and closed."
        )
    flags = {
        "ui_bearing": ui_bearing,
        "stales_design_brief": stales_design_brief,
        "exempt_from_verification": exempt_from_verification,
        "dashboard_truth_gated": dashboard_truth_gated,
    }
    for flag, value in flags.items():
        # `type is bool`, not isinstance or truthiness: "no" is truthy and 1 is not a flag.
        # stales_design_brief alone may be None, meaning "follow ui_bearing".
        if type(value) is not bool and not (flag == "stales_design_brief" and value is None):
            raise ValueError(f"work-order type {name!r}: {flag} must be a bool, got {quote(value)}")
    if type(artifact_class) is not str or artifact_class not in ARTIFACT_CLASSES:
        raise ValueError(
            f"work-order type {name!r} names unknown artifact class {quote(artifact_class)}."
            f" Known: {', '.join(sorted(ARTIFACT_CLASSES))}."
        )
    if type(description) is not str:
        raise ValueError(
            f"work-order type {name!r}: description must be a string, got {quote(description)}"
        )
    if (
        len(description) > MAX_DESCRIPTION_LENGTH
        or "\n" in description
        or "\r" in description
        or "|" in description
    ):
        raise ValueError(
            f"work-order type {name!r}: description must be one line of at most"
            f" {MAX_DESCRIPTION_LENGTH} characters with no '|' (it is a table row)"
        )
    if order is not None and (type(order) is not int or order < 0):
        raise ValueError(
            f"work-order type {name!r}: order must be a non-negative integer, got {quote(order)}"
        )
    stales = ui_bearing if stales_design_brief is None else stales_design_brief
    if ui_bearing and not stales:
        raise ValueError(
            f"work-order type {name!r} is ui_bearing but does not stale the design brief;"
            " a type that ships a surface moves the design surface"
        )
    return WorkOrderType(
        name=name,
        artifact_class=artifact_class,
        ui_bearing=bool(ui_bearing),
        stales_design_brief=bool(stales),
        exempt_from_verification=bool(exempt_from_verification),
        dashboard_truth_gated=bool(dashboard_truth_gated),
        description=description,
        # Placeholder; _store assigns the next position when none was given.
        order=-1 if order is None else order,
        declared_by=declared_by,
    )


def _store(declared: WorkOrderType) -> WorkOrderType:
    """Add a validated declaration. A type with no explicit order goes after every other."""
    if declared.name in _REGISTRY:
        raise ValueError(f"work-order type {declared.name!r} is already registered")
    if declared.order < 0:
        last = max((t.order for t in _REGISTRY.values()), default=0)
        declared = replace(declared, order=last + 10)
    _REGISTRY[declared.name] = declared
    return declared


def register_work_order_type(
    name: str,
    *,
    artifact_class: str,
    ui_bearing: bool = False,
    stales_design_brief: bool | None = None,
    exempt_from_verification: bool = False,
    dashboard_truth_gated: bool = False,
    description: str = "",
    order: int | None = None,
    declared_by: str | None = None,
) -> WorkOrderType:
    """Declare a work-order type. Refuses, always with ValueError, a duplicate, a malformed
    or overlong name, a non-bool flag, an unknown artifact class, a bad description or order,
    and a UI-bearing type that does not stale the design brief.

    ``stales_design_brief`` defaults to ``ui_bearing``: a type that ships a surface moves
    the design surface. Pass it explicitly to declare a type that moves the surface
    without owing a CWV result (as ``saas_feature`` does).

    ``order`` defaults to after every type already declared. The manifest is applied first, so
    a name a pack declared is a duplicate here whichever call came first.
    """
    ensure_loaded()
    with _LOCK:
        return _store(
            _build(
                name,
                artifact_class=artifact_class,
                ui_bearing=ui_bearing,
                stales_design_brief=stales_design_brief,
                exempt_from_verification=exempt_from_verification,
                dashboard_truth_gated=dashboard_truth_gated,
                description=description,
                order=order,
                declared_by=declared_by,
            )
        )


def ensure_loaded() -> None:
    """Apply the running checkout's (or installed app's) ``packs.yaml`` to the registry, once.

    Called by every accessor below and by ``register_work_order_type``; nothing else needs to
    remember to. Idempotent and thread-safe. Raises ``PackManifestError`` if the manifest is
    unreadable or invalid, on every call until it is fixed, and leaves the registry as it was.
    """
    if _STATE["loaded"]:
        return
    with _LOCK:
        if _STATE["loaded"] or _STATE["loading"]:
            return
        from .type_manifest import fingerprint, load_pack_work_order_types

        # The fingerprint is taken BEFORE the read, so an edit that lands during the load is
        # reported as a change rather than recorded as already seen.
        seen = fingerprint()
        load_pack_work_order_types()
        _STATE["loaded"] = True
        _STATE["fingerprint"] = seen


def manifest_changed_since_load() -> str | None:
    """A one-line warning if the manifest this process loaded has changed on disk, else None.

    The manifest is read once per process, so a long-lived one (``ds mcp serve``) keeps serving
    the types it loaded until it is restarted. This compares the file's size and mtime with
    what was seen at load (no read), so it is cheap enough to call on every request.
    """
    recorded = _STATE.get("fingerprint")
    if not recorded:
        return None
    from .type_manifest import fingerprint

    if fingerprint(Path(recorded[0])) == recorded:
        return None
    return (
        f"the pack manifest {recorded[0]} changed on disk after this process loaded its"
        " work-order types; restart the process to pick up the edit"
    )


@contextmanager
def loading() -> Iterator[None]:
    """Mark a manifest load in progress, so its own registrations do not recurse.

    For ``type_manifest`` only. Rolls the registry back if the load raises, so a manifest is
    applied whole or not at all.
    """
    with _LOCK:
        if _STATE["loading"]:
            yield
            return
        saved = dict(_REGISTRY)
        _STATE["loading"] = True
        try:
            yield
        except BaseException:
            _REGISTRY.clear()
            _REGISTRY.update(saved)
            raise
        finally:
            _STATE["loading"] = False


#: Who is inside a scope (thread id) and how deeply. Scopes swap the process-global registry, so
#: two of them on different threads would interleave their saves and restores and leave a
#: type registered for good; a second thread entering one is refused instead.
_SCOPE: dict[str, int | None] = {"owner": None, "depth": 0}


@contextmanager
def _one_thread_at_a_time(what: str) -> Iterator[None]:
    me = threading.get_ident()
    with _LOCK:
        if _SCOPE["owner"] not in (None, me):
            raise RuntimeError(
                f"{what}: another thread is already inside a scoped registration. Scopes swap the"
                " process-wide registry and are for single-threaded tests; two overlapping on"
                " different threads would leave a type registered permanently."
            )
        _SCOPE["owner"] = me
        _SCOPE["depth"] = (_SCOPE["depth"] or 0) + 1
    try:
        yield
    finally:
        with _LOCK:
            _SCOPE["depth"] = (_SCOPE["depth"] or 1) - 1
            if _SCOPE["depth"] == 0:
                _SCOPE["owner"] = None


@contextmanager
def scoped_registration() -> Iterator[None]:
    """Let a test register types and have them gone afterwards.

    The registry is a process-global with no public unregister, on purpose: nothing at runtime
    should be able to remove a declaration other code has already read. A test that registers
    one wraps the registering in this and the registry is exactly what it was on the way out,
    whether the block returned or raised.

    SINGLE-THREADED BY CONTRACT. The scope swaps the registry for the whole process, so a reader
    on another thread sees the scoped state while it lasts, and a second thread entering a scope
    is refused with a RuntimeError rather than interleaved.
    """
    ensure_loaded()
    with _one_thread_at_a_time("scoped_registration"):
        with _LOCK:
            saved = dict(_REGISTRY)
        try:
            yield
        finally:
            with _LOCK:
                _REGISTRY.clear()
                _REGISTRY.update(saved)


@contextmanager
def scoped_pack_manifest(
    packs_yaml_path: Path, *, trusted: frozenset[str] = frozenset()
) -> Iterator[None]:
    """Run a block against the built-ins plus ONE manifest, then restore everything.

    For tests of the loader and of a pack-declared type end to end: the real checkout's
    manifest is set aside inside the block, ``packs_yaml_path`` is applied in its place (with
    ``trusted`` as the packs the operator has allowed to declare an exemption: none, unless a
    test names them; the operator's real trust file is never read), and on the way out the registry and its loaded/unloaded state are exactly what they were.

    Single-threaded by contract, like ``scoped_registration``.
    """
    from .type_manifest import load_pack_work_order_types

    with _one_thread_at_a_time("scoped_pack_manifest"):
        with _LOCK:
            saved = dict(_REGISTRY)
            saved_state = dict(_STATE)
        try:
            with _LOCK:
                for name in [n for n in _REGISTRY if n not in _BUILTIN_NAMES]:
                    del _REGISTRY[name]
                _STATE["loaded"] = True
            load_pack_work_order_types(packs_yaml_path=packs_yaml_path, trusted=trusted)
            yield
        finally:
            with _LOCK:
                _REGISTRY.clear()
                _REGISTRY.update(saved)
                _STATE.clear()
                _STATE.update(saved_state)


def work_order_type_names() -> tuple[str, ...]:
    """Every declared type name, in declaration order."""
    ensure_loaded()
    return tuple(_REGISTRY)


def builtin_work_order_type_names() -> tuple[str, ...]:
    """The ten types the platform itself declares, in declaration order. Fixed: no manifest
    and no registration changes it. For tests and generators that mean the built-in subset."""
    return tuple(_BUILTIN_NAMES)


def builtin_work_order_types() -> tuple[WorkOrderType, ...]:
    """The ten built-in declarations, by presentation order, without loading any manifest.

    For a generator that renders a manifest it was handed (``build_agents_md``) without
    touching the process-wide registry.
    """
    return tuple(sorted((_BUILTIN[n] for n in _BUILTIN_NAMES), key=lambda t: (t.order, t.name)))


def work_order_types_in_presentation_order() -> tuple[WorkOrderType, ...]:
    """Every declared type, by ``order`` then name: the order the generated AGENTS.md lists."""
    ensure_loaded()
    return tuple(sorted(_REGISTRY.values(), key=lambda t: (t.order, t.name)))


def get_work_order_type(name: str | None) -> WorkOrderType | None:
    """The declaration for ``name``, or None when it is not declared."""
    if not name:
        return None
    ensure_loaded()
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


def is_dashboard_truth_gated(name: str | None) -> bool:
    """Closing ``name`` is held to the live-authority dashboard invariants."""
    declared = get_work_order_type(name)
    return bool(declared and declared.dashboard_truth_gated)


def design_brief_staling_types() -> tuple[str, ...]:
    """The declared types whose closing means the design surface moved, sorted."""
    ensure_loaded()
    return tuple(sorted(t.name for t in _REGISTRY.values() if t.stales_design_brief))


def _register_builtin(order: int, name: str, description: str, **facts: object) -> None:
    declared = _store(_build(name, description=description, order=order, **facts))  # type: ignore[arg-type]
    _BUILTIN_NAMES.append(name)
    _BUILTIN[name] = declared


# The ten built-ins, in the alphabetical order the closed tuple declared them. ``order`` is
# the order the generated AGENTS.md presents them in (UI first, documentation last), and the
# description is the sentence it prints.
_register_builtin(
    30,
    "api_endpoint",
    "Adding or modifying a backend route, including request/response contract",
    artifact_class=CODE,
)
_register_builtin(
    40,
    "authentication",
    "Implementing login, session management, OAuth, or token handling",
    artifact_class=CODE,
)
_register_builtin(
    60,
    "data_pipeline",
    "ETL, ingestion, transformation, or batch processing work",
    artifact_class=DATA,
    dashboard_truth_gated=True,
)
_register_builtin(
    80,
    "deployment",
    "CI/CD pipeline, containerization, infrastructure-as-code, release automation",
    artifact_class=CONFIG,
)
_register_builtin(
    100,
    "documentation",
    "Technical specs, API references, architecture decision records",
    artifact_class=DOCUMENT,
    exempt_from_verification=True,
)
_register_builtin(
    70,
    "game_mechanic",
    "A gameplay rule, interaction system, or physics behavior",
    artifact_class=CODE,
)
_register_builtin(
    90,
    "infrastructure",
    "Database schema, cloud resource provisioning, network configuration",
    artifact_class=CONFIG,
)
_register_builtin(
    50,
    "saas_feature",
    "A user-facing product capability that spans UI + API (e.g., billing)",
    artifact_class=CODE,
    stales_design_brief=True,
    dashboard_truth_gated=True,
)
_register_builtin(
    10,
    "ui_component",
    "Building a reusable UI element (button, card, modal, chart)",
    artifact_class=CODE,
    ui_bearing=True,
)
_register_builtin(
    20,
    "ui_page",
    "Building a complete screen/view with navigation and layout",
    artifact_class=CODE,
    ui_bearing=True,
)
