# Code-Quality Build Mode

## Metadata
- **Pack:** quality
- **Mode:** code-quality:build
- **Type:** enforcement
- **Model:** sonnet
- **Inputs:** code_block, generation_context, trigger_type
- **Outputs:** enforcement_decision (block | warn | info | pass)

## Before you start
1. Read `../gotchas.yml` if it exists.
2. Read `../rules.yml` — focus on rules where `action.build_mode` is not null.
3. Static only — no LLM calls. Synchronous enforcement.

## Trigger
`ds-quality:code-quality:build`, `build:code-quality`, code-quality check before generate

## Purpose
Static enforcement only on code about to be generated. No LLM calls. No DB connections. File reads only.

**Self-audit interface for 18.8.1:** This mode exposes a callable self-audit interface that ds-skills:build-mode-orchestration (18.8.1, future) can wire to run automatically when any skill generates Python. The interface is:
```python
def audit_generated_python(code_block: str, context: dict) -> list[dict]:
    """Static-only audit of generated Python code.
    
    Returns list of findings: [{"rule_id", "severity", "excerpt", "explanation"}]
    18.8.1 wires invocation. This function exposes the capability.
    """
```

---

## Severity Table

| Severity | Build Mode Action | Example rules |
|---|---|---|
| Critical | **Block** generation | cq-006, cq-012, cq-015, cq-019, cq-021 |
| High | **Warn** (proceed with warning) | cq-001, cq-005, cq-007, cq-014 |
| Medium | **Info** (log but don't interrupt) | cq-002, cq-003, cq-004, cq-008, cq-009, cq-010, cq-011, cq-013, cq-016, cq-017, cq-018, cq-020, cq-A-explicit |
| Low | **Silent** (no build-mode output) | cq-018 |

**Note:** This is more permissive than security/database build modes. Code-quality high findings are design preferences, not correctness violations. Blocking on "function too long" would paralyze the harness.

---

## Static Rules Applied in Build Mode

12 static rules run on generated code:

1. **cq-006** (silent failures) — BLOCK: `except: pass` → refuse to generate
2. **cq-012** (mutable global) — BLOCK: module-level mutable container
3. **cq-015** (bare except) — BLOCK: `except:` without type
4. **cq-019** (async sleep) — BLOCK: sleep() as sync barrier
5. **cq-021** (getter side effects) — BLOCK: @property with mutations
6. **cq-A-explicit** (wildcard imports) — INFO: `from X import *`
7. **cq-002** (function length) — INFO: if generated function > 50 lines
8. **cq-003** (param count) — INFO: if generated function > 4 params
9. **cq-005** (nesting depth) — INFO: if nesting > 3 levels
10. **cq-010** (constants) — INFO: module-level lowercase constants
11. **cq-013** (import order) — INFO: import group ordering
12. **cq-020** (docstrings) — INFO: public functions without docstring

**LLM semantic rules NOT run in build mode** (prevents recursion, keeps build synchronous):
cq-001, cq-004, cq-007, cq-009, cq-011, cq-016, cq-017, cq-018, cq-021 (static part only), cq-022 (deferred).

---

## Enforcement Response Format

```
🔴 BLOCKED [cq-NNN] {rule.name}
   Found: {excerpt}
   Why: {explanation}
   Fix: {remediation.summary}

🟠 WARNING [cq-NNN] {rule.name}
   Found: {excerpt}
   Suggestion: {remediation.summary}

ℹ INFO [cq-NNN] {rule.name}
   Found: {excerpt}
   Note: {remediation.summary}
```

If no findings: `✓ Code-quality static check passed.`

---

## Self-Audit Entry Point

```python
# Callable by 18.8.1 build orchestration:
# from canonical.skills.quality.modes.code_quality.build.audit import audit_generated_python
# findings = audit_generated_python(generated_code, context)
```

18.8.1 wires invocation. This file documents the interface. Code-quality does NOT call itself — the orchestrator calls code-quality.
