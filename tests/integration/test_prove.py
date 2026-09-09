"""WO-PROVE-HARNESS: `ds prove` demonstrates the four substrate guarantees against a
disposable scratch project, and — the hard constraint — never touches the operator's live
authority DB.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import pathlib
from pathlib import Path

from interfaces.cli.commands.prove import prove_main

_LIVE_DB = Path.home() / ".dream-studio" / "state" / "studio.db"


def _live_fingerprint() -> tuple[bool, str | None, int | None]:
    if not _LIVE_DB.exists():
        return (False, None, None)
    data = _LIVE_DB.read_bytes()
    return (True, hashlib.sha256(data).hexdigest(), len(data))


def test_prove_all_four_claims_pass(capsys):
    rc = prove_main(as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True, data
    assert len(data["claims"]) == 4
    titles = [c["title"] for c in data["claims"]]
    assert any("denied" in t for t in titles)
    assert any("symptom" in t for t in titles)
    assert any("blind" in t for t in titles)
    assert any("drift" in t for t in titles)
    for claim in data["claims"]:
        assert claim["passed"] is True, f"claim {claim['claim']} failed: {claim['evidence']}"
    assert rc == 0


def test_prove_points_both_resolvers_at_its_scratch_home(monkeypatch):
    """The hard constraint, asserted where a test can actually observe it.

    WHY NOT A FINGERPRINT OF THE LIVE DATABASE. tests/conftest.py sets DREAM_STUDIO_HOME and
    DREAM_STUDIO_DB_PATH to a session temp directory for the whole session, so inside pytest
    nothing reaches the live file whatever prove does -- a byte-hash or connection-recording
    test cannot fail for the real reason, and mutation confirmed it: removing prove's
    DREAM_STUDIO_DB_PATH override left such a test green.

    What it CAN check is what prove sets. Two resolvers answer "where is the authority" and
    they read different variables: core/config/paths.py::user_data_dir reads
    DREAM_STUDIO_HOME, core/config/database.py::_default_db_path reads DREAM_STUDIO_DB_PATH
    and otherwise goes straight to Path.home(). Setting only the first left 4194 live
    connections in a traced run outside pytest, from the spool ingestor -- because closing a
    work order emits events and the ingestor asks the second resolver.
    """
    from interfaces.cli.commands import prove as prove_mod

    seen: dict[str, str | None] = {}

    def _capture(scratch) -> tuple[bool, str]:
        seen["home"] = os.environ.get("DREAM_STUDIO_HOME")
        seen["db"] = os.environ.get("DREAM_STUDIO_DB_PATH")
        seen["scratch_root"] = str(pathlib.Path(scratch.root).resolve())
        return True, "captured the environment the claims run under"

    monkeypatch.setattr(prove_mod, "_CLAIMS", [("capture the environment", _capture)])
    prove_main(as_json=True)
    root = seen["scratch_root"]
    assert seen["home"], "prove ran its claims without setting DREAM_STUDIO_HOME"
    assert seen["db"], (
        "prove ran its claims without setting DREAM_STUDIO_DB_PATH -- the spool ingestor "
        "resolves its database from that variable, so events land in the operator's live "
        "authority"
    )
    assert str(pathlib.Path(seen["home"]).resolve()).startswith(root), (seen, root)
    assert str(pathlib.Path(seen["db"]).resolve()).startswith(root), (seen, root)


def test_prove_restores_the_callers_environment(monkeypatch):
    """prove runs inside sessions that set these themselves -- conftest is one -- so leaking
    a temp path out of a run would break the caller's isolation instead of protecting it."""
    from interfaces.cli.commands import prove as prove_mod

    monkeypatch.setenv("DREAM_STUDIO_HOME", "SENTINEL_HOME")
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", "SENTINEL_DB")
    monkeypatch.setattr(prove_mod, "_CLAIMS", [("noop", lambda _s: (True, "noop"))])

    prove_main(as_json=True)

    assert os.environ.get("DREAM_STUDIO_HOME") == "SENTINEL_HOME"
    assert os.environ.get("DREAM_STUDIO_DB_PATH") == "SENTINEL_DB"


def test_prove_nonzero_exit_is_wired(capsys, monkeypatch):
    """`ds prove` returns a non-zero exit code if any claim fails, so it is usable as a CI
    gate — verified by forcing one claim to fail."""
    from interfaces.cli.commands import prove as prove_mod

    def _failing_claim(_s):
        return (False, "forced failure")

    # Replace the last claim with a guaranteed failure and confirm the exit code flips.
    original = list(prove_mod._CLAIMS)
    monkeypatch.setattr(
        prove_mod, "_CLAIMS", original[:-1] + [("forced failure demo", _failing_claim)]
    )
    rc = prove_main(as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert data["ok"] is False
