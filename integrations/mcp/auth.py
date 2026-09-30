"""Bearer-token auth for the MCP server -- a root token plus named, capability-scoped clients.

WHY A TOKEN AT ALL. This server is meant to be reachable by a process that is not
this machine's own terminal (Fulcrum, a gateway) -- the CORS-and-localhost "safety"
the dashboard API relies on (projections/api/safety.py) assumes a browser on the same
machine, which does not hold once the bind address leaves 127.0.0.1. Every read-only
tool here (still all of them, as of this file) carries private project detail (secrets/
auth paths excepted per the adapter-projection boundary), so a network-facing listener
needs real credential auth, not just a network-topology assumption.

WHERE THE TOKEN LIVES. `~/.dream-studio/state/mcp-token.json`, alongside the other
state-tier files (state.py's config.json is a sibling). The root token is generated on
first use, never logged, never returned by any tool -- only `ds mcp token` prints it,
and only on the operator's own terminal.

WHY A SECOND, NAMED LAYER ON TOP OF THE ROOT TOKEN. The root token is the operator's
own machine-local secret -- unrestricted, equivalent to "operator at a terminal", the
same trust this server has always assumed for every tool it exposes. A tool that
MUTATES authority state (dispatching a review, running a command in its lane, recording
a verdict, closing a work order -- none of which exist in this registry yet) cannot
reuse that same undifferentiated trust: an MCP client is a specific, distinct caller
that should be nameable, revocable, and limited to exactly what it needs. `add_client`
issues a second kind of credential for exactly that -- one name, one token, one
explicit set of capabilities -- stored the same way `core.work_orders.review_answers`
already stores a review lane's per-reviewer credential: the plaintext token is shown
to the operator once, at issuance, and only its sha256 hash is ever persisted.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

TOKEN_FILENAME = "mcp-token.json"
SCHEMA_VERSION = 2

#: Reserved now, consumed by no tool yet (every tool in tools.py is still read-only,
#: required_capability=None). Provisioning a client against this set ahead of the
#: tools that will need it means adding one of those tools later needs no further CLI
#: or auth.py change -- just a new Tool(required_capability=...) entry.
KNOWN_CAPABILITIES = frozenset(
    {
        "work_order:task_mutate",
        "work_order:close",
        "review:dispatch",
        "review:run",
        "review:record",
    }
)

#: A single client granted BOTH would be, in one identity, the round table's chair
#: (record_dispatch() mints and returns every reviewer's plaintext credential to
#: whoever calls dispatch) AND a reviewer able to spend one of those credentials
#: (record_answers(), "the recording door") -- exactly the collapse
#: review_answers.py's own credential scheme exists to prevent ("a local tool without
#: an identity system cannot prove the chair did not answer as a seat"). This does not
#: stop one human operator holding two separate client tokens from manually relaying a
#: credential between them -- no local, identity-less tool can -- it stops one MCP
#: session/identity from doing both itself.
_MUTUALLY_EXCLUSIVE = ("review:dispatch", "review:record")


@dataclass(frozen=True)
class Identity:
    """Who authenticated. `capabilities=None` is the root-token sentinel: the
    operator's own token, equivalent to "operator at a terminal", always satisfies
    every capability check. A named client always carries a concrete (non-empty)
    frozenset -- see `add_client`'s refusal of an empty one."""

    name: str
    capabilities: frozenset[str] | None


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


def _read_doc(dream_studio_home: Path | None = None) -> dict[str, Any]:
    """The whole token file, as a dict -- always carrying `token` (maybe None) and
    `clients` (maybe {}), regardless of whether the file exists yet or predates the
    `clients` key (a v1 file, schema_version 1). Every mutator in this module reads
    through this and writes back through `_write_doc` so no mutator can accidentally
    drop a sibling key it doesn't itself own -- see `rotate_token`'s docstring for the
    bug this exists to prevent."""
    path = _token_path(dream_studio_home)
    doc: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                doc = loaded
        except (json.JSONDecodeError, OSError):
            doc = {}
    doc.setdefault("token", None)
    doc.setdefault("clients", {})
    return doc


def _write_doc(doc: dict[str, Any], dream_studio_home: Path | None = None) -> None:
    doc["schema_version"] = SCHEMA_VERSION
    _atomic_write(_token_path(dream_studio_home), doc)


def _credential_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------------
# The root token -- unchanged behavior, now living alongside `clients` in one file.
# --------------------------------------------------------------------------------


def read_token(dream_studio_home: Path | None = None) -> str | None:
    """Return the current root token, or None if one has never been generated."""
    token = _read_doc(dream_studio_home).get("token")
    return token if isinstance(token, str) and token else None


def ensure_token(dream_studio_home: Path | None = None) -> tuple[str, bool]:
    """Return (token, created). Generates and persists one on first call."""
    doc = _read_doc(dream_studio_home)
    existing = doc.get("token")
    if isinstance(existing, str) and existing:
        return existing, False
    token = secrets.token_urlsafe(32)
    doc["token"] = token
    _write_doc(doc, dream_studio_home)
    return token, True


def rotate_token(dream_studio_home: Path | None = None) -> str:
    """Generate a fresh root token unconditionally, invalidating the old one.

    READS THE FULL DOC FIRST. The first version of this function replaced the whole
    file with a fresh two-key dict built from nothing -- correct while the file held
    only the root token, but once `clients` moved into the same document that same
    write silently deleted every provisioned client on the next `ds mcp token
    --rotate`. Routing through `_read_doc`/`_write_doc` like every other mutator here
    keeps `clients` untouched.
    """
    doc = _read_doc(dream_studio_home)
    token = secrets.token_urlsafe(32)
    doc["token"] = token
    _write_doc(doc, dream_studio_home)
    return token


# --------------------------------------------------------------------------------
# Named, capability-scoped clients.
# --------------------------------------------------------------------------------


def _validate_capabilities(capabilities: Iterable[str]) -> frozenset[str]:
    caps = frozenset(capabilities)
    if not caps:
        raise ValueError(
            "capabilities must be non-empty -- a client that can call nothing "
            "capability-gated gets nothing a plain authenticated caller doesn't "
            "already get for free; that's a mistake, not a client"
        )
    unknown = caps - KNOWN_CAPABILITIES
    if unknown:
        raise ValueError(
            f"unknown capability(ies): {sorted(unknown)}. Known: {sorted(KNOWN_CAPABILITIES)}"
        )
    if all(cap in caps for cap in _MUTUALLY_EXCLUSIVE):
        raise ValueError(
            f"a single client cannot hold both {_MUTUALLY_EXCLUSIVE[0]!r} and "
            f"{_MUTUALLY_EXCLUSIVE[1]!r} -- that one identity would both mint every "
            "reviewer's credential (dispatch) and be able to spend one (record), "
            "collapsing the chair/reviewer separation the credential scheme exists "
            "to hold. Split these across two clients."
        )
    return caps


def add_client(
    name: str, *, capabilities: Iterable[str], dream_studio_home: Path | None = None
) -> str:
    """Issue a new named client. Returns its plaintext token -- shown once, never
    persisted, the same "generate, hash, hand back the plaintext exactly once" shape
    `core.work_orders.review_answers.record_dispatch` already uses for reviewer
    credentials."""
    if not name or not name.strip():
        raise ValueError("client name must be non-empty")
    caps = _validate_capabilities(capabilities)
    doc = _read_doc(dream_studio_home)
    if name in doc["clients"]:
        raise ValueError(f"client {name!r} already exists -- use rotate_client to reissue")
    token = secrets.token_hex(32)
    doc["clients"][name] = {
        "token_hash": _credential_hash(token),
        "capabilities": sorted(caps),
        "created_at": _now_iso(),
    }
    _write_doc(doc, dream_studio_home)
    return token


def list_clients(dream_studio_home: Path | None = None) -> dict[str, dict[str, Any]]:
    """name -> {capabilities, created_at, rotated_at?} -- never the hash."""
    clients = _read_doc(dream_studio_home)["clients"]
    return {
        name: {k: v for k, v in record.items() if k != "token_hash"}
        for name, record in clients.items()
    }


def revoke_client(name: str, dream_studio_home: Path | None = None) -> None:
    doc = _read_doc(dream_studio_home)
    if name not in doc["clients"]:
        raise ValueError(f"no such client: {name!r}")
    del doc["clients"][name]
    _write_doc(doc, dream_studio_home)


def rotate_client(name: str, dream_studio_home: Path | None = None) -> str:
    """New token, same capabilities. Returns the new plaintext token once."""
    doc = _read_doc(dream_studio_home)
    record = doc["clients"].get(name)
    if record is None:
        raise ValueError(f"no such client: {name!r}")
    token = secrets.token_hex(32)
    record["token_hash"] = _credential_hash(token)
    record["rotated_at"] = _now_iso()
    _write_doc(doc, dream_studio_home)
    return token


# --------------------------------------------------------------------------------
# Authentication.
# --------------------------------------------------------------------------------


def authenticate(
    header_value: str | None, *, dream_studio_home: Path | None = None
) -> Identity | None:
    """Constant-time check of an `Authorization: Bearer <token>` header value against
    the root token first, then every named client. Returns the matched Identity, or
    None."""
    if not header_value or not header_value.startswith("Bearer "):
        return None
    presented = header_value.removeprefix("Bearer ").strip()
    if not presented:
        return None
    doc = _read_doc(dream_studio_home)
    root = doc.get("token")
    if isinstance(root, str) and root and secrets.compare_digest(presented, root):
        return Identity(name="operator", capabilities=None)
    presented_hash = _credential_hash(presented)
    for name, record in doc["clients"].items():
        stored_hash = record.get("token_hash")
        if isinstance(stored_hash, str) and secrets.compare_digest(presented_hash, stored_hash):
            return Identity(name=name, capabilities=frozenset(record.get("capabilities", ())))
    return None
