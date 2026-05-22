# TA5 Fabricator Inventory
_Audit date: 2026-05-22_

## Summary

**Total fabricators found: 2** (the exact count the audit named). Proceed without operator review gate.

---

## Fabricator 1 — `_build_skill_costs`

**File:** `projections/api/routes/metrics.py:59–89`
**Caller:** `get_token_metrics()` at line 396 (fallback branch when `has_skill_costs` is False)

### What it returns
```python
{
    skill_name: {
        "skill_name": skill_name,
        "total_tokens": 0,          # ← HARDCODED ZERO
        "invocations": r["cnt"],    # ← real invocation count
        "cost_usd": None,           # ← fabricated None
        "cost": None,               # ← fabricated None
        "cost_visibility": "unavailable",  # ← always unavailable
        "cost_status": "unknown",   # ← always unknown
    }
}
```

### Why it's a fabricator
`total_tokens: 0` is hardcoded for every skill. `cost_usd: None`. The function returns a plausible-looking dict structure but every numeric field is either zero or None. The dashboard displays `$0.00` cost and `0 tokens` for all skills when this fallback runs — fabricated data.

### Data source used
`skill_invocations` via `skill_usage_sql()` (legacy table, not canonical_events).

### Replacement
Return `{}` (empty dict) with `data_status: "empty"` when no real skill cost data exists. The `by_skill` field should be absent or empty rather than populated with synthetic zeros.

---

## Fabricator 2 — `_build_exec_time_ranges`

**File:** `projections/api/routes/metrics.py:92–119`
**Caller:** `get_skill_metrics()` at line 304

### What it returns
```python
{
    skill_name: {
        "min_m": <float>,  # from skill_invocations.execution_time_s
        "max_m": <float>,  # (often NULL → 0.0)
    }
}
```

### Why it's a fabricator (per audit)
Reads `execution_time_s` from `skill_invocations.metadata_json`. This field is sparsely populated — most rows have NULL, which silently maps to `min_m: 0.0`, `max_m: 0.0`. The dashboard displays "0 min – 0 min" ranges as if real. The underlying `skill_invocations` table is a legacy store (pre-canonical_events), not the authoritative source.

### Data source used
`skill_invocations` via `skill_usage_sql()` (legacy table).

### Replacement
Query `canonical_events` where `event_type = 'skill.executed'`, extract `json_extract(payload, '$.duration_ms')`, group by `json_extract(payload, '$.skill_name')`. If no data, return empty dict → min/max duration fields become 0 with `data_status: "empty"`.

---

## Non-Fabricator `_build_*` Functions in metrics.py (audit clear)

| Function | Source | Verdict |
|----------|--------|---------|
| `_build_token_timeline` | `token_usage_records` via `token_usage_sql()` | Real data — keep |
| `_build_success_trend` | `skill_invocations` via `skill_usage_sql()` | Real data from legacy table — out of TA5 scope |
| `_build_skill_heatmap` | `skill_invocations` via `skill_usage_sql()` | Real data from legacy table — out of TA5 scope |

---

## Other `_build_*` Patterns Scanned

Scanned all `*.py` in `projections/` for `_build_` functions containing hardcoded zeros, `cost.*None`, or synthesized data patterns. Found no additional fabricators. The other `_build_*` methods in:
- `projections/generators/production_dashboard.py` — HTML builder, not a data fabricator
- `projections/exporters/powerbi_exporter.py` — table shape builders, reads from collector output
- `projections/core/reports/generator.py` — summary section builders, reads from collector output

---

## Decision

**2 fabricators confirmed.** Matches the audit exactly. Proceeding with deletion and replacement per TA5 plan.
