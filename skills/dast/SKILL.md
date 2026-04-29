---
name: dast
description: "Web application dynamic testing — generate ZAP/Nuclei configs, ingest DAST results, score web-specific vulnerabilities. Trigger on dast:, web scan, pen test web, zap scan."
user_invocable: true
args: mode
argument-hint: "[setup | run | ingest | status] [--client <name>] [--target <name>]"
pack: security
---

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

## Storage
See `docs/security-storage-layout.md`. See skill-specific paths in layout doc.

## Templates
See `templates/security/README.md` for template registry.

## Client Profile
See `docs/client-profile-schema.md`. Required fields vary by mode.

---

## Client Profile Fields Used

Read from `~/.dream-studio/clients/{name}.yaml`:

| Profile field | Used by |
|---|---|
| `client.name`, `client.github_org` | All modes — identity |
| `targets.web_apps[]` | All modes — target list |
| `targets.web_apps[].url` | `setup`, `run` — scan target URL |
| `targets.web_apps[].auth` | `setup`, `run` — authentication config |
| `targets.web_apps[].scan_profile` | `setup`, `run` — scan intensity |
| `targets.web_apps[].excluded_paths` | `setup` — paths to skip |
| `targets.web_apps[].openapi_spec` | `setup` — API-aware scanning |
| `stack.languages`, `stack.frameworks` | `setup` — Nuclei template selection |

---

## Mode: `setup`

### Step S0: Parse Arguments

Extract from user input:
- `--client <name>` — required. If absent, list available profiles and ask.
- `--target <name>` — optional. If provided, generate only for that target. If absent, generate for all `targets.web_apps`.

### Step S1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. If file does not exist: **stop** with — "Client profile not found at `~/.dream-studio/clients/{client}.yaml`. Run `client-work:intake` to create it."
3. Validate `targets.web_apps` is present and non-empty.
4. If `targets.web_apps` is missing or empty: **stop** with — "No web app targets defined in profile. Add `targets.web_apps` entries to enable DAST scanning."

### Step S2: Generate ZAP Configuration

For each web app target in `targets.web_apps`:

1. Read `builds/dream-studio/templates/security/dast/zap-config.yaml.j2`.
2. Fill Jinja2 variables from the target entry and client profile.
3. Write rendered file to `~/.dream-studio/security/dast/{client}/{target.name}/zap-config.yaml`.

**Variable mapping:**

| Template variable | Source |
|---|---|
| `target.url` | `targets.web_apps[].url` |
| `target.auth.type` | `targets.web_apps[].auth.type` |
| `target.auth.token_env` | `targets.web_apps[].auth.token_env` |
| `target.auth.header` | `targets.web_apps[].auth.header` |
| `target.scan_profile` | `targets.web_apps[].scan_profile` |
| `target.excluded_paths` | `targets.web_apps[].excluded_paths` |

### Step S3: Generate Nuclei Configuration

For each web app target:

1. Read `builds/dream-studio/templates/security/dast/nuclei-config.yaml.j2`.
2. Select template tags based on:
   - `scan_profile: full` → tags: `cve,misconfig,exposure,takeover,tech-detect`
   - `scan_profile: api-only` → tags: `cve,misconfig,exposure,api`
   - `scan_profile: auth-only` → tags: `cve,default-login,misconfig`
   - `scan_profile: passive` → tags: `tech-detect,exposure`
3. Write to `~/.dream-studio/security/dast/{client}/{target.name}/nuclei-config.yaml`.

### Step S4: Generate GitHub Actions DAST Workflow

1. Read `builds/dream-studio/templates/security/github-actions/dast-scan.yml.j2`.
2. Fill variables from all web app targets.
3. Write to `~/.dream-studio/security/actions/{client}/dast-scan.yml`.

### Step S5: Present Output

Show:
1. Files generated (one per line with full path).
2. For local scans: "Run `dast run --client {client}` to execute scans locally."
3. For CI scans: commit instructions for the DAST workflow.
4. Any targets skipped and why (e.g., missing auth config).

---

## Mode: `run`

### Step R0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--target <name>` — optional. If absent, scan all configured web app targets.

### Step R1: Load Client Profile and Validate

1. Read client profile. Validate `targets.web_apps` is present.
2. Confirm DAST config exists: `~/.dream-studio/security/dast/{client}/{target}/zap-config.yaml`. If absent: **stop** — "Run `dast setup --client {client}` first."

### Step R2: Pre-flight Checks

For each target:
1. Confirm URL is reachable: `curl -s -o /dev/null -w "%{http_code}" {target.url}`. If not reachable: **warn** and skip.
2. Confirm ZAP is installed: `which zap.sh || which zap-cli || docker images owasp/zap2docker-stable`. If missing: show install instructions and **stop**.
3. Confirm Nuclei is installed: `which nuclei`. If missing: show install instructions and continue with ZAP only.

### Step R3: Execute ZAP Scan

1. Run ZAP in automation mode:
   ```bash
   zap.sh -cmd -autorun ~/.dream-studio/security/dast/{client}/{target}/zap-config.yaml
   ```
   Or via Docker:
   ```bash
   docker run --rm -v ~/.dream-studio/security/dast/{client}/{target}:/zap/config \
     owasp/zap2docker-stable zap.sh -cmd -autorun /zap/config/zap-config.yaml
   ```
2. Collect `zap-report.json` from the output directory.

### Step R4: Execute Nuclei Scan

1. Run Nuclei with the generated config:
   ```bash
   nuclei -u {target.url} \
     -t {template_tags} \
     -jsonl -o nuclei-output.jsonl \
     -rate-limit 10
   ```
2. Rate limit is intentionally conservative — active scanning should not overwhelm targets.

### Step R5: Store Results

1. Create directory: `~/.dream-studio/security/scans/{client}/{target}/{date}/`
2. Move `zap-report.json` and `nuclei-output.jsonl` into the directory.
3. Write `scan-meta.json`:
   ```json
   {
     "schema_version": 1,
     "client": "{client}",
     "target": "{target}",
     "target_type": "webapp",
     "date": "{YYYY-MM-DD}",
     "source": "local-run",
     "scanners": ["zap", "nuclei"],
     "url": "{target.url}",
     "scan_profile": "{target.scan_profile}",
     "ingested_at": "{ISO-8601}"
   }
   ```

### Step R6: Present Summary

Show: target URL, scanners run, result storage path, preliminary finding counts, next steps.

---

## Mode: `ingest`

### Step I0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--target <name>` — required.
- `--file <path>` — optional. If provided, ingest from local file. If absent, look in latest scan directory.

### Step I1: Locate Results

1. If `--file` provided: use that file.
2. Else: find most recent `~/.dream-studio/security/scans/{client}/{target}/{date}/` directory.
3. Look for `zap-report.json` and/or `nuclei-output.jsonl`.

### Step I2: Parse Results

1. Run parse_dast.py:
   ```bash
   py -3.12 templates/security/etl/parse_dast.py --client {client} --scans-dir {scan_dir}
   ```
2. This normalizes ZAP + Nuclei outputs to unified findings with `target_type: webapp`.

### Step I3: Store Parsed Findings

1. Write normalized findings JSON to the scan directory.
2. Update `scan-meta.json` with finding counts.

### Step I4: Present Summary

Show: finding counts by severity, OWASP category breakdown, storage path, "Run `security-dashboard refresh --client {client}` to update the dashboard."

---

## Mode: `status`

### Step T0: Parse Arguments

- `--client <name>` — required.

### Step T1: Inventory DAST Scan Store

1. List all target directories under `~/.dream-studio/security/dast/{client}/`.
2. For each target: find most recent scan, check staleness (>7 days = STALE).
3. For targets in profile but not scanned: mark NO RESULTS.

### Step T2: Render Coverage Report

```
# DAST Coverage — {client} ({date})

| Web App | URL | Scan Profile | Last Scan | Age | Findings | Status |
|---------|-----|-------------|-----------|-----|----------|--------|
| vendor-portal-web | https://vendor.plm... | full | 2026-04-20 | 2d | 12 | CURRENT |
| pricing-api-web | https://api.plm... | api-only | — | — | — | NO RESULTS |

**Summary:** {N} targets | {N} current | {N} stale | {N} no results
```

---

## DAST-Specific Finding Fields

| Field | Description |
|---|---|
| `target_type` | `webapp` |
| `target_name` | Web app target name from profile |
| `url` | Full URL where vulnerability was found |
| `http_method` | GET, POST, PUT, etc. |
| `parameter` | Vulnerable parameter name |
| `response_code` | HTTP status code |
| `evidence` | Response snippet showing the vulnerability |
| `attack_vector` | The payload that triggered the finding |

## Scanner Details

**OWASP ZAP** (primary DAST scanner):
- Automation Framework YAML for repeatable scans
- Passive scan (no attack traffic) + Active scan (fuzzing, injection)
- JSON reports with CWE and WASC mappings
- GH Action: `zaproxy/action-full-scan@v0.12.0`
- Auth: recorded sequences, header injection, token env vars

**Nuclei** (template-based scanner):
- 9000+ community templates (CVEs, misconfigs, exposed panels, default creds)
- JSON output with severity, CWE, CVSSv3
- GH Action: `projectdiscovery/nuclei-action@main`
- Template tags selected per client stack

**Rule ID patterns:** `DAST-zap-{N}`, `DAST-nuc-{template-id}`

---

## Anti-Patterns

- **Active scanning against production without explicit config** — default to passive mode. Active mode requires `scan_profile: full` in the target config. Always warn before active scanning.
- **Skipping auth config validation** — DAST against authenticated apps requires working auth. If auth config is incomplete, skip the target and report why.
- **Running without pre-flight URL check** — always verify the target URL is reachable before starting a scan. Scanning a dead URL wastes time and produces no findings.
- **Overwhelming the target** — rate-limit Nuclei (`-rate-limit 10`). ZAP has built-in throttling via the Automation Framework config.
- **Ingesting without scan-meta.json** — every scan directory must have `scan-meta.json` with `target_type: webapp`. Downstream skills depend on it.
- **Treating DAST findings as definitive** — DAST findings have higher false-positive rates than SAST. Mark findings as `status: "needs-verification"` when confidence is low.
- **Not excluding admin/danger paths** — always respect `excluded_paths` from the target config. Scanning admin endpoints on production can cause real damage.
