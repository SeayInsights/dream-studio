# Database Compliance — Regulatory Data Handling Audit

## Mode dispatch

0. Apply portable skill contract.
1. Parse mode from argument (first word).
2. Default to `audit` if no mode given.
3. Read `modes/<mode>/SKILL.md` completely.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, compliance audit:, gdpr audit:, privacy audit:, dbc audit: |

## What This Skill Does

`audit` — automated review of data-handling code and database schemas for regulatory
compliance. Detects PII classification gaps, missing retention policies, right-to-erasure
failures, absent consent tracking, and data minimization violations. Auto-skips when
`has_pii_schema=False` (no PII detected in schema).

## Source Authority

Rules defined in `rules.yml`. Default: GDPR. Config-driven opt-in for HIPAA, CCPA, COPPA.
Thresholds and framework activation in `config.yml`.

## Supported Languages (Phase 1)

All 12 rules apply to: Python, TypeScript, JavaScript, Go, Rust.
Detection: SQL migration files, HTTP route files, schema definitions, LLM semantic judgment.

## GDPR Default / Multi-Regulation Opt-In

Default `compliance_frameworks: [gdpr]` in `config.yml` fires all 12 Phase 1 rules.
Rules dbc-001–011 apply under GDPR. Rule dbc-012 is HIPAA-only — fires only when
`hipaa` is in `compliance_frameworks`.

Project override: create `database_compliance_config.yml` at project root:
```yaml
compliance_frameworks: [gdpr, hipaa]   # adds HIPAA-only rules
jurisdiction: us-healthcare
```

## Skill Boundary

**This skill owns:** PII classification, retention, right to erasure/access, consent,
data minimization, BAA documentation (HIPAA).

**Deferred (see rules.yml header for named owners):**
- Encryption at rest → sec-009 (security)
- PII in runtime output → sec-013 (security)
- PII in log call sites → ops-003 (ops)
- Backup strategy → db-016/017/018 (database)

**Cross-references:**
- `dbc-001` ↔ `db-020` (regulatory taxonomy vs schema structural correctness — dual-angle)
- `dbc-007` ↔ `db-002` (right-to-erasure cascade vs general FK ON DELETE — dual-angle)

## Auto-Skip Conditions

- `has_pii_schema=False`: skill produces 0 findings (no PII detected → no compliance scope)
- `compliance_frameworks` empty or unset: uses GDPR default
- dbc-012 (HIPAA BAA): only activates when `hipaa` in `compliance_frameworks`
