"""WO-SPLIT-HANDOFF: handoff validate module — thin sub-facade.

Implementation lives in handoff_validate_{sections,dryrun,evals,regenerate}.py;
this module re-exports the public API so existing
`from core.work_orders.handoff_validate import X` callers are unchanged.
"""

from __future__ import annotations

from .handoff_validate_sections import parse_prompt_sections
from .handoff_validate_dryrun import dry_run_handoff_prompt
from .handoff_validate_evals import evaluate_handoff_prompt
from .handoff_validate_regenerate import (
    regenerate_handoff_prompt,
    self_validate_generated_handoff,
)

__all__ = [
    "dry_run_handoff_prompt",
    "evaluate_handoff_prompt",
    "parse_prompt_sections",
    "regenerate_handoff_prompt",
    "self_validate_generated_handoff",
]
