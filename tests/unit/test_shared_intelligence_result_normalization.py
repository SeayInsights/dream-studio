from __future__ import annotations

from core.shared_intelligence.result_normalization import (
    normalize_adapter_result_payload,
)

# adapter_result_records dropped migration 131. record_normalized_adapter_result and
# adapter_result_summary are now no-op/empty stubs, so the SQLite-record tests that
# asserted a written row were deleted (tests of removed behavior). Only the pure
# payload-normalization function remains under test here.


def test_normalize_adapter_result_payload_maps_refs_and_status() -> None:
    normalized = normalize_adapter_result_payload(
        {
            "type": "code_change",
            "status": "passed",
            "decisions": "decision://1",
            "code_changes": ["git://commit"],
            "evidence": ["evidence://validation"],
            "validations": ["pytest://suite"],
            "research": ["research://note"],
            "risks": ["risk://low"],
            "artifacts": ["artifact://report"],
            "outcomes": ["outcome://complete"],
        }
    )

    assert normalized["result_type"] == "code_change"
    assert normalized["normalized_status"] == "validated"
    assert normalized["decision_refs"] == ["decision://1"]
    assert normalized["code_change_refs"] == ["git://commit"]
    assert normalized["validation_refs"] == ["pytest://suite"]
    assert normalized["payload"]["adapter_output_is_authority"] is False
