# Governance, Security, And Privacy Contract

Phase: 11C - Governance, Security, And Privacy Fixes

Dream Studio governance signals are local operational evidence. They make security, audit, risk, and privacy posture visible without moving authority into dashboards, exports, scanners, cloud tooling, or company-specific deployments.

## Authority Principles

1. Local canonical runtime state remains authoritative.
2. Governance and security records are local evidence unless an explicit event, state, or projection contract names a stronger owner.
3. Scanner output is evidence. A SARIF, CVE, guardrail, or LLM safety scanner finding does not own workflow, orchestration, execution, decision, memory, or architecture truth.
4. Dashboards and API routes may summarize governance/security state and may use named local governance write exceptions. They must not silently become canonical runtime writers.
5. Exports are operator-selected snapshots. They must preserve privacy/export classification and cannot become upstream authority on re-import without a future import contract.
6. Cloud, org, global, tenant, client, company, or compliance-pack layers may later aggregate selected redacted projections only. They do not own local canonical state.

## Signal Ownership

| Surface | Owner | Classification | Rule |
| --- | --- | --- | --- |
| `risk_register`, `risk_mitigations` | Reserved local governance owner, no active writer in Phase 11C | Local governance state | Local-only until an explicit writer is named. Do not add writers without a future contract update. |
| `audit_runs` | `projections.api.routes.audits` | Named local governance API write exception | May record audit runs; does not own workflow/execution state. |
| `guardrail_decisions` | `guardrails.evaluator` | Local guardrail decision audit | May write guardrail decisions and emit approved guardrail/decision lineage. |
| `guardrail_rules_audit` | Reserved local governance diagnostic owner, no active writer in Phase 11C | Governance diagnostic state | Rule audit evidence only. Do not add writers without a future contract update. |
| `sec_sarif_findings` | SARIF parser/security routes | Local security evidence | Scanner evidence only; never workflow authority. |
| `sec_cve_matches`, `sec_manual_reviews`, `sec_hook_checks` | Reserved local security evidence owners, no active writer in Phase 11C | Local security evidence | Scanner/manual/hook evidence only. Do not add writers without a future contract update. |
| `activity_log` security/governance entries | Legacy operational hub | Named legacy evidence surface | Compatibility evidence only; canonical event authority stays with `canonical_events`. |
| `validation_failures` | Event store validation path | Diagnostic rejected payload evidence | Local-only/private by default. |

## Privacy And Export Classes

| Class | Examples | Export rule |
| --- | --- | --- |
| Non-exportable local state | `memory_entries`, raw handoff/session content, rejected event payloads in `validation_failures`, full runtime DB backups | Do not export through projection/report routes. Full DB backups are not redacted exports and require explicit operator choice. |
| Local-only by default | `canonical_events` payloads, `activity_log` payloads, `raw_sessions`, `raw_token_usage` | Export only through a future explicit redaction/classification path. Aggregates may be safer than row payloads. |
| Exportable with redaction | Security finding paths/messages, audit summaries/report paths, manual review text, BOM/package lists | Redact local paths, secrets, credentials, PII, and raw content before external sharing. |
| Aggregate exportable | Counts, trends, severity summaries, status summaries, risk score aggregates | May be exported as derived snapshots when the export identifies them as projections. |
| Safe local diagnostic metadata | Runtime preflight/recovery status, schema versions, backup candidate hashes/mtime/size | Safe for local operator diagnostics; still avoid treating metadata as state authority. |

## Export And Backup Rules

- Export/report routes and exporters must not directly export raw private tables such as `memory_entries`, `raw_sessions`, `raw_token_usage`, `validation_failures`, raw handoff/session content, or raw `canonical_events` payloads without a future explicit redaction contract.
- Export/report creation must pass an executable privacy classification gate before producing derived projection snapshots or files. Requests for raw/private sources must be rejected unless the caller explicitly classifies the output as `redacted` or `aggregate`; the gate does not perform redaction itself.
- Projection exports must describe themselves as derived snapshots. Re-importing them must not promote them to canonical local state.
- `studio_backup.py` and local backup helpers copy full SQLite state. Those backups are operator-controlled recovery artifacts, not redacted reports.
- Optional cloud backup behavior, when explicitly configured by the operator, remains backup transport only. It does not create cloud, org, or global authority.

## Scanner And Guardrail Rules

- SARIF, CVE, manual review, hook security, prompt injection, LLM guard, and Giskard-style scanner outputs are evidence.
- Scanner/parsing/scoring code may write only named security evidence tables or named legacy evidence surfaces: `sec_sarif_findings`, `sec_cve_matches`, `sec_manual_reviews`, `sec_hook_checks`, and `activity_log`.
- Scanner/parsing/scoring code must not write canonical workflow, orchestration, execution, memory, or event tables.
- Guardrail evaluation may emit approved guardrail events, emit decision lineage through `core.decisions`, and write `guardrail_decisions`.
- Guardrail trigger matching against `activity_log` is a legacy compatibility surface aligned to supported fields: `activity_id`, `activity_type`, `stream_id`, `stream_type`, `event_data`, and `severity`. Named trigger fields map onto those columns; unsupported legacy custom-query fields such as `event_type`, `event_id`, `metadata`, and `tool_name` fail closed.

## Company And Org Boundaries

Company, client, tenant, Power BI, SOC, NIST, HIPAA, PCI, and organization-specific logic is non-core unless a future contract names it. Current optional CLI/export/example surfaces may contain those terms as local-only tooling or future org/security-pack candidates, but canonical core/control/runtime authority paths must not depend on them.

Current classified optional surfaces include `interfaces/cli/validate_client_profile.py`, `interfaces/cli/init_security_state.py`, and Power BI exporter/example files under `projections/exporters`. They are not canonical runtime authority.

Future org aggregation may consume selected redacted projections or aggregate governance summaries. It must not ingest raw private local state or overwrite local canonical runtime state.

## Active Hook Boundary

Canonical hook implementations live under `runtime/hooks`. Active hooks must not depend on the retired `hooks/lib` path. A hook may add the repository root to `sys.path` when executed directly, but it must not recreate or import from the retired hook library.

## Schema Posture

Phase 11B does not require schema changes. Any future governance/security/privacy schema change must name the owner, export class, redaction behavior, replay expectations, and boundary tests before it ships.
