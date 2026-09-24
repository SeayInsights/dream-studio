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

from .tools import TOOLS, TOOLS_BY_NAME

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
                    "inputSchema": t.input_schema,
                }
                for t in TOOLS
            ]
        },
    )


def _handle_tools_call(
    request_id: Any, params: dict[str, Any], *, dream_studio_home: Path | None
) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or name not in TOOLS_BY_NAME:
        return _error(request_id, -32602, f"unknown tool: {name!r}")
    tool = TOOLS_BY_NAME[name]
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "arguments must be an object")
    try:
        payload = tool.handler(dream_studio_home=dream_studio_home, **arguments)
    except TypeError as exc:
        # A caller sent an argument the handler's signature does not accept, or
        # omitted one it requires -- a client-input error (invalid params), not a
        # server fault. Message text is safe: TypeError from a mismatched call
        # names only the parameter, never data read from the authority.
        return _result(
            request_id,
            {"content": [{"type": "text", "text": f"invalid arguments: {exc}"}], "isError": True},
        )
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
    message: dict[str, Any], *, dream_studio_home: Path | None = None
) -> dict[str, Any] | None:
    """Handle one parsed JSON-RPC message. Returns None for a notification (no id)."""
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
        return _handle_tools_call(request_id, params, dream_studio_home=dream_studio_home)
    handler = _METHODS.get(method)
    if handler is None:
        return _error(request_id, -32601, f"method not found: {method!r}")
    return handler(request_id, params)
