"""WO-VERIFY-CONFORMANCE task 1 (+ gap 0a64cf8c): the grader I/O contract is published —
as the combined union schema AND four explicit per-role schemas each requiring its own
score — and the existing mock grader fixtures validate against it (the contract matches
reality). Plus gap 930ea6df's real-provider-evidence guards.
"""

from __future__ import annotations

import pytest

from config.grader_profiles import GRADER_ROLES, real_provider_profiles
from core.work_orders.verify_shared import (
    _MOCK_COMPLETION,
    _MOCK_CORRECTNESS,
    _MOCK_MIGRATION,
    _MOCK_QUALITY,
    StubConformanceNotProviderEvidence,
    grader_verdict_schema,
    record_provider_conformance,
    run_provider_conformance_or_block,
    validate_grader_verdict,
)

_MOCKS = {
    "completion": _MOCK_COMPLETION,
    "correctness": _MOCK_CORRECTNESS,
    "quality": _MOCK_QUALITY,
    "migration": _MOCK_MIGRATION,
}


def test_schema_loads_and_is_wellformed():
    schema = grader_verdict_schema()
    assert schema.get("title")
    assert "anyOf" in schema  # at least one role score required


@pytest.mark.parametrize(
    "fixture",
    [_MOCK_COMPLETION, _MOCK_CORRECTNESS, _MOCK_QUALITY, _MOCK_MIGRATION],
)
def test_mock_fixtures_validate_against_schema(fixture):
    assert validate_grader_verdict(fixture) == []


# ── gap 0a64cf8c: four explicit per-role schemas, each requiring its own score ─────


@pytest.mark.parametrize("role", GRADER_ROLES)
def test_each_role_schema_requires_its_own_score(role):
    schema = grader_verdict_schema(role)
    assert schema.get("required") == [f"{role}_score"], f"{role} schema must require its score"
    assert schema["title"].endswith(f"{role} role")


@pytest.mark.parametrize("role", GRADER_ROLES)
def test_role_fixture_validates_against_its_own_role_schema(role):
    assert validate_grader_verdict(_MOCKS[role], role=role) == []


@pytest.mark.parametrize("role", GRADER_ROLES)
def test_role_schema_rejects_a_different_roles_verdict(role):
    # A verdict carrying ONLY a different role's score must fail this role's contract.
    other = next(r for r in GRADER_ROLES if r != role)
    errors = validate_grader_verdict({f"{other}_score": 1.0}, role=role)
    assert errors, f"{role} schema should reject a {other}-only verdict"


# ── gap 930ea6df: real-provider registry + evidence guards ─────────────────────────


def test_registry_has_at_least_two_real_providers():
    providers = real_provider_profiles()
    assert len(providers) >= 2, "registry must hold >=2 real providers to claim portability"
    assert "claude-cli" in providers
    assert all(not p.get("is_stub") for p in providers.values())


def test_record_provider_conformance_refuses_a_stub(tmp_path):
    stub_result = {"provider": "stub", "is_stub": True, "passed": True}
    with pytest.raises(StubConformanceNotProviderEvidence):
        record_provider_conformance(stub_result, tmp_path / "evidence.json")
    assert not (tmp_path / "evidence.json").exists(), "a stub run must not be persisted as evidence"


def test_record_provider_conformance_accepts_a_real_provider(tmp_path):
    real_result = {"provider": "codex", "is_stub": False, "passed": True}
    out = record_provider_conformance(real_result, tmp_path / "evidence.json")
    assert out.is_file()


def test_run_provider_conformance_blocks_when_unavailable(monkeypatch):
    # An unknown/unreachable provider must yield blocked=True, never a fabricated pass.
    from config import grader_profiles

    monkeypatch.setitem(
        grader_profiles.PROVIDER_PROFILES,
        "ghost-cli",
        {"provider_id": "ghost-cli", "command": "definitely-not-a-real-binary-xyz-123"},
    )
    result = run_provider_conformance_or_block("ghost-cli")
    assert result["blocked"] is True
    assert "not invocable" in result["reason"]


def test_non_conformant_verdict_is_rejected():
    # No role score at all -> not a conformant grader verdict.
    assert validate_grader_verdict({"summary": "no score here"}) != []
    # Score out of range.
    assert validate_grader_verdict({"completion_score": 1.5}) != []
    # Not even an object.
    assert validate_grader_verdict("nope") != []
