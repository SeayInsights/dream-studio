"""WO-VERIFY-CONFORMANCE task 1: the grader I/O contract is published as a schema, and
the existing mock grader fixtures validate against it (the contract matches reality).
"""

from __future__ import annotations

import pytest

from core.work_orders.verify_shared import (
    _MOCK_COMPLETION,
    _MOCK_CORRECTNESS,
    _MOCK_MIGRATION,
    _MOCK_QUALITY,
    grader_verdict_schema,
    validate_grader_verdict,
)


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


def test_non_conformant_verdict_is_rejected():
    # No role score at all -> not a conformant grader verdict.
    assert validate_grader_verdict({"summary": "no score here"}) != []
    # Score out of range.
    assert validate_grader_verdict({"completion_score": 1.5}) != []
    # Not even an object.
    assert validate_grader_verdict("nope") != []
