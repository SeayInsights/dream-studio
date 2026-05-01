# netcompat — Detailed Reference

Extracted from SKILL.md to reduce context injection size.

## Orchestration Steps

Follow in order for the active mode. Do not skip steps. Do not proceed past a failed gate.

---

### Mode: `rules`

#### Step R0: Parse Arguments

Extract from user input:
- `--client <name>` — required. If absent, list available profiles and ask.

#### Step R1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. If file does not exist: **stop** with — "Client profile not found at `~/.dream-studio/clients/{client}.yaml`. Run `client-work:intake` to create it."
3. Validate required fields: `client.name`, `network.proxy.type`.
4. If `network.proxy` is absent: warn — "No network.proxy section in profile. Generating baseline rules only (non-standard-port, websocket-no-tls)."

#### Step R2: Render Semgrep Template

1. Read `builds/dream-studio/templates/security/semgrep-rules/netcompat.yaml.j2`.
2. Render Jinja2 template with client profile data:
   - `client.name` → rule ID prefix and messages
   - `network.proxy.type` → conditional blocks per proxy type
   - `network.proxy.blocked_ports` → port list in rule 4 message
   - `network.proxy.dlp_patterns` → DLP pattern list in rule 6 message (Zscaler only)
   - `network.proxy.custom_ca` → CA guidance in rule 1–3 messages
3. Write rendered file to `~/.dream-studio/security/rules/{client}/netcompat.yaml`.

#### Step R3: Present Output

Show:
1. Output file path.
2. Number of rules generated and which proxy-type-specific rules were included.
3. Commit instructions:
   ```
   1. Copy ~/.dream-studio/security/rules/{client}/netcompat.yaml
      → .github/semgrep/netcompat.yaml in each target repo
   2. Commit and push — the security-scan workflow will pick it up
   ```
4. Next step: "Run `scan ingest --client {client} --repo {repo}` after the next workflow run, then `netcompat analyze --client {client}` to score results."

---

### Mode: `analyze`

#### Step A0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--repo <repo>` — optional. If provided, analyze only that repo. If absent, analyze all repos with ingested SARIF under `~/.dream-studio/security/scans/{client}/`.

#### Step A1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. Validate required fields: `client.name`, `network.proxy.type`.
3. Extract DLP terms: combine `data.critical` + `data.sensitive` into a flat list for cross-reference.

#### Step A2: Locate SARIF Findings

1. Enumerate `~/.dream-studio/security/scans/{client}/{repo}/{date}/` directories.
2. For each repo (or the specified `--repo`): select the most recent date directory.
3. Read `semgrep.sarif` from that directory.
4. Filter results to rule IDs matching `ZSC-*` or `net-*` or `{client}-zsc-*` or `{client}-net-*`.
5. If no netcompat-related findings: note "No netcompat findings for {repo}" and include in output with score=100.

#### Step A3: Score Per Repo

For each repo, start at score=100 and apply deductions:

| Finding type | Rule ID pattern | Deduction per instance |
|---|---|---|
| cert_pinning | `*-001` | -20 |
| custom_ssl_context | `*-002` | -15 |
| hardcoded_ca | `*-003` | -10 |
| non_standard_port | `*-004` | -10 |
| websocket_no_tls | `*-005` | -15 |
| custom_dns | `*-006` (Zscaler only) | -10 |
| mtls_conflict | `*-007` (Zscaler only) | -20 |

Floor score at 0. Score formula: `max(0, 100 - sum(deductions))`.

#### Step A4: DLP Risk Assessment

For each repo, scan outbound URL patterns and payload construction in SARIF findings:
1. Extract `locations` from each finding to identify files and lines.
2. Cross-reference finding messages for data classification terms from `data.critical` + `data.sensitive`.
3. If any finding message or location path contains a data classification term: mark `dlp_risk=high`. If indirect match: `dlp_risk=medium`. Otherwise: `dlp_risk=low`.

#### Step A5: Generate Fix Recommendations

For each finding, produce a one-line fix recommendation:

| Finding type | Fix template |
|---|---|
| cert_pinning | "Remove cert pinning in `{file}:{line}` — add proxy CA to trust bundle instead (see network.proxy.custom_ca in profile)" |
| custom_ssl_context | "In `{file}:{line}`, set REQUESTS_CA_BUNDLE env var instead of loading CA bundle explicitly" |
| hardcoded_ca | "In `{file}:{line}`, replace hardcoded CA path with REQUESTS_CA_BUNDLE or SSL_CERT_FILE env var" |
| non_standard_port | "In `{file}:{line}`, move to port 443 (HTTPS) — port blocked by {proxy_type} policy" |
| websocket_no_tls | "In `{file}:{line}`, replace ws:// with wss:// and confirm server supports WSS" |
| custom_dns | "In `{file}:{line}`, use system DNS (Python default) — custom resolvers bypass Zscaler DNS inspection" |
| mtls_conflict | "In `{file}:{line}`, add Zscaler SSL bypass rule for this destination rather than disabling SSL inspection globally" |

#### Step A6: Write CSV Output

Write `~/.dream-studio/security/datasets/{client}/netcompat.csv` with columns:

```
repo,zscaler_score,cert_pinning,dlp_risk,port_issues,fixes_needed
```

- `zscaler_score`: integer 0–100
- `cert_pinning`: count of cert-pinning findings
- `dlp_risk`: high | medium | low
- `port_issues`: count of non-standard-port + websocket-no-tls findings combined
- `fixes_needed`: total count of all findings across all categories

#### Step A7: Present Summary

Show as a markdown table:

```
# Netcompat Analysis — {client} ({date})

| Repo | Score | Cert Pinning | DLP Risk | Port Issues | Fixes Needed |
|------|-------|-------------|---------|-------------|-------------|
| repo-a | 90 | 0 | low | 1 | 1 |
| repo-b | 45 | 2 | high | 3 | 7 |

**Output:** ~/.dream-studio/security/datasets/{client}/netcompat.csv
**Proxy type:** {proxy_type}
**Action:** Run `netcompat report --client {client}` for full fix instructions.
```

---

### Mode: `report`

#### Step P0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--repo <repo>` — optional. If provided, report only that repo.

#### Step P1: Load Results

1. Read `~/.dream-studio/security/datasets/{client}/netcompat.csv`.
2. If file does not exist: **stop** with — "No analysis results found. Run `netcompat analyze --client {client}` first."
3. Load all SARIF files from `~/.dream-studio/security/scans/{client}/` to get detailed findings.

#### Step P2: Generate Fix Report

For each repo (or specified `--repo`):
1. List all findings with file, line, rule ID, and fix recommendation.
2. Group findings by category (cert_pinning, ssl_context, port, websocket, dns, mtls).
3. Sort within each group: ERROR severity first, then WARNING.
4. Show DLP risk assessment and which data classifications are at risk.

Report format:

```markdown
# Netcompat Compatibility Report — {repo}
**Client:** {client}
**Proxy:** {proxy_type}
**Score:** {score}/100
**DLP Risk:** {high|medium|low}
**Date:** {date}

---

## Findings

### Cert Pinning ({N} findings)
- `{file}:{line}` — {fix recommendation}

### Non-Standard Ports ({N} findings)
- `{file}:{line}` (port {PORT}) — Move to 443 (HTTPS)

### WebSocket without TLS ({N} findings)
- `{file}:{line}` — Replace ws:// with wss://

{... remaining categories ...}

---

## DLP Risk Assessment
{If high/medium: list which data classification terms appear near outbound connections}

---

## Remediation Priority
1. Fix all cert-pinning and mTLS conflicts first (highest breakage risk)
2. Replace non-standard ports and ws:// connections
3. Update CA bundle handling to use env vars
4. Test against proxy in staging before deploying to {client} environment
```

---

## Output Schema

### `netcompat.csv`

| Column | Type | Description |
|---|---|---|
| `repo` | string | Repository name |
| `zscaler_score` | int (0–100) | Compatibility score; 100 = fully compatible |
| `cert_pinning` | int | Count of cert-pinning violations |
| `dlp_risk` | enum | `high` / `medium` / `low` |
| `port_issues` | int | Count of non-standard-port + websocket-no-tls findings |
| `fixes_needed` | int | Total finding count across all categories |

### Score Interpretation

| Score | Meaning |
|---|---|
| 90–100 | Compatible — minor or no changes needed |
| 70–89 | Likely compatible — a few low-risk patterns to clean up |
| 50–69 | At risk — multiple issues; validate in staging before deploy |
| 0–49 | Incompatible — will break in this proxy environment without remediation |

---

