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


def test_the_contract_lists_every_capability_gated_tool():
    """The contract called the server a read-only slice and said every tool declared
    required_capability=None, beside a paragraph about granting capabilities and a
    registry where twelve tools are gated."""
    from integrations.mcp.tools import TOOLS

    text = CONTRACT.read_text(encoding="utf-8")
    assert "read-only slice" not in text
    assert "every tool declares `required_capability=None`" not in text
    for tool in TOOLS:
        if tool.required_capability:
            assert f"`{tool.name}`" in text and f"`{tool.required_capability}`" in text, tool.name


def test_the_identity_docstring_allows_a_read_only_client():
    from integrations.mcp.auth import Identity

    assert "non-empty" not in (Identity.__doc__ or "")
