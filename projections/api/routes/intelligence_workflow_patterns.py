"""Intelligence API - workflow pattern detection endpoints (18.8.4).

WO-GF-API-ROUTES: split out of intelligence.py.
"""

from __future__ import annotations

from fastapi import HTTPException

from core.config.database import get_connection

from .intelligence_router import router

# ── Workflow Pattern Detection (18.8.4) ──────────────────────────────────────


@router.get("/workflow-patterns")
async def get_workflow_patterns(
    project_id: str | None = None,
    include_suppressed: bool = False,
    min_confidence: float = 0.0,
):
    """Return detected workflow skill co-occurrence patterns.

    Observation-only — no action. Phase 19 reads confidence_score >= 0.8
    AND suppressed = 0 as input to adaptive learning.

    Pattern types:
      - always_paired: two skills invoked together in the same session
      - post_completion: skill invoked after work order closes
      - pre_close: skill invoked just before work order closes
    """
    conn = get_connection()
    try:
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        analyzer = WorkflowPatternAnalyzer(conn)
        patterns = analyzer.get_patterns(
            project_id=project_id,
            include_suppressed=include_suppressed,
            min_confidence=min_confidence,
        )
        return {
            "patterns": patterns,
            "total": len(patterns),
            "project_id": project_id,
            "include_suppressed": include_suppressed,
            "min_confidence": min_confidence,
            "phase19_eligible": sum(
                1 for p in patterns if p["confidence_score"] >= 0.8 and not p["suppressed"]
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workflow patterns: {str(e)}")
    finally:
        conn.close()


@router.post("/workflow-patterns/{pattern_id}/suppress")
async def suppress_workflow_pattern(pattern_id: str):
    """Dismiss a workflow pattern — sets suppressed=1.

    Suppressed patterns:
      - Still visible via GET with include_suppressed=true
      - Excluded from Phase 19 adaptive learning reads
      - Will NOT be auto-re-surfaced on next analyze() run

    Operator action: 'This pattern isn't meaningful, don't act on it.'
    """
    conn = get_connection()
    try:
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        analyzer = WorkflowPatternAnalyzer(conn)
        updated = analyzer.suppress_pattern(pattern_id)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")
        return {"pattern_id": pattern_id, "suppressed": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to suppress pattern: {str(e)}")
    finally:
        conn.close()


@router.post("/workflow-patterns/analyze")
async def run_workflow_pattern_analysis(
    project_id: str | None = None,
    min_occurrences: int = 2,
    min_confidence: float = 0.3,
):
    """Run the pattern analyzer on canonical_events history.

    Detects all three pattern types and upserts to ds_workflow_pattern_signals.
    Typically called on session-end harvest. Can also be called on-demand.
    """
    conn = get_connection()
    try:
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        analyzer = WorkflowPatternAnalyzer(conn)
        signals = analyzer.analyze(
            project_id=project_id,
            min_occurrences=min_occurrences,
            min_confidence=min_confidence,
        )
        return {
            "signals_detected": len(signals),
            "project_id": project_id,
            "patterns_by_type": {
                "always_paired": sum(1 for s in signals if s["pattern_type"] == "always_paired"),
                "post_completion": sum(
                    1 for s in signals if s["pattern_type"] == "post_completion"
                ),
                "pre_close": sum(1 for s in signals if s["pattern_type"] == "pre_close"),
            },
            "high_confidence": sum(1 for s in signals if s["confidence_score"] >= 0.8),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pattern analysis failed: {str(e)}")
    finally:
        conn.close()
