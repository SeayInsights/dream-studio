from __future__ import annotations

from core.shared_intelligence.maturity_ledger import (
    REQUIRED_AREA_IDS,
    maturity_ledger,
    validate_maturity_ledger,
)


def test_maturity_ledger_covers_required_dream_studio_areas() -> None:
    ledger = maturity_ledger(project_id="dream-studio")

    assert validate_maturity_ledger(ledger) == []
    assert ledger["derived_view"] is True
    assert ledger["primary_authority"] is False
    assert ledger["db_write_authorized"] is False
    area_ids = {area["area_id"] for area in ledger["areas"]}
    assert REQUIRED_AREA_IDS <= area_ids
    assert ledger["status_counts"]["runtime_validated"] >= 8
    assert ledger["status_counts"]["tested_only"] >= 4
    assert ledger["status_counts"].get("designed_not_proven", 0) >= 0


def test_maturity_ledger_marks_unproven_adapter_execution_honestly() -> None:
    ledger = maturity_ledger(project_id="dream-studio")
    areas = {area["area_id"]: area for area in ledger["areas"]}

    assert areas["claude_adapter"]["status"] == "tested_only"
    assert areas["claude_adapter"]["can_claim_publicly"] is False
    assert "unproven" in " ".join(areas["claude_adapter"]["known_gaps"])
    assert areas["codex_adapter"]["status"] == "tested_only"
    assert areas["codex_adapter"]["can_claim_publicly"] is False
    assert areas["contract_atlas"]["can_use_operationally"] is True
    assert areas["docker_runtime_profiles"]["status"] == "tested_only"
    assert areas["docker_runtime_profiles"]["can_use_operationally"] is True
    assert areas["external_project_pipeline"]["status"] == "runtime_validated"
    assert areas["analytics_only_profile"]["status"] == "runtime_validated"


def test_maturity_ledger_validator_rejects_missing_evidence() -> None:
    ledger = maturity_ledger()
    ledger["areas"][0]["evidence"] = []

    errors = validate_maturity_ledger(ledger)

    assert f"area {ledger['areas'][0]['area_id']} missing evidence" in errors
