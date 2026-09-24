"""Streamable HTTP transport for the MCP server -- one POST endpoint.

A separate small FastAPI app rather than a router mounted into
projections/api/main.py: that app serves a browser-facing dashboard under a
same-machine CORS/localhost trust model (projections/api/safety.py). This one
serves a protocol endpoint to a network client (Fulcrum, a gateway) under a
bearer-token trust model. Different trust boundaries stay separate apps, the
same way `ds dashboard --serve` and this are separate commands.

Every request needs `Authorization: Bearer <token>` (see auth.py) except the
unauthenticated health check, matching the dashboard API's own `/api/health`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import auth
from .server import handle_message

MCP_PATH = "/mcp"


def build_app(*, dream_studio_home: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Dream Studio MCP Server",
        description="Read-only MCP projection over Dream Studio authority.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy", "server": "dream-studio-mcp"}

    @app.post(MCP_PATH)
    async def mcp_endpoint(request: Request):
        if not auth.verify_bearer(
            request.headers.get("authorization"), dream_studio_home=dream_studio_home
        ):
            return JSONResponse(
                status_code=401,
                content={"error": "missing or invalid bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            message = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "parse error"},
                },
            )
        response = handle_message(message, dream_studio_home=dream_studio_home)
        if response is None:
            # A notification: the transport-level answer is "accepted, no body".
            return JSONResponse(status_code=202, content=None)
        return JSONResponse(content=response)

    return app


app = build_app()
