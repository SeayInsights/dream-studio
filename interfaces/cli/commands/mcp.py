"""ds mcp command group — serve the MCP tool projection, manage its bearer token."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from interfaces.cli.cli_utils import _print

SAFE_DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``mcp`` subparser tree to *subcommands*."""
    mcp_cmd = subcommands.add_parser(
        "mcp", help="MCP server: expose a curated, read-only Dream Studio tool surface"
    )
    mcp_sub = mcp_cmd.add_subparsers(dest="mcp_command", required=True)

    serve_cmd = mcp_sub.add_parser("serve", help="Start the MCP server (Streamable HTTP)")
    serve_cmd.add_argument(
        "--host",
        default=SAFE_DEFAULT_HOST,
        help=f"Bind address (default {SAFE_DEFAULT_HOST}; pass 0.0.0.0 explicitly to expose "
        "beyond localhost)",
    )
    serve_cmd.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Default {DEFAULT_PORT}")

    token_cmd = mcp_sub.add_parser("token", help="Show or rotate the MCP bearer token")
    token_cmd.add_argument(
        "--rotate", action="store_true", help="Generate a new token, invalidating the old one"
    )


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Dispatch ds mcp {serve,token} commands."""
    del source_root  # tools resolve their own REPO_ROOT; kept for signature parity

    if args.mcp_command == "token":
        from integrations.mcp import auth

        if args.rotate:
            token = auth.rotate_token(dream_studio_home=dream_studio_home)
            return _print({"ok": True, "rotated": True, "token": token})
        token, created = auth.ensure_token(dream_studio_home=dream_studio_home)
        return _print({"ok": True, "created": created, "token": token})

    if args.mcp_command == "serve":
        import uvicorn

        from integrations.mcp import auth
        from integrations.mcp.app import build_app

        _token, created = auth.ensure_token(dream_studio_home=dream_studio_home)
        if created:
            print(
                "Generated a new MCP bearer token. Run `ds mcp token` on this machine to "
                "read it -- it is never printed by `serve` itself, since a long-running "
                "server's stderr commonly ends up captured in a log (systemd, docker logs, "
                "CI). Clients need `Authorization: Bearer <token>`.",
                file=sys.stderr,
            )
        else:
            print(
                "Dream Studio MCP server. Run `ds mcp token` to read the bearer token "
                "clients need to send as `Authorization: Bearer <token>`.",
                file=sys.stderr,
            )
        if args.host == "0.0.0.0":
            print(
                "[mcp] WARNING: binding to 0.0.0.0 exposes this server to all network "
                "interfaces. Every request still requires the bearer token, but treat this "
                "host like any other network-facing service.",
                file=sys.stderr,
            )
        app = build_app(dream_studio_home=dream_studio_home)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    return 1
