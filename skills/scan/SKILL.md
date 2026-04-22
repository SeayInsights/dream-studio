---
name: scan
description: "Security scanning orchestrator — generates GitHub Actions workflows and Semgrep custom rules from client profiles, ingests SARIF/JSON results into structured storage, and reports scan coverage across a client's GitHub org. Trigger on scan:, scan org:, run security scan."
user_invocable: true
args: mode
argument-hint: "[setup | ingest | status] [--client <name>] [--repo <repo>] [--file <path>]"
pack: quality
---

# Scan — Security Scanning Orchestrator

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

## Storage Layout

```
~/.dream-studio/security/
├── scans/{client}/{repo}/{date}/      # Ingested scan results (SARIF/JSON)
│   ├── semgrep.sarif
│   ├── trivy.json
│   └── scan-meta.json
├── rules/{client}/                    # Generated Semgrep rule files
│   ├── data-protection.yaml
│   ├── injection.yaml
│   ├── access-control.yaml
│   ├── secrets.yaml
│   ├── transport.yaml
│   └── netcompat.yaml
└── actions/{client}/                  # Generated GitHub Actions workflow
    └── security-scan.yml
```

## Templates Referenced

Source templates live in the dream-studio repo:

```
builds/dream-studio/templates/security/
├── semgrep-rules/
│   ├── data-protection.yaml.j2
│   ├── injection.yaml.j2
│   ├── access-control.yaml.j2
│   ├── secrets.yaml.j2
│   ├── transport.yaml.j2
│   └── netcompat.yaml.j2
└── github-actions/
    └── security-scan.yml.j2
```

---

## Client Profile Fields Used

Read from `~/.dream-studio/clients/{name}.yaml`. Fields consumed by each mode:

| Profile field | Used by |
|---|---|
| `client.name`, `client.github_org` | All modes — identity |
| `data.critical`, `data.sensitive`, `data.pii_patterns` | `setup` — data-protection + secrets rules |
| `isolation.model`, `isolation.tenant_key`, `isolation.alternate_keys` | `setup` — access-control rules |
| `network.proxy.*` | `setup` — netcompat rules |
| `stack.languages` | `setup` — selects language rulesets for workflow |
| `scan.schedule` | `setup` — cron expression in generated workflow |
| `scan.priority_repos` | `setup`, `status` — repos to configure first |
| `scan.exclude_repos` | `setup`, `status` — repos to skip |
| `scan.semgrep_rulesets` | `setup` — community rulesets to include alongside custom rules |
| `scan.extra_scanners` | `setup` — additional scanners to add (e.g., trivy, codeql) |

---

## Orchestration Steps

Follow in order for the active mode. Do not skip steps. Do not proceed past a failed gate.

---

### Mode: `setup`

#### Step S0: Parse Arguments

Extract from user input:
- `--client <name>` — required. If absent, list available profiles and ask.
- `--repo <repo>` — optional. If provided, generate only for that repo. If absent, generate for all `scan.priority_repos`.

#### Step S1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. If file does not exist: **stop** with — "Client profile not found at `~/.dream-studio/clients/{client}.yaml`. Run `client-work:intake` to create it."
3. Validate required fields are present: `client.name`, `client.github_org`, `stack.languages`.
4. If `stack.languages` is empty or missing: warn — "No languages declared in profile. Generated workflow will use default Semgrep rulesets only."

#### Step S2: Generate Semgrep Rules

For each template in `builds/dream-studio/templates/security/semgrep-rules/`:

1. Read the `.j2` template file.
2. Fill Jinja2 variables using client profile data (mapping below).
3. Write rendered file to `~/.dream-studio/security/rules/{client}/{rule-name}.yaml`.
4. If a template has no matching profile data (e.g., `netcompat.yaml.j2` but `network.proxy` is absent): skip that template and note it in the output summary.

**Variable mapping per template:**

| Template | Profile fields injected |
|---|---|
| `data-protection.yaml.j2` | `data.critical`, `data.sensitive`, `data.pii_patterns` |
| `injection.yaml.j2` | `stack.languages` |
| `access-control.yaml.j2` | `isolation.model`, `isolation.tenant_key`, `isolation.alternate_keys` |
| `secrets.yaml.j2` | `data.critical`, `client.name` |
| `transport.yaml.j2` | `stack.languages` |
| `netcompat.yaml.j2` | `network.proxy.*` |

#### Step S3: Generate GitHub Actions Workflow

1. Read `builds/dream-studio/templates/security/github-actions/security-scan.yml.j2`.
2. Fill variables:
   - `client_name` → `client.name`
   - `github_org` → `client.github_org`
   - `schedule` → `scan.schedule` (cron string, e.g. `"0 2 * * 1"`)
   - `languages` → `stack.languages` (list)
   - `semgrep_rulesets` → `scan.semgrep_rulesets` (list of community ruleset IDs)
   - `custom_rules_path` → `.github/semgrep/` (the path where the user will commit the generated rules)
   - `extra_scanners` → `scan.extra_scanners` (list of scanner names)
3. Write rendered file to `~/.dream-studio/security/actions/{client}/security-scan.yml`.

#### Step S4: Present Output

Show the user:
1. Files generated (one per line with full path).
2. Step-by-step commit instructions:
   ```
   1. Copy .github/workflows/security-scan.yml → each target repo
   2. Create .github/semgrep/ directory in each repo
   3. Copy generated rule files from ~/.dream-studio/security/rules/{client}/ → .github/semgrep/
   4. Commit and push — the workflow will trigger on the next push or scheduled run
   ```
3. Any skipped templates and why.
4. Next step: "Run `scan ingest --client {client} --repo {repo}` after the first workflow run to pull results in."

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
  "ingested_at": "{ISO-8601}"
}
```

5. Parse SARIF to extract finding counts: iterate `runs[].results[]`, group by `level` (error=critical/high, warning=medium, note=low).

#### Step I4: Present Summary

Show:
1. Storage path where results were saved.
2. Finding counts table: Critical / High / Medium / Low / Note.
3. "Run `scan status --client {client}` to see full coverage, or `secure: pr-review` to triage findings."

---

### Mode: `status`

#### Step T0: Parse Arguments

Extract from user input:
- `--client <name>` — required.

#### Step T1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. Collect repo list: `scan.priority_repos` minus `scan.exclude_repos`. If `priority_repos` is empty, note that — coverage report will only reflect repos with ingested results.

#### Step T2: Inventory Scan Store

1. List all directories under `~/.dream-studio/security/scans/{client}/`.
2. For each repo directory found:
   - Find the most recent `{date}/` subdirectory.
   - Read `scan-meta.json` if present.
   - Determine staleness: if most recent scan date is >7 days ago, mark **STALE**.
3. For repos in `priority_repos` with no directory under `scans/{client}/`: mark **NO RESULTS**.

#### Step T3: Check Workflow Presence

For each repo in `priority_repos`:
1. Run `gh api repos/{github_org}/{repo}/contents/.github/workflows/security-scan.yml --silent` to check if the workflow file is committed.
2. If not found (404): mark **NO SCANNER**.

#### Step T4: Render Coverage Report

Output as a markdown table:

```
# Scan Coverage — {client} ({date})

| Repo | Scanner | Last Scan | Age | Critical | High | Status |
|------|---------|-----------|-----|----------|------|--------|
| repo-a | ✓ | 2026-04-20 | 2d | 0 | 1 | CURRENT |
| repo-b | ✓ | 2026-04-10 | 12d | 2 | 3 | STALE |
| repo-c | ✗ | — | — | — | — | NO SCANNER |
| repo-d | ✓ | — | — | — | — | NO RESULTS |

**Summary:** {N} repos total | {N} current | {N} stale | {N} no scanner | {N} no results

**Action items:**
- STALE repos: run `scan ingest --client {client} --repo {repo}` after next workflow run
- NO SCANNER repos: run `scan setup --client {client} --repo {repo}` to generate workflow
- NO RESULTS repos: workflow exists but no results ingested yet — trigger a run and ingest
```

---

## Output Schema

### `scan-meta.json` (written per ingested scan)

```json
{
  "schema_version": 1,
  "client": "string",
  "repo": "string",
  "date": "YYYY-MM-DD",
  "source": "github-actions | local-file",
  "run_id": "string | null",
  "files": ["filename.sarif", "filename.json"],
  "finding_counts": {
    "critical": 0,
    "high": 0,
    "medium": 0,
    "low": 0,
    "note": 0
  },
  "ingested_at": "ISO-8601"
}
```

### Generated workflow output location
`~/.dream-studio/security/actions/{client}/security-scan.yml`

### Generated rule output location
`~/.dream-studio/security/rules/{client}/{rule-name}.yaml` (one file per template rendered)

---

## Anti-patterns

- **Running scanners directly** — this skill generates configuration and ingests results. It never executes `semgrep`, `trivy`, or other tools locally. Scanning happens in GitHub Actions.
- **Pushing to GitHub** — never push generated workflow or rule files. Output them for the user to commit. The user controls what goes into client repos.
- **Inlining secrets from profile** — client profiles may contain tenant keys or API tokens. Never render these into workflow YAML or Semgrep rule files. Reference them as GitHub Actions secrets (`${{ secrets.KEY }}`).
- **Treating stale results as current** — results older than 7 days are STALE. Do not surface stale findings to `secure` or `ship` without a freshness warning.
- **Skipping `scan-meta.json`** — every ingested scan directory must have `scan-meta.json`. Downstream skills (`secure`, `dashboard-dev`) rely on it for counts and provenance. Never write raw SARIF without the meta file.
- **Generating rules without a profile** — do not interpolate empty strings into Jinja2 templates. If a required profile field is missing, skip that template and note it. Partially-filled rules produce false negatives.
- **Ignoring `scan.exclude_repos`** — always filter excluded repos from setup and status. Never generate workflows for excluded repos.
- **Acting on stale findings without confirming** — before triaging any finding from an ingested SARIF, confirm the code path still exists in the repo. Findings go stale within days of active development.
