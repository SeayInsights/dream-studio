"""WO-VERIFY-CONFORMANCE tasks 2-3: a conformance suite any provider must pass, run
against a second provider (a swapped-in stub — the portability proof) with the result
recorded as evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.work_orders.verify_shared import (
    record_conformance_result,
    run_grader_conformance,
)

# A conformant second provider: reads the prompt on stdin, emits ONLY a grader verdict.
_CONFORMANT_STUB = """import sys, json
sys.stdin.read()
print(json.dumps({"completion_score": 1.0, "summary": "second-provider verdict", "gaps": []}))
"""

# A non-conformant provider: emits something that is not a valid grader verdict.
_BAD_STUB = """import sys
sys.stdin.read()
print("I refuse to emit JSON")
"""


def _use_stub(monkeypatch, tmp_path, body: str) -> None:
    stub = tmp_path / "provider_stub.py"
    stub.write_text(body, encoding="utf-8")
    monkeypatch.delenv("DS_GRADER_ARGV", raising=False)
    monkeypatch.setenv("DS_GRADER_STUB", str(stub))


def test_provider_passes_conformance_suite(monkeypatch, tmp_path):
    _use_stub(monkeypatch, tmp_path, _CONFORMANT_STUB)
    result = run_grader_conformance()
    assert result["passed"] is True, f"conformant provider should pass: {result['errors']}"
    assert result["verdict"]["completion_score"] == 1.0


def test_non_conformant_provider_fails_conformance(monkeypatch, tmp_path):
    _use_stub(monkeypatch, tmp_path, _BAD_STUB)
    result = run_grader_conformance()
    assert result["passed"] is False
    assert result["errors"]


def test_second_provider_result_recorded(monkeypatch, tmp_path):
    """Run the suite against the second (stub) provider and record the result as evidence."""
    _use_stub(monkeypatch, tmp_path, _CONFORMANT_STUB)
    result = run_grader_conformance()
    out = record_conformance_result(result, tmp_path / "evidence" / "second_provider.json")
    assert out.is_file()
    recorded = json.loads(out.read_text(encoding="utf-8"))
    assert recorded["passed"] is True
    assert recorded["verdict"]["completion_score"] == 1.0
