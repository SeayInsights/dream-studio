"""Immutable relationship catalog — advisory validation for entity relationships.

Built from the canonical RelationType enum and CANONICAL_RELATIONSHIPS
declared in core.ontology.schema. No runtime registration, no mutation.

Advisory only: validates source/target compatibility and cardinality
hints but never blocks writes or emissions.

Created: 2026-05-09 (Phase 4F - Relationship Advisory Validation)
"""

import logging
from types import MappingProxyType
from typing import FrozenSet, Mapping, Optional, Sequence, Union

from core.ontology.registry import ValidationResult
from core.ontology.schema import (
    CANONICAL_RELATIONSHIPS,
    EntityType,
    RelationType,
    RelationshipSpec,
)

logger = logging.getLogger(__name__)

_KNOWN_ENTITY_VALUES: FrozenSet[str] = frozenset(m.value for m in EntityType)
_KNOWN_RELATION_VALUES: FrozenSet[str] = frozenset(m.value for m in RelationType)


def _to_str(value: Union[EntityType, RelationType, str]) -> str:
    return value.value if isinstance(value, (EntityType, RelationType)) else str(value)


class RelationshipCatalog:
    """Immutable catalog of canonical relationship specs.

    Built once from static RelationshipSpec declarations. No runtime
    registration, no mutation, no dynamic plugin behavior.
    """

    __slots__ = ("_by_relation", "_all_specs")

    def __init__(self, specs: Sequence[RelationshipSpec]) -> None:
        by_relation: dict[str, list[RelationshipSpec]] = {}
        for spec in specs:
            key = _to_str(spec.relation_type)
            by_relation.setdefault(key, []).append(spec)

        frozen: dict[str, tuple[RelationshipSpec, ...]] = {
            k: tuple(v) for k, v in by_relation.items()
        }

        object.__setattr__(self, "_by_relation", MappingProxyType(frozen))
        object.__setattr__(self, "_all_specs", tuple(specs))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("RelationshipCatalog is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("RelationshipCatalog is immutable")

    @property
    def specs(self) -> Mapping[str, tuple[RelationshipSpec, ...]]:
        return self._by_relation

    @property
    def all_specs(self) -> tuple[RelationshipSpec, ...]:
        return self._all_specs

    def has_relation(self, relation_type: Union[RelationType, str]) -> bool:
        return _to_str(relation_type) in _KNOWN_RELATION_VALUES

    def has_specs(self, relation_type: Union[RelationType, str]) -> bool:
        return _to_str(relation_type) in self._by_relation

    def get_specs(self, relation_type: Union[RelationType, str]) -> tuple[RelationshipSpec, ...]:
        return self._by_relation.get(_to_str(relation_type), ())

    def validate_relationship(
        self,
        source_type: Union[EntityType, str],
        relation_type: Union[RelationType, str],
        target_type: Union[EntityType, str],
        *,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> ValidationResult:
        """Validate a relationship against the canonical catalog.

        Advisory only: returns warnings but never raises or blocks.
        """
        warnings: list[str] = []

        rel_key = _to_str(relation_type)
        src_key = _to_str(source_type)
        tgt_key = _to_str(target_type)

        if rel_key not in _KNOWN_RELATION_VALUES:
            warnings.append(
                f"Unknown relation type '{rel_key}'. " f"Not in canonical RelationType enum."
            )
            return ValidationResult(valid=False, warnings=warnings)

        if src_key not in _KNOWN_ENTITY_VALUES:
            warnings.append(
                f"Unmanaged source entity type '{src_key}'. " f"Not in canonical EntityType enum."
            )
        if tgt_key not in _KNOWN_ENTITY_VALUES:
            warnings.append(
                f"Unmanaged target entity type '{tgt_key}'. " f"Not in canonical EntityType enum."
            )
        if warnings:
            return ValidationResult(valid=False, warnings=warnings)

        specs = self._by_relation.get(rel_key, ())
        if not specs:
            warnings.append(
                f"Relation type '{rel_key}' is known but has no "
                f"source/target specifications defined."
            )
            return ValidationResult(valid=False, warnings=warnings)

        for spec in specs:
            if _to_str(spec.source_type) == src_key and _to_str(spec.target_type) == tgt_key:
                return ValidationResult(valid=True, warnings=[])

        allowed_pairs = [f"({_to_str(s.source_type)} -> {_to_str(s.target_type)})" for s in specs]
        warnings.append(
            f"Relation '{rel_key}' does not allow "
            f"source='{src_key}' -> target='{tgt_key}'. "
            f"Allowed pairs: {', '.join(allowed_pairs)}."
        )
        return ValidationResult(valid=False, warnings=warnings)


RELATIONSHIP_CATALOG = RelationshipCatalog(CANONICAL_RELATIONSHIPS)


def validate_relationship(
    source_type: Union[EntityType, str],
    relation_type: Union[RelationType, str],
    target_type: Union[EntityType, str],
    *,
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    context: Optional[dict] = None,
) -> ValidationResult:
    """Validate a relationship against the canonical catalog.

    Module-level convenience function delegating to RELATIONSHIP_CATALOG.
    Advisory only: returns warnings but never raises or blocks.
    """
    return RELATIONSHIP_CATALOG.validate_relationship(
        source_type,
        relation_type,
        target_type,
        source_id=source_id,
        target_id=target_id,
        context=context,
    )
