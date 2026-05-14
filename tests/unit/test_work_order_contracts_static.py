from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO_ROOT / "docs" / "contracts"
OPERATIONS_ROOT = REPO_ROOT / "docs" / "operations"

WORK_ORDER_DOCS = [
    CONTRACT_ROOT / "work-order-contract.md",
    CONTRACT_ROOT / "approval-contract.md",
    CONTRACT_ROOT / "execution-packet-contract.md",
    CONTRACT_ROOT / "work-result-contract.md",
    CONTRACT_ROOT / "work-ledger-contract.md",
    CONTRACT_ROOT / "human-in-the-loop-contract.md",
    CONTRACT_ROOT / "eval-artifact-contract.md",
    CONTRACT_ROOT / "security-review-profile-pack-contract.md",
    OPERATIONS_ROOT / "work-orders.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _all_work_order_contract_text() -> str:
    return "\n".join(_read(path) for path in WORK_ORDER_DOCS)


def test_phase16a_required_contract_docs_exist() -> None:
    missing = [str(path.relative_to(REPO_ROOT)) for path in WORK_ORDER_DOCS if not path.exists()]

    assert missing == []


def test_work_order_contract_documents_required_fields() -> None:
    text = _read(CONTRACT_ROOT / "work-order-contract.md")

    required_fields = [
        "work_order_id",
        "project_name",
        "target_path",
        "objective",
        "approval_mode",
        "risk_level",
        "scope.include",
        "scope.exclude",
        "allowed_skills",
        "allowed_agents",
        "workflow",
        "forbidden_actions",
        "validation_commands",
        "expected_outputs",
        "stop_conditions",
        "created_by",
        "created_at",
        "status",
        "storage_class",
        "privacy_export_classification",
    ]

    missing = [field for field in required_fields if field not in text]

    assert missing == []
    assert "file_backed" in text
    assert "ds-<slug>" in text
    assert "Authority Principles" in text


def test_approval_contract_documents_modes_states_and_human_gate() -> None:
    text = _read(CONTRACT_ROOT / "approval-contract.md")

    expected_terms = [
        "observe_only",
        "render_only",
        "manual_execute",
        "approval_required",
        "blocked",
        "not_required",
        "requested",
        "approved",
        "rejected",
        "expired",
        "revoked",
        "file-backed",
        "No mutation is allowed without explicit approval",
    ]

    missing = [term for term in expected_terms if term not in text]

    assert missing == []


def test_execution_packet_contract_documents_targets_and_render_only_fields() -> None:
    text = _read(CONTRACT_ROOT / "execution-packet-contract.md")

    expected_terms = [
        "codex",
        "claude",
        "chatgpt",
        "cursor",
        "manual",
        "docker_sandbox",
        "packet_id",
        "target",
        "linked_work_order_id",
        "evidence_requirements",
        "render_only",
        "Renderers must not",
        "execute the packet",
    ]

    missing = [term for term in expected_terms if term not in text]

    assert missing == []


def test_work_result_contract_documents_result_evidence_shape() -> None:
    text = _read(CONTRACT_ROOT / "work-result-contract.md")

    expected_terms = [
        "result_id",
        "linked_work_order_id",
        "raw_output_ref",
        "structured_findings",
        "validation_results",
        "eval_artifacts",
        "next_work_order_recommendation",
        "privacy_export_classification",
        "local/private by default",
        "does not create or approve the next Work Order automatically",
    ]

    missing = [term for term in expected_terms if term not in text]

    assert missing == []


def test_ledger_and_human_contracts_document_file_backed_non_delegable_control() -> None:
    ledger = _read(CONTRACT_ROOT / "work-ledger-contract.md")
    human = _read(CONTRACT_ROOT / "human-in-the-loop-contract.md")
    schema_updates = "schema " + "migra" + "tions"

    assert "Phase 16 ledger is file-backed only" in ledger
    assert "DB/event integration is deferred" in ledger
    assert "Future event names" in ledger
    assert "must not imply real-runtime-DB writes" in ledger
    assert "add Work Order DB tables in Phase 16" in ledger
    assert f"{schema_updates} in Phase 16" in ledger

    assert "operator" in human
    assert "reviewer" in human
    assert "executor" in human
    assert "observer" in human
    assert "approve_manual_execution" in human
    assert "Non-Delegable Actions" in human
    assert "cannot be delegated" in human


def test_operations_doc_describes_phase16a_as_contract_only() -> None:
    text = _read(OPERATIONS_ROOT / "work-orders.md")

    expected_terms = [
        "contract and static guardrails only",
        "There is no Work Order CLI",
        "file-backed only",
        "Planned Commands",
        "create",
        "validate",
        "render",
        "record-result",
        "report",
        "These commands must not mutate target repos during Phase 16",
        "DreamySuite is Phase 17 only",
    ]

    missing = [term for term in expected_terms if term not in text]

    assert missing == []


def test_work_order_contracts_do_not_introduce_forbidden_skill_identifier_literals() -> None:
    text = _all_work_order_contract_text()
    legacy_product_prefix = "dream" "-studio" + ":"
    quoted_legacy_ds_prefix = '"' + "d" "s" + ":"
    backticked_legacy_ds_prefix = "`" + "d" "s" + ":"

    assert legacy_product_prefix not in text
    assert quoted_legacy_ds_prefix not in text
    assert backticked_legacy_ds_prefix not in text
