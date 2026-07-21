from __future__ import annotations

from pathlib import Path


def _work_order(target_path: Path, *, work_order_id: str = "wo-report-001") -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "Report Test",
        "target_path": str(target_path),
        "objective": "Generate file-backed report evidence.",
        "approval_mode": "observe_only",
        "risk_level": "low",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core"],
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
        "expected_outputs": ["report"],
        "stop_conditions": ["mutation"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "validated",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _result_text() -> str:
    return "\n".join(
        [
            "Summary: Report-ready result.",
            "Files inspected: README.md",
            "Files changed: none",
            "Commands: not run",
            "Forbidden actions: complied",
            "Target mutation: no",
            "Warnings: none",
            "Risks: none",
            "Next Work Order: Objective: review generated report; Risk: low; Approval: observe_only; Non-goals: mutation; Validation: static checks.",
            "",
        ]
    )


def _snapshot(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): item.read_text(encoding="utf-8")
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_generate_report_includes_result_eval_summary_and_marks_reported(tmp_path) -> None:
    from core.work_orders.packet_store import get_packet_artifact
    from core.work_orders.renderers import render_work_order
    from core.work_orders.reporting import generate_report
    from core.work_orders.results import record_result
    from core.work_orders.storage import load_work_order, save_work_order

    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("before\n", encoding="utf-8")
    before = _snapshot(target)
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)
    render_work_order("wo-report-001", target="codex", storage_root=storage_root)
    source = tmp_path / "result.md"
    source.write_text(_result_text(), encoding="utf-8")
    record_result("wo-report-001", source_path=source, storage_root=storage_root)

    result = generate_report("wo-report-001", storage_root=storage_root)
    # WO-FILESDB-C5: report body lives in the packet store (kind='report'), not report.md.
    report_text = get_packet_artifact("wo-report-001", "report", storage_root=storage_root)
    assert report_text is not None
    stored, _ = load_work_order("wo-report-001", storage_root=storage_root)

    assert result["result_present"] is True
    assert stored["status"] == "reported"
    assert "## Objective" in report_text
    assert "## Rendered Packet Paths" in report_text
    assert "## Raw Result Reference" in report_text
    assert "## Eval Artifact Summary" in report_text
    assert "## Proven" in report_text
    assert "## Failed" in report_text
    assert "## Incomplete / Unavailable" in report_text
    assert "## Next Recommended Work Order" in report_text
    assert "work_order_render_completeness" in report_text
    assert "result_report_completeness" in report_text
    assert "recommended_next_work_order: none" in report_text
    # WO-FILESDB-C3: eval artifacts live in the packet store (kind='eval', instance_key=eval_type).
    assert (
        get_packet_artifact(
            "wo-report-001",
            "eval",
            instance_key="result_report_completeness",
            storage_root=storage_root,
        )
        is not None
    )
    assert (
        get_packet_artifact(
            "wo-report-001",
            "eval",
            instance_key="next_work_order_recommendation",
            storage_root=storage_root,
        )
        is None
    )
    assert _snapshot(target) == before


def test_generate_report_without_result_is_incomplete_and_does_not_mark_reported(tmp_path) -> None:
    from core.work_orders.packet_store import get_packet_artifact
    from core.work_orders.reporting import generate_report
    from core.work_orders.storage import load_work_order, save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(
        _work_order(target, work_order_id="wo-report-missing-001"), storage_root=storage_root
    )

    result = generate_report("wo-report-missing-001", storage_root=storage_root)
    # WO-FILESDB-C5: report body lives in the packet store (kind='report'), not report.md.
    report_text = get_packet_artifact("wo-report-missing-001", "report", storage_root=storage_root)
    assert report_text is not None
    stored, _ = load_work_order("wo-report-missing-001", storage_root=storage_root)

    assert result["result_present"] is False
    assert stored["status"] == "validated"
    assert "Report status: incomplete / unavailable" in report_text
    assert "result evidence unavailable" in report_text
