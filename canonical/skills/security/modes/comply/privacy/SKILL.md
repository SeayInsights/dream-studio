---
dream_studio:
  skill_id: ds-security
  pack: security
  mode: comply
  sub_mode: privacy
  mode_type: diagnostic
  inputs: [source_root, db_path, target_path]
  outputs: [privacy_compliance_report]
  capabilities_required: [Read, Grep, Bash, Glob]
  model_preference: sonnet
  estimated_duration: 10-20min
  write_posture: read-only
  lifecycle: published
---

# Comply — Privacy Compliance Audit

## What This Does

Automated regulatory compliance scan for data-handling code and schemas. 12 rules covering
PII classification, retention, erasure, access/portability, consent, minimization, and
HIPAA-specific requirements (opt-in). Read-only — classifies and reports only. This is the
in-repo detector half of `comply`: `map`/`gaps`/`evidence` (see `../SKILL.md`) map an external
client's SARIF scan findings against SOC 2/NIST/ASVS/CWE controls; `privacy` instead audits
THIS repository's own data-handling code and schema directly, with no client profile or SARIF
input required.

## Invocation

```
ds-security comply: privacy <path>
```

## Source Authority

Rules defined in `rules.yml` in this directory. Default: GDPR. Config-driven opt-in for HIPAA,
CCPA, COPPA. Thresholds and framework activation in `config.yml`.

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

**This sub-mode owns:** PII classification, retention, right to erasure/access, consent,
data minimization, BAA documentation (HIPAA) — regulatory obligations on THIS repo's own
data-handling code and schema.

**vs. `comply`'s other sub-modes (`map`/`gaps`/`evidence`):** those map an external client's
SARIF scan findings onto compliance framework controls (SOC 2, NIST CSF, OWASP ASVS, CWE Top 25)
and require `--client`. `privacy` runs directly against a local path with no client profile —
it is a detector, not a mapper. A future mapping template (e.g. `gdpr-mapping.yaml`) could let
`privacy`'s findings feed into `map`/`gaps`/`evidence`, but none exists yet; treat them as
pipeline-adjacent peers, not one flow.

**Deferred (see rules.yml header for named owners):**
- Encryption at rest → sec-009 (security:review)
- PII in runtime output → sec-013 (security:review)
- PII in log call sites → ops-003 (ops)
- Backup strategy → db-016/017/018 (database)

**Cross-references:**
- `dbc-001` ↔ `db-020` (regulatory taxonomy vs schema structural correctness — dual-angle)
- `dbc-007` ↔ `db-002` (right-to-erasure cascade vs general FK ON DELETE — dual-angle)

## Auto-Skip Conditions

- `has_pii_schema=False`: returns immediately with 0 findings and message:
  "No PII schema detected — privacy audit skipped (scope gap, not a clean bill of health)"
- This is correct behavior on purely operational codebases (e.g., dream-studio-clean) — it means
  no PII scope was found to audit, not that the codebase was checked and found compliant.
- `compliance_frameworks` empty or unset: uses GDPR default
- dbc-012 (HIPAA BAA): only activates when `hipaa` in `compliance_frameworks`

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
