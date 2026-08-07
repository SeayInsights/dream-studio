# Pre-Launch Skill — Audit Mode

## What This Does

Launch readiness scan across 5 categories (20 rules). Produces a T1/T2/T3 tiered report.
T1 findings produce CLI exit code 1. Read-only — never modifies code.

## Invocation

```
ds-quality audit: pre-launch <path>
```

## Pipeline

1. **Stack detection** — reads `service_type`, `has_changelog`, `has_runbook`,
   `changelog_convention`, `release_tooling`
2. **Config load** — read `config.yml` defaults; merge `pre_launch_config.yml` if present
   (override `service_type` here)
3. **Legal docs pass** (pl-001–006) — file detection per service_type dispatch
4. **Release docs pass** (pl-007–010) — file detection + git tag format check
5. **Ops readiness pass** (pl-011–014) — file detection + LLM quality confirmation
6. **Sign-off pass** (pl-015–017) — file + CI config detection
7. **Feature safety pass** (pl-018–020) — LLM code scan + CI config
8. **Report** — tiered findings: T1 (blocking), T2 (warning), T3 (advisory)

## Output Shape

```json
{
  "verdict": "LAUNCH_READY" | "LAUNCH_BLOCKED" | "LAUNCH_WARNING",
  "service_type": "consumer" | "developer-tool" | "internal-service" | "library",
  "t1_blocking": [...],
  "t2_warnings": [...],
  "t3_advisories": [...],
  "rules_run": 20,
  "rules_skipped": N
}
```

`LAUNCH_BLOCKED` when any T1 finding. `LAUNCH_WARNING` when T2 only. `LAUNCH_READY` when clean.

## Finding Hash

| Rule category | Hash input |
|---------------|-----------|
| Legal docs (pl-001–006) | `rule_id + service_root + doc_type` |
| Release docs (pl-007–010) | `rule_id + changelog_path + version_tag` |
| Ops docs (pl-011–014) | `rule_id + service_root + doc_type` |
| Sign-off (pl-015–017) | `rule_id + service_root + review_type` |
| Feature safety (pl-018–020) | `rule_id + file_path + feature_scope` |

## Token Budget

- File detection rules (pl-001–014 static): ~0 LLM tokens
- LLM quality confirmation (pl-011, 012, 016): ~400 tokens × file count
- LLM code scan (pl-018–020): ~500 tokens × file count sampled
- Typical estimate (50-file service): 5,000–12,000 tokens
