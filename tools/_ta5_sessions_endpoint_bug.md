# Finding: SessionMetrics Pydantic outcomes None key (TA5-followup)

**Discovered:** 2026-05-22 during TA5 dashboard testing
**Severity:** 500 error — `/api/v1/metrics/sessions` is completely broken

## Symptom

`GET /api/v1/metrics/sessions` returns HTTP 500:

```
Error collecting session metrics: ...
Pydantic validation error: SessionMetrics.outcomes — None is not a valid key
```

## Root Cause (suspected)

`SessionCollector.collect()` returns an `outcomes` dict that may contain `None` as a key when session records have a null outcome field. The `SessionMetrics` Pydantic model likely declares `outcomes: Dict[str, int]` (or similar), which rejects `None` keys at validation time.

## Pre-existing Status

This bug predates TA5. The sessions endpoint was not working before this PR and the TA5 changes do not touch session collection logic. Confirmed by checking: `projections/api/routes/metrics.py` `get_session_metrics()` still calls `SessionCollector(db_path).collect()` unchanged.

## Fix (future: TA5-followup)

1. Locate `SessionCollector.collect()` — filter or remap `None` outcome keys to a sentinel string (e.g., `"unknown"`) before returning
2. OR update the `SessionMetrics` model to accept `Optional[str]` keys via a validator
3. Ensure the fix handles the `get_all_metrics()` endpoint as well (it also calls `SessionCollector`)

## Scope of this PR (TA5)

No fix. Document only. Follow-on backlog entry: **TA5-followup: fix SessionMetrics Pydantic outcomes None key**.
