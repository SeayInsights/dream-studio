"""Phase 13B enterprise/org/ML aggregation boundary guardrails.

The checks that read the adjacent ``dream-studio-enterprise`` checkout live in
``tests/install_checks/test_adjacent_enterprise_repo.py``: they describe another
repository on one machine and skip-when-absent in this suite could not fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "enterprise-aggregation-contract.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_enterprise_aggregation_contract_defines_required_boundaries():
    contract = _read(CONTRACT_PATH)

    for section in [
        "## Authority Principles",
        "## Allowed Enterprise Inputs",
        "## Forbidden Live DB Defaults",
        "## Redacted/Aggregate Projection Package Expectations",
        "## Explicit Operator-Selected Inputs",
        "## ML Artifact Classification",
        "## Org Graph And Report Classification",
        "## Import Boundary Rules",
        "## Enterprise Test Promotion Rules",
        "## Privacy And Export Constraints",
        "## Relationship To Other Contracts",
        "## Violations",
        "## Schema Posture",
    ]:
        assert section in contract

    contract_lower = contract.lower()
    for phrase in [
        "local runtime database remains authoritative",
        "optional derived consumers",
        "must not read `~/.dream-studio/state/studio.db`",
        "explicit operator-selected inputs",
        "redacted/aggregate projection packages",
        "derived enterprise-local artifacts",
        "derived aggregate projections",
        "not canonical authority",
        "not normal main validation",
        "phase 13b adds no schema migrations",
    ]:
        assert phrase in contract_lower


def test_main_repo_org_intelligence_is_a_real_package():
    """Verify org_intelligence bring-back complete: real package exists, stub removed.

    The projections/ml subsystem was removed in Wave 3 (2026-06-05); its
    package/route assertions were dropped here. org_intelligence is unaffected.
    """
    # Stub must be gone
    assert not (
        REPO_ROOT / "core" / "org_intelligence.py"
    ).exists(), "stub core/org_intelligence.py must be deleted after bring-back"

    # Real package must exist
    oi_pkg = REPO_ROOT / "core" / "org_intelligence"
    assert oi_pkg.is_dir(), "core/org_intelligence must be a package directory"
    assert (oi_pkg / "__init__.py").exists(), "core/org_intelligence/__init__.py missing"

