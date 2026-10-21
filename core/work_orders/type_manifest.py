"""Load the work-order types a pack declares in ``packs.yaml`` into the type registry.

A pack declares them under its entry, beside ``modes`` and ``skill``::

    packs:
      legal:
        skill: legal
        modes: [review]
        contributes:
          work_order_types:
            - name: legal_review
              artifact_class: document        # code | config | document | data
              description: Reviewing a contract or policy for completeness and accuracy
              exempt_from_verification: false  # optional flags, all default false:
              ui_bearing: false                #   ui_bearing, stales_design_brief,
              stales_design_brief: false       #   exempt_from_verification,
              dashboard_truth_gated: false     #   dashboard_truth_gated

``name``, ``artifact_class`` and ``description`` are required. Every refusal is a
``PackManifestError`` that names the file, the pack and the entry, so an author knows what to
fix and where. The whole manifest is validated before anything is registered and registered
as one unit, so a manifest with one bad entry registers none of them.

THE SCHEMA IS CLOSED. An unknown key on a type, or an unknown key under ``contributes``, is an
error rather than being ignored: ``contributes.gates`` and ``contributes.finding_categories``
are named by the pack capability contract but nothing consumes them yet, and a pack that
declares one and is silently accepted would believe it had a gate.

Where this is called from, and why, is in ``type_registry``'s docstring (``ensure_loaded``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import type_registry
from .type_registry import PackManifestError, WorkOrderType

MANIFEST_NAME = "packs.yaml"

#: The ``contributes`` keys a pack may use today.
_CONTRIBUTES_KEYS = frozenset({"work_order_types"})

_REQUIRED = ("name", "artifact_class", "description")
_FLAG_KEYS = (
    "ui_bearing",
    "stales_design_brief",
    "exempt_from_verification",
    "dashboard_truth_gated",
)
_TYPE_KEYS = frozenset(_REQUIRED) | frozenset(_FLAG_KEYS)

#: The manifest schema version that introduced ``contributes``.
_MIN_SCHEMA_VERSION = 2


def default_manifest_path() -> Path:
    """The ``packs.yaml`` of the running checkout or installed app.

    ``code_root()`` is the one place the code location is resolved: the repository root in a
    checkout, the site-packages directory in an installed app, whose wheel ships ``packs.yaml``
    at the same relative path (pyproject's shipped-root-data).
    """
    from core.config.paths import code_root

    return code_root() / MANIFEST_NAME


def _read(path: Path) -> dict[str, Any]:
    import yaml

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackManifestError(
            f"cannot read the pack manifest {path}: {exc}. Work-order types a pack declares"
            " are read from it, so no type can be declared or refused correctly without it."
        ) from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackManifestError(f"the pack manifest {path} is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PackManifestError(f"the pack manifest {path} must be a mapping at the top level")
    return data


def _declarations(path: Path, data: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
    """Every (pack, index, entry) the manifest declares, after shape checks only."""
    packs = data.get("packs")
    if packs is None:
        return []
    if not isinstance(packs, dict):
        raise PackManifestError(f"{path}: 'packs' must be a mapping of pack key to its entry")
    found: list[tuple[str, int, dict[str, Any]]] = []
    for pack, entry in packs.items():
        if not isinstance(entry, dict) or "contributes" not in entry:
            continue
        where = f"{path}: pack {pack!r}"
        schema = data.get("schema_version")
        if type(schema) is not int or schema < _MIN_SCHEMA_VERSION:
            raise PackManifestError(
                f"{where} declares 'contributes', which needs schema_version"
                f" {_MIN_SCHEMA_VERSION} or later (this manifest has {schema!r})"
            )
        contributes = entry["contributes"]
        if not isinstance(contributes, dict):
            raise PackManifestError(f"{where}: 'contributes' must be a mapping")
        unknown = sorted(str(k) for k in contributes if k not in _CONTRIBUTES_KEYS)
        if unknown:
            raise PackManifestError(
                f"{where}: 'contributes' has unsupported key(s) {unknown}; today only"
                f" {sorted(_CONTRIBUTES_KEYS)} is read. Declaring one that nothing reads would"
                " look like a capability the pack does not have."
            )
        declared = contributes.get("work_order_types")
        if declared is None:
            continue
        if not isinstance(declared, list):
            raise PackManifestError(f"{where}: 'work_order_types' must be a list")
        for index, item in enumerate(declared):
            if not isinstance(item, dict):
                raise PackManifestError(
                    f"{where}: work_order_types[{index}] must be a mapping, got {item!r}"
                )
            found.append((str(pack), index, item))
    return found


def _build_one(path: Path, pack: str, index: int, item: dict[str, Any]) -> WorkOrderType:
    where = f"{path}: pack {pack!r}, work_order_types[{index}]"
    unknown = sorted(str(k) for k in item if k not in _TYPE_KEYS)
    if unknown:
        raise PackManifestError(
            f"{where} has unknown key(s) {unknown}. Known: {sorted(_TYPE_KEYS)}"
        )
    missing = [k for k in _REQUIRED if k not in item]
    if missing:
        raise PackManifestError(f"{where} is missing required key(s) {missing}")
    flags = {k: item[k] for k in _FLAG_KEYS if k in item}
    try:
        return type_registry._build(
            item["name"],
            artifact_class=item["artifact_class"],
            description=item["description"],
            declared_by=pack,
            **flags,
        )
    except ValueError as exc:
        raise PackManifestError(f"{where}: {exc}") from exc


def load_pack_work_order_types(packs_yaml_path: Path | None = None) -> tuple[WorkOrderType, ...]:
    """Register the work-order types ``packs_yaml_path`` declares; return what was registered.

    Defaults to the running checkout's or installed app's manifest. All or nothing: the whole
    manifest is validated (shape, each entry through the registry's own checks, no duplicate
    across packs, no collision with a built-in or an already registered type) before the first
    registration, and the registry is rolled back if a registration still fails. Raises
    ``PackManifestError`` naming the file, the pack and the entry.

    Registers through the registry's own store, so every type a pack declares passes exactly
    the validation ``register_work_order_type`` applies. Not idempotent by itself: loading the
    same manifest twice is a collision with itself. ``type_registry.ensure_loaded`` is the
    idempotent entry point.
    """
    path = Path(packs_yaml_path) if packs_yaml_path is not None else default_manifest_path()
    entries = _declarations(path, _read(path))
    built: list[WorkOrderType] = []
    first_pack: dict[str, str] = {}
    for pack, index, item in entries:
        declared = _build_one(path, pack, index, item)
        where = f"{path}: pack {pack!r}, work_order_types[{index}]"
        if declared.name in type_registry.builtin_work_order_type_names():
            raise PackManifestError(
                f"{where}: {declared.name!r} is a built-in work-order type and cannot be redeclared"
            )
        if declared.name in first_pack:
            raise PackManifestError(
                f"{where}: {declared.name!r} is already declared by pack"
                f" {first_pack[declared.name]!r}"
            )
        first_pack[declared.name] = pack
        built.append(declared)

    with type_registry.loading():
        registered: list[WorkOrderType] = []
        for declared in built:
            where = f"{path}: pack {declared.declared_by!r}"
            try:
                registered.append(
                    type_registry.register_work_order_type(
                        declared.name,
                        artifact_class=declared.artifact_class,
                        ui_bearing=declared.ui_bearing,
                        stales_design_brief=declared.stales_design_brief,
                        exempt_from_verification=declared.exempt_from_verification,
                        dashboard_truth_gated=declared.dashboard_truth_gated,
                        description=declared.description,
                        declared_by=declared.declared_by,
                    )
                )
            except ValueError as exc:
                raise PackManifestError(f"{where}: {exc}") from exc
    return tuple(registered)
