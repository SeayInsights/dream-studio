---
ds:
  pack: security
  mode: netcompat
  mode_type: analysis
  inputs: [codebase, network_profile, proxy_config, outbound_connections]
  outputs: [compatibility_score, issues, fix_recommendations]
  capabilities_required: [Read, Write, Grep, Bash]
  model_preference: haiku
  estimated_duration: 15-30min
---

# Netcompat — Network/Proxy Compatibility Analyzer

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`netcompat:`, `zscaler check`, `proxy compat`, `proxy compatibility`, `/netcompat`

## Purpose
Analyze application code for network and proxy compatibility issues before deployment into corporate network environments. Reads the client's network configuration profile (proxy type, SSL inspection, DLP policies, blocked ports), generates proxy-type-specific Semgrep rules via Jinja2 templates, scans all outbound connections in the codebase, and produces a per-repo compatibility score with targeted fix recommendations.

This skill never runs scanners directly. It generates Semgrep rules for the user to commit and processes SARIF findings that have already been ingested by `scan ingest`. It never modifies client repos directly.

## Modes
- `analyze` — Scan repos for proxy/network compatibility issues. Reads client network config from profile. Runs netcompat Semgrep rules. Calculates per-repo compatibility score. Writes results to `~/.dream-studio/security/datasets/{client}/netcompat.csv`.
- `report` — Generate a compatibility report with fix recommendations per finding, grouped by repo and severity.
- `rules` — Generate Semgrep rules for network compatibility checks by rendering `templates/security/semgrep-rules/netcompat.yaml.j2` with the client's network profile.

---

## Storage
See `docs/security-storage-layout.md`. See skill-specific paths in layout doc.

## Templates
See `templates/security/README.md` for template registry.

## Client Profile
See `docs/client-profile-schema.md`. Required fields vary by mode.

---

## Proxy-Type-Specific Behavior

| Proxy type | Checks enabled |
|---|---|
| `zscaler` | cert-pinning, custom-ssl-context, hardcoded-ca, non-standard-port, websocket-no-tls, custom-dns, mTLS-conflict |
| `bluecoat` | cert-pinning, custom-ssl-context, hardcoded-ca, non-standard-port, websocket-no-tls |
| `palo-alto` | cert-pinning, custom-ssl-context, non-standard-port, websocket-no-tls |
| `none` | non-standard-port, websocket-no-tls (baseline checks only) |

Zscaler is the strictest proxy type and triggers all seven check categories. BlueCoat and Palo Alto omit DNS and mTLS checks because those proxies do not intercept DNS or break mTLS by default.

---

## Anti-patterns

- **Running Semgrep directly** — this skill generates rules and processes ingested SARIF. It never executes `semgrep` locally. Scanning runs in GitHub Actions via `scan setup`.
- **Pushing rules to client repos** — output rules and workflow files for the user to commit. Never push directly.
- **Ignoring proxy type when generating rules** — always check `network.proxy.type`. Zscaler-specific rules (DNS, mTLS) must not be emitted for non-Zscaler proxy environments; they generate false positives.
- **Treating score=100 as "no risk"** — a score of 100 means no netcompat findings were detected, not that the code is free of network issues. Inform the user if no netcompat rules have been run yet.
- **DLP assessment without data profile** — if `data.critical` and `data.sensitive` are both absent from the profile, skip DLP risk assessment and note it. Do not guess at data classifications.
- **Surfacing stale findings** — before showing any finding, confirm the SARIF source is from the most recent scan date. Flag any findings from SARIF older than 7 days as potentially stale.
- **Conflating port issues with security vulnerabilities** — port blocking is a network policy issue, not a security vulnerability. Frame port findings as compatibility blockers, not OWASP violations.

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
