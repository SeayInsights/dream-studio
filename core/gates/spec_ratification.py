"""Ratified-contract gate logic — a contract-bearing WO's spec must be Ratified.

The `api_contract_exists` close gate reads the WO's `api_contract` artifact and, for
work orders created on or after the cutover, requires its lifecycle Status to be
`Ratified` (Draft/Reviewed blocks close). Work orders created before the cutover are
grandfathered to the prior exists-only behavior. See docs/specs/README.md.

`evaluate_api_contract` is pure (text + timestamps in, verdict out) so the gate stays a
thin caller and the behavior is unit-tested without a database.
"""

from __future__ import annotations

import re

# Ratification is enforced only for work orders created on or after this date (the
# date the gate shipped). Earlier WOs are grandfathered — see docs/specs/README.md.
# ISO-8601 date; compared lexicographically against the WO's ISO created_at.
RATIFY_ENFORCED_AFTER = "2026-08-02"

RATIFIED = "ratified"

# Matches "Status: Ratified" / "- **Status:** Ratified" (case-insensitive), taking the
# first Status line of the lifecycle header.
_STATUS_RE = re.compile(
    r"^\s*[-*]?\s*\**status\**\s*:\s*\**\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE
)


def parse_spec_status(text: str) -> str | None:
    """Return the lower-cased Status from a spec's lifecycle header, or None."""
    match = _STATUS_RE.search(text)
    return match.group(1).strip().lower() if match else None


def _is_grandfathered(wo_created_at: str | None, enforced_after: str) -> bool:
    """A WO with no known creation time, or created before the cutover, is exempt from
    ratification (but still needs the contract artifact to exist)."""
    if not wo_created_at:
        return True
    # ISO-8601 timestamps sort lexicographically; compare the date prefix.
    return wo_created_at[:10] < enforced_after


def evaluate_api_contract(
    contract_text: str | None,
    wo_created_at: str | None,
    *,
    enforced_after: str = RATIFY_ENFORCED_AFTER,
) -> tuple[bool, str]:
    """Return (passed, reason_core) for the api-contract gate. ``reason_core`` carries
    no gate-name prefix so both the ``api_contract_exists`` and
    ``api_contract_and_security_review`` gates can reuse it and prefix their own name.

    - No artifact  → fail (contract not found) — the prior behavior, unchanged.
    - Grandfathered WO (created before the cutover) → pass on existence alone.
    - Otherwise → pass only if the spec's Status is Ratified.
    """
    if contract_text is None:
        return False, "api-contract.md not found"
    if _is_grandfathered(wo_created_at, enforced_after):
        return True, ""
    status = parse_spec_status(contract_text)
    if status == RATIFIED:
        return True, ""
    shown = status or "missing"
    return (
        False,
        f"linked spec is not Ratified (status={shown}); "
        f"ratify the spec before close (see docs/specs/README.md)",
    )
