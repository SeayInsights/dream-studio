"""Shared security-audit verdict detection for close gates (WO-SECGATE-BLOCKED-TOKEN).

The milestone-close security gate (core/milestones/close.py) and the work-order security_scan
gate (core/work_orders/close_gates.py) both fail a security artifact that reports a blocking
finding. That blocker must be detected by a FINDING MARKER, not a naive ``"BLOCKED" in text``
substring — otherwise an honest "No BLOCKED findings" / "0 BLOCKED" summary false-fails the gate
(the false-positive that blocked the Attribution Coherence milestone close). Centralized so both
gates share one definition.
"""

from __future__ import annotations

import re

# A genuine blocker is written as a finding or a verdict, never as the word "blocked" inside a
# negated summary. Match, case-insensitive, multiline:
#   - a finding line that BEGINS with BLOCKED (optionally bulleted): "BLOCKED ...", "- BLOCKED ..."
#   - an inline finding marker: "BLOCKED: <reason>"
#   - a status/result/verdict/finding line whose value is BLOCKED: "Status: BLOCKED",
#     "Finding: BLOCKED critical issue"
# "No BLOCKED findings" / "0 BLOCKED" do NOT match (BLOCKED is mid-line, uncoloned, not a verdict;
# "findings" is not the whole word "finding", so the negated summary never triggers the label rule).
_BLOCKED_FINDING_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?BLOCKED\b"
    r"|\bBLOCKED\s*:"
    r"|\b(?:status|result|verdict|finding)\b[^\n]*?:\s*BLOCKED\b"
)


def is_security_blocked(content: str | None) -> bool:
    """True when a security-audit/scan artifact reports a blocking finding.

    Detects a BLOCKED *finding marker* (see the regex above), so a negated or zeroed mention
    ("No BLOCKED findings", "0 BLOCKED") correctly passes.
    """
    return bool(_BLOCKED_FINDING_RE.search(content or ""))
