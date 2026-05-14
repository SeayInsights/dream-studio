"""Phase 4F tests — advisory relationship validation.

Proves that:
- Known relationship patterns validate successfully
- Unknown relation types return advisory warnings without raising
- Invalid source/target pairings return advisory warnings without raising
- Unmanaged entity types are handled safely
- Lifecycle-less entities are handled safely
- RelationshipCatalog is immutable
- No dynamic registration exists
- Cardinality metadata is advisory only
- RelationType does not collapse into EventType or Lifecycle
- Existing 4A/4B/4C/4D/4E tests still pass
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.ontology.registry import ValidationResult
from core.ontology.schema import (
    CANONICAL_RELATIONSHIPS,
    EntityType,
    RelationType,
    RelationshipSpec,
)
from core.ontology.relationships import (
    RELATIONSHIP_CATALOG,
    RelationshipCatalog,
    validate_relationship,
)

# ── Known relationship patterns validate ──────────────────────────────────────


class TestKnownRelationships:
    def test_contains_project_session(self):
        result = validate_relationship(
            EntityType.PROJECT,
            RelationType.CONTAINS,
            EntityType.SESSION,
        )
        assert result.valid is True
        assert result.warnings == []

    def test_contains_session_event(self):
        result = validate_relationship(
            EntityType.SESSION,
            RelationType.CONTAINS,
            EntityType.EVENT,
        )
        assert result.valid is True

    def test_contains_workflow_node(self):
        result = validate_relationship(
            EntityType.WORKFLOW,
            RelationType.CONTAINS,
            EntityType.WORKFLOW_NODE,
        )
        assert result.valid is True

    def test_triggers_event_workflow(self):
        result = validate_relationship(
            EntityType.EVENT,
            RelationType.TRIGGERS,
            EntityType.WORKFLOW,
        )
        assert result.valid is True

    def test_produces_workflow_artifact(self):
        result = validate_relationship(
            EntityType.WORKFLOW,
            RelationType.PRODUCES,
            EntityType.ARTIFACT,
        )
        assert result.valid is True

    def test_depends_on_node_node(self):
        result = validate_relationship(
            EntityType.WORKFLOW_NODE,
            RelationType.DEPENDS_ON,
            EntityType.WORKFLOW_NODE,
        )
        assert result.valid is True

    def test_caused_by_decision_event(self):
        result = validate_relationship(
            EntityType.DECISION,
            RelationType.CAUSED_BY,
            EntityType.EVENT,
        )
        assert result.valid is True

    def test_applied_to_policy_skill(self):
        result = validate_relationship(
            EntityType.POLICY,
            RelationType.APPLIED_TO,
            EntityType.SKILL,
        )
        assert result.valid is True

    def test_detected_in_finding_scan(self):
        result = validate_relationship(
            EntityType.FINDING,
            RelationType.DETECTED_IN,
            EntityType.SCAN,
        )
        assert result.valid is True

    def test_learned_from_lesson_session(self):
        result = validate_relationship(
            EntityType.LESSON,
            RelationType.LEARNED_FROM,
            EntityType.SESSION,
        )
        assert result.valid is True

    def test_references_memory_event(self):
        result = validate_relationship(
            EntityType.MEMORY,
            RelationType.REFERENCES,
            EntityType.EVENT,
        )
        assert result.valid is True

    def test_corrects_decision_decision(self):
        result = validate_relationship(
            EntityType.DECISION,
            RelationType.CORRECTS,
            EntityType.DECISION,
        )
        assert result.valid is True

    def test_all_canonical_relationships_pass(self):
        for spec in CANONICAL_RELATIONSHIPS:
            result = validate_relationship(
                spec.source_type,
                spec.relation_type,
                spec.target_type,
            )
            assert result.valid is True, (
                f"{spec.source_type.value} --{spec.relation_type.value}--> "
                f"{spec.target_type.value} should be valid"
            )

    def test_string_args_accepted(self):
        result = validate_relationship("project", "contains", "session")
        assert result.valid is True

    def test_mixed_enum_and_string_args(self):
        result = validate_relationship(
            EntityType.PROJECT,
            "contains",
            EntityType.SESSION,
        )
        assert result.valid is True


# ── Unknown relation types ────────────────────────────────────────────────────


class TestUnknownRelationTypes:
    def test_unknown_relation_returns_advisory(self):
        result = validate_relationship("project", "invented_relation", "session")
        assert result.valid is False
        assert len(result.warnings) == 1
        assert "Unknown relation type" in result.warnings[0]

    def test_unknown_relation_does_not_raise(self):
        result = validate_relationship("project", "nonexistent", "session")
        assert isinstance(result, ValidationResult)
        assert result.valid is False

    def test_domain_specific_blocks_not_canonical(self):
        result = validate_relationship("workflow_node", "blocks", "workflow_node")
        assert result.valid is False
        assert "Unknown relation type" in result.warnings[0]

    def test_domain_specific_informs_not_canonical(self):
        result = validate_relationship("workflow_node", "informs", "workflow_node")
        assert result.valid is False

    def test_domain_specific_triggered_not_canonical(self):
        result = validate_relationship("decision", "triggered", "event")
        assert result.valid is False


# ── Invalid source/target pairings ────────────────────────────────────────────


class TestInvalidSourceTargetPairing:
    def test_reversed_contains(self):
        result = validate_relationship(
            EntityType.SESSION,
            RelationType.CONTAINS,
            EntityType.PROJECT,
        )
        assert result.valid is False
        assert any("does not allow" in w for w in result.warnings)

    def test_wrong_source_for_triggers(self):
        result = validate_relationship(
            EntityType.WORKFLOW,
            RelationType.TRIGGERS,
            EntityType.EVENT,
        )
        assert result.valid is False
        assert any("does not allow" in w for w in result.warnings)

    def test_wrong_target_for_detected_in(self):
        result = validate_relationship(
            EntityType.FINDING,
            RelationType.DETECTED_IN,
            EntityType.PROJECT,
        )
        assert result.valid is False

    def test_invalid_pairing_shows_allowed_pairs(self):
        result = validate_relationship(
            EntityType.PROJECT,
            RelationType.CONTAINS,
            EntityType.ARTIFACT,
        )
        assert result.valid is False
        assert any("Allowed pairs" in w for w in result.warnings)

    def test_invalid_pairing_does_not_raise(self):
        result = validate_relationship(
            EntityType.SCAN,
            RelationType.PRODUCES,
            EntityType.MEMORY,
        )
        assert isinstance(result, ValidationResult)
        assert result.valid is False


# ── Unmanaged entity types ────────────────────────────────────────────────────


class TestUnmanagedEntityTypes:
    def test_unknown_source_entity(self):
        result = validate_relationship("unknown_entity", "contains", "session")
        assert result.valid is False
        assert any("Unmanaged source" in w for w in result.warnings)

    def test_unknown_target_entity(self):
        result = validate_relationship("project", "contains", "unknown_entity")
        assert result.valid is False
        assert any("Unmanaged target" in w for w in result.warnings)

    def test_both_unknown_entities(self):
        result = validate_relationship("foo", "contains", "bar")
        assert result.valid is False
        assert any("Unmanaged source" in w for w in result.warnings)
        assert any("Unmanaged target" in w for w in result.warnings)

    def test_unknown_entity_does_not_raise(self):
        result = validate_relationship("xyzzy", "contains", "plugh")
        assert isinstance(result, ValidationResult)


# ── Lifecycle-less entities ───────────────────────────────────────────────────


class TestLifecyclelessEntities:
    def test_event_is_valid_entity(self):
        result = validate_relationship(
            EntityType.EVENT,
            RelationType.TRIGGERS,
            EntityType.WORKFLOW,
        )
        assert result.valid is True

    def test_trace_is_valid_entity(self):
        result = validate_relationship(
            EntityType.TRACE,
            RelationType.REFERENCES,
            EntityType.EVENT,
        )
        assert result.valid is False
        assert any("does not allow" in w for w in result.warnings)

    def test_agent_is_valid_entity(self):
        assert RELATIONSHIP_CATALOG.has_relation("contains")
        result = validate_relationship("agent", "contains", "workflow")
        assert result.valid is False


# ── Catalog immutability ──────────────────────────────────────────────────────


class TestCatalogImmutability:
    def test_no_register_method(self):
        assert not hasattr(RELATIONSHIP_CATALOG, "register")

    def test_no_add_method(self):
        assert not hasattr(RELATIONSHIP_CATALOG, "add")

    def test_setattr_raises(self):
        with pytest.raises(AttributeError, match="immutable"):
            RELATIONSHIP_CATALOG.new_field = "sneaky"

    def test_delattr_raises(self):
        with pytest.raises(AttributeError, match="immutable"):
            del RELATIONSHIP_CATALOG._by_relation

    def test_specs_property_is_read_only_mapping(self):
        specs = RELATIONSHIP_CATALOG.specs
        with pytest.raises(TypeError):
            specs["sneaky"] = None

    def test_internal_by_relation_is_mapping_proxy(self):
        assert isinstance(RELATIONSHIP_CATALOG._by_relation, MappingProxyType)

    def test_all_specs_is_tuple(self):
        assert isinstance(RELATIONSHIP_CATALOG.all_specs, tuple)


# ── No dynamic registration ──────────────────────────────────────────────────


class TestNoDynamicRegistration:
    def test_no_register_method_exists(self):
        assert not hasattr(RelationshipCatalog, "register")

    def test_no_add_spec_method_exists(self):
        assert not hasattr(RelationshipCatalog, "add_spec")

    def test_no_remove_method_exists(self):
        assert not hasattr(RelationshipCatalog, "remove")

    def test_catalog_built_from_static_specs(self):
        assert len(RELATIONSHIP_CATALOG.all_specs) == len(CANONICAL_RELATIONSHIPS)
        for i, spec in enumerate(RELATIONSHIP_CATALOG.all_specs):
            assert spec is CANONICAL_RELATIONSHIPS[i]


# ── Cardinality metadata is advisory only ─────────────────────────────────────


class TestCardinalityAdvisory:
    def test_cardinality_present_in_specs(self):
        for spec in CANONICAL_RELATIONSHIPS:
            assert spec.cardinality in ("1:1", "1:N", "N:1", "N:M")

    def test_cardinality_does_not_affect_validation(self):
        result = validate_relationship(
            EntityType.PROJECT,
            RelationType.CONTAINS,
            EntityType.SESSION,
        )
        assert result.valid is True

    def test_cardinality_accessible_from_catalog(self):
        specs = RELATIONSHIP_CATALOG.get_specs(RelationType.CONTAINS)
        assert len(specs) >= 1
        for spec in specs:
            assert hasattr(spec, "cardinality")
            assert isinstance(spec.cardinality, str)

    def test_relationship_spec_is_frozen(self):
        spec = CANONICAL_RELATIONSHIPS[0]
        with pytest.raises(AttributeError):
            spec.cardinality = "changed"


# ── Type separation ──────────────────────────────────────────────────────────


class TestTypeSeparation:
    def test_relation_type_is_not_entity_type(self):
        assert type(RelationType.CONTAINS) is not type(EntityType.PROJECT)

    def test_relation_type_not_in_entity_type(self):
        relation_values = {m.value for m in RelationType}
        entity_values = {m.value for m in EntityType}
        assert relation_values.isdisjoint(entity_values)

    def test_relation_type_not_in_lifecycle(self):
        from core.ontology.lifecycles import ExecutionLifecycle, MemoryLifecycle

        relation_values = {m.value for m in RelationType}
        exec_values = {m.value for m in ExecutionLifecycle}
        mem_values = {m.value for m in MemoryLifecycle}
        assert relation_values.isdisjoint(exec_values)
        assert relation_values.isdisjoint(mem_values)

    def test_relation_type_not_in_event_type(self):
        from core.events.types import EventType

        relation_values = {m.value for m in RelationType}
        event_attrs = {
            v for k, v in vars(EventType).items() if not k.startswith("_") and isinstance(v, str)
        }
        assert relation_values.isdisjoint(event_attrs)


# ── Catalog query methods ─────────────────────────────────────────────────────


class TestCatalogQueries:
    def test_has_relation_known(self):
        assert RELATIONSHIP_CATALOG.has_relation(RelationType.CONTAINS) is True
        assert RELATIONSHIP_CATALOG.has_relation("contains") is True

    def test_has_relation_unknown(self):
        assert RELATIONSHIP_CATALOG.has_relation("blocks") is False
        assert RELATIONSHIP_CATALOG.has_relation("invented") is False

    def test_has_specs_with_specs(self):
        assert RELATIONSHIP_CATALOG.has_specs(RelationType.CONTAINS) is True

    def test_has_specs_without_specs(self):
        assert RELATIONSHIP_CATALOG.has_specs(RelationType.SUPERSEDES) is False

    def test_get_specs_returns_tuple(self):
        specs = RELATIONSHIP_CATALOG.get_specs(RelationType.CONTAINS)
        assert isinstance(specs, tuple)

    def test_get_specs_contains_has_three(self):
        specs = RELATIONSHIP_CATALOG.get_specs(RelationType.CONTAINS)
        assert len(specs) == 3

    def test_get_specs_unknown_returns_empty(self):
        specs = RELATIONSHIP_CATALOG.get_specs("nonexistent")
        assert specs == ()

    def test_supersedes_known_but_no_specs(self):
        assert RELATIONSHIP_CATALOG.has_relation(RelationType.SUPERSEDES) is True
        assert RELATIONSHIP_CATALOG.has_specs(RelationType.SUPERSEDES) is False
        result = validate_relationship("memory", "supersedes", "memory")
        assert result.valid is False
        assert any("no source/target specifications" in w for w in result.warnings)


# ── No import cycles ──────────────────────────────────────────────────────────


class TestNoImportCycles:
    def test_relationships_imports_cleanly(self):
        import core.ontology.relationships  # noqa: F401

    def test_does_not_import_runtime_modules(self):
        import core.ontology.relationships as mod

        source = Path(mod.__file__).read_text()
        forbidden = [
            "from core.event_store",
            "from core.projections",
            "from core.memory",
            "from core.storage",
            "from core.execution",
            "from core.security",
            "from core.events",
        ]
        for pattern in forbidden:
            assert pattern not in source, f"Relationship catalog must not import: {pattern}"


# ── ValidationResult reuse ────────────────────────────────────────────────────


class TestValidationResultReuse:
    def test_uses_ontology_validation_result(self):
        result = validate_relationship(
            EntityType.PROJECT,
            RelationType.CONTAINS,
            EntityType.SESSION,
        )
        assert isinstance(result, ValidationResult)

    def test_result_has_valid_and_warnings(self):
        result = validate_relationship("project", "contains", "session")
        assert hasattr(result, "valid")
        assert hasattr(result, "warnings")

    def test_valid_result_has_empty_warnings(self):
        result = validate_relationship(
            EntityType.PROJECT,
            RelationType.CONTAINS,
            EntityType.SESSION,
        )
        assert result.warnings == []

    def test_invalid_result_has_nonempty_warnings(self):
        result = validate_relationship("project", "invented", "session")
        assert len(result.warnings) > 0
