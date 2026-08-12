"""WO-GRADER-PROVIDER-NEUTRAL end-to-end: the WO-verify grader path runs against a
swapped-in stub provider (DS_GRADER_STUB) and yields a real scored verdict — no vendor
CLI required. This is the behavioral proof that the verification plane is portable (and
the mechanism that lets verify run headlessly / in CI).
"""

from __future__ import annotations

from pathlib import Path

from core.work_orders.verify_graders import _run_graders_parallel
from core.work_orders.verify_shared import _MOCK_ENV

_STUB = """import sys, json
sys.stdin.read()  # consume the prompt (delivered on stdin)
print(json.dumps({
    "completion_score": 1.0,
    "correctness_score": 1.0,
    "quality_score": 1.0,
    "summary": "stub provider verdict",
}))
"""


def test_stub_provider_yields_scored_verdict(tmp_path, monkeypatch):
    stub = tmp_path / "stub_grader.py"
    stub.write_text(_STUB, encoding="utf-8")
    monkeypatch.delenv(_MOCK_ENV, raising=False)  # exercise the real spawn path, not mock mode
    monkeypatch.delenv("DS_GRADER_ARGV", raising=False)
    monkeypatch.setenv("DS_GRADER_STUB", str(stub))

    results = _run_graders_parallel(
        {
            "completion": "grade the completion",
            "correctness": "grade the correctness",
            "quality": "grade the quality",
        }
    )

    for role in ("completion", "correctness", "quality"):
        r = results[role]
        assert not r.get("unreviewable"), f"{role} should be reviewable via the stub provider"
        assert not r.get("_grader_error"), f"{role} grader errored: {r.get('_grader_error')}"
    assert results["completion"]["completion_score"] == 1.0
    assert results["correctness"]["correctness_score"] == 1.0
    assert results["quality"]["quality_score"] == 1.0
