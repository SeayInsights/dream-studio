---
dream_studio:
  skill_id: ds-security
  pack: security
  mode: scan
  mode_type: orchestration
  inputs: [client_profile, repo_list, scan_config]
  outputs: [github_workflows, semgrep_rules, scan_results, status_report]
  capabilities_required: [Read, Write, Bash]
  model_preference: haiku
  estimated_duration: 20-60min
  write_posture: independent
  lifecycle: published
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
See `<skill-dir>/templates/security/README.md`. Uses:
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
3. Keep the run's `databaseId` and `conclusion` for the run record (Step I3). If `conclusion` is not `success`, say so in chat and ingest anyway; the scan is recorded as partial, and the record, not the chat message, is what the dashboards and `scan status` read.
4. Get each scanner's own result: `gh run view {run_id} --repo {github_org}/{repo} --json jobs` lists the workflow's jobs with a `conclusion` each (`Semgrep SAST` = `semgrep`, `Bandit Python SAST` = `bandit`, `TruffleHog Secrets Scan` = `trufflehog`, `pip-audit Dependency CVEs` = `pip-audit`, `npm audit Dependency CVEs` = `npm-audit`). The CycloneDX job produces an SBOM, not findings: leave it out of the record.
5. Download artifacts: `gh run download {run_id} --repo {github_org}/{repo} --dir /tmp/scan-{client}-{repo}/`
6. Find SARIF/JSON files in the download directory.

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
  "source": "github-actions",
  "run_id": "{run_id}",
  "run": {"run_id": "{run_id}", "status": "completed", "conclusion": "{conclusion}"},
  "planned_steps": ["semgrep", "bandit"],
  "steps": [
    {"step": "semgrep", "status": "{ran|skipped|failed}", "tool": "semgrep"},
    {"step": "bandit", "status": "{ran|skipped|failed}", "tool": "bandit",
     "reason": "{why, when the status is not ran}"}
  ],
  "files": ["semgrep-results.sarif", "bandit-results.json"],
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

   `planned_steps` lists every scanner the workflow runs for this client: `semgrep`, plus
   each of `scan.extra_scanners` from the profile (`bandit`, `trufflehog`, `pip-audit`,
   `npm-audit`). `steps` is the run record, one entry per planned scanner: `ran` for a job
   that concluded `success`, `failed` for `failure` or `timed_out`, `skipped` for
   `cancelled` or `skipped`, with the `tool` and, when it did not run, the `reason` (for
   example "job concluded failure"). `run.conclusion` is the whole run's conclusion as
   `gh` reported it; a run that did not conclude `success` makes the scan `partial`
   whatever the steps say, and `parse_sarif.py` names it. A scan directory with no `steps`
   or `run` (an ingest from `--file`: nothing says which scanners ran or whether the run
   finished) reads `unknown`, never `complete`. Write `source` as `local-file` for it and
   omit `run`, `planned_steps` and `steps`. A `github-actions` scan always records `run`:
   with `source` `github-actions` and no `run` it reads `unknown` too. Write `run.status`
   as `completed` (a conclusion on a run that is not completed contradicts itself and reads
   `unknown`). A SARIF with no run, or whose runs hold no `results` list, is not a completed
   semgrep scan: it reads `partial` ("no runs in the SARIF"), and so does a second file for
   a scanner (named like it) that cannot be read.
   Every field is read as the type documented here (`source`, `outcome` and `run.status` text; `planned_steps` a list of text; `steps` a list of objects): a field present with another type (a list where text belongs) is a record the code cannot read, and the scan reads `unknown`, never `complete`. `null` is the same as absent.

5. Parse SARIF to extract finding counts: iterate `runs[].results[]`, group by `level` (error=critical/high, warning=medium, note=low).
6. Run `py -3.12 <skill-dir>/templates/security/etl/parse_sarif.py --client {client} --scans-dir {scan_dir} --coverage-output {scan_dir}/coverage.json`. Every finding carries `coverage` (`complete` | `partial` | `unknown`) and `limitations`; `coverage.json` holds the same per scan directory and is the only place coverage shows when a scan produced no findings. It reads the scanner outputs directly in `{scan_dir}` (SARIF, Bandit and pip-audit JSON, and TruffleHog's JSON Lines `trufflehog-results.jsonl`, one result per line); an output it has no reader for (npm audit) leaves that scanner `ran` but unread, so the scan is `partial` and the file is named. A TruffleHog result carries the secret itself in `Raw`; a finding never does: it carries the detector, file, line, whether TruffleHog verified it, and "value redacted", never the secret. The workflow writes TruffleHog's own log to `trufflehog.log` on the runner; that log is not uploaded, so ingest never sees it.

#### Step I4: Present Summary

Show:
1. Storage path where results were saved.
2. The coverage, first when it is not `complete`: the run's conclusion and every failed, skipped or unread scanner, from `coverage.json`. "No findings" from a partial scan is not a clean result.
3. Finding counts table: Critical / High / Medium / Low / Note.
4. "Run `scan status --client {client}` to see full coverage, or `secure: pr-review` to triage findings."

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
   - Skip a directory whose `scan-meta.json` has `target_type` `webapp` or `binary`: dast and binary-scan write under `scans/{client}/` too, and `dast status` and `binary-scan status` report them. A target is not a repo.
   - Find the most recent `{date}/` subdirectory whose `scan-meta.json` does not say `outcome` `not_scanned`: a `{date}-not-scanned` directory is a record that a scan did not happen (see `dast`), never the most recent scan, so it must not read CURRENT. When the newest directory is one, mark the repo **NOT SCANNED** with its `reason`, and show the date of the last scan that ran beside it.
   - Read `scan-meta.json` if present, and `coverage.json` beside it.
   - Determine staleness: if most recent scan date is >7 days ago, mark **STALE**.
   - Coverage: when `coverage.json` (or the `run` / `steps` of `scan-meta.json`) says `partial` (the run did not conclude `success`, or a scanner failed, was skipped or was not read) or `unknown` (no run record), say so in the Status column next to CURRENT or STALE, for example `CURRENT (partial: run concluded failure)`. A partial scan is not a clean one.
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
| repo-e | ✓ | 2026-04-02 | 20d | 0 | 4 | NOT SCANNED (target unreachable; last scan that ran 2026-04-02) |

**Summary:** {N} repos total | {N} current | {N} stale | {N} no scanner | {N} no results

**Action items:**
- STALE repos: run `scan ingest --client {client} --repo {repo}` after next workflow run
- NO SCANNER repos: run `scan setup --client {client} --repo {repo}` to generate workflow
- NO RESULTS repos: workflow exists but no results ingested yet — trigger a run and ingest
```

---

## Detailed Reference

See `examples.md` in this directory for the output schema, generated-file locations, and anti-patterns.
