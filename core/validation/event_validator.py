"""
Event validation module for Dream Studio.

Validates all events against the canonical schema before persistence.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import jsonschema


@dataclass
class ValidationResult:
    """Result of event validation."""

    is_valid: bool
    errors: list[str]

    def __bool__(self) -> bool:
        return self.is_valid


class EventValidator:
    """
    Validates events against canonical schema and taxonomy.

    Enforcement rules:
    - Event type must be in allowed taxonomy
    - Schema compliance (JSON Schema validation)
    - Event type format (domain.entity.action)
    - Trace completeness (at least one trace ID)
    - Referential integrity (future: check IDs exist)
    """

    def __init__(self, taxonomy_path: str, schema_path: str):
        """
        Initialize validator with taxonomy and schema.

        Args:
            taxonomy_path: Path to event_taxonomy_v1.json
            schema_path: Path to canonical_event_v1_schema.json
        """
        self.taxonomy = self._load_taxonomy(taxonomy_path)
        self.schema = self._load_schema(schema_path)
        self.allowed_types = self._flatten_taxonomy()

        # Compile regex for event_type format
        self.event_type_pattern = re.compile(r"^[a-z]+\.[a-z_]+\.[a-z_]+$")

    def _load_taxonomy(self, path: str) -> dict:
        """Load event taxonomy from JSON file."""
        with open(path) as f:
            return json.load(f)

    def _load_schema(self, path: str) -> dict:
        """Load JSON Schema for canonical events."""
        with open(path) as f:
            return json.load(f)

    def _flatten_taxonomy(self) -> set:
        """Flatten taxonomy into set of allowed event types."""
        allowed = set()
        for domain, events in self.taxonomy["allowed_event_types"].items():
            allowed.update(events)
        return allowed

    def validate(self, event: dict) -> ValidationResult:
        """
        Validate event against all rules.

        Args:
            event: Event dictionary to validate

        Returns:
            ValidationResult with is_valid and errors
        """
        errors = []

        # 1. Check event_type against registry
        event_type = event.get("event_type")
        if not event_type:
            errors.append("Missing required field: event_type")
        elif event_type not in self.allowed_types:
            errors.append(
                f"Unknown event_type: '{event_type}'. "
                f"Not in taxonomy. Valid types: {sorted(self.allowed_types)}"
            )

        # 2. Validate schema compliance (JSON Schema)
        try:
            jsonschema.validate(instance=event, schema=self.schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema validation failed: {e.message}")
        except jsonschema.SchemaError as e:
            errors.append(f"Invalid JSON Schema: {e.message}")

        # 3. Check event_type format (domain.entity.action)
        if event_type and not self.event_type_pattern.match(event_type):
            errors.append(
                f"Invalid event_type format: '{event_type}'. "
                "Must match pattern: domain.entity.action (lowercase, underscores allowed)"
            )

        # 4. Validate trace completeness (at least one ID present)
        trace = event.get("trace", {})
        if not isinstance(trace, dict):
            errors.append("Trace must be an object")
        elif not any(trace.values()):
            errors.append(
                "Trace must contain at least one ID "
                "(project_id, prd_id, task_id, agent_id, workflow_id, execution_id)"
            )

        # 5. Validate event_id is valid UUID
        event_id = event.get("event_id")
        if event_id:
            try:
                UUID(event_id)
            except (ValueError, TypeError):
                errors.append(f"Invalid event_id: '{event_id}'. Must be a valid UUID")

        # 6. Validate timestamp is ISO-8601
        timestamp = event.get("timestamp")
        if timestamp:
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                errors.append(f"Invalid timestamp: '{timestamp}'. Must be ISO-8601 format")

        # 7. Validate severity is in allowed values
        severity = event.get("severity")
        if severity and severity not in ["info", "low", "medium", "high", "critical"]:
            errors.append(
                f"Invalid severity: '{severity}'. "
                "Must be one of: info, low, medium, high, critical"
            )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def validate_event_type_format(self, event_type: str) -> bool:
        """
        Check if event_type matches domain.entity.action pattern.

        Args:
            event_type: Event type string to validate

        Returns:
            True if format is valid, False otherwise
        """
        return bool(self.event_type_pattern.match(event_type))

    def validate_trace(self, trace: dict) -> bool:
        """
        Check if trace contains at least one ID.

        Args:
            trace: Trace dictionary to validate

        Returns:
            True if trace is valid, False otherwise
        """
        if not isinstance(trace, dict):
            return False
        return any(trace.values())

    def get_allowed_event_types(self) -> list[str]:
        """
        Get list of all allowed event types.

        Returns:
            Sorted list of allowed event types
        """
        return sorted(self.allowed_types)

    def get_event_types_for_domain(self, domain: str) -> list[str]:
        """
        Get event types for a specific domain.

        Args:
            domain: Domain name (e.g., 'research', 'prd')

        Returns:
            List of event types for that domain, or empty list if domain not found
        """
        return self.taxonomy["allowed_event_types"].get(domain, [])
