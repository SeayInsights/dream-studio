"""Load the work-order types a pack declares in ``packs.yaml`` into the type registry.

A pack declares them under its entry, beside ``modes`` and ``skill``::

    packs:
      legal:
        skill: legal
        modes: [review]
        contributes:
          work_order_types:
            - name: contract_review
              artifact_class: document         # code | config | document | data
              description: Reviewing a contract or policy for completeness and accuracy
              ui_bearing: false                # declared, never defaulted (see below)
              exempt_from_verification: false  # declared, never defaulted; true needs the operator
              stales_design_brief: false       # optional; defaults to ui_bearing
              dashboard_truth_gated: false     # optional; only adds a close gate

``name``, ``artifact_class``, ``description``, ``ui_bearing`` and ``exempt_from_verification``
are required. Every refusal is a ``PackManifestError`` that names the file, the pack and the
entry, so an author knows what to fix and where. The whole manifest is validated before anything
is registered and registered as one unit, so a manifest with one bad entry registers none of them.

WHAT A MANIFEST CAN AND CANNOT DO TO GOVERNANCE. A manifest is the pack's own statement about
itself, so nothing in it can be trusted to LOWER how work is reviewed:

- ``exempt_from_verification: true`` lets work close with no independent review. It is refused
  unless the OPERATOR has allowed that pack by name in ``<home>/pack-trust.yaml`` (a file in the
  operator's Dream Studio home, outside every pack, which no manifest can edit or point at).
  An environment variable was rejected: it would have to be set in every process that reads the
  registry (the CLI, the MCP server, each hook), and one that was not would silently differ.
- ``ui_bearing`` and ``exempt_from_verification`` have NO default: omitting either is an error,
  so a pack that ships a page cannot skip the milestone design audit by saying nothing. They
  are attestations the pack author owns; the contract documents what each one switches off.
- ``artifact_class`` selects which review standards apply. It cannot be checked against what a
  type actually delivers, so it is an attestation too, and the shipped manifest's governance
  profile is printed by ``ds doctor`` and pinned by a test.
- A name core already writes or has written (``type_registry.RESERVED_WORK_ORDER_TYPES``) cannot
  be declared: it would retroactively change how existing work orders of that type are reviewed.

THE MANIFEST IS UNTRUSTED INPUT TO THIS PROCESS. It is bounded (``MAX_MANIFEST_BYTES``, nesting
``MAX_NESTING``, ``MAX_TYPES``), YAML anchors and aliases are refused outright (an alias
chain multiplies a few hundred bytes into gigabytes when an error message repr()s it), nothing
caller-supplied is ever repr()-ed into a message, and any failure to read or parse it is a
``PackManifestError`` naming the file, never a raw traceback.

THE SCHEMA IS CLOSED. An unknown key on a type, or an unknown key under ``contributes``, is an
error rather than being ignored: ``contributes.gates`` and ``contributes.finding_categories``
are named by the pack capability contract but nothing consumes them yet, and a pack that
declares one and is silently accepted would believe it had a gate.

Where this is called from, and why, is in ``type_registry``'s docstring (``ensure_loaded``). A
manifest is read once per process: a long-lived process (``ds mcp serve``) must be restarted to
see an edit, and says so in its log when the file has changed on disk since it loaded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import type_registry
from .type_registry import PackManifestError, WorkOrderType, quote

MANIFEST_NAME = "packs.yaml"
TRUST_NAME = "pack-trust.yaml"

#: The shipped manifest is about 9 KB. A file this much larger is not a manifest.
MAX_MANIFEST_BYTES = 256 * 1024
MAX_TRUST_BYTES = 64 * 1024
#: Shipped depth is 4; a declared type sits at 6. Deeper than this is refused before the
#: composer (which recurses) ever sees it.
MAX_NESTING = 12
#: Across all packs. Ten built-ins; a pack declares a handful.
MAX_TYPES = 200
#: How many key names one message lists.
_MAX_KEYS_SHOWN = 8

#: The ``contributes`` keys a pack may use today.
_CONTRIBUTES_KEYS = frozenset({"work_order_types"})

#: Declared, never defaulted: each one switches governance off or on.
_REQUIRED = ("name", "artifact_class", "description", "ui_bearing", "exempt_from_verification")
_OPTIONAL = ("stales_design_brief", "dashboard_truth_gated")
_TYPE_KEYS = frozenset(_REQUIRED) | frozenset(_OPTIONAL)

#: The manifest schema version that introduced ``contributes``.
_MIN_SCHEMA_VERSION = 2

_TRUST_KEYS = frozenset({"exempt_from_verification"})


def default_manifest_path() -> Path:
    """The ``packs.yaml`` of the running checkout or installed app.

    ``code_root()`` is the one place the code location is resolved: the repository root in a
    checkout, the site-packages directory in an installed app, whose wheel ships ``packs.yaml``
    at the same relative path (pyproject's shipped-root-data).
    """
    from core.config.paths import code_root

    return code_root() / MANIFEST_NAME


def default_trust_path() -> Path:
    """The operator's pack-trust file, in the Dream Studio home. Read-only here, never created."""
    from core.config.paths import home_dir

    return home_dir() / TRUST_NAME


def _keys(mapping: dict[Any, Any]) -> str:
    shown = [quote(k) for k in list(mapping)[:_MAX_KEYS_SHOWN]]
    more = len(mapping) - len(shown)
    return "[" + ", ".join(shown) + (f", ... {more} more" if more > 0 else "") + "]"


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def _load_yaml(path: Path, *, limit: int, what: str) -> Any:
    """The parsed YAML document at ``path``, or a PackManifestError naming it.

    Bounded in size, strictly UTF-8, with anchors, aliases and deep nesting refused before the
    document is composed, and every failure of any kind turned into a PackManifestError.
    """
    import yaml

    try:
        size = path.stat().st_size
        if size > limit:
            raise PackManifestError(
                f"the {what} {path} is {size} bytes; the limit is {limit}. A file that large is"
                " not a manifest, and reading it whole is how a hostile one costs this process."
            )
        raw = path.read_bytes()
    except PackManifestError:
        raise
    except OSError as exc:
        raise PackManifestError(
            f"cannot read the {what} {path}: {_short(exc)}. Work-order types a pack declares"
            " are read from it, so no type can be declared or refused correctly without it."
        ) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackManifestError(
            f"the {what} {path} is not UTF-8 text ({_short(exc)}); it must be UTF-8"
        ) from exc
    try:
        depth = 0
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise PackManifestError(
                    f"the {what} {path} uses a YAML anchor or alias. They are refused: an alias"
                    " chain expands a few hundred bytes into gigabytes."
                )
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
                if depth > MAX_NESTING:
                    raise PackManifestError(
                        f"the {what} {path} nests deeper than {MAX_NESTING} levels"
                    )
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
        return yaml.load(text, Loader=yaml.SafeLoader)
    except PackManifestError:
        raise
    except (yaml.YAMLError, RecursionError, MemoryError, ValueError) as exc:
        raise PackManifestError(f"the {what} {path} is not valid YAML: {_short(exc)}") from exc


def _read(path: Path) -> dict[str, Any]:
    data = _load_yaml(path, limit=MAX_MANIFEST_BYTES, what="pack manifest")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PackManifestError(f"the pack manifest {path} must be a mapping at the top level")
    return data


def read_pack_trust(trust_path: Path | None = None) -> frozenset[str]:
    """The pack keys the operator has allowed ``exempt_from_verification: true`` for.

    An absent file allows none, which is the normal case. A file that is present but invalid is
    an error naming it, not an empty allow-list: the operator wrote something, and silently
    ignoring it would refuse a pack they meant to allow with a message about the pack.
    """
    path = Path(trust_path) if trust_path is not None else default_trust_path()
    if not path.exists():
        return frozenset()
    data = _load_yaml(path, limit=MAX_TRUST_BYTES, what="pack trust file")
    if data is None:
        return frozenset()
    if not isinstance(data, dict):
        raise PackManifestError(f"the pack trust file {path} must be a mapping")
    unknown = [k for k in data if k not in _TRUST_KEYS]
    if unknown:
        raise PackManifestError(
            f"the pack trust file {path} has unknown key(s) {_keys(dict.fromkeys(unknown))};"
            f" only {sorted(_TRUST_KEYS)} is read"
        )
    allowed = data.get("exempt_from_verification") or []
    if not isinstance(allowed, list) or not all(type(p) is str for p in allowed):
        raise PackManifestError(
            f"the pack trust file {path}: exempt_from_verification must be a list of pack keys"
        )
    return frozenset(allowed)


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
        where = f"{path}: pack {quote(pack)}"
        schema = data.get("schema_version")
        if type(schema) is not int or schema < _MIN_SCHEMA_VERSION:
            raise PackManifestError(
                f"{where} declares 'contributes', which needs schema_version"
                f" {_MIN_SCHEMA_VERSION} or later (this manifest has {quote(schema)})"
            )
        contributes = entry["contributes"]
        if not isinstance(contributes, dict):
            raise PackManifestError(f"{where}: 'contributes' must be a mapping")
        unknown = {k: None for k in contributes if k not in _CONTRIBUTES_KEYS}
        if unknown:
            raise PackManifestError(
                f"{where}: 'contributes' has unsupported key(s) {_keys(unknown)}; today only"
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
                    f"{where}: work_order_types[{index}] must be a mapping, got {quote(item)}"
                )
            found.append((str(pack)[:64], index, item))
            if len(found) > MAX_TYPES:
                raise PackManifestError(
                    f"{path}: more than {MAX_TYPES} work-order types declared across all packs"
                )
    return found


def _build_one(
    path: Path, pack: str, index: int, item: dict[str, Any], trusted: frozenset[str]
) -> WorkOrderType:
    where = f"{path}: pack {quote(pack)}, work_order_types[{index}]"
    unknown = {k: None for k in item if k not in _TYPE_KEYS}
    if unknown:
        raise PackManifestError(
            f"{where} has unknown key(s) {_keys(unknown)}. Known: {sorted(_TYPE_KEYS)}"
        )
    missing = [k for k in _REQUIRED if k not in item]
    if missing:
        raise PackManifestError(
            f"{where} is missing required key(s) {missing}. ui_bearing and"
            " exempt_from_verification are never defaulted: each one switches governance on or"
            " off, so the pack must say which."
        )
    if item["exempt_from_verification"] is True and pack not in trusted:
        raise PackManifestError(
            f"{where} declares exempt_from_verification: true, which lets work of this type close"
            " with no independent review. A manifest cannot grant itself that: the operator"
            f" allows it per pack in {TRUST_NAME} in the Dream Studio home"
            f" (exempt_from_verification: [{pack}])."
        )
    flags = {
        k: item[k] for k in ("ui_bearing", "exempt_from_verification", *_OPTIONAL) if k in item
    }
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


def read_pack_work_order_types(
    packs_yaml_path: Path | None = None,
    *,
    trust_path: Path | None = None,
    trusted: frozenset[str] | None = None,
) -> tuple[WorkOrderType, ...]:
    """Validate the manifest and return what it declares, registering nothing.

    The pure half of ``load_pack_work_order_types``: shape, every entry through the registry's
    own checks, the governance rules above, no duplicate across packs and no built-in collision.
    ``order`` is left unassigned (-1); the registry places each after every type already declared.

    ``trusted`` is the set of pack keys the operator allows to declare an exemption; when it is
    None the operator's trust file (``trust_path``, default ``<home>/pack-trust.yaml``) is read.
    """
    path = Path(packs_yaml_path) if packs_yaml_path is not None else default_manifest_path()
    entries = _declarations(path, _read(path))
    # Only read the operator's trust file when something needs it: a manifest that declares no
    # exemption must not fail because an unrelated trust file is malformed.
    needs_trust = any(
        isinstance(item, dict) and item.get("exempt_from_verification") is True
        for _pack, _index, item in entries
    )
    if trusted is None:
        trusted = read_pack_trust(trust_path) if needs_trust else frozenset()
    built: list[WorkOrderType] = []
    first_pack: dict[str, str] = {}
    builtin = type_registry.builtin_work_order_type_names()
    for pack, index, item in entries:
        declared = _build_one(path, pack, index, item, trusted)
        where = f"{path}: pack {quote(pack)}, work_order_types[{index}]"
        if declared.name in builtin:
            raise PackManifestError(
                f"{where}: {declared.name!r} is a built-in work-order type and cannot be redeclared"
            )
        if declared.name in first_pack:
            raise PackManifestError(
                f"{where}: {declared.name!r} is already declared by pack"
                f" {quote(first_pack[declared.name])}"
            )
        first_pack[declared.name] = pack
        built.append(declared)
    return tuple(built)


def load_pack_work_order_types(
    packs_yaml_path: Path | None = None,
    *,
    trust_path: Path | None = None,
    trusted: frozenset[str] | None = None,
) -> tuple[WorkOrderType, ...]:
    """Register the work-order types ``packs_yaml_path`` declares; return what was registered.

    Defaults to the running checkout's or installed app's manifest and the operator's trust
    file. All or nothing: the whole manifest is validated (``read_pack_work_order_types``)
    before the first registration, and the registry is rolled back if a registration still
    fails (a collision with a type registered through the API). Raises ``PackManifestError``
    naming the file, the pack and the entry.

    Registers through the registry's own store, so every type a pack declares passes exactly
    the validation ``register_work_order_type`` applies. Not idempotent by itself: loading the
    same manifest twice is a collision with itself. ``type_registry.ensure_loaded`` is the
    idempotent entry point.
    """
    path = Path(packs_yaml_path) if packs_yaml_path is not None else default_manifest_path()
    built = read_pack_work_order_types(path, trust_path=trust_path, trusted=trusted)
    with type_registry.loading():
        registered: list[WorkOrderType] = []
        for declared in built:
            where = f"{path}: pack {quote(declared.declared_by)}"
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


def fingerprint(path: Path | None = None) -> tuple[str, int, int]:
    """(path, size, mtime_ns) of the manifest; (path, -1, -1) when it cannot be statted.

    Cheap: no read. The unstattable value is a value, not None, so a manifest that vanished
    after a process loaded it compares unequal to what that process recorded.
    """
    target = Path(path) if path is not None else default_manifest_path()
    try:
        stat = target.stat()
    except OSError:
        return (str(target), -1, -1)
    return (str(target), stat.st_size, stat.st_mtime_ns)


def governance_profile(declared: WorkOrderType) -> dict[str, object]:
    """What a declared type is held to, in the terms an operator weighs a pack by.

    ``review_rules`` is how many baseline review standards its artifact class is judged against
    (8 for code against 5 for a document: declaring the lighter class lightens the review),
    and ``independent_review_at_close`` is False only for an exempt type. Printed by
    ``ds doctor`` and pinned for the shipped manifest by a test.
    """
    from .review_rules import rules_for_kind

    return {
        "type": declared.name,
        "declared_by": declared.declared_by or "(built in)",
        "artifact_class": declared.artifact_class,
        "review_rules": len(rules_for_kind(declared.artifact_class)),
        "independent_review_at_close": not declared.exempt_from_verification,
        "ui_bearing": declared.ui_bearing,
        "stales_design_brief": declared.stales_design_brief,
        "dashboard_truth_gated": declared.dashboard_truth_gated,
    }
