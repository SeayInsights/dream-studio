"""WO-SPLIT-HANDOFF: handoff security module — thin sub-facade.

Implementation lives in handoff_security_{shared,review_remediation,
remediation_mutation,post_remediation_review,evals}.py; this module
re-exports the public API so existing
`from core.work_orders.handoff_security import X` callers are unchanged.
"""

from __future__ import annotations

from .handoff_security_review_remediation import (
    build_security_review_remediation_handoff_prompt,
)
from .handoff_security_remediation_mutation import (
    build_security_remediation_mutation_handoff_prompt,
)
from .handoff_security_post_remediation_review import (
    build_security_post_remediation_review_handoff_prompt,
)
from .handoff_security_evals import (
    evaluate_security_post_remediation_review_handoff_prompt,
    evaluate_security_remediation_mutation_handoff_prompt,
    evaluate_security_review_next_handoff_prompt,
)

__all__ = [
    "build_security_post_remediation_review_handoff_prompt",
    "build_security_remediation_mutation_handoff_prompt",
    "build_security_review_remediation_handoff_prompt",
    "evaluate_security_post_remediation_review_handoff_prompt",
    "evaluate_security_remediation_mutation_handoff_prompt",
    "evaluate_security_review_next_handoff_prompt",
]
