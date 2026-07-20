"""WO-BROWNFIELD-OFFER-INVOKE: fold operator-approved audit findings into the
brownfield readiness report + stabilization scope.

Follow-on to WO-BROWNFIELD-ADAPTIVE (present-only routing). These tests cover the
aggregation step: the recommended audits are offered (never auto-run), and once
their findings are persisted, `aggregate_findings` / `aggregate_readiness` fold
them into a per-project readiness report and a severity-ordered stabilization
scope. The engine only CONSUMES already-persisted findings — it never runs an audit.
"""

from __future__ import annotations

from core.projects.acquisition import aggregate_findings, aggregate_readiness
from core.projects.adaptive_routing import recommend_dispatches


def _web_db_findings() -> list[dict[str, object]]:
    return [
        {
            "rule_id": "sql-injection",
            "severity": "critical",
            "file_path": "db.py",
            "description": "raw SQL",
        },
        {
            "rule_id": "missing-authz",
            "severity": "high",
            "file_path": "api.py",
            "description": "no authz",
        },
        {
            "rule_id": "n-plus-one",
            "severity": "medium",
            "file_path": "api.py",
            "description": "n+1 query",
        },
    ]


def test_web_db_project_aggregates_findings_into_readiness_and_scope():
    # A web+db project routes to backend-api + database audits (WO-BROWNFIELD-ADAPTIVE).
    dispatches = recommend_dispatches({"web_framework": "fastapi", "database_type": "postgres"})
    modes = [d["mode"] for d in dispatches]
    assert "backend-api" in modes and "database" in modes

    result = aggregate_findings(_web_db_findings(), dispatches)
    report = result["readiness_report"]

    # Readiness report lists the findings sourced from the recommended audits.
    assert report["finding_count"] == 3
    assert report["findings"] == _web_db_findings()
    assert report["severity_counts"] == {"critical": 1, "high": 1, "medium": 1}
    assert "ds-quality:backend-api" in report["audits"]
    assert "ds-quality:database" in report["audits"]

    # Stabilization scope reflects those findings, ordered highest-severity first.
    scope = result["stabilization_scope"]
    assert [item["severity"] for item in scope] == ["critical", "high", "medium"]
    assert scope[0]["count"] == 1 and scope[0]["files"] == ["db.py"]
    # api.py backs both the high and medium items.
    assert scope[1]["files"] == ["api.py"]


def test_no_findings_yields_empty_scope():
    result = aggregate_findings([], recommend_dispatches({"web_framework": "django"}))
    assert result["readiness_report"]["finding_count"] == 0
    assert result["readiness_report"]["severity_counts"] == {}
    assert result["stabilization_scope"] == []


def test_aggregate_readiness_folds_persisted_scan_findings(monkeypatch):
    # aggregate_readiness reads findings the approved audits already persisted
    # (via get_scan_summary) — it never runs an audit itself.
    import core.projects.intake as intake

    monkeypatch.setattr(
        intake,
        "get_scan_summary",
        lambda project_id: {"project_id": project_id, "findings": _web_db_findings()},
    )
    dispatches = recommend_dispatches({"web_framework": "fastapi", "database_type": "postgres"})
    result = aggregate_readiness("proj-1", dispatches=dispatches)

    assert result["ok"] is True
    assert result["project_id"] == "proj-1"
    assert result["readiness_report"]["finding_count"] == 3
    assert result["recommended_dispatches"] == dispatches
    # Highest-severity stabilization item leads.
    assert result["stabilization_scope"][0]["severity"] == "critical"


def test_unknown_severity_sorts_last():
    findings = [
        {"severity": "weird", "file_path": "x.py"},
        {"severity": "high", "file_path": "y.py"},
    ]
    scope = aggregate_findings(findings)["stabilization_scope"]
    assert [item["severity"] for item in scope] == ["high", "weird"]
