"""Immutable type catalog — validation contract for entity lifecycles.

The TypeCatalog is a lightweight, frozen validation layer. It does not own
business behavior, mutate at runtime, or import operational subsystems.

Operational subsystems (memory, execution, documents) import this module
for validation. This module never imports them.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LifecycleSpec:
    """Declares the lifecycle binding for one entity type."""

    entity_type: str
    lifecycle_enum: type[Enum]
    transitions: Mapping[str, frozenset[str]]

    def __post_init__(self) -> None:
        if not isinstance(self.transitions, MappingProxyType):
            object.__setattr__(self, "transitions", MappingProxyType(dict(self.transitions)))


@dataclass(frozen=True)
class ValidationResult:
    """Advisory validation outcome — never blocks, only reports."""

    valid: bool
    warnings: list[str] = field(default_factory=list)


class TypeCatalog:
    """Immutable catalog of entity-lifecycle bindings.

    Built once from static LifecycleSpec declarations. No runtime registration,
    no mutation, no dynamic plugin behavior. Internal maps are exposed as
    read-only MappingProxyType views.
    """

    __slots__ = ("_specs",)

    def __init__(self, specs: Sequence[LifecycleSpec]) -> None:
        raw: dict[str, LifecycleSpec] = {}
        for spec in specs:
            raw[spec.entity_type] = spec
        object.__setattr__(self, "_specs", MappingProxyType(raw))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("TypeCatalog is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("TypeCatalog is immutable")

    @property
    def specs(self) -> Mapping[str, LifecycleSpec]:
        return self._specs

    def has_lifecycle(self, entity_type: str) -> bool:
        return entity_type in self._specs

    def get_lifecycle(self, entity_type: str) -> type[Enum] | None:
        spec = self._specs.get(entity_type)
        return spec.lifecycle_enum if spec else None

    def validate_state(self, entity_type: str, state: str) -> bool:
        spec = self._specs.get(entity_type)
        if spec is None:
            logger.debug("No lifecycle registered for entity type %r", entity_type)
            return True

        values = {m.value for m in spec.lifecycle_enum}
        return state in values

    def validate_transition(self, entity_type: str, from_state: str, to_state: str) -> bool:
        spec = self._specs.get(entity_type)
        if spec is None:
            logger.debug("No lifecycle registered for entity type %r", entity_type)
            return True

        allowed = spec.transitions.get(from_state)
        if allowed is None:
            return False
        return to_state in allowed
