"""WO-VERIFY-CONFORMANCE tasks 2-3 (+ gap 2bbed8d8): a conformance suite any provider must
pass — across ALL FOUR grader roles and the three specifically-named adversarial cases —
run against a second provider (a swapped-in stub — the portability proof) with the result
recorded as evidence. The suite is driven from a resolved provider *profile*, not an ambient
default.
"""

from __future__ import annotations

import json

import pytest

from config.grader_profiles import GRADER_ROLES, resolve_grader_profile
from core.work_orders.verify_shared import (
    record_conformance_result,
    run_conformance_suite,
    run_grader_conformance,
)

# A conformant second provider: reads the prompt on stdin, emits ONLY a grader verdict.
_CONFORMANT_STUB = """import sys, json
sys.stdin.read()
print(json.dumps({"completion_score": 1.0, "summary": "second-provider verdict", "gaps": []}))
"""

# A conformant provider covering ALL FOUR roles (carries every role's score).
_ALL_ROLES_STUB = """import sys, json
sys.stdin.read()
print(json.dumps({
    "completion_score": 1.0, "correctness_score": 1.0,
    "quality_score": 1.0, "migration_score": 1.0, "summary": "ok",
}))
"""

# A non-conformant provider: emits something that is not a valid grader verdict.
_BAD_STUB = """import sys
sys.stdin.read()
print("I refuse to emit JSON")
"""

# Adversarial 1 (WO-GRADER-JSON-EXTRACT): explanatory prose BEFORE the JSON object.
_PROSE_PREFIX_STUB = """import sys, json
sys.stdin.read()
print("Here is my assessment of the work order:")
print("The tasks look addressed. Verdict follows.")
print(json.dumps({"completion_score": 1.0, "summary": "ok", "gaps": []}))
"""

# Adversarial 2 (WO-VERIFY-NOSUMMARY): empty output — must be unreviewable, not blocking.
_EMPTY_STUB = """import sys
sys.stdin.read()
"""

# Adversarial 3 (WO-GRADER-RETRY-NONJSON): non-JSON on the first spawn, valid JSON on the
# retry spawn — proves the conformance run goes THROUGH the retry-owning path. Cross-spawn
# state via a sentinel file whose path arrives on stdin-independent env.
_FLAKY_RETRY_STUB = """import sys, os, json
sys.stdin.read()
sentinel = os.environ["FLAKY_SENTINEL"]
if os.path.exists(sentinel):
    print(json.dumps({"completion_score": 1.0, "summary": "recovered on retry", "gaps": []}))
else:
    open(sentinel, "w").close()
    print("sorry, not JSON this time")
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


# ── gap 2bbed8d8: all four roles, driven from a resolved provider profile ──────────


def test_conformance_covers_all_four_roles(monkeypatch, tmp_path):
    """The suite asserts a schema-valid verdict for completion, correctness, quality AND
    migration — driven from a profile resolved via config.grader_profiles, not an ambient
    default (gap 2bbed8d8)."""
    _use_stub(monkeypatch, tmp_path, _ALL_ROLES_STUB)
    profile = resolve_grader_profile("completion")  # explicit profile resolution
    suite = run_conformance_suite(profile, roles=GRADER_ROLES)
    assert set(suite["roles"]) == set(GRADER_ROLES)
    assert suite["passed"] is True, suite["roles"]
    for role in GRADER_ROLES:
        r = suite["roles"][role]
        assert r["passed"] is True, f"{role}: {r['errors']}"
        assert r["role"] == role


@pytest.mark.parametrize("role", GRADER_ROLES)
def test_each_role_validates_against_its_own_schema(monkeypatch, tmp_path, role):
    _use_stub(monkeypatch, tmp_path, _ALL_ROLES_STUB)
    result = run_grader_conformance(resolve_grader_profile(role), role=role)
    assert result["passed"] is True, f"{role}: {result['errors']}"
    assert result["verdict"][f"{role}_score"] == 1.0


# ── gap 2bbed8d8: the three named adversarial cases ───────────────────────────────


def test_adversarial_prose_prefixed_output_still_extracts(monkeypatch, tmp_path):
    """WO-GRADER-JSON-EXTRACT: explanatory prose before the JSON must still yield a
    schema-valid verdict."""
    _use_stub(monkeypatch, tmp_path, _PROSE_PREFIX_STUB)
    result = run_grader_conformance(resolve_grader_profile("completion"), role="completion")
    assert result["passed"] is True, result["errors"]
    assert result["verdict"]["completion_score"] == 1.0


def test_adversarial_empty_output_is_unreviewable_not_blocking(monkeypatch, tmp_path):
    """WO-VERIFY-NOSUMMARY: empty output is classified unreviewable — distinct from a
    conformance failure, so it is not close-blocking."""
    _use_stub(monkeypatch, tmp_path, _EMPTY_STUB)
    result = run_grader_conformance(resolve_grader_profile("completion"), role="completion")
    assert result["unreviewable"] is True
    assert result["passed"] is False


def test_adversarial_non_json_triggers_retry_through_retry_path(monkeypatch, tmp_path):
    """WO-GRADER-RETRY-NONJSON: a non-JSON first reply is re-tried once through the shared
    retry path the conformance run uses; the clean retry verdict is accepted."""
    _use_stub(monkeypatch, tmp_path, _FLAKY_RETRY_STUB)
    monkeypatch.setenv("FLAKY_SENTINEL", str(tmp_path / "flaky.sentinel"))
    result = run_grader_conformance(resolve_grader_profile("completion"), role="completion")
    assert result["passed"] is True, result["errors"]
    assert result["verdict"]["summary"] == "recovered on retry"
