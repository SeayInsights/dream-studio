# Dream Studio Guardrails Reference

Deterministic policy enforcement engine for security, quality, and prompt-injection controls.

**Source:** `guardrails/`  
**Rule files:** `guardrails/rules/`  
**Hook integration:** `hooks/on-commit.py`  
**Event emitted:** `guardrail.decision` → `ai_canonical_events`

---

## Architecture

Guardrails are YAML-driven policy rules evaluated against canonical event data. The engine is deterministic — no LLM involved in enforcement decisions.

```
GuardrailRule (YAML)
    → GuardrailEvaluator.evaluate(event_id, rules_dir)
        → query canonical_events for trigger conditions
        → determine most severe action (BLOCK > REQUIRE_APPROVAL > ADVISORY > ALLOW)
        → emit GUARDRAIL_DECISION event
        → return GuardrailAction
```

---

## Core Modules

| Module | Purpose |
|--------|---------|
| `guardrails/models.py` | Pydantic models: `GuardrailAction`, `Severity`, `TriggerCondition`, `GuardrailRule`, `GuardrailDecision` |
| `guardrails/loader.py` | YAML rule loader with strict and lenient validation modes |
| `guardrails/evaluator.py` | Policy enforcement engine — queries events, determines action, emits decision |
| `guardrails/enforcement.py` | Content-level detectors (pure text functions, no DB/IO) |
| `guardrails/delta_guard.py` | Change detection |
| `guardrails/memory_taint.py` | Memory taint tracking |
| `guardrails/scanners/` | Scanner implementations: giskard, llm_guard_scorer, rebuff_validator |

---

## Actions

| Action | Exit code | Behavior |
|--------|-----------|---------|
| `ALLOW` | 0 | Permit the operation |
| `ADVISORY` | 0 | Print warning but do not block |
| `REQUIRE_APPROVAL` | 2 | Escalate for manual review |
| `BLOCK` | 1 | Deny the operation |

Priority when multiple rules trigger: `BLOCK > REQUIRE_APPROVAL > ADVISORY > ALLOW`

---

## Severity Levels

`INFO` · `LOW` · `MEDIUM` · `HIGH` · `CRITICAL`

---

## Rule Files

### `guardrails/rules/security.yaml` — Security rules

| Rule | Action | Trigger |
|------|--------|---------|
| GR-001 | advisory | Hardcoded credentials in commit |
| GR-002 | advisory | Critical vulnerability finding |
| GR-003 | advisory | `eval()` usage |
| GR-004 | advisory | `shell=True` or `os.system()` |
| GR-005 | advisory | Private keys in source |

_All security rules are in advisory/pilot mode as of 2026-05-13._

---

### `guardrails/rules/quality.yaml` — Code quality rules

| Rule | Action | Trigger |
|------|--------|---------|
| GR-010 | advisory | Large commits (>25 files) |
| GR-011 | advisory | Missing tests |
| GR-012 | advisory | Debug leftovers |
| GR-013 | advisory | Large files (>200 lines) |
| GR-014 | advisory | Quality score <6/10 _(disabled)_ |

---

### `guardrails/rules/guard-patterns.yaml` — Prompt injection rules

14 rules for detecting prompt-injection and jailbreak attempts. Phase 1 — all in advisory mode.

**Critical static-fire rules** (8 rules — exact-match patterns):
- Direct instruction override
- Role hijacking
- System prompt injection
- Instruction tag injection (`[INST]`/`[/INST]`)
- ChatML markers
- Memory override
- Instruction discard
- Dream Studio context injection via docstring

**High severity static-fire** (1 rule):
- New instructions header

**High severity LLM-confirm** (4 rules — require LLM confirmation):
- Role impersonation
- Settings override
- Privileged mode activation
- Jailbreak keywords

**Suppressed paths** (never scanned):
`guardrails/*`, `tests/*`, `docs/*`, `node_modules/*`, `.venv/*`, `vendor/*`, `__pycache__/*`, `.git/*`, `dist/*`, `build/*`, `.next/*`, `canonical/skills/quality/modes/security/**`

---

## Trigger Condition Fields

| Field | Purpose |
|-------|---------|
| `event_type` | Match canonical event type |
| `finding_type` | Match finding classification |
| `severity` | Filter by severity level |
| `tool_name` | Match scanner/tool that produced finding |
| `file_pattern` | Regex match against file path |
| `custom_query` | Read-only SELECT against `canonical_events` or `hook_invocations` |

**Custom query support:** `json_extract(payload, '$.field')` for nested event data. File pattern matching against payload fields: `file`, `file_path`, `path`, `filename`.

---

## Hook Integration

`hooks/on-commit.py` — optional git pre-commit guardrail enforcement.

```
py hooks/on-commit.py --event-id=<id> [--mode=advisory|enforce]
```

| Mode | Behavior |
|------|---------|
| `advisory` (default) | Print violations but allow commit |
| `enforce` | Block or require approval based on rule actions |

Output indicators: ✅ allow · ❌ block · ⏸️ require_approval · ℹ️ advisory

---

## MCP Integration

The guardrail evaluator is accessible via MCP through the `ds-security` pack. The `GUARDRAIL_DECISION` event (emitted after each evaluation) provides a complete audit trail in `ai_canonical_events`.

The `guardrail_decisions` table in the authority database stores the full decision record including: `rule_id`, `action`, `trigger_condition`, `event_id`, `decided_at`.

---

## Cross-references

- Events: [`docs/reference/events.md`](events.md) — `guardrail.decision`
- Security scan: [`docs/reference/gates.md`](gates.md) — pre-push gate `atlas-leak`
- Schema: [`docs/reference/schema.md`](schema.md) — `security_findings`
- Hook that runs security scan on file writes: [`docs/reference/hooks.md`](hooks.md) — `on-security-scan`
