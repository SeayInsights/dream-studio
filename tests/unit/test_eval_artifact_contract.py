from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_CONTRACT = REPO_ROOT / "docs" / "contracts" / "eval-artifact-contract.md"
WORK_ORDER_CONTRACT = REPO_ROOT / "docs" / "contracts" / "work-order-contract.md"
WORK_RESULT_CONTRACT = REPO_ROOT / "docs" / "contracts" / "work-result-contract.md"
OPERATIONS_DOC = REPO_ROOT / "docs" / "operations" / "work-orders.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_eval_artifact_contract_documents_minimum_fields() -> None:
    text = _read(EVAL_CONTRACT)

    required_fields = [
        "eval_id",
        "eval_type",
        "subject_type",
        "subject_id",
        "linked_work_order_id",
        "input_artifact",
        "expected_behavior",
        "observed_behavior",
        "score",
        "pass_fail",
        "evaluator",
        "evidence",
        "privacy_export_classification",
        "created_at",
    ]

    missing = [field for field in required_fields if field not in text]

    assert missing == []


def test_eval_artifact_contract_documents_subject_and_evaluator_types() -> None:
    text = _read(EVAL_CONTRACT)

    subject_types = [
        "skill",
        "agent",
        "workflow",
        "work_order",
        "model",
        "tool",
        "research",
        "approval",
    ]
    evaluator_types = [
        "deterministic",
        "human",
        "rubric",
        "model_assisted",
    ]

    missing_subject_types = [
        subject_type for subject_type in subject_types if subject_type not in text
    ]
    missing_evaluator_types = [
        evaluator_type for evaluator_type in evaluator_types if evaluator_type not in text
    ]

    assert missing_subject_types == []
    assert missing_evaluator_types == []


def test_required_phase16_eval_types_are_documented() -> None:
    eval_contract = _read(EVAL_CONTRACT)
    operations = _read(OPERATIONS_DOC)

    required_eval_types = [
        "work_order_render_completeness",
        "skill_identifier_safety",
        "observe_only_compliance",
        "forbidden_action_compliance",
        "target_repo_mutation",
        "result_report_completeness",
        "next_work_order_recommendation",
    ]

    missing_from_contract = [
        eval_type for eval_type in required_eval_types if eval_type not in eval_contract
    ]
    missing_from_operations = [
        eval_type for eval_type in required_eval_types if eval_type not in operations
    ]

    assert missing_from_contract == []
    assert missing_from_operations == []


def test_eval_artifacts_are_file_backed_evidence_not_authority() -> None:
    text = _read(EVAL_CONTRACT)

    assert "Eval artifacts are evidence, not canonical runtime state" in text
    assert "Phase 16 eval artifacts are file-backed only" in text
    assert "Eval artifacts do not write real-runtime-DB events by default" in text
    assert "Eval artifacts do not create schema migrations or DB tables" in text
    assert "local_only" in text


def test_work_order_and_result_contracts_link_to_eval_artifacts() -> None:
    work_order = _read(WORK_ORDER_CONTRACT)
    work_result = _read(WORK_RESULT_CONTRACT)

    assert "Eval artifact contract" in work_order
    assert "eval_artifacts" in work_result
    assert "next_work_order_recommendation" in work_result
