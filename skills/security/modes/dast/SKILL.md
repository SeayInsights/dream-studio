# DAST — Web Application Dynamic Testing

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`dast:`, `web scan`, `pen test web`, `zap scan`, `/dast`

## Purpose
Orchestrate dynamic application security testing (DAST) against web application targets defined in the client profile. The skill generates OWASP ZAP and Nuclei scanning configurations, can execute scans locally (unlike `scan` which is CI-only), and ingests results into the unified findings store for downstream skills (mitigate, comply, security-dashboard).

Unlike `scan` (which generates configs for CI execution only), `dast:run` CAN execute ZAP and Nuclei locally because DAST requires network access to the target and the user explicitly authorizes pen testing.

## Modes
- `setup` — Generate ZAP Automation Framework YAML, Nuclei config, and GitHub Actions DAST workflow for each web app target.
- `run` — Execute DAST scan locally against configured web app targets.
- `ingest` — Parse ZAP JSON + Nuclei JSONL results into unified findings with `target_type: webapp`.
- `status` — Show DAST scan coverage: which web apps are scanned, staleness, coverage.

---

## Anti-Patterns

- **Active scanning against production without explicit config** — default to passive mode. Active mode requires `scan_profile: full` in the target config. Always warn before active scanning.
- **Skipping auth config validation** — DAST against authenticated apps requires working auth. If auth config is incomplete, skip the target and report why.
- **Running without pre-flight URL check** — always verify the target URL is reachable before starting a scan. Scanning a dead URL wastes time and produces no findings.
- **Overwhelming the target** — rate-limit Nuclei (`-rate-limit 10`). ZAP has built-in throttling via the Automation Framework config.
- **Ingesting without scan-meta.json** — every scan directory must have `scan-meta.json` with `target_type: webapp`. Downstream skills depend on it.
- **Treating DAST findings as definitive** — DAST findings have higher false-positive rates than SAST. Mark findings as `status: "needs-verification"` when confidence is low.
- **Not excluding admin/danger paths** — always respect `excluded_paths` from the target config. Scanning admin endpoints on production can cause real damage.

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
