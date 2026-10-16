"""A client that only reads gets its own named token, never the root token.

The contract tells every connecting client to use `ds mcp client add`, but a client
with no capability could not be created (`--capabilities` was required and an empty
list refused), so a read-only gateway was pushed onto the root token the doc forbids.
And a refused `client add` printed `ok: false` and exited 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _ds(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env.update({"DREAM_STUDIO_HOME": str(home), "PYTHONPATH": str(REPO)})
    return subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(home), "mcp", "client", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )


def _json(proc: subprocess.CompletedProcess) -> dict:
    out = proc.stdout + proc.stderr
    start, end = out.index("{"), out.rindex("}") + 1
    return json.loads(out[start:end])


def test_a_read_only_client_is_issued_its_own_token(tmp_path):
    from integrations.mcp import auth

    proc = _ds(tmp_path, "add", "gateway", "--read-only")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = _json(proc)
    assert report["ok"] and report["capabilities"] == []
    identity = auth.authenticate(f"Bearer {report['token']}", dream_studio_home=tmp_path)
    assert identity is not None and identity.name == "gateway"
    assert identity.capabilities == frozenset(), "a read-only client holds no capability"


def test_a_refused_client_add_exits_non_zero(tmp_path):
    assert _ds(tmp_path, "add", "x", "--capabilities", "not:a:capability").returncode != 0
    assert _ds(tmp_path, "add", "x", "--capabilities", "").returncode != 0
    assert _ds(tmp_path, "revoke", "nobody").returncode != 0
