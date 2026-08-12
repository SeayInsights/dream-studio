"""WO-PROVE-HARNESS: `ds prove` demonstrates the four substrate guarantees against a
disposable scratch project, and — the hard constraint — never touches the operator's live
authority DB.
"""

from __future__ import annotations

import hashlib
import json
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


def test_prove_does_not_touch_live_authority(capsys):
    """The hard constraint: a full `ds prove` run leaves the operator's live studio.db
    byte-for-byte unchanged (and does not create it if absent)."""
    before = _live_fingerprint()
    prove_main(as_json=True)
    capsys.readouterr()
    after = _live_fingerprint()
    assert before == after, (
        "ds prove mutated the live authority DB — scratch isolation is broken "
        f"(before={before}, after={after})"
    )


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
