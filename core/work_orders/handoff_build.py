"""WO-SPLIT-HANDOFF: handoff build module — thin sub-facade.

Implementation lives in handoff_build_{helpers,push,prompt,sections}.py; this
module re-exports the public API so existing
`from core.work_orders.handoff_build import X` callers are unchanged.
"""

from __future__ import annotations

from .handoff_build_prompt import build_handoff_prompt
from .handoff_build_sections import build_handoff_sections

__all__ = [
    "build_handoff_prompt",
    "build_handoff_sections",
]
