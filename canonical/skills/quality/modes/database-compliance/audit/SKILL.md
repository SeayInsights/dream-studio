# Database Compliance Skill — Audit Mode

## What This Does

Automated regulatory compliance scan for data-handling code and schemas. 12 rules covering
PII classification, retention, erasure, access/portability, consent, minimization, and
HIPAA-specific requirements (opt-in). Read-only — classifies and reports only.

## Invocation

```
ds-quality audit: database-compliance <path>
```

## Auto-Skip

- `has_pii_schema=False`: returns immediately with 0 findings and message:
  "No PII schema detected — database-compliance audit skipped"
- This is correct behavior on purely operational codebases (e.g., dream-studio-clean)

## Pipeline

1. **Stack detection** — reads `has_pii_schema`, `compliance_hints`, `has_privacy_policy`
2. **Auto-skip check** — if `has_pii_schema=False`, return empty result
3. **Config load** — read `config.yml` defaults; merge `database_compliance_config.yml` if present
4. **PII schema scan** — parse migration SQL for PII-suggestive columns; build PII table map
5. **Static pass** — schema/route-based rules:
   - dbc-001: migration SQL for classification annotations
   - dbc-005: code scan for purge/DELETE patterns on PII tables
   - dbc-006: route scan for user deletion endpoint
   - dbc-007: FK ON DELETE CASCADE on PII tables
   - dbc-008: route scan for data export endpoint
   - dbc-009: schema scan for consent table/columns
6. **LLM pass** — semantic rules:
   - dbc-002, 003, 004, 010, 011 (context-dependent judgment)
   - dbc-012 (HIPAA only, if opted in)
7. **Report** — findings table: rule_id, severity, file_path, line, excerpt, explanation

## Finding Hash

| Rule category | Hash input |
|---------------|-----------|
| Classification (dbc-001–003) | `rule_id + migration_file + table_name + column_name` |
| Retention (dbc-004, 005) | `rule_id + table_name + violation_type` |
| Erasure (dbc-006, 007) | `rule_id + service_root` or `rule_id + fk_table + parent_table` |
| Access (dbc-008) | `rule_id + service_root` |
| Consent (dbc-009, 010) | `rule_id + schema_or_route` |
| Minimization (dbc-011) | `rule_id + service_root + data_scope` |
| HIPAA (dbc-012) | `rule_id + service_root` |

Hash is SHA-256. Stable on rescan when migrations/routes unchanged.

## Token Budget

- Static rules (dbc-001, 005–009): ~0 LLM tokens
- LLM rules (dbc-002, 003, 004, 010, 011, 012): ~500 tokens × file count sampled
- Typical full-repo estimate (50-file TypeScript service): 8,000–15,000 tokens
