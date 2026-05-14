"""Unit tests for core.ontology — lifecycle enums, TypeCatalog, and helpers.

Lifecycle enums are plain Enum (not str, Enum). All string comparison goes
through explicit boundary helpers. Direct enum-to-string equality must fail.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.ontology.lifecycles import (
    DOCUMENT_TRANSITIONS,
    EXECUTION_TRANSITIONS,
    LIFECYCLE_CATALOG,
    MEMORY_TRANSITIONS,
    DocumentLifecycle,
    ExecutionLifecycle,
    MemoryLifecycle,
    from_db_value,
    normalize_lifecycle,
    to_db_value,
)

# ── MemoryLifecycle enum ────────────────────────────────────────────────────


class TestMemoryLifecycle:
    def test_values_are_uppercase_strings(self):
        for member in MemoryLifecycle:
            assert member.value == member.value.upper()
            assert isinstance(member.value, str)

    def test_value_matches_db_string(self):
        assert MemoryLifecycle.ACTIVE.value == "ACTIVE"
        assert MemoryLifecycle.DRAFT.value == "DRAFT"
        assert MemoryLifecycle.ARCHIVED.value == "ARCHIVED"

    def test_enum_is_not_equal_to_raw_string(self):
        assert MemoryLifecycle.ACTIVE != "ACTIVE"
        assert MemoryLifecycle.DRAFT != "DRAFT"

    def test_case_insensitive_construction(self):
        assert MemoryLifecycle("active") is MemoryLifecycle.ACTIVE
        assert MemoryLifecycle("Active") is MemoryLifecycle.ACTIVE
        assert MemoryLifecycle("ACTIVE") is MemoryLifecycle.ACTIVE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            MemoryLifecycle("nonexistent")

    def test_all_seven_states_exist(self):
        names = {m.name for m in MemoryLifecycle}
        assert names == {
            "DRAFT",
            "CANDIDATE",
            "PROMOTED",
            "ACTIVE",
            "STALE",
            "SUPERSEDED",
            "ARCHIVED",
        }


# ── ExecutionLifecycle enum ─────────────────────────────────────────────────


class TestExecutionLifecycle:
    def test_values_are_lowercase_strings(self):
        for member in ExecutionLifecycle:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)

    def test_value_matches_db_string(self):
        assert ExecutionLifecycle.PENDING.value == "pending"
        assert ExecutionLifecycle.COMPLETED.value == "completed"

    def test_enum_is_not_equal_to_raw_string(self):
        assert ExecutionLifecycle.PENDING != "pending"
        assert ExecutionLifecycle.ACTIVE != "active"
        assert ExecutionLifecycle.COMPLETED != "completed"

    def test_case_insensitive_construction(self):
        assert ExecutionLifecycle("PENDING") is ExecutionLifecycle.PENDING
        assert ExecutionLifecycle("Pending") is ExecutionLifecycle.PENDING

    def test_all_six_states_exist(self):
        names = {m.name for m in ExecutionLifecycle}
        assert names == {
            "PENDING",
            "ACTIVE",
            "BLOCKED",
            "COMPLETED",
            "FAILED",
            "SKIPPED",
        }


# ── DocumentLifecycle enum ──────────────────────────────────────────────────


class TestDocumentLifecycle:
    def test_values_are_lowercase_strings(self):
        for member in DocumentLifecycle:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)

    def test_value_matches_db_string(self):
        assert DocumentLifecycle.ACTIVE.value == "active"
        assert DocumentLifecycle.ARCHIVED.value == "archived"

    def test_enum_is_not_equal_to_raw_string(self):
        assert DocumentLifecycle.ACTIVE != "active"
        assert DocumentLifecycle.ARCHIVED != "archived"

    def test_case_insensitive_construction(self):
        assert DocumentLifecycle("ACTIVE") is DocumentLifecycle.ACTIVE
        assert DocumentLifecycle("Active") is DocumentLifecycle.ACTIVE


# ── Cross-domain comparison ─────────────────────────────────────────────────


class TestCrossDomain:
    def test_memory_active_is_not_execution_active(self):
        assert MemoryLifecycle.ACTIVE != ExecutionLifecycle.ACTIVE

    def test_memory_active_is_not_document_active(self):
        assert MemoryLifecycle.ACTIVE != DocumentLifecycle.ACTIVE

    def test_execution_active_is_not_document_active(self):
        assert ExecutionLifecycle.ACTIVE != DocumentLifecycle.ACTIVE

    def test_same_domain_active_equals_itself(self):
        assert MemoryLifecycle.ACTIVE == MemoryLifecycle.ACTIVE
        assert ExecutionLifecycle.ACTIVE == ExecutionLifecycle.ACTIVE
        assert DocumentLifecycle.ACTIVE == DocumentLifecycle.ACTIVE

    def test_cross_domain_same_db_value_still_not_equal(self):
        assert ExecutionLifecycle.ACTIVE.value == DocumentLifecycle.ACTIVE.value
        assert ExecutionLifecycle.ACTIVE != DocumentLifecycle.ACTIVE

    def test_different_enum_types(self):
        assert type(MemoryLifecycle.ACTIVE) is not type(ExecutionLifecycle.ACTIVE)
        assert type(ExecutionLifecycle.ACTIVE) is not type(DocumentLifecycle.ACTIVE)
        assert type(MemoryLifecycle.ACTIVE) is not type(DocumentLifecycle.ACTIVE)


# ── Parse/normalize helpers (boundary layer) ────────────────────────────────


class TestHelpers:
    def test_from_db_value_exact_match(self):
        assert from_db_value("ACTIVE", MemoryLifecycle) is MemoryLifecycle.ACTIVE

    def test_from_db_value_case_insensitive(self):
        assert from_db_value("active", MemoryLifecycle) is MemoryLifecycle.ACTIVE
        assert from_db_value("pending", ExecutionLifecycle) is ExecutionLifecycle.PENDING
        assert from_db_value("PENDING", ExecutionLifecycle) is ExecutionLifecycle.PENDING

    def test_from_db_value_invalid_returns_none(self):
        assert from_db_value("nonexistent", MemoryLifecycle) is None

    def test_from_db_value_empty_returns_none(self):
        assert from_db_value("", MemoryLifecycle) is None

    def test_to_db_value_returns_persisted_string(self):
        assert to_db_value(MemoryLifecycle.ACTIVE) == "ACTIVE"
        assert to_db_value(ExecutionLifecycle.PENDING) == "pending"
        assert to_db_value(DocumentLifecycle.ARCHIVED) == "archived"

    def test_to_db_value_returns_str_type(self):
        result = to_db_value(MemoryLifecycle.ACTIVE)
        assert type(result) is str

    def test_normalize_lifecycle_is_alias(self):
        result = normalize_lifecycle("draft", MemoryLifecycle)
        assert result is MemoryLifecycle.DRAFT

    def test_roundtrip_preserves_identity(self):
        for member in MemoryLifecycle:
            db_val = to_db_value(member)
            parsed = from_db_value(db_val, MemoryLifecycle)
            assert parsed is member

        for member in ExecutionLifecycle:
            db_val = to_db_value(member)
            parsed = from_db_value(db_val, ExecutionLifecycle)
            assert parsed is member

        for member in DocumentLifecycle:
            db_val = to_db_value(member)
            parsed = from_db_value(db_val, DocumentLifecycle)
            assert parsed is member

    def test_from_db_value_wrong_domain_returns_none(self):
        assert from_db_value("DRAFT", ExecutionLifecycle) is None
        assert from_db_value("pending", MemoryLifecycle) is None


# ── TypeCatalog ─────────────────────────────────────────────────────────────


class TestTypeCatalog:
    def test_has_lifecycle_registered(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("memory") is True
        assert LIFECYCLE_CATALOG.has_lifecycle("workflow") is True
        assert LIFECYCLE_CATALOG.has_lifecycle("workflow_node") is True
        assert LIFECYCLE_CATALOG.has_lifecycle("artifact") is True

    def test_has_lifecycle_unregistered(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("event") is False
        assert LIFECYCLE_CATALOG.has_lifecycle("trace") is False
        assert LIFECYCLE_CATALOG.has_lifecycle("agent") is False
        assert LIFECYCLE_CATALOG.has_lifecycle("policy") is False

    def test_has_lifecycle_unknown(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("xyzzy") is False

    def test_get_lifecycle_returns_enum_class(self):
        assert LIFECYCLE_CATALOG.get_lifecycle("memory") is MemoryLifecycle
        assert LIFECYCLE_CATALOG.get_lifecycle("workflow") is ExecutionLifecycle
        assert LIFECYCLE_CATALOG.get_lifecycle("artifact") is DocumentLifecycle

    def test_get_lifecycle_unregistered_returns_none(self):
        assert LIFECYCLE_CATALOG.get_lifecycle("event") is None
        assert LIFECYCLE_CATALOG.get_lifecycle("agent") is None
        assert LIFECYCLE_CATALOG.get_lifecycle("unknown_type") is None

    def test_validate_state_valid(self):
        assert LIFECYCLE_CATALOG.validate_state("memory", "ACTIVE") is True
        assert LIFECYCLE_CATALOG.validate_state("memory", "DRAFT") is True
        assert LIFECYCLE_CATALOG.validate_state("workflow", "pending") is True
        assert LIFECYCLE_CATALOG.validate_state("artifact", "active") is True

    def test_validate_state_invalid(self):
        assert LIFECYCLE_CATALOG.validate_state("memory", "pending") is False
        assert LIFECYCLE_CATALOG.validate_state("memory", "nonexistent") is False
        assert LIFECYCLE_CATALOG.validate_state("workflow", "DRAFT") is False

    def test_validate_state_unregistered_returns_true(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="core.ontology.registry"):
            result = LIFECYCLE_CATALOG.validate_state("event", "anything")
        assert result is True
        assert "No lifecycle registered" in caplog.text

    def test_validate_state_unknown_entity_returns_true(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="core.ontology.registry"):
            result = LIFECYCLE_CATALOG.validate_state("xyzzy", "whatever")
        assert result is True

    def test_validate_transition_valid(self):
        assert LIFECYCLE_CATALOG.validate_transition("memory", "DRAFT", "CANDIDATE") is True
        assert LIFECYCLE_CATALOG.validate_transition("memory", "CANDIDATE", "PROMOTED") is True
        assert LIFECYCLE_CATALOG.validate_transition("memory", "PROMOTED", "ACTIVE") is True
        assert LIFECYCLE_CATALOG.validate_transition("workflow", "pending", "active") is True
        assert LIFECYCLE_CATALOG.validate_transition("artifact", "active", "archived") is True

    def test_validate_transition_invalid(self):
        assert LIFECYCLE_CATALOG.validate_transition("memory", "DRAFT", "ACTIVE") is False
        assert LIFECYCLE_CATALOG.validate_transition("memory", "ARCHIVED", "ACTIVE") is False
        assert LIFECYCLE_CATALOG.validate_transition("workflow", "completed", "active") is False

    def test_validate_transition_unregistered_returns_true(self):
        assert LIFECYCLE_CATALOG.validate_transition("event", "a", "b") is True

    def test_validate_transition_unknown_from_state(self):
        assert LIFECYCLE_CATALOG.validate_transition("memory", "NONEXISTENT", "ACTIVE") is False

    def test_catalog_contains_expected_bindings(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("memory")
        assert LIFECYCLE_CATALOG.has_lifecycle("workflow")
        assert LIFECYCLE_CATALOG.has_lifecycle("workflow_node")
        assert LIFECYCLE_CATALOG.has_lifecycle("session")
        assert LIFECYCLE_CATALOG.has_lifecycle("finding")
        assert LIFECYCLE_CATALOG.has_lifecycle("artifact")


# ── Catalog immutability ────────────────────────────────────────────────────


class TestCatalogImmutability:
    def test_no_register_method(self):
        assert not hasattr(LIFECYCLE_CATALOG, "register")

    def test_no_add_method(self):
        assert not hasattr(LIFECYCLE_CATALOG, "add")

    def test_setattr_raises(self):
        with pytest.raises(AttributeError, match="immutable"):
            LIFECYCLE_CATALOG.new_field = "sneaky"

    def test_delattr_raises(self):
        with pytest.raises(AttributeError, match="immutable"):
            del LIFECYCLE_CATALOG._specs

    def test_specs_property_is_read_only_mapping(self):
        specs = LIFECYCLE_CATALOG.specs
        with pytest.raises(TypeError):
            specs["sneaky"] = None

    def test_internal_specs_is_mapping_proxy(self):
        from types import MappingProxyType

        assert isinstance(LIFECYCLE_CATALOG._specs, MappingProxyType)

    def test_catalog_constructed_with_correct_count(self):
        assert len(LIFECYCLE_CATALOG.specs) == 6


# ── Transition maps ─────────────────────────────────────────────────────────


class TestTransitionMaps:
    def test_memory_transitions_complete(self):
        assert set(MEMORY_TRANSITIONS.keys()) == {m.value for m in MemoryLifecycle}

    def test_execution_transitions_complete(self):
        assert set(EXECUTION_TRANSITIONS.keys()) == {m.value for m in ExecutionLifecycle}

    def test_document_transitions_complete(self):
        assert set(DOCUMENT_TRANSITIONS.keys()) == {m.value for m in DocumentLifecycle}

    def test_archived_is_terminal_for_memory(self):
        assert MEMORY_TRANSITIONS["ARCHIVED"] == frozenset()

    def test_completed_is_terminal_for_execution(self):
        assert EXECUTION_TRANSITIONS["completed"] == frozenset()

    def test_skipped_is_terminal_for_execution(self):
        assert EXECUTION_TRANSITIONS["skipped"] == frozenset()

    def test_memory_full_promotion_chain(self):
        assert LIFECYCLE_CATALOG.validate_transition("memory", "DRAFT", "CANDIDATE")
        assert LIFECYCLE_CATALOG.validate_transition("memory", "CANDIDATE", "PROMOTED")
        assert LIFECYCLE_CATALOG.validate_transition("memory", "PROMOTED", "ACTIVE")

    def test_transition_targets_are_valid_states(self):
        memory_values = {m.value for m in MemoryLifecycle}
        for targets in MEMORY_TRANSITIONS.values():
            assert targets <= memory_values

        execution_values = {m.value for m in ExecutionLifecycle}
        for targets in EXECUTION_TRANSITIONS.values():
            assert targets <= execution_values


# ── Persisted string compatibility ──────────────────────────────────────────


class TestPersistedStringCompatibility:
    def test_memory_lifecycle_roundtrip_with_existing_db_strings(self):
        existing_db_strings = [
            "DRAFT",
            "CANDIDATE",
            "PROMOTED",
            "ACTIVE",
            "STALE",
            "SUPERSEDED",
            "ARCHIVED",
        ]
        for s in existing_db_strings:
            member = from_db_value(s, MemoryLifecycle)
            assert member is not None, f"Failed to parse existing DB string: {s}"
            assert to_db_value(member) == s

    def test_execution_lifecycle_roundtrip_with_existing_db_strings(self):
        existing_db_strings = ["pending", "active", "blocked", "completed", "failed", "skipped"]
        for s in existing_db_strings:
            member = from_db_value(s, ExecutionLifecycle)
            assert member is not None, f"Failed to parse existing DB string: {s}"
            assert to_db_value(member) == s

    def test_document_lifecycle_roundtrip_with_existing_db_strings(self):
        existing_db_strings = ["active", "archived"]
        for s in existing_db_strings:
            member = from_db_value(s, DocumentLifecycle)
            assert member is not None, f"Failed to parse existing DB string: {s}"
            assert to_db_value(member) == s

    def test_case_insensitive_db_parse_still_works(self):
        assert from_db_value("active", MemoryLifecycle) is MemoryLifecycle.ACTIVE
        assert from_db_value("ACTIVE", MemoryLifecycle) is MemoryLifecycle.ACTIVE
        assert from_db_value("PENDING", ExecutionLifecycle) is ExecutionLifecycle.PENDING
        assert from_db_value("Active", DocumentLifecycle) is DocumentLifecycle.ACTIVE


# ── Enum is NOT str subclass ───────────────────────────────────────────────


class TestEnumIsNotStr:
    def test_memory_lifecycle_is_not_str(self):
        assert not isinstance(MemoryLifecycle.ACTIVE, str)

    def test_execution_lifecycle_is_not_str(self):
        assert not isinstance(ExecutionLifecycle.ACTIVE, str)

    def test_document_lifecycle_is_not_str(self):
        assert not isinstance(DocumentLifecycle.ACTIVE, str)

    def test_enum_not_usable_in_string_operations(self):
        with pytest.raises(TypeError):
            _ = MemoryLifecycle.ACTIVE + " suffix"
