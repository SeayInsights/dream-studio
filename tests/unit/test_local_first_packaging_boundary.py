from __future__ import annotations

from core.release.packaging_boundary import (
    EXTERNAL_TARGET,
    IGNORED_TEMP,
    REPO_SOURCE,
    USER_LOCAL_STATE,
    classify_packaging_path,
    validate_packaging_boundary_manifest,
)


def test_packaging_boundary_classifies_repo_source_as_shippable() -> None:
    item = classify_packaging_path("/Users/example/builds/dream-studio/core/release/versioning.py")

    assert item["category"] == REPO_SOURCE
    assert item["ship_in_repo"] is True
    assert item["requires_manual_review"] is False


def test_packaging_boundary_keeps_user_local_state_out_of_repo() -> None:
    item = classify_packaging_path("/Users/example/.dream-studio/state/studio.db")

    assert item["category"] == USER_LOCAL_STATE
    assert item["ship_in_repo"] is False
    assert item["runtime_generated"] is True


def test_packaging_boundary_classifies_temp_and_external_targets() -> None:
    temp = classify_packaging_path("/Users/example/builds/dream-studio/.tmp/run/output.json")
    external = classify_packaging_path("/Users/example/builds/other-project/src/app.py")

    assert temp["category"] == IGNORED_TEMP
    assert temp["ship_in_repo"] is False
    assert external["category"] == EXTERNAL_TARGET
    assert external["requires_manual_review"] is True


def test_packaging_boundary_validator_rejects_unsafe_manifest_entries() -> None:
    issues = validate_packaging_boundary_manifest(
        [
            {"category": USER_LOCAL_STATE, "ship_in_repo": True},
            {"category": IGNORED_TEMP, "ship_in_repo": True},
            {"category": EXTERNAL_TARGET, "ship_in_repo": True},
            {"category": "manual_review", "requires_manual_review": False},
        ]
    )

    assert "item_0_user_local_state_must_not_ship_in_repo" in issues
    assert "item_1_ignored_temp_must_not_ship_in_repo" in issues
    assert "item_2_external_target_must_not_ship_in_repo" in issues
    assert "item_3_manual_review_not_marked" in issues
