# Decision Query Layer — Usage Examples

## Basic Queries

### 1. Query decisions by type
```python
from core.decisions import query

# Get all trust score decisions
decisions = query.decisions().where("trust_score.assignment").execute()

# Get TTL assignment decisions
ttl_decisions = query.decisions().where("ttl.assignment").execute()

# Get unlock pattern matches
unlock_decisions = query.decisions().where("unlock_pattern.match").execute()
```

### 2. Filter by confidence threshold
```python
# Get high-confidence decisions only
high_confidence = (
    query.decisions()
    .where("trust_score.assignment")
    .min_confidence(0.7)
    .execute()
)
```

### 3. Filter by subsystem
```python
# Get all decisions made by research engine
research_decisions = (
    query.decisions()
    .from_subsystem("research_engine")
    .execute()
)

# Get all guardrail decisions
guardrail_decisions = (
    query.decisions()
    .from_subsystem("guardrails")
    .execute()
)
```

### 4. Combine filters
```python
# Get high-confidence trust score decisions from research engine
decisions = (
    query.decisions()
    .where("trust_score.assignment")
    .from_subsystem("research_engine")
    .min_confidence(0.8)
    .limit(50)
    .execute()
)
```

## Explanation Queries

### 5. Explain a specific decision
```python
# Get full explanation with reasoning
explanation = query.explain("abc-123-decision-id")

print(f"Decision type: {explanation['decision'].decision_type}")
print(f"Outcome: {explanation['decision'].outcome}")
print(f"Reasoning: {explanation['reasoning']}")
print(f"Policy: {explanation['policy_applied']}")
print(f"Linked events: {len(explanation['linked_events'])}")
```

### 6. Trace event to decisions
```python
# Find what decisions were made because of an event
trace = query.trace("event-id-123")

print(f"Event: {trace['event']['event_type']}")
print(f"Decisions made: {len(trace['decisions_made'])}")
print(f"Events caused: {len(trace['caused_events'])}")

for decision in trace['decisions_made']:
    print(f"  - {decision['decision_type']}: {decision['outcome']}")
```

## Audit Queries

### 7. Audit trust score decisions
```python
# Get distribution of trust scores
audit = query.audit("trust_score.assignment")

print(f"Total decisions: {audit['total_decisions']}")
print(f"Outcome distribution: {audit['outcome_distribution']}")
print(f"Confidence histogram: {audit['confidence_histogram']}")
print(f"Policies used: {audit['policies_used']}")
```

### 8. Audit TTL assignments
```python
# Analyze TTL decision patterns
audit = query.audit("ttl.assignment")

print(f"Common reasoning factors: {audit['common_reasoning_factors']}")
print(f"Outcome distribution: {audit['outcome_distribution']}")
```

## Real-World Usage

### 9. Answer "Why did this research get cached?"
```python
# Find the trust score decision for a specific query
decisions = (
    query.decisions()
    .where("trust_score.assignment")
    .execute()
)

for decision in decisions:
    if decision.context.get("query_hash") == "abc123...":
        print(f"Trust score: {decision.outcome}")
        print(f"Reason: {decision.reasoning['rationale']}")
        print(f"Policy: {decision.policy_applied}")
```

### 10. Answer "Why was this mode unlocked?"
```python
# Find unlock decisions for a specific pack
decisions = (
    query.decisions()
    .where("unlock_pattern.match")
    .execute()
)

for decision in decisions:
    if decision.context.get("pack") == "security":
        print(f"Matched pattern: {decision.context['pattern']}")
        print(f"Confidence: {decision.confidence}")
        print(f"Reasoning: {decision.reasoning['rationale']}")
```

### 11. Answer "What policy caused this block?"
```python
# Find guardrail enforcement decisions
decisions = (
    query.decisions()
    .where("guardrail.policy_enforcement")
    .execute()
)

for decision in decisions:
    if decision.outcome == "block":
        print(f"Triggered rules: {decision.reasoning['triggered_rule_ids']}")
        print(f"Policy: {decision.policy_applied}")
```

### 12. Detect inconsistent reasoning
```python
# Audit trust score decisions to find patterns
audit = query.audit("trust_score.assignment")

# Check if same source types get different scores
reasoning_factors = audit['common_reasoning_factors']
if 'rule' in reasoning_factors:
    print("Trust score rules applied:")
    for rule, count in reasoning_factors['rule'].items():
        print(f"  - {rule}: {count} times")
```

## Direct SQL (Advanced)

For complex queries not covered by the fluent API:

```python
from core.event_store.studio_db import _connect

with _connect() as conn:
    # Find decisions with low confidence that led to actions
    rows = conn.execute("""
        SELECT d.decision_id, d.decision_type, d.outcome, d.confidence, d.reasoning
        FROM decision_log d
        WHERE d.confidence < 0.5
          AND EXISTS (
              SELECT 1 FROM canonical_events e
              WHERE json_extract(e.payload, '$.decision_id') = d.decision_id
          )
    """).fetchall()
    
    for row in rows:
        print(f"Low-confidence decision {row[0]} led to action")
```
