"""Correlation ID composition rules — Phase 18.1.3.

Correlation IDs link related events across the raw, business canonical, and AI
canonical layers. This module is the single canonical implementation of the
composition rules. All future event emitters must use these functions rather
than hand-building correlation_id strings.

Composition format
------------------
A correlation_id is a colon-delimited string of typed segments:

    sess-<session_id>:wf-<workflow_id>:skill-<skill_id>:agent-<agent_id>:hook-<hook_id>:tool-<tool_id>

Rules:
1. Only non-null segments are included.
2. Segments always appear in the canonical order:
       session → workflow → skill → agent → hook → tool
   (outermost context first)
3. Each segment is prefixed with its entity type so pattern matching works
   without knowing positional index.
4. Segment values may contain alphanumeric characters plus [-._:].
   No spaces or special characters.

Propagation pattern
-------------------
The caller passes its own correlation_id as the ``base`` to any callee it
triggers. The callee calls ``extend(base, entity_type, entity_id)`` to add its
own segment, then passes the extended ID to any further callees.

Example chain::

    session-level code           compose({"session": "abc"})
        → skill invocation       extend("sess-abc", "skill", "ds-security-scan-789")
        → tool call (raw only)   extend("sess-abc:skill-ds-security-scan-789", "tool", "Read")
"""

from __future__ import annotations

import re

# Canonical order of context levels. This ordering determines the string
# structure and is enforced by validate().
_COMPONENT_ORDER: tuple[str, ...] = (
    "session",
    "workflow",
    "skill",
    "agent",
    "hook",
    "tool",
)

# Prefix for each entity type in the composed string.
_PREFIX: dict[str, str] = {
    "session": "sess",
    "workflow": "wf",
    "skill": "skill",
    "agent": "agent",
    "hook": "hook",
    "tool": "tool",
}

# Reverse map: string prefix → entity type key
_REVERSE_PREFIX: dict[str, str] = {v: k for k, v in _PREFIX.items()}

# Valid characters in a segment value (after the prefix-).
_VALUE_RE = re.compile(r"^[A-Za-z0-9\-._:]+$")

# Matches a single typed segment: prefix-value
_SEGMENT_RE = re.compile(r"^(sess|wf|skill|agent|hook|tool)-(.+)$")

# Splits a correlation_id at colons that are immediately followed by a known
# prefix. This allows segment *values* to contain colons (e.g. skill IDs like
# "ds-security:scan") without being misinterpreted as segment boundaries.
_SEGMENT_SPLIT_RE = re.compile(r":(?=(?:sess|wf|skill|agent|hook|tool)-)")


def compose(parts: dict[str, str | None]) -> str | None:
    """Compose a correlation_id from a dict of entity IDs.

    Parameters
    ----------
    parts:
        Dict with optional keys: ``session``, ``workflow``, ``skill``,
        ``agent``, ``hook``, ``tool``. Values that are ``None`` or missing
        are omitted.

    Returns
    -------
    str | None
        Composed correlation_id, or ``None`` if no non-null parts are
        provided.

    Example
    -------
    >>> compose({"session": "abc", "skill": "ds-security-scan-789"})
    'sess-abc:skill-ds-security-scan-789'
    """
    segments: list[str] = []
    for entity_type in _COMPONENT_ORDER:
        value = parts.get(entity_type)
        if value is not None:
            prefix = _PREFIX[entity_type]
            segments.append(f"{prefix}-{value}")
    return ":".join(segments) if segments else None


def decompose(correlation_id: str) -> dict[str, str]:
    """Parse a correlation_id back into its component entity IDs.

    Parameters
    ----------
    correlation_id:
        A composed correlation_id string.

    Returns
    -------
    dict[str, str]
        Dict mapping entity_type keys (``session``, ``workflow``, etc.) to
        their raw ID values (without prefix). Unknown or malformed segments
        are silently skipped.

    Example
    -------
    >>> decompose("sess-abc:wf-xyz:skill-scan-789")
    {'session': 'abc', 'workflow': 'xyz', 'skill': 'scan-789'}
    """
    result: dict[str, str] = {}
    for segment in _SEGMENT_SPLIT_RE.split(correlation_id):
        m = _SEGMENT_RE.match(segment)
        if m:
            prefix, value = m.group(1), m.group(2)
            entity_type = _REVERSE_PREFIX.get(prefix)
            if entity_type:
                result[entity_type] = value
    return result


def extend(base: str | None, entity_type: str, entity_id: str) -> str:
    """Add a deeper context segment to an existing correlation_id.

    The new segment is appended **only** if the entity_type is not already
    present in ``base``. If it is present, ``base`` is returned unchanged
    (extending with the same type twice is a no-op to prevent duplicates).

    Parameters
    ----------
    base:
        Existing correlation_id to extend, or ``None`` to start a new one.
    entity_type:
        One of ``session``, ``workflow``, ``skill``, ``agent``, ``hook``,
        ``tool``.
    entity_id:
        Raw entity ID (without prefix). Must match ``[A-Za-z0-9\\-._:]+``.

    Returns
    -------
    str
        New correlation_id with the segment appended.

    Raises
    ------
    ValueError
        If ``entity_type`` is not one of the known component types.

    Example
    -------
    >>> extend("sess-abc", "skill", "ds-security-scan-789")
    'sess-abc:skill-ds-security-scan-789'
    """
    if entity_type not in _PREFIX:
        raise ValueError(
            f"Unknown entity_type {entity_type!r}. "
            f"Must be one of: {', '.join(_COMPONENT_ORDER)}"
        )
    prefix = _PREFIX[entity_type]
    new_segment = f"{prefix}-{entity_id}"

    if base is None:
        return new_segment

    # No-op if this entity type already appears in the chain.
    existing = decompose(base)
    if entity_type in existing:
        return base

    return f"{base}:{new_segment}"


def validate(correlation_id: str) -> tuple[bool, str | None]:
    """Check that a correlation_id follows composition rules.

    Parameters
    ----------
    correlation_id:
        The string to validate.

    Returns
    -------
    tuple[bool, str | None]
        ``(True, None)`` if valid; ``(False, error_message)`` otherwise.

    Checks performed:
    - Non-empty string
    - All segments match ``prefix-value`` pattern with known prefixes
    - Segment values contain only allowed characters
    - Segment types appear in canonical order (no duplicates)
    """
    if not correlation_id:
        return False, "correlation_id is empty"

    # Split only at colon boundaries between known-prefix segments so that
    # segment values containing colons (e.g. "skill-ds-security:scan") are
    # treated as a single segment rather than two.
    segments = _SEGMENT_SPLIT_RE.split(correlation_id)
    seen_order: list[int] = []

    for segment in segments:
        m = _SEGMENT_RE.match(segment)
        if not m:
            return False, f"Segment {segment!r} does not match prefix-value pattern"

        prefix, value = m.group(1), m.group(2)
        entity_type = _REVERSE_PREFIX.get(prefix)
        if entity_type is None:
            # Should not happen given _SEGMENT_RE covers all known prefixes,
            # but guard anyway.
            return False, f"Unknown prefix {prefix!r} in segment {segment!r}"

        if not _VALUE_RE.match(value):
            return False, (
                f"Segment {segment!r} value {value!r} contains invalid characters. "
                f"Allowed: alphanumeric, dash, dot, underscore, colon"
            )

        idx = _COMPONENT_ORDER.index(entity_type)
        if seen_order and idx <= seen_order[-1]:
            return False, (
                f"Segment {segment!r} is out of order. "
                f"Expected order: {' → '.join(_COMPONENT_ORDER)}"
            )
        seen_order.append(idx)

    return True, None


def normalize_legacy(correlation_id: str | None) -> tuple[str | None, str]:
    """Best-effort normalization of a correlation_id that may predate the rules.

    Used by the backfill script for historical events whose correlation_ids
    were composed by ad-hoc logic before Phase 18.1.3.

    Parameters
    ----------
    correlation_id:
        The string to normalize, or ``None``.

    Returns
    -------
    tuple[str | None, str]
        ``(normalized_id_or_None, action)`` where action is one of:
        - ``"kept"`` — already valid, returned as-is
        - ``"normalized"`` — parsed and recomposed in canonical order
        - ``"unfixable"`` — could not be normalized (returns ``None``)

    Notes
    -----
    Normalization is best-effort. A legacy id like ``sess-abc:wf-xyz`` that
    already follows the rules is returned as kept. An id with out-of-order
    segments is recomposed. Segments with unknown prefixes are dropped.
    """
    if correlation_id is None:
        return None, "unfixable"

    is_valid, _ = validate(correlation_id)
    if is_valid:
        return correlation_id, "kept"

    # Try to extract whatever typed segments we can and recompose.
    components = decompose(correlation_id)
    if not components:
        return None, "unfixable"

    recomposed = compose(components)
    if recomposed:
        return recomposed, "normalized"

    return None, "unfixable"
