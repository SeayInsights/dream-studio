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
    # backend-api/frontend-ux were folded into fullstack:backend/frontend's `audit`
    # sub-modes in the pack-split campaign's fullstack merge -- neither is an
    # invocable mode name on its own any more, so the recommendation must name the
    # real modes (backend, frontend) rather than dead targets.
    assert "backend" in modes
    assert "backend-api" not in modes
    assert "frontend" in modes
    assert "frontend-ux" not in modes
    assert "database" in modes
    # Every recommendation carries a reason and its mode's ACTUAL current pack --
    # not a single hardcoded pack for all of them (the pack-split campaign has
    # moved several of these modes since this test was first written).
    by_mode = {r["mode"]: r for r in recs}
    assert by_mode["backend"]["pack"] == "ds-fullstack"
    assert "audit" in by_mode["backend"]["reason"]
    assert by_mode["frontend"]["pack"] == "ds-fullstack"
    assert "audit" in by_mode["frontend"]["reason"]
    assert by_mode["database"]["pack"] == "ds-data"
    assert all(r["reason"] for r in recs)


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
    # database-compliance was folded into comply's `privacy` sub-mode in the
    # pack-split campaign's security merge -- "database-compliance" is no longer
    # an invocable mode name, so the recommendation must name the real mode
    # (comply) rather than a dead target, with the sub-mode named in the reason.
    assert "comply" in modes
    assert "database-compliance" not in modes
    assert "pre-launch" in modes
    # The compliance reason surfaces the detected hint and the real invocation.
    dc = next(r for r in recs if r["mode"] == "comply")
    assert "gdpr" in dc["reason"]
    assert "privacy" in dc["reason"]
    assert dc["pack"] == "ds-security"
    pl = next(r for r in recs if r["mode"] == "pre-launch")
    assert pl["pack"] == "ds-release"


def test_recommendations_are_deduped_and_stable():
    stack = {"web_framework": "django-rest", "architecture_framework": "nestjs"}
    recs = recommend_dispatches(stack)
    modes = _modes(recs)
    assert modes == ["backend", "architecture"]
    assert len(modes) == len(set(modes))
