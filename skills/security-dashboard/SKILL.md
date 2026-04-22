---
name: security-dashboard
description: "ETL orchestration + Power BI dataset export — runs the full security ETL pipeline (SARIF → scored → compliance-mapped → mitigated → Power BI CSVs), calculates org risk score from client profile weights, and manages the Power BI template lifecycle. Trigger on security dashboard:, refresh dashboard, export dataset."
user_invocable: true
args: mode
argument-hint: "[generate | refresh | template] [--client <name>]"
pack: security
---

# Security Dashboard — ETL Orchestration + Power BI Export

## Trigger
`security dashboard:`, `refresh dashboard`, `export dataset`, `/security-dashboard`

## Purpose
Run the full security ETL pipeline to transform raw scan results into Power BI-ready datasets. The pipeline parses SARIF/JSON scan outputs, scores findings by CVSS and business impact, merges compliance mappings, merges mitigation recommendations, merges network compatibility data, calculates a composite org risk score, and exports structured CSVs that plug directly into the enterprise security Power BI template.

This skill never modifies scan results or client code. It reads from upstream skill outputs and writes to the dataset directory.

## Modes
- `generate` — Run the full ETL pipeline from scratch. Parses all scan results, scores, maps, mitigates, and exports the complete dataset.
- `refresh` — Re-run ETL with latest scan data. Preserves trends history (appends to trends.csv instead of overwriting). Use after new scans are ingested via `scan:ingest`.
- `template` — Copy the Power BI template (.pbit) to `~/Downloads/` with a connection-info README showing the dataset path for this client.

---

## Storage Layout

```
~/.dream-studio/security/
├── scans/{client}/{repo}/{date}/       # INPUT: ingested scan results (from scan:ingest)
│   ├── semgrep.sarif
│   ├── bandit.json
│   ├── trufflehog.json
│   └── scan-meta.json
├── datasets/{client}/                  # OUTPUT: Power BI-ready CSVs
│   ├── findings.csv
│   ├── mitigations.csv
│   ├── compliance.csv
│   ├── repos.csv
│   ├── trends.csv
│   ├── netcompat.csv
│   └── metadata.json
└── reports/{client}/                   # OUTPUT: executive report (downstream)
```

## ETL Scripts Referenced

Source scripts live in the dream-studio repo:

```
builds/dream-studio/templates/security/etl/
├── parse_sarif.py           # Step 1: SARIF/JSON → normalized findings JSON
├── score_findings.py        # Step 2: Add CVSS + business impact scores
├── map_compliance.py        # Step 3: Add compliance framework control IDs
├── generate_mitigations.py  # Step 4: Match findings to mitigation templates
├── analyze_netcompat.py     # Step 5: Zscaler/proxy compatibility scoring
└── export_dataset.py        # Step 6: Export all CSVs + metadata.json
```

---

## Client Profile Fields Used

Read from `~/.dream-studio/clients/{name}.yaml`:

| Profile field | Used by |
|---|---|
| `client.name`, `client.enterprise` | `generate`, `refresh` — metadata identity |
| `data.critical`, `data.sensitive` | `generate` — business impact scoring in score_findings |
| `isolation.tenant_key` | `generate` — access-control scoring weight |
| `network.proxy.*` | `generate` — netcompat analysis input |
| `compliance.frameworks` | `generate` — which frameworks to map (SOC 2, NIST CSF, OWASP ASVS) |
| `dashboard.org_score.weights` | `generate`, `refresh` — severity weights for org score formula |
| `scan.priority_repos` | `generate` — included in repos.csv |

---

## Mode: `generate`

Full ETL pipeline execution. Run this after `scan:ingest` has populated scan results and after `mitigate:findings`, `comply:map`, and `netcompat:analyze` have produced their outputs.

### Prerequisites
Before running `generate`, these must exist:
- `~/.dream-studio/security/scans/{client}/` — at least one repo with scan results
- `~/.dream-studio/clients/{client}.yaml` — valid client profile

### Orchestration Steps

1. **Validate inputs**
   - Read client profile from `~/.dream-studio/clients/{client}.yaml`
   - Confirm scans directory exists and has at least one repo with results
   - Confirm client profile has `dashboard.org_score.weights` (fall back to defaults if missing)

2. **Run parse_sarif.py**
   ```
   py -3.12 templates/security/etl/parse_sarif.py --client {client}
   ```
   Reads all SARIF/JSON files from `scans/{client}/`. Normalizes across scanner outputs (Semgrep SARIF, Bandit JSON, TruffleHog JSON, pip-audit JSON). Deduplicates. Outputs normalized findings JSON to stdout.

3. **Run score_findings.py**
   ```
   py -3.12 templates/security/etl/parse_sarif.py --client {client} | \
   py -3.12 templates/security/etl/score_findings.py --client {client}
   ```
   Reads normalized findings from stdin. Assigns CVSS scores from rule severity + CWE. Adds business impact score from client profile data classification. Calculates per-repo risk score. Outputs scored findings JSON to stdout.

4. **Run map_compliance.py**
   ```
   py -3.12 ... | py -3.12 templates/security/etl/map_compliance.py --client {client}
   ```
   Reads scored findings from stdin. Cross-references against compliance framework mapping YAMLs. Adds framework control IDs to each finding. Identifies gap controls (controls with no scan coverage). Outputs compliance-enriched JSON to stdout.

5. **Run generate_mitigations.py**
   ```
   py -3.12 ... | py -3.12 templates/security/etl/generate_mitigations.py --client {client}
   ```
   Reads compliance-enriched findings from stdin. Matches each finding to mitigation templates by rule ID, CWE, or OWASP category. Adds fix recommendations (code before/after, verification test, effort estimate). Outputs fully enriched JSON to stdout.

6. **Run analyze_netcompat.py** (parallel with steps 3-5 if desired)
   ```
   py -3.12 templates/security/etl/analyze_netcompat.py --client {client}
   ```
   Reads SARIF findings filtered to ZSC-* rules + client network profile. Calculates per-repo Zscaler compatibility score. Writes `netcompat.csv` directly to the datasets directory.

7. **Run export_dataset.py**
   ```
   py -3.12 ... | py -3.12 templates/security/etl/export_dataset.py --client {client}
   ```
   Reads fully enriched findings JSON from stdin. Exports all Power BI-ready CSVs. Calculates org risk score using weights from client profile. Writes `metadata.json` with summary statistics.

### Full pipeline command (chained)
```bash
ETL="builds/dream-studio/templates/security/etl"
py -3.12 $ETL/parse_sarif.py --client {client} | \
py -3.12 $ETL/score_findings.py --client {client} | \
py -3.12 $ETL/map_compliance.py --client {client} | \
py -3.12 $ETL/generate_mitigations.py --client {client} | \
py -3.12 $ETL/export_dataset.py --client {client}
```

Run `analyze_netcompat.py` separately (it writes directly to the dataset directory):
```bash
py -3.12 $ETL/analyze_netcompat.py --client {client}
```

### Output

After `generate` completes, report:

```
DASHBOARD GENERATED: {client}
  Org score:       {score}/100
  Total findings:  {count}
  Repos scanned:   {count}
  Dataset path:    ~/.dream-studio/security/datasets/{client}/
  Files:
    findings.csv      ({N} rows)
    mitigations.csv   ({N} rows)
    compliance.csv    ({N} rows)
    repos.csv         ({N} rows)
    trends.csv        ({N} rows)
    netcompat.csv     ({N} rows)
    metadata.json
```

---

## Mode: `refresh`

Re-run the ETL pipeline with the latest scan data. Identical to `generate` except:
- `trends.csv` appends a new row for today rather than overwriting (the export_dataset.py script handles this automatically — it preserves existing rows and replaces only the current date's entry)
- Report includes delta from previous run (findings added/resolved, score change)

### Orchestration Steps

Same as `generate` steps 1-7. The pipeline scripts are idempotent — running them again with updated scan data produces correct output.

After running, compare current `metadata.json` against the previous one (if it exists) to compute deltas:
- Findings delta: new count - previous count
- Score delta: new score - previous score
- New repos: repos in current but not previous

### Output

```
DASHBOARD REFRESHED: {client}
  Org score:       {score}/100 ({delta})
  Total findings:  {count} ({delta})
  Repos scanned:   {count}
  New findings:    {count}
  Resolved:        {count}
  Dataset path:    ~/.dream-studio/security/datasets/{client}/
```

---

## Mode: `template`

Copy the Power BI template and generate a connection-info README for this client.

### Orchestration Steps

1. Check that the dataset directory exists: `~/.dream-studio/security/datasets/{client}/`
2. Copy the Power BI template to `~/Downloads/enterprise-security-{client}.pbit`
3. Generate a connection README at `~/Downloads/enterprise-security-{client}-README.txt` containing:
   - Dataset directory path (absolute)
   - CSV file list with column descriptions
   - Data model relationship instructions for Power BI Desktop
   - Parameter setup instructions (client name, dataset path)

### Data Model Relationships (for Power BI)

Document these relationships in the README:

| From | To | Key | Cardinality |
|---|---|---|---|
| findings.csv | mitigations.csv | id → finding_id | 1:1 |
| findings.csv | compliance.csv | compliance_controls → control_id | M:N (via split) |
| findings.csv | repos.csv | repo → name | M:1 |
| findings.csv | trends.csv | (date aggregation) | via date column |
| repos.csv | netcompat.csv | name → repo | 1:1 |

### Output

```
TEMPLATE EXPORTED: {client}
  Power BI template: ~/Downloads/enterprise-security-{client}.pbit
  Connection README: ~/Downloads/enterprise-security-{client}-README.txt
  Dataset path:      ~/.dream-studio/security/datasets/{client}/
```

---

## Dataset Schema Reference

### findings.csv
| Column | Type | Description |
|---|---|---|
| id | string | Unique finding identifier |
| repo | string | Repository name |
| file | string | File path within repo |
| line | int | Line number |
| rule_id | string | Scanner rule ID (e.g., KRG-001, ZSC-003) |
| severity | string | critical / high / medium / low |
| cvss | float | Estimated CVSS score |
| business_impact | string | Impact level from client data classification |
| risk_score | float | Composite risk score (CVSS × business impact weight) |
| owasp | string | OWASP Top 10 category |
| cwe | string | CWE identifier |
| status | string | open / resolved / suppressed |
| age_days | int | Days since first detected |
| scanner | string | Source scanner (semgrep, bandit, trufflehog, pip-audit) |
| message | string | Finding description |
| compliance_controls | string | Semicolon-separated framework control IDs |

### mitigations.csv
| Column | Type | Description |
|---|---|---|
| finding_id | string | References findings.id |
| rule_id | string | Scanner rule ID |
| title | string | Mitigation title |
| immediate_fix | string | Short-term fix description |
| long_term_fix | string | Architectural fix description |
| verification_test | string | How to verify the fix works |
| effort_estimate | string | Estimated effort (hours/days) |
| code_before | string | Vulnerable code example |
| code_after | string | Fixed code example |

### compliance.csv
| Column | Type | Description |
|---|---|---|
| framework | string | SOC2 / NIST-CSF / OWASP-ASVS / CWE-TOP25 |
| control_id | string | Framework control identifier |
| title | string | Control title/description |
| covered_by_scan | string | yes / partial / no |
| finding_count | int | Number of findings mapped to this control |
| gap_status | string | covered / gap |

### repos.csv
| Column | Type | Description |
|---|---|---|
| name | string | Repository name |
| language | string | Primary language |
| last_scan | date | Last scan date (ISO 8601) |
| risk_score | float | Aggregate repo risk score |
| finding_count | int | Total findings |
| critical_count | int | Critical severity count |
| high_count | int | High severity count |

### trends.csv
| Column | Type | Description |
|---|---|---|
| date | date | Scan date (ISO 8601) |
| total_findings | int | Total findings on this date |
| critical | int | Critical count |
| high | int | High count |
| medium | int | Medium count |
| low | int | Low count |
| org_score | float | Org risk score on this date |
| resolved_count | int | Findings resolved since previous scan |

### netcompat.csv
| Column | Type | Description |
|---|---|---|
| repo | string | Repository name |
| zscaler_score | float | Compatibility score (0-100) |
| cert_pinning | string | pass / fail / not_applicable |
| dlp_risk | string | Risk level for DLP trigger |
| port_issues | string | Non-standard port findings |
| fixes_needed | string | Summary of required fixes |

### metadata.json
```json
{
  "client_name": "PLMarketing",
  "enterprise": "Kroger",
  "scan_date": "2026-04-22",
  "total_repos": 12,
  "total_findings": 147,
  "severity_counts": {
    "critical": 3,
    "high": 18,
    "medium": 67,
    "low": 59
  },
  "org_score": 62.4,
  "frameworks": ["SOC2", "NIST-CSF", "OWASP-ASVS"]
}
```

---

## Org Score Formula

```
org_score = 100 - (weighted_penalty_sum / ceiling) × 100
```

Where:
- `weighted_penalty_sum` = Σ (severity_weight for each finding)
- `ceiling` = total_findings × max(severity_weights)
- Default weights: `{ critical: 10, high: 4, medium: 1, low: 0.25 }`
- Clamped to 0-100

Override weights via client profile:
```yaml
dashboard:
  org_score:
    weights:
      critical: 10
      high: 4
      medium: 1
      low: 0.25
```

---

## Anti-Patterns

- **Do NOT run scans from this skill.** Scanning is `dream-studio:scan`'s responsibility. This skill only reads existing scan results.
- **Do NOT modify scan SARIF/JSON files.** The ETL pipeline is read-only over scan data.
- **Do NOT hardcode client names.** Always parameterize from `--client` argument.
- **Do NOT skip the validation step.** If scans directory is empty, abort with a clear message directing the user to run `scan:ingest` first.
- **Do NOT write the Power BI .pbit file to the project directory.** Always write to `~/Downloads/` per the file output rule.
- **Do NOT overwrite trends.csv entirely.** The export script preserves history automatically — only the current date's row is replaced.

---

## Feed Integration

After `generate` or `refresh`, update `~/.dream-studio/feeds/security.json`:

```json
{
  "last_scan": {
    "client": "plmarketing-kroger",
    "date": "2026-04-22",
    "repos_scanned": 12,
    "findings_count": 147,
    "org_score": 62.4
  },
  "last_report": {
    "path": "~/.dream-studio/security/reports/plmarketing-kroger/executive-report-2026-04-22.md",
    "date": "2026-04-22"
  },
  "active_workflow": null
}
```
