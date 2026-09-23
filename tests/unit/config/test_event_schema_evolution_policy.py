"""H6 — Event schema evolution policy: additive-only + required-key enforcement.

Layer 2 enforcement: fixture-based CI test.
Every registered event type with payload_required_keys has a known-good
fixture invocation.  The test verifies that:

  1. All required keys are present in each fixture payload.
  2. write_event() raises ValueError when a required key is absent.
  3. Registry entries with payload_required_keys follow the naming
     convention (event_type or event_type.vN for versioned variants).
  4. No two entries share an event_type string (registry integrity).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Known-good payloads for every entry that has payload_required_keys.
# These are the canonical emitter payloads as of Phase 18.1.11.
# Update this dict when a new event type gains payload_required_keys.
_GOOD_PAYLOADS: dict[str, dict] = {
    "work_order.created": {
        "title": "Write auth middleware",
        "status": "created",
        "type": "api_endpoint",
    },
    "work_order.started": {
        "work_order_id": str(uuid.uuid4()),
        "title": "Write auth middleware",
        "type": "api_endpoint",
        "project_id": "proj-test",
    },
    # The three lifecycle transitions #797 registered -- in_review, pushed, ci_issues. They
    # carry required keys, so they owe a known-good payload here; #797 merged without one
    # and main's Full CI went red on exactly this.
    "work_order.review_requested": {
        "work_order_id": str(uuid.uuid4()),
        "title": "Write auth middleware",
        "project_id": "proj-test",
    },
    "work_order.pushed": {
        "work_order_id": str(uuid.uuid4()),
        "title": "Write auth middleware",
        "project_id": "proj-test",
    },
    "work_order.ci_failed": {
        "work_order_id": str(uuid.uuid4()),
        "title": "Write auth middleware",
        "project_id": "proj-test",
    },
    "work_order.blocked": {
        "work_order_id": str(uuid.uuid4()),
        "title": "Write auth middleware",
        "project_id": "proj-test",
        "reason": "Waiting for design sign-off",
    },
    "work_order.unblocked": {
        "work_order_id": str(uuid.uuid4()),
        "title": "Write auth middleware",
        "project_id": "proj-test",
    },
    "work_order.closed": {
        "work_order_id": str(uuid.uuid4()),
        "title": "Write auth middleware",
        "project_id": "proj-test",
        "forced": False,
    },
    # WO 17f20d48. acceptance_criteria is write-once in the projection, so a typo in a
    # check was only correctable with --force. task.ac_repointed is the one writer that
    # SETs it, and it carries `previous` and `reason` so the correction is auditable —
    # which is exactly why those two are required keys and belong in this fixture.
    "task.ac_repointed": {
        "acceptance_criteria": "TEST-CHECK: tests/unit/test_example.py::test_it",
        "previous": "TEST-CHECK: tests/unit/test_example.py::test_i",
        "reason": "Typo in the node id; same test, only the address corrected.",
    },
    "design_brief.created": {
        "brief_id": str(uuid.uuid4()),
        "project_id": "proj-test",
    },
    "design_brief.updated": {
        "brief_id": str(uuid.uuid4()),
        "field": "audience",
        "new_value": "enterprise buyers",
    },
    "design_brief.locked": {
        "brief_id": str(uuid.uuid4()),
    },
    "project.activated": {
        "project_id": "proj-test",
    },
    "project.deactivated": {
        "project_id": "proj-test",
    },
    "project.client_assigned": {
        "project_id": "proj-test",
        "client_id": "seayinsights",
    },
    "client.created": {
        "client_id": "acme",
    },
    "client.archived": {
        "client_id": "acme",
    },
    "client.deleted": {
        "client_id": "acme",
    },
    "work_order.deleted": {
        "work_order_id": str(uuid.uuid4()),
        "project_id": "proj-test",
    },
    # WO 175299fc: registered by #712 without the fixture the registration obliges, which
    # is what put Full CI red for seven consecutive merges. `work_order.reopened` was added
    # because a rebuild reverted every reopened work order to `closed` -- the registration
    # was right; the payload every registered type owes was not added with it.
    "work_order.cancelled": {
        "work_order_id": str(uuid.uuid4()),
        "project_id": "proj-test",
    },
    "work_order.reopened": {
        "work_order_id": str(uuid.uuid4()),
        "project_id": "proj-test",
    },
    "design_brief.deleted": {
        "brief_id": str(uuid.uuid4()),
        "project_id": "proj-test",
    },
    "security.finding.logged": {
        "finding_id": str(uuid.uuid4()),
        "project_id": "proj-test",
        "severity": "high",
        "status": "open",
    },
    "security.finding.resolved": {
        "finding_id": str(uuid.uuid4()),
        "project_id": "proj-test",
    },
}


def _entries_with_required_keys():
    from config.event_type_registry import all_entries

    return [e for e in all_entries() if e.payload_required_keys]


class TestRegistryIntegrity:
    def test_no_duplicate_event_types(self):
        from config.event_type_registry import all_entries

        seen: set[str] = set()
        for entry in all_entries():
            assert entry.event_type not in seen, f"Duplicate event_type: {entry.event_type}"
            seen.add(entry.event_type)

    def test_versioned_naming_convention(self):
        """Versioned event types must use dot-v suffix: <base>.v<N>."""
        import re

        from config.event_type_registry import all_entries

        versioned_pattern = re.compile(r"^.+\.v\d+$")
        for entry in all_entries():
            parts = entry.event_type.split(".")
            if len(parts) >= 3 and re.match(r"^v\d+$", parts[-1]):
                assert versioned_pattern.match(
                    entry.event_type
                ), f"Versioned entry '{entry.event_type}' does not follow <base>.v<N> convention"


class TestPayloadRequiredKeys:
    def test_every_required_key_type_has_a_fixture(self):
        """The gap reports as a named list, before any parametrised node raises KeyError.

        WO 175299fc. Two of the three parametrised nodes below index _GOOD_PAYLOADS
        directly, so a registered type with no fixture raises `KeyError: 'work_order.reopened'`
        -- which reads as a broken test rather than as a missing fixture, and puts the
        remedy nowhere near the failure. That is how six of the twelve failures that kept
        Full CI red for seven consecutive merges presented.

        This runs first and unparametrised, so the whole gap arrives as ONE failure naming
        every type that owes a fixture. The per-type nodes keep their own assertion: this
        one says WHAT is missing, they say whether each fixture is correct.
        """
        missing = sorted(
            e.event_type
            for e in _entries_with_required_keys()
            if e.event_type not in _GOOD_PAYLOADS
        )
        assert not missing, (
            "registered event type(s) declare payload_required_keys and have no fixture in "
            f"_GOOD_PAYLOADS: {missing}. Registering a type obliges a known-good payload -- "
            "add one per type above. Without this the parametrised nodes below fail with a "
            "bare KeyError, which reads as a broken test rather than a missing fixture."
        )

    @pytest.mark.parametrize("entry", _entries_with_required_keys(), ids=lambda e: e.event_type)
    def test_fixture_payload_contains_all_required_keys(self, entry):
        """Every registered event type with required keys has a passing fixture."""
        assert entry.event_type in _GOOD_PAYLOADS, (
            f"No fixture payload defined for '{entry.event_type}' in _GOOD_PAYLOADS. "
            "Add a known-good payload when adding payload_required_keys to the registry."
        )
        payload = _GOOD_PAYLOADS[entry.event_type]
        missing = entry.payload_required_keys - payload.keys()
        assert (
            not missing
        ), f"Fixture payload for '{entry.event_type}' is missing keys: {sorted(missing)}"

    @pytest.mark.parametrize("entry", _entries_with_required_keys(), ids=lambda e: e.event_type)
    def test_write_event_raises_on_missing_required_key(self, entry, tmp_path):
        """write_event() fails fast when a required payload key is absent."""
        from spool.writer import write_event

        for missing_key in entry.payload_required_keys:
            bad_payload = {
                k: v for k, v in _GOOD_PAYLOADS[entry.event_type].items() if k != missing_key
            }
            envelope = {
                "event_id": str(uuid.uuid4()),
                "event_type": entry.event_type,
                "timestamp": "2026-05-23T00:00:00+00:00",
                "schema_version": 1,
                "payload": bad_payload,
            }
            with pytest.raises(ValueError, match=missing_key):
                write_event(envelope, root=tmp_path)

    @pytest.mark.parametrize("entry", _entries_with_required_keys(), ids=lambda e: e.event_type)
    def test_write_event_succeeds_with_complete_payload(self, entry, tmp_path):
        """write_event() succeeds when all required payload keys are present."""
        from spool.writer import write_event

        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": entry.event_type,
            "timestamp": "2026-05-23T00:00:00+00:00",
            "schema_version": 1,
            "payload": _GOOD_PAYLOADS[entry.event_type],
        }
        path = write_event(envelope, root=tmp_path)
        assert path.exists()
