"""A tool must never expose an argument that selects WHICH authority or directory a call uses.

Issue #903: every handler took `dream_studio_home` as a real parameter and `tools/call` let a
client's argument of that name replace the server's own binding. The fix binds the home once
(`CallContext`, passed positionally) and enforces each tool's advertised schema before its
handler is reached. This guard keeps it that way as the registry grows, from three sides:

- the advertised `inputSchema` may not name an authority-selecting property, at any depth,
- the handler's signature must be `(ctx, /, *, <exactly the schema's properties>)`: no
  `**kwargs`, no parameter the schema does not advertise (which is how a home or an identity
  would become client-reachable again), and
- every object in the schema is closed (`additionalProperties: false`), so what the server
  validates is what the handler can receive.

`violations()` is the checker; the last tests run it over deliberately bad tools, so a checker
that stops checking fails here rather than silently passing the real registry.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from integrations.mcp.tools import TOOLS, CallContext, Tool

#: Names that select which authority, directory, database or caller a call acts on. A tool
#: argument by any of these names is a way to point the server somewhere it was not pointed.
AUTHORITY_SELECTORS = frozenset(
    {
        "dream_studio_home",
        "home",
        "home_dir",
        "source_root",
        "repo_root",
        "project_root",
        "planning_root",
        "read_planning_dir",
        "state_dir",
        "root",
        "db_path",
        "database",
        "db",
        "sqlite_path",
        "dsn",
        "identity",
        "actor",
        "ctx",
        "client",
        "run_checks",
        "force",
        "skip_verify",
    }
)

#: Anything path-shaped is an authority selector until a reviewer says it is data. The
#: pattern is what catches the NEXT such name (`state_path`, `workspace_dir`, `config_file`)
#: that the explicit list above cannot know about.
PATH_SHAPED = re.compile(r"(home|root|_db$|^db_|sqlite|database|dir|directory|path|file)", re.I)

#: (tool, property) pairs that are DATA the server records, not a place it reads or writes
#: on the client's behalf. Each needs a reason a reviewer accepted.
DATA_PATHS = {
    ("ds_project_create", "project_path"): (
        "recorded on the project row, and used by core.projects.mutations_register to write "
        "the project's marker file; never selects the authority. See the contract's "
        "'Argument classes' section for what the server does with it."
    ),
}

SUPPORTED_KEYWORDS = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "additionalProperties",
    "description",
}


def _walk(schema: Any, path: str = ""):
    """Every (path, node) of a schema, descending into properties and items."""
    yield path, schema
    if not isinstance(schema, dict):
        return
    for key, sub in (schema.get("properties") or {}).items():
        yield from _walk(sub, f"{path}/{key}")
    if "items" in schema:
        yield from _walk(schema["items"], f"{path}[]")


def violations(tool: Tool) -> list[str]:
    found: list[str] = []
    schema = tool.input_schema

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # noqa: BLE001 - reported as a violation
        found.append(f"input_schema is not a valid JSON Schema: {exc}")

    # 1. The advertised schema, at every depth.
    for path, node in _walk(schema):
        if not isinstance(node, dict):
            found.append(f"{path or '/'}: schema node is not an object")
            continue
        for keyword in node:
            if keyword not in SUPPORTED_KEYWORDS:
                found.append(f"{path or '/'}: unsupported schema keyword {keyword!r}")
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                found.append(f"{path or '/'}: object is not closed (additionalProperties false)")
            if "properties" not in node:
                found.append(f"{path or '/'}: object names no properties")
        for name in node.get("properties") or {}:
            top_level = path == ""
            if name in AUTHORITY_SELECTORS:
                found.append(f"{path}/{name}: names an authority-selecting argument")
            elif PATH_SHAPED.search(name) and not (top_level and (tool.name, name) in DATA_PATHS):
                found.append(f"{path}/{name}: path-shaped name not accepted as data")

    # 2. The handler's own signature: (ctx, /, *, exactly the schema's properties).
    params = list(inspect.signature(tool.handler).parameters.values())
    if not params or params[0].kind is not inspect.Parameter.POSITIONAL_ONLY:
        found.append("handler's first parameter must be the positional-only call context")
        keyword_params = params
    else:
        keyword_params = params[1:]
    advertised = set((schema.get("properties") or {}))
    required = set(schema.get("required") or [])
    accepted: set[str] = set()
    for p in keyword_params:
        if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            found.append(f"handler accepts {'**' if p.kind is p.VAR_KEYWORD else '*'}{p.name}")
            continue
        if p.kind is not inspect.Parameter.KEYWORD_ONLY:
            found.append(f"handler parameter {p.name!r} is not keyword-only")
        accepted.add(p.name)
        if p.name in AUTHORITY_SELECTORS:
            found.append(f"handler parameter {p.name!r} selects the authority")
        elif PATH_SHAPED.search(p.name) and (tool.name, p.name) not in DATA_PATHS:
            found.append(f"handler parameter {p.name!r} is path-shaped and not accepted as data")
        if p.name not in advertised:
            found.append(f"handler parameter {p.name!r} is not in the advertised inputSchema")
        if (p.default is inspect.Parameter.empty) != (p.name in required):
            found.append(f"handler parameter {p.name!r}: required-ness differs from the schema")
    for name in sorted(advertised - accepted):
        found.append(f"inputSchema advertises {name!r} but the handler takes no such parameter")
    for name in sorted(required - advertised):
        found.append(f"inputSchema requires {name!r} which it does not define")
    return found


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_no_tool_exposes_an_authority_selecting_argument(tool):
    assert violations(tool) == []


def test_the_registry_is_not_empty_and_names_are_unique():
    assert len(TOOLS) >= 20
    assert len({t.name for t in TOOLS}) == len(TOOLS)


def test_every_data_path_exception_names_a_tool_and_property_that_exist():
    """A stale allow-list entry would quietly keep an exemption for something removed."""
    by_name = {t.name: t for t in TOOLS}
    for tool_name, prop in DATA_PATHS:
        assert tool_name in by_name, f"{tool_name} no longer exists"
        assert prop in by_name[tool_name].input_schema["properties"], f"{tool_name}.{prop} is gone"


# ── the checker itself, over tools that must be caught ──────────────────────


def _tool(handler, properties=None, required=(), **schema_extra) -> Tool:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties if properties is not None else {"x": {"type": "string"}},
        "required": list(required),
    }
    schema.update(schema_extra)
    return Tool(name="ds_probe", description="probe", input_schema=schema, handler=handler)


def _good(ctx: CallContext, /, *, x: str) -> Any:  # a tool that must pass
    return {"x": x}


def test_the_checker_passes_a_well_formed_tool():
    assert violations(_tool(_good, required=("x",))) == []


@pytest.mark.parametrize(
    ("label", "tool", "fragment"),
    [
        (
            "home_added_to_the_handler",
            _tool(lambda ctx, /, *, x, dream_studio_home=None: 0, required=("x",)),
            "dream_studio_home",
        ),
        (
            "home_added_to_the_schema",
            _tool(
                lambda ctx, /, *, x, dream_studio_home=None: 0,
                {"x": {"type": "string"}, "dream_studio_home": {"type": "string"}},
                ("x",),
            ),
            "authority-selecting",
        ),
        (
            "unadvertised_handler_parameter",
            _tool(lambda ctx, /, *, x, flavour="a": 0, required=("x",)),
            "not in the advertised",
        ),
        ("var_keyword", _tool(lambda ctx, /, **kwargs: 0, {}), "**kwargs"),
        ("var_positional", _tool(lambda ctx, /, *args, x: 0, required=("x",)), "*args"),
        (
            "no_context_parameter",
            _tool(lambda *, x: 0, required=("x",)),
            "positional-only call context",
        ),
        (
            "context_not_positional_only",
            _tool(lambda ctx, *, x: 0, required=("x",)),
            "positional-only call context",
        ),
        (
            "positional_or_keyword_parameter",
            _tool(lambda ctx, /, x: 0, required=("x",)),
            "not keyword-only",
        ),
        (
            "schema_property_the_handler_lacks",
            _tool(lambda ctx, /: 0, {"x": {"type": "string"}}),
            "takes no such parameter",
        ),
        (
            "path_shaped_name_nobody_reviewed",
            _tool(
                lambda ctx, /, *, workspace_dir: 0,
                {"workspace_dir": {"type": "string"}},
                ("workspace_dir",),
            ),
            "path-shaped",
        ),
        (
            "path_shaped_by_a_new_unreviewed_tool_sharing_project_path",
            _tool(
                lambda ctx, /, *, project_path: 0,
                {"project_path": {"type": "string"}},
                ("project_path",),
            ),
            "path-shaped",
        ),
        (
            "identity_as_an_argument",
            _tool(lambda ctx, /, *, identity: 0, {"identity": {"type": "string"}}, ("identity",)),
            "identity",
        ),
        (
            "open_top_level_object",
            _tool(_good, required=("x",), additionalProperties=True),
            "not closed",
        ),
        (
            "open_nested_object",
            _tool(
                lambda ctx, /, *, x: 0,
                {"x": {"type": "object", "properties": {"a": {"type": "string"}}}},
                ("x",),
            ),
            "not closed",
        ),
        (
            "authority_name_nested_in_an_array_item",
            _tool(
                lambda ctx, /, *, x: 0,
                {
                    "x": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"db_path": {"type": "string"}},
                        },
                    }
                },
                ("x",),
            ),
            "db_path",
        ),
        (
            "keyword_that_reopens_an_object",
            _tool(_good, required=("x",), patternProperties={".*": {}}),
            "unsupported schema keyword",
        ),
        (
            "required_differs_from_the_default",
            _tool(lambda ctx, /, *, x="a": 0, required=("x",)),
            "required-ness",
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_the_checker_catches_a_tool_that_breaks_the_rule(label, tool, fragment):
    found = violations(tool)
    assert found, f"{label}: the checker found nothing wrong"
    assert any(fragment in line for line in found), f"{label}: {found}"
