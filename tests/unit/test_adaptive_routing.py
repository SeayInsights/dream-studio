"""WO-BROWNFIELD-ADAPTIVE: detected stack signals -> relevant ds-quality modes."""

from __future__ import annotations

from core.projects.adaptive_routing import recommend_dispatches


def _modes(recs):
    return [r["mode"] for r in recs]


def test_empty_or_none_returns_no_recommendations():
    assert recommend_dispatches(None) == []
    assert recommend_dispatches({}) == []
    # Adapter with no dispatch signals -> nothing to route.
    assert recommend_dispatches({"adapter": "python", "confidence": 0.9}) == []


def test_web_and_frontend_and_db_map_to_modes():
    recs = recommend_dispatches(
        {
            "web_framework": "fastapi",
            "frontend_framework": "react",
            "database_type": "postgres",
        }
    )
    modes = _modes(recs)
    assert "backend-api" in modes
    assert "frontend-ux" in modes
    assert "database" in modes
    # Every recommendation targets the ds-quality pack and carries a reason.
    assert all(r["pack"] == "ds-quality" and r["reason"] for r in recs)


def test_ops_signals_map_to_ops_once():
    recs = recommend_dispatches(
        {"has_dockerfile": True, "has_k8s_manifest": True, "deployment_type": "container"}
    )
    # Multiple ops signals collapse to a single ops recommendation (deduped).
    assert _modes(recs) == ["ops"]


def test_compliance_and_prelaunch_signals():
    recs = recommend_dispatches(
        {"has_pii_schema": True, "compliance_hints": ["gdpr"], "service_type": "consumer"}
    )
    modes = _modes(recs)
    assert "database-compliance" in modes
    assert "pre-launch" in modes
    # The compliance reason surfaces the detected hint.
    dc = next(r for r in recs if r["mode"] == "database-compliance")
    assert "gdpr" in dc["reason"]


def test_recommendations_are_deduped_and_stable():
    stack = {"web_framework": "django-rest", "architecture_framework": "nestjs"}
    recs = recommend_dispatches(stack)
    modes = _modes(recs)
    assert modes == ["backend-api", "architecture"]
    assert len(modes) == len(set(modes))
