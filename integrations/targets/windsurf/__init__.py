"""Dream Studio integration target: windsurf (Phase 20).

Thin package marker; the placement spec lives in integrations.targets.registry
(TARGET_SPECS["windsurf"]) so all targets share one resolver.
"""

from __future__ import annotations

from integrations.targets.registry import get_target_spec

SPEC = get_target_spec("windsurf")
