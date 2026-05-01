---
name: scan
model_tier: sonnet
description: "Security scanning orchestrator — generates GitHub Actions workflows and Semgrep custom rules from client profiles, ingests SARIF/JSON results into structured storage, and reports scan coverage across a client's GitHub org. Trigger on scan:, scan org:, run security scan."
user_invocable: true
args: mode
argument-hint: "[setup | ingest | status] [--client <name>] [--repo <repo>] [--file <path>]"
pack: quality
chain_suggests:
  - condition: "findings_found"
    next: "mitigate"
    prompt: "Vulnerabilities found — run mitigate?"
---

# Scan — Security Scanning Orchestrator

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`scan:`, `scan org:`, `run security scan`, `/scan`

## Purpose
Orchestrate security scanning across a client's GitHub org without running scans directly. The skill generates GitHub Actions workflows from templates, fills Semgrep rule Jinja2 templates with client-specific data, and ingests SARIF/JSON results into a structured store for downstream skills (`secure`, `dashboard-dev`).

This skill never pushes to GitHub. It outputs files for the user to commit. It never executes scanners locally — it generates configuration and ingests results.

## Modes
- `setup` — Generate a `security-scan.yml` GitHub Actions workflow and custom Semgrep rules for a client, ready to commit to each repo.
- `ingest` — Pull SARIF or JSON scan results from GitHub Actions artifacts or a local file path into `~/.dream-studio/security/scans/{client}/{repo}/{date}/`.
- `status` — Show scan coverage: which repos are scanned, which results are stale (>7 days), which have no scanner configured.

---

## Storage
See `docs/security-storage-layout.md`. Uses:
- `scans/{client}/{repo}/{date}/` — Ingested scan results
- `rules/{client}/` — Generated Semgrep rules
- `actions/{client}/` — Generated GitHub Actions workflow

## Templates
See `templates/security/README.md`. Uses:
- `semgrep-rules/*.yaml.j2` — Custom rule templates
- `github-actions/security-scan.yml.j2` — CI workflow template

## Client Profile
See `docs/client-profile-schema.md`. Required: `client.name`, `client.github_org`, `stack.languages`. Optional: `data.*`, `isolation.*`, `network.proxy.*`, `scan.*`

## Orchestration
See `docs/security-orchestration-pattern.md` for standard workflow. Mode-specific steps:

### Mode: `setup`

**Parse:** `--client <name>` (required), `--repo <repo>` (optional)  
**Load:** Validate `client.name`, `client.github_org`, `stack.languages`

**Generate:** Render 6 Semgrep rule templates + 1 GitHub Actions workflow using client profile data. Write to `rules/{client}/` and `actions/{client}/`.  
**Output:** File list + commit instructions. Next: `scan ingest` after first workflow run.

---

### Mode: `ingest`

#### Step I0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--repo <repo>` — required.
- `--file <path>` — optional. If provided, ingest from a local SARIF/JSON file. If absent, pull from GitHub Actions artifacts.

#### Step I1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`. Confirm `client.github_org` is present.
2. If profile missing: **stop** with the same error as Step S1.

#### Step I2: Resolve Result Source

**If `--file` is provided:**
1. Confirm the file exists and is readable.
2. Detect format: SARIF (`.sarif`, `.json` with `$schema` containing `sarif`) or plain JSON.
3. Proceed to Step I3.

**If `--file` is absent (GitHub Actions source):**
1. Use `gh run list --repo {github_org}/{repo} --workflow security-scan.yml --limit 1 --json databaseId,status,conclusion` to find the latest run.
2. If no run found: **stop** with — "No completed `security-scan.yml` run found for `{github_org}/{repo}`. Commit the workflow first using `scan setup`, then trigger a run."
3. If latest run `conclusion` is not `success`: warn — "Latest run concluded `{conclusion}`. Ingesting anyway — findings may be partial."
4. Download artifacts: `gh run download {run_id} --repo {github_org}/{repo} --dir /tmp/scan-{client}-{repo}/`
5. Find SARIF/JSON files in the download directory.

#### Step I3: Parse and Store Results

1. Determine date: ISO-8601 date of the run (or today for local files).
2. Create storage directory: `~/.dream-studio/security/scans/{client}/{repo}/{date}/`
3. Copy/move result files into the directory. Preserve original filenames.
4. Write `scan-meta.json`:

```json
{
  "schema_version": 1,
  "client": "{client}",
  "repo": "{repo}",
  "date": "{YYYY-MM-DD}",
  "source": "github-actions | local-file",
  "run_id": "{run_id | null}",
  "files": ["semgrep.sarif", "trivy.json"],
  "finding_counts": {
    "critical": N,
    "high": N,
    "medium": N,
    "low": N,
    "note": N
  },

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
