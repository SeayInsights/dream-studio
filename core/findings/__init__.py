"""Normalised findings: one shape across the three producers.

See model.py for why this is a read-layer normalisation rather than a schema
migration.
"""

from .collect import collect_findings, summarize
from .model import SEVERITY_ORDER, Finding, normalize_severity, severity_rank

__all__ = [
    "Finding",
    "SEVERITY_ORDER",
    "collect_findings",
    "normalize_severity",
    "severity_rank",
    "summarize",
]
