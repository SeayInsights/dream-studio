# Ops Skill — Audit Mode

## What This Does

Automated operational readiness scan. 13 rules covering logging, health/metrics, config,
shutdown, recovery, and deployment artifacts. Read-only — classifies and reports only.

## Invocation

```
ds-quality audit: ops <path>
```

## Pipeline

1. **Stack detection** — `detect_stack(path)` → `DetectedStack`
   Reads: `has_dockerfile`, `has_docker_compose`, `has_k8s_manifest`, `is_service`, `deployment_type`

2. **Rule dispatch** — skip conditional rules when context doesn't apply:
   - ops-005, ops-006, ops-008: skip if `is_service=False`
   - ops-012: skip if `has_dockerfile=False`
   - ops-013: skip if `has_k8s_manifest=False` AND `has_docker_compose=False`

3. **Static pass** — pattern-based detection per language:
   - ops-001: unstructured logging (print/console.log without logging lib)
   - ops-005: /health route presence in route files
   - ops-006: /metrics or prometheus/otel import presence
   - ops-008: signal.signal(SIGTERM) presence in service entrypoint
   - ops-011: HTTP client calls without timeout parameter
   - ops-012: Dockerfile stage count + USER instruction
   - ops-013: YAML resources.limits + livenessProbe presence

4. **LLM confirmation** — for candidates requiring semantic judgment:
   - ops-001 candidates: LLM confirms production vs script context
   - ops-003: LLM on log calls containing potentially sensitive variables
   - ops-009: LLM judges retry/backoff sufficiency

5. **LLM-only rules** — ops-002, ops-004, ops-007, ops-010:
   Applied per-file with context_scope appropriate to rule.

6. **Report** — findings table: rule_id, severity, file_path, line, excerpt, explanation

## Finding Hash

| Rule category | Hash input |
|---------------|-----------|
| Logging (ops-001–004) | `rule_id + file_path + line` |
| Health/Metrics (ops-005, 006) | `rule_id + service_root` |
| Config/Shutdown (ops-007, 008) | `rule_id + entrypoint_or_config_file` |
| Retry/Timeout (ops-009, 011) | `rule_id + file_path + call_site_line` |
| Deployment (ops-010, 012, 013) | `rule_id + artifact_path + violation_type` |

Hash is SHA-256. Stable on rescan when code/manifests unchanged.

## Token Budget

- Static-only rules: ~0 LLM tokens
- LLM confirmation (ops-001, 003, 009): ~400 tokens × candidate count
- LLM-only rules (ops-002, 004, 007, 010): ~500 tokens × file count sampled
- Typical full-repo estimate (100-file Python service): 15,000–25,000 tokens

Use `--sample N` to limit LLM rules to N files on large repos.
