# Plan: Security Target Expansion — Waves 6-9

Spec: `.planning/security-target-expansion.md`
Traceability: `.planning/traceability.yaml`
Date: 2026-04-22

## Requirements

| TR-ID | Description | Priority | Tasks |
|-------|-------------|----------|-------|
| TR-001 | Client profile schema supports `targets` block (repos, web_apps, binaries) | must | 1 |
| TR-002 | Unified findings schema adds `target_type`, `target_name`, `url`, `http_method`, `binary_hash` | must | 2, 4 |
| TR-003 | PLMarketing-Kroger profile includes sample web app and binary targets | must | 3 |
| TR-004 | export_dataset.py emits new columns in findings.csv + targets.csv, backward compatible | must | 4 |
| TR-005 | DAST skill with setup/run/ingest/status modes | must | 5 |
| TR-006 | ZAP Automation Framework YAML template (Jinja2) | must | 6 |
| TR-007 | Nuclei config template + DAST GH Actions workflow template | must | 7 |
| TR-008 | parse_dast.py ETL script parses ZAP JSON + Nuclei JSONL to unified findings | must | 8 |
| TR-009 | binary-scan skill with setup/analyze/ingest/status modes | must | 9 |
| TR-010 | YARA rule template + checksec config template | must | 10 |
| TR-011 | parse_binary.py ETL script parses checksec JSON + YARA JSON to unified findings | must | 11 |
| TR-012 | Binary scan GH Actions workflow template | must | 12 |
| TR-013 | security-audit.yaml workflow adds dast-scan and binary-scan parallel nodes | must | 13 |
| TR-014 | CLAUDE.md routing table + packs.yaml updated with dast + binary-scan | must | 14 |
| TR-015 | Dashboard spec adds DAST Overview + Binary Analysis pages + new DAX measures | must | 15 |
| TR-016 | score_findings.py extended with runtime_exploitability and deployment_exposure scoring | should | 4 |

## Tasks

### 1. Expand client profile schema with `targets` block
- Implements: TR-001
- Files: `~/.dream-studio/clients/_schema.yaml`
- Depends on: none
- Acceptance:
  - `_schema.yaml` has a `targets` section with `repos` (list of `{name, type, github_org, branch}`), `web_apps` (list of `{name, type, url, auth, scan_profile, excluded_paths, openapi_spec}`), and `binaries` (list of `{name, type, artifact_source, artifact_repo, artifact_pattern, path, platform}`)
  - All fields have type, required, and description annotations matching existing schema style
  - Existing fields unchanged

### 2. Expand unified findings schema in parse_sarif.py
- Implements: TR-002
- Files: `templates/security/etl/parse_sarif.py`
- Depends on: none
- Acceptance:
  - Every finding dict includes `target_type` (default `"repo"`), `target_name`, `url`, `http_method`, `binary_hash` — all default to `""` or `None`
  - `generate_sample()` produces findings with `target_type: "repo"` and the new fields present
  - Existing SAST parsers (semgrep, bandit, trufflehog, pip-audit) set `target_type: "repo"` on every finding
  - No behavior change for existing callers — new fields are additive

### 3. Update PLMarketing-Kroger profile with sample targets
- Implements: TR-003
- Files: `~/.dream-studio/clients/plmarketing-kroger.yaml`
- Depends on: 1
- Acceptance:
  - Profile has `targets.repos` listing vendor-portal, pricing-api, planogram-service (matching existing `scan.priority_repos`)
  - Profile has `targets.web_apps` with at least 2 entries (vendor-portal-web, pricing-api-web) using oauth2 and api_key auth types
  - Profile has `targets.binaries` with at least 1 entry (data-processor with github-release source)
  - Existing `scan.priority_repos`/`scan.exclude_repos` unchanged (backward compat)
  - Profile passes any existing validation (`validate_client_profile.py` if present)

### 4. Update export_dataset.py for new columns + scoring extensions
- Implements: TR-002, TR-004, TR-016
- Files: `templates/security/etl/export_dataset.py`, `templates/security/etl/score_findings.py`
- Depends on: 2
- Acceptance:
  - `FINDINGS_FIELDS` includes `target_type`, `target_name`, `url`, `http_method`, `binary_hash`
  - `build_findings_csv()` extracts the new fields from finding dicts
  - `REPOS_FIELDS` includes `medium_count`, `low_count` (currently missing from the truncated list)
  - A new `build_targets_csv()` function exports `targets.csv` with columns: `name`, `target_type`, `url`, `platform`, `last_scan`, `risk_score`, `finding_count`
  - `repos.csv` still exported as a backward-compatible filtered view
  - `score_findings.py` adds `runtime_exploitability` boost for `target_type == "webapp"` and `deployment_exposure` for `target_type == "binary"`, configurable via `dashboard.org_score.weights.dast_multiplier` and `dashboard.org_score.weights.binary_multiplier`
  - Running the pipeline with existing SAST-only data produces identical output (new columns are empty/default)

### 5. Create DAST skill (dast/SKILL.md)
- Implements: TR-005
- Files: `skills/dast/SKILL.md` (new)
- Depends on: none
- Acceptance:
  - Frontmatter has `name: dast`, `pack: security`, `user_invocable: true`, `args: mode`, `argument-hint` listing setup/run/ingest/status
  - Mode `setup`: reads `targets.web_apps` from client profile, generates ZAP config + Nuclei config + GH Actions workflow per target, writes to `~/.dream-studio/security/dast/{client}/{target}/` and `~/.dream-studio/security/actions/{client}/`
  - Mode `run`: confirms URL reachable, runs ZAP headless + Nuclei locally, stores results in `~/.dream-studio/security/scans/{client}/{target}/{date}/`
  - Mode `ingest`: parses ZAP JSON + Nuclei JSONL via `parse_dast.py`, normalizes to unified findings with `target_type: webapp`, writes scan-meta.json with `target_type: webapp`
  - Mode `status`: shows which web app targets have been scanned, staleness, coverage
  - Anti-patterns section warns about active scanning against production (passive default), auth complexity, missing tools
  - Structure follows `scan/SKILL.md` conventions (step numbering, gate stops, output schemas)

### 6. Create ZAP Automation Framework template
- Implements: TR-006
- Files: `templates/security/dast/zap-config.yaml.j2` (new)
- Depends on: none
- Acceptance:
  - Valid Jinja2 template that renders a ZAP Automation Framework YAML
  - Template variables: `target.url`, `target.auth.type`, `target.auth.token_env`, `target.scan_profile`, `target.excluded_paths`
  - Rendered output includes: context definition (URL, auth, excludes), passive scan config, active scan config (conditional on `scan_profile == "full"`), spider config, JSON report output
  - Auth section handles oauth2, basic, api_key, none types
  - `scan_profile: passive` only runs passive scan (no active fuzzing)

### 7. Create Nuclei config + DAST GH Actions templates
- Implements: TR-007
- Files: `templates/security/dast/nuclei-config.yaml.j2` (new), `templates/security/github-actions/dast-scan.yml.j2` (new)
- Depends on: none
- Acceptance:
  - `nuclei-config.yaml.j2` renders a Nuclei config selecting template tags based on `target.scan_profile` and detected stack
  - `dast-scan.yml.j2` renders a GitHub Actions workflow that:
    - Uses `zaproxy/action-full-scan@v0.12.0` with the generated ZAP config
    - Uses `projectdiscovery/nuclei-action@main` with selected templates
    - Uploads ZAP JSON + Nuclei JSONL as artifacts
    - Has `workflow_dispatch` trigger + optional schedule from client profile
  - Template variables sourced from client profile `targets.web_apps` entries
  - Follows same Jinja2 + `{% raw %}` patterns as existing `security-scan.yml.j2`

### 8. Create parse_dast.py ETL script
- Implements: TR-008
- Files: `templates/security/etl/parse_dast.py` (new)
- Depends on: 2
- Acceptance:
  - `parse_zap_json(data, target_name)` parses ZAP Automation Framework JSON report (detects via `"@version"` + `"site"` keys), returns list of finding dicts with: `target_type: "webapp"`, `url`, `http_method`, `parameter`, `response_code`, `evidence`, `attack_vector`
  - `parse_nuclei_jsonl(path, target_name)` parses Nuclei JSONL output (one JSON object per line with `"template-id"`), returns list of finding dicts
  - Both parsers map to CWE/OWASP using ZAP alert IDs and Nuclei template metadata
  - Rule ID patterns: `DAST-zap-{N}`, `DAST-nuc-{template-id}`
  - Fingerprinting uses `_fingerprint()` pattern from parse_sarif.py
  - Auto-detect function recognizes ZAP and Nuclei formats
  - CLI: `--client`, `--scans-dir`, `--output`, `--sample` (generates synthetic DAST findings)
  - Follows same stdin/stdout/stderr conventions as parse_sarif.py

### 9. Create binary-scan skill (binary-scan/SKILL.md)
- Implements: TR-009
- Files: `skills/binary-scan/SKILL.md` (new)
- Depends on: none
- Acceptance:
  - Frontmatter has `name: binary-scan`, `pack: security`, `user_invocable: true`, modes: setup/analyze/ingest/status
  - Mode `setup`: reads `targets.binaries` from client profile, generates YARA rules + checksec config + analyze.sh per target, writes to `~/.dream-studio/security/binary/{client}/{target}/`
  - Mode `analyze`: locates binary from config, runs checksec + YARA + strings extraction + PE/ELF header parsing, stores in scan dir
  - Mode `ingest`: parses checksec JSON + YARA JSON via `parse_binary.py`, normalizes to unified findings with `target_type: binary`
  - Mode `status`: coverage report for binary targets
  - Platform detection: uses `winchecksec` on Windows, `checksec` on Linux
  - Structure follows `scan/SKILL.md` conventions

### 10. Create YARA rule + checksec config templates
- Implements: TR-010
- Files: `templates/security/binary/yara-rules.yar.j2` (new), `templates/security/binary/checksec-config.yaml.j2` (new), `templates/security/binary/analyze.sh.j2` (new)
- Depends on: none
- Acceptance:
  - `yara-rules.yar.j2` generates YARA rules from client profile `data.pii_patterns` + `data.critical` terms + hardcoded malware signature patterns; valid YARA syntax when rendered
  - `checksec-config.yaml.j2` lists which hardening checks to run (NX, PIE, RELRO, canaries, FORTIFY, CFI) with pass/fail thresholds
  - `analyze.sh.j2` renders a shell script that: runs checksec, runs YARA, runs strings + grep for secrets/URLs, collects PE/ELF headers, outputs JSON results
  - Template variables sourced from `targets.binaries` entries + `data.*` from client profile

### 11. Create parse_binary.py ETL script
- Implements: TR-011
- Files: `templates/security/etl/parse_binary.py` (new)
- Depends on: 2
- Acceptance:
  - `parse_checksec_json(data, target_name)` parses checksec JSON output (detects via `"file"` key with nested hardening checks), returns one finding per failed check with: `target_type: "binary"`, `binary_name`, `binary_hash`, `hardening_check`
  - `parse_yara_json(data, target_name)` parses YARA JSON output (detects via `"matches"` array with `"rule"` entries), returns one finding per match with: `yara_rule`, `binary_section`
  - `parse_strings_findings(data, target_name)` handles strings/grep analysis output
  - Rule ID patterns: `BIN-chk-{check}`, `BIN-yar-{rule}`, `BIN-str-{N}`, `BIN-hdr-{N}`
  - CLI: `--client`, `--scans-dir`, `--output`, `--sample`
  - Follows same conventions as parse_sarif.py

### 12. Create binary scan GH Actions template
- Implements: TR-012
- Files: `templates/security/github-actions/binary-scan.yml.j2` (new)
- Depends on: none
- Acceptance:
  - Renders a GH Actions workflow that:
    - Triggers on release publish + workflow_dispatch
    - Downloads release artifacts matching `artifact_pattern` from `artifact_repo`
    - Runs checksec (via Docker or install step)
    - Runs YARA with generated rules
    - Uploads JSON results as artifacts
  - Template variables from `targets.binaries` entries
  - Handles `artifact_source: github-release` and `artifact_source: ci-artifact`

### 13. Update security-audit workflow YAML
- Implements: TR-013
- Files: `workflows/security-audit.yaml` (new — no existing security workflow found)
- Depends on: 5, 9
- Acceptance:
  - Workflow has nodes: `intake` → parallel [`generate-rules`, `dast-scan`, `binary-scan`] → `ingest-scans` → parallel [`mitigate`, `comply`, `netcompat`] → `export-dashboard`
  - `dast-scan` node: `skill: dast`, `input: mode: run`
  - `binary-scan` node: `skill: binary-scan`, `input: mode: analyze`
  - `ingest-scans` depends on all three scan nodes
  - Existing parallel analysis nodes (mitigate, comply, netcompat) unchanged
  - Valid YAML, follows same node schema as other workflow files

### 14. Update routing table + packs.yaml
- Implements: TR-014
- Files: `CLAUDE.md`, `packs.yaml`
- Depends on: 5, 9
- Acceptance:
  - `CLAUDE.md` Security Pack table has two new rows:
    - DAST: `dream-studio:dast` with triggers `dast:, web scan, pen test web, zap scan`
    - Binary: `dream-studio:binary-scan` with triggers `binary-scan:, scan binary, analyze exe, checksec`
  - `packs.yaml` security skills list is `[scan, dast, binary-scan, mitigate, comply, netcompat, security-dashboard]`
  - No other changes to CLAUDE.md or packs.yaml

### 15. Add dashboard DAST + Binary pages to spec
- Implements: TR-015
- Files: `templates/security/powerbi/dashboard-spec.md`
- Depends on: 2
- Acceptance:
  - Dashboard spec header updated: "Pages: 16 total"
  - Page 15 — DAST Overview: cards (DAST Findings, Critical DAST, Web Apps Scanned), bar chart by OWASP, findings table, donut by target
  - Page 16 — Binary Analysis: cards (Binary Findings, Failed Hardening, YARA Matches), checksec table, YARA table, bar by target
  - New DAX measures added to Shared Measures section: `DAST Findings`, `Binary Findings`, `SAST Findings`, `Web Apps Scanned`, `Binaries Analyzed`
  - Page 1 update note: add `target_type` slicer
  - Page 13 update note: rename to "Target Inventory"
  - Data Model section updated: Findings table has new columns, new `Targets` table relationship noted

### 16. End-to-end test with sample DAST + binary data
- Implements: TR-008, TR-011, TR-002
- Files: none (verification task — runs pipeline)
- Depends on: 4, 8, 11
- Acceptance:
  - `parse_dast.py --sample --client plmarketing-kroger` produces valid JSON with `target_type: webapp` findings
  - `parse_binary.py --sample --client plmarketing-kroger` produces valid JSON with `target_type: binary` findings
  - Full pipeline runs: `parse_sarif.py --sample` + `parse_dast.py --sample` → combined findings → `score_findings.py` → `export_dataset.py`
  - Output `findings.csv` has rows with all three `target_type` values
  - Output `targets.csv` exists with repo, webapp, and binary rows
  - `repos.csv` still exists with only repo-type entries
  - All existing columns preserved, new columns populated for DAST/binary rows

## Summary

| # | Task | Depends on | TR-IDs | Complexity |
|---|------|------------|--------|------------|
| 1 | Expand client profile schema | none | TR-001 | low |
| 2 | Expand findings schema in parse_sarif.py | none | TR-002 | low |
| 3 | Update PLMarketing-Kroger profile | 1 | TR-003 | low |
| 4 | Update export_dataset.py + score_findings.py | 2 | TR-002, TR-004, TR-016 | medium |
| 5 | Create DAST skill (SKILL.md) | none | TR-005 | medium |
| 6 | Create ZAP config template | none | TR-006 | medium |
| 7 | Create Nuclei config + DAST GH Actions template | none | TR-007 | medium |
| 8 | Create parse_dast.py ETL script | 2 | TR-008 | high |
| 9 | Create binary-scan skill (SKILL.md) | none | TR-009 | medium |
| 10 | Create YARA + checksec templates | none | TR-010 | medium |
| 11 | Create parse_binary.py ETL script | 2 | TR-011 | high |
| 12 | Create binary scan GH Actions template | none | TR-012 | medium |
| 13 | Create security-audit workflow YAML | 5, 9 | TR-013 | low |
| 14 | Update routing table + packs.yaml | 5, 9 | TR-014 | low |
| 15 | Add dashboard DAST + Binary pages | 2 | TR-015 | medium |
| 16 | End-to-end test (verification) | 4, 8, 11 | TR-008, TR-011, TR-002 | medium |

## Parallelism

**Wave 6 (Foundation):** Tasks 1, 2 in parallel → then 3, 4 (depend on 1, 2)
**Wave 7 (DAST):** Tasks 5, 6, 7 in parallel → then 8 (depends on 2)
**Wave 8 (Binary):** Tasks 9, 10, 12 in parallel → then 11 (depends on 2)
**Wave 9 (Integration):** Tasks 13, 14, 15 after skills exist → then 16 (end-to-end)

Waves 7 and 8 can run in parallel with each other (no cross-dependencies).
