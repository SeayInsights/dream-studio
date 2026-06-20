"""Dream Studio integration target: cursor (Phase 20).

Thin package marker; the placement spec lives in integrations.targets.registry
(TARGET_SPECS["cursor"]) so all targets share one resolver.
"""

from __future__ import annotations

from integrations.targets.registry import get_target_spec

SPEC = get_target_spec("cursor")
