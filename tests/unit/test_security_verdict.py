"""WO-SECGATE-BLOCKED-TOKEN: the shared security-verdict detector flags a BLOCKED *finding*, not
the substring — so an honest 'No BLOCKED findings' / '0 BLOCKED' summary passes the close gates."""

from __future__ import annotations

import pytest

from core.gates.security_verdict import is_security_blocked


@pytest.mark.parametrize(
    "text",
    [
        "BLOCKED — critical RCE in auth handler",  # finding line at start
        "- BLOCKED: hardcoded secret in config",  # bulleted finding
        "BLOCKED: SQL injection in report query",  # inline finding marker
        "Status: BLOCKED",  # verdict line
        "Result: BLOCKED — do not ship",  # verdict line
        "Finding: BLOCKED critical issue",  # labelled finding (no colon after BLOCKED, not line-start)
    ],
)
def test_real_blocker_is_detected(text: str) -> None:
    assert is_security_blocked(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "No BLOCKED findings. No CRITICAL or HIGH issues.",  # negated summary
        "0 BLOCKED, 0 critical.",  # zeroed count
        "Result: CLEAR. Nothing that blocks milestone completion.",  # 'blocks' != BLOCKED
        "All checks passed; the change is unblocked and safe.",  # 'unblocked'
        "",  # empty
        None,  # missing artifact text
    ],
)
def test_negated_or_clear_is_not_blocked(text) -> None:
    assert is_security_blocked(text) is False
