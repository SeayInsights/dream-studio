"""The MCP JSON-RPC message handler -- pure, no transport dependency.

Implements the subset of the Model Context Protocol a tools-only server needs:
`initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`. No
resources, prompts, or sampling -- this server has nothing to offer there yet, and
claiming those capabilities would be advertising a surface with nothing behind it.

Kept separate from any HTTP framework so the protocol logic is testable directly:
build a request dict, call `handle_message`, assert on the response dict. `app.py`
is the thin Streamable-HTTP transport wrapper around this.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, validators

from .auth import Identity
from .tools import TOOLS, TOOLS_BY_NAME, CallContext, Tool

PROTOCOL_VERSION = "2026-03-26"
SERVER_NAME = "dream-studio"


def _server_version() -> str:
    try:
        from core.config.paths import plugin_version

        return plugin_version()
    except Exception:
        return "0.0.0"


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _handle_initialize(request_id: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return _result(
        request_id,
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": _server_version()},
        },
    )


def _handle_tools_list(request_id: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return _result(
        request_id,
        {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.schema(),
                }
                for t in TOOLS
            ]
        },
    )


#: JSON Schema's own `integer` accepts 1.0 (and `bool` is an `int` in Python); a handler that
#: slices with `limit` or orders by `order_index` wants a real integer, which is also what
#: the advertised schema says.
_StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda _checker, value: isinstance(value, int) and not isinstance(value, bool)
    ),
)

#: How many problems one invalid-params message names -- enough to fix a call in one round
#: trip, bounded so a hostile payload cannot make the server echo megabytes back.
_MAX_REPORTED_PROBLEMS = 5
_MAX_PROBLEM_CHARS = 200

_VALIDATORS: dict[str, Any] = {}


def _validator_for(tool: Tool) -> Any:
    validator = _VALIDATORS.get(tool.name)
    if validator is None:
        validator = _VALIDATORS[tool.name] = _StrictValidator(tool.input_schema)
    return validator


def _schema_problems(tool: Tool, arguments: dict[str, Any]) -> list[str]:
    """Every way `arguments` departs from the tool's advertised input schema, or [].

    The advertised schema is the whole contract: a property it does not name, at any depth,
    a wrong type, a missing required one, a value outside an enum -- each is a problem.
    Nothing here reads the authority; a message names the property and the rule, and echoes
    a client's value only where the schema keyword itself does (a type or enum mismatch).
    """
    problems = []
    for error in sorted(_validator_for(tool).iter_errors(arguments), key=lambda e: list(e.path)):
        where = "/".join(str(part) for part in error.path) or "arguments"
        problems.append(f"{where}: {error.message}"[:_MAX_PROBLEM_CHARS])
    return problems[:_MAX_REPORTED_PROBLEMS]


def _handle_tools_call(
    request_id: Any,
    params: dict[str, Any],
    *,
    dream_studio_home: Path | None,
    identity: Identity | None = None,
) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or name not in TOOLS_BY_NAME:
        return _error(request_id, -32602, f"unknown tool: {name!r}")
    tool = TOOLS_BY_NAME[name]
    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "invalid params: arguments must be an object")
    if tool.required_capability is not None:
        # identity=None fails closed here (a direct/internal caller that never
        # authenticated), same as an identity whose capabilities don't include this
        # one. capabilities=None is the root-token sentinel -- always satisfied.
        allowed = identity is not None and (
            identity.capabilities is None or tool.required_capability in identity.capabilities
        )
        if not allowed:
            return _error(
                request_id, -32001, f"forbidden: missing capability {tool.required_capability!r}"
            )
    # After the capability check (a caller without the capability learns nothing from the
    # shape of its refusal) and before the handler. Only arguments the advertised schema
    # names get past here, so the handler's keywords are the schema's properties and
    # nothing else -- never a home, a root, a path to a database, or an identity.
    problems = _schema_problems(tool, arguments)
    if problems:
        return _error(request_id, -32602, "invalid params: " + "; ".join(problems))
    # The one place the home is bound: the server's own, passed positionally and never
    # merged with anything a client sent.
    ctx = CallContext(dream_studio_home=dream_studio_home, identity=identity)
    try:
        payload = tool.handler(ctx, **arguments)
    except Exception as exc:  # noqa: BLE001 — reported to the caller, never trusted further
        return _result(
            request_id,
            {
                "content": [
                    {"type": "text", "text": f"{type(exc).__name__}: {exc}"},
                ],
                "isError": True,
            },
        )
    return _result(
        request_id,
        {"content": [{"type": "text", "text": json.dumps(payload, default=str)}], "isError": False},
    )


def _handle_ping(request_id: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return _result(request_id, {})


_METHODS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "ping": _handle_ping,
}


def handle_message(
    message: dict[str, Any],
    *,
    dream_studio_home: Path | None = None,
    identity: Identity | None = None,
) -> dict[str, Any] | None:
    """Handle one parsed JSON-RPC message. Returns None for a notification (no id).

    `identity` is None for a direct/internal call (a test that calls `handle_message`
    without going through `app.py`'s HTTP auth): a capability-gated tool then fails
    closed rather than defaulting open.
    """
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(
            message.get("id") if isinstance(message, dict) else None, -32600, "invalid request"
        )

    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    is_notification = "id" not in message
    if method == "notifications/initialized":
        return None  # acknowledged implicitly; nothing to send back
    if is_notification:
        return None  # any other notification: no response is ever sent

    if method == "tools/call":
        return _handle_tools_call(
            request_id, params, dream_studio_home=dream_studio_home, identity=identity
        )
    handler = _METHODS.get(method)
    if handler is None:
        return _error(request_id, -32601, f"method not found: {method!r}")
    return handler(request_id, params)
