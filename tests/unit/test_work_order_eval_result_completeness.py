from __future__ import annotations

import json
from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {"work_order_id": "wo-report-eval-001", "target_path": str(target_path)}


def test_result_report_completeness_eval_passes_for_required_sections(tmp_path) -> None:
    from core.work_orders.evals import REQUIRED_REPORT_TERMS, create_result_report_completeness_eval

    target = tmp_path / "target"
    target.mkdir()
    report = tmp_path / "report.md"
    report_text = "\n".join(REQUIRED_REPORT_TERMS) + "\n"
    report.write_text(report_text, encoding="utf-8")

    artifact, path = create_result_report_completeness_eval(
        work_order=_work_order(target),
        report_path=report,
        report_text=report_text,
        result_exists=True,
        storage_root=tmp_path / "store",
    )
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert artifact["pass_fail"] == "pass"
    assert stored["eval_type"] == "result_report_completeness"


def test_result_report_completeness_eval_fails_for_missing_sections(tmp_path) -> None:
    from core.work_orders.evals import create_result_report_completeness_eval

    target = tmp_path / "target"
    target.mkdir()
    report = tmp_path / "report.md"
    report_text = "Objective\n"
    report.write_text(report_text, encoding="utf-8")

    artifact, _ = create_result_report_completeness_eval(
        work_order=_work_order(target),
        report_path=report,
        report_text=report_text,
        result_exists=True,
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "fail"
    assert "missing required evidence" in artifact["observed_behavior"]
