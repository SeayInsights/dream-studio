"""`ds mcp serve` does not default to a port other local MCP tooling uses, and the
contract tells a connecting client to use a named, scoped credential.

It defaulted to 8765, which other local MCP tooling also binds: on a machine running
both, whichever started second failed to bind.
"""

from __future__ import annotations

from pathlib import Path

from interfaces.cli.ds import build_parser

COLLIDING_PORT = 8765
CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "mcp-server-contract.md"


def test_serve_defaults_to_8788_not_the_colliding_port():
    args = build_parser().parse_args(["mcp", "serve"])
    assert args.port == 8788
    assert args.port != COLLIDING_PORT
    assert args.host == "127.0.0.1"


def test_serve_port_stays_explicitly_overridable():
    assert build_parser().parse_args(["mcp", "serve", "--port", "9000"]).port == 9000


def test_a_connecting_client_is_told_to_use_a_named_scoped_client():
    text = CONTRACT.read_text(encoding="utf-8")
    start, end = text.index("## Connecting a client"), text.index("## Network exposure")
    section = text[start:end]
    assert "ds mcp client add" in section
    assert "never the root token" in section
    assert "ds mcp token" not in section
