"""Multi-signal stack detection for project-intelligence platform.

Combines multiple detection strategies to identify project stack with confidence scoring.

WO-GF-CONTROL-INSTALL-split: implementation moved to detector_{shared,signals,
dispatch,release,core}.py; this module re-exports the public+private surface
so existing `from control.analysis.stacks.detector import X` callers are
unchanged.
"""

from __future__ import annotations

from .detector_core import detect_stack
from .detector_dispatch import (
    _detect_architecture_framework,
    _detect_database_type,
    _detect_frontend_framework,
    _detect_monorepo_structure,
    _detect_test_framework,
    _detect_web_framework,
)
from .detector_release import (
    _detect_compliance_context,
    _detect_ops_context,
    _detect_release_context,
    _infer_service_type,
)
from .detector_shared import DetectedStack, StackSignal
from .detector_signals import _combine_signals, _detect_by_files

__all__ = [
    "DetectedStack",
    "StackSignal",
    "_combine_signals",
    "_detect_architecture_framework",
    "_detect_by_files",
    "_detect_compliance_context",
    "_detect_database_type",
    "_detect_frontend_framework",
    "_detect_monorepo_structure",
    "_detect_ops_context",
    "_detect_release_context",
    "_detect_test_framework",
    "_detect_web_framework",
    "_infer_service_type",
    "detect_stack",
]
