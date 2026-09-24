"""Bearer-token auth for the MCP server.

WHY A TOKEN AT ALL. This server is meant to be reachable by a process that is not
this machine's own terminal (Fulcrum, a gateway) -- the CORS-and-localhost "safety"
the dashboard API relies on (projections/api/safety.py) assumes a browser on the same
machine, which does not hold once the bind address leaves 127.0.0.1. Every tool here
is read-only, but the SQLite authority it reads can carry private project detail
(secrets/auth paths excepted per the adapter-projection boundary), so a network-facing
listener still needs real credential auth, not just a network-topology assumption.

WHERE THE TOKEN LIVES. `~/.dream-studio/state/mcp-token.json`, alongside the other
state-tier files (state.py's config.json is a sibling). Generated on first use,
never logged, never returned by any tool -- only `ds mcp token` prints it, and only
on the operator's own terminal.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

TOKEN_FILENAME = "mcp-token.json"
SCHEMA_VERSION = 1


def _token_path(dream_studio_home: Path | None = None) -> Path:
    from core.config.paths import home_dir

    home = dream_studio_home or home_dir()
    return home / "state" / TOKEN_FILENAME


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # best-effort on platforms without POSIX permission bits
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def read_token(dream_studio_home: Path | None = None) -> str | None:
    """Return the current token, or None if one has never been generated."""
    path = _token_path(dream_studio_home)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    token = doc.get("token")
    return token if isinstance(token, str) and token else None


def ensure_token(dream_studio_home: Path | None = None) -> tuple[str, bool]:
    """Return (token, created). Generates and persists one on first call."""
    existing = read_token(dream_studio_home)
    if existing:
        return existing, False
    token = secrets.token_urlsafe(32)
    _atomic_write(
        _token_path(dream_studio_home),
        {"schema_version": SCHEMA_VERSION, "token": token},
    )
    return token, True


def rotate_token(dream_studio_home: Path | None = None) -> str:
    """Generate a fresh token unconditionally, invalidating the old one."""
    token = secrets.token_urlsafe(32)
    _atomic_write(
        _token_path(dream_studio_home),
        {"schema_version": SCHEMA_VERSION, "token": token},
    )
    return token


def verify_bearer(header_value: str | None, *, dream_studio_home: Path | None = None) -> bool:
    """Constant-time check of an `Authorization: Bearer <token>` header value."""
    if not header_value or not header_value.startswith("Bearer "):
        return False
    presented = header_value.removeprefix("Bearer ").strip()
    expected = read_token(dream_studio_home)
    if not expected or not presented:
        return False
    return secrets.compare_digest(presented, expected)
