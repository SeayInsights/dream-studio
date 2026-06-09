from __future__ import annotations

from pathlib import Path


def _valid_work_order(target_path: Path, **overrides) -> dict:
    data = {
        "work_order_id": "wo-valid-001",
        "project_name": "Dream Studio Test",
        "target_path": str(target_path),
        "objective": "Observe target readiness without changing files.",
        "approval_mode": "observe_only",
        "risk_level": "medium",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core", "ds-quality"],
        "allowed_agents": [],
        "workflow": "observe-only",
        "forbidden_actions": [
            "no edits, writes, patches, formats, or moves",
            "no commits, staging, or pushes",
            "no deletes or removes",
            "no schema changes",
            "no dependency or package changes",
            "no external actions, network calls, publishing, deploys, or cloud actions",
            "no target repo mutation",
        ],
        "validation_commands": ["python -m pytest -q"],
        "expected_outputs": ["status evidence"],
        "stop_conditions": ["target changes"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "draft",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }
    data.update(overrides)
    return data


def _messages(result) -> str:
    return "\n".join(issue.message for issue in result.issues)


def test_valid_work_order_passes_and_defaults_storage_class(tmp_path) -> None:
    from core.work_orders.validation import validate_work_order

    target = tmp_path / "target"
    target.mkdir()
    data = _valid_work_order(target)
    data.pop("storage_class")

    result = validate_work_order(data)

    assert result.ok is True
    assert result.work_order["storage_class"] == "file_backed"


def test_required_fields_are_enforced(tmp_path) -> None:
    from core.work_orders.validation import validate_work_order

    target = tmp_path / "target"
    target.mkdir()
    data = _valid_work_order(target)
    data.pop("objective")

    result = validate_work_order(data)

    assert result.ok is False
    assert any(issue.field == "objective" for issue in result.issues)


def test_target_path_must_be_absolute_and_exist_unless_allowed(tmp_path) -> None:
    from core.work_orders.validation import validate_work_order

    relative = _valid_work_order(tmp_path)
    relative["target_path"] = "relative/path"
    missing = _valid_work_order(tmp_path / "missing")

    relative_result = validate_work_order(relative)
    missing_result = validate_work_order(missing)
    allowed_missing_result = validate_work_order(missing, allow_missing_target=True)

    assert relative_result.ok is False
    assert "absolute path" in _messages(relative_result)
    assert missing_result.ok is False
    assert "does not exist" in _messages(missing_result)
    assert allowed_missing_result.ok is True


def test_contract_value_sets_are_enforced(tmp_path) -> None:
    from core.work_orders.validation import validate_work_order

    target = tmp_path / "target"
    target.mkdir()

    assert validate_work_order(_valid_work_order(target, approval_mode="bad")).ok is False
    assert validate_work_order(_valid_work_order(target, risk_level="bad")).ok is False
    assert validate_work_order(_valid_work_order(target, status="bad")).ok is False
    assert validate_work_order(_valid_work_order(target, storage_class="db_backed")).ok is False
    assert (
        validate_work_order(_valid_work_order(target, privacy_export_classification="public")).ok
        is False
    )


def test_allowed_skills_must_use_ds_slug_and_reject_legacy_forms(tmp_path) -> None:
    from core.work_orders.validation import validate_work_order

    target = tmp_path / "target"
    target.mkdir()
    legacy_product = "dream" "-studio" + ":core"
    legacy_ds = "d" "s" + ":core"

    valid = validate_work_order(_valid_work_order(target, allowed_skills=["ds-core"]))
    product = validate_work_order(_valid_work_order(target, allowed_skills=[legacy_product]))
    colon = validate_work_order(_valid_work_order(target, allowed_skills=[legacy_ds]))
    malformed = validate_work_order(_valid_work_order(target, allowed_skills=["core"]))

    assert valid.ok is True
    assert product.ok is False
    assert colon.ok is False
    assert malformed.ok is False


def test_observe_only_requires_explicit_forbidden_action_categories(tmp_path) -> None:
    from core.work_orders.validation import validate_work_order

    target = tmp_path / "target"
    target.mkdir()
    data = _valid_work_order(target, forbidden_actions=["no commits"])

    result = validate_work_order(data)

    assert result.ok is False
    messages = _messages(result)
    assert "edits" in messages
    assert "deletes" in messages
    assert "schema changes" in messages
    assert "dependency changes" in messages
    assert "external actions" in messages
    assert "target repo mutation" in messages
