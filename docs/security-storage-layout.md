# Security Storage Layout

All security skills write to `~/.dream-studio/security/`. This is the single source of truth for security data paths.

## Directory Structure

```
~/.dream-studio/security/
├── scans/{client}/{repo}/{date}/       # Ingested scan results
│   ├── semgrep.sarif                   # Semgrep SARIF output
│   ├── trivy.json                      # Trivy JSON output
│   ├── codeql.sarif                    # CodeQL SARIF (if enabled)
│   ├── zap-report.json                 # ZAP DAST results
│   └── scan-meta.json                  # Metadata (date, scanner versions, finding counts)
│
├── datasets/{client}/                  # Processed datasets for analysis
│   ├── mitigations.csv                 # Per-finding fix recommendations (mitigate skill)
│   ├── mitigations.md                  # Sprint planning export (markdown)
│   ├── mitigations-{date}.json         # Timestamped snapshot
│   ├── compliance.csv                  # Framework control mappings (comply skill)
│   ├── compliance-gaps.md              # Controls with no scan coverage
│   ├── evidence-{framework}.md         # Audit-ready evidence docs
│   ├── netcompat-{date}.json           # Zscaler compatibility analysis
│   └── dashboard-export-{date}.csv     # Power BI dataset export
│
├── rules/{client}/                     # Generated scanner configurations
│   ├── data-protection.yaml            # Custom Semgrep rules
│   ├── injection.yaml
│   ├── access-control.yaml
│   ├── secrets.yaml
│   ├── transport.yaml
│   └── netcompat.yaml
│
├── actions/{client}/                   # Generated GitHub Actions workflows
│   └── security-scan.yml               # CI/CD scanner workflow
│
├── binaries/{client}/                  # Binary analysis artifacts (binary-scan)
│   ├── {filename}-{hash}/
│   │   ├── checksec.json               # Hardening analysis
│   │   ├── yara-matches.json           # Malware signature matches
│   │   └── metadata.json               # PE/ELF/Mach-O metadata
│
└── checkpoint.json                     # Concurrency guard (secure skill)
```

## Path Patterns

### Scan Results
**Pattern:** `scans/{client}/{repo}/{YYYY-MM-DD}/`

**Example:** `scans/kroger/vendor-portal/2026-04-26/semgrep.sarif`

**Written by:** `scan:ingest`, `dast:run`  
**Read by:** `secure`, `mitigate`, `comply`, `security-dashboard`

---

### Datasets
**Pattern:** `datasets/{client}/{dataset}.csv`

**Examples:**
- `datasets/kroger/mitigations.csv`
- `datasets/kroger/compliance.csv`
- `datasets/kroger/dashboard-export-2026-04-26.csv`

**Written by:** `mitigate`, `comply`, `security-dashboard`  
**Read by:** `security-dashboard` (ETL), Power BI (external)

---

### Generated Rules
**Pattern:** `rules/{client}/{category}.yaml`

**Example:** `rules/kroger/injection.yaml`

**Written by:** `scan:setup`  
**Read by:** GitHub Actions scanner workflow (external)

---

### Actions Workflows
**Pattern:** `actions/{client}/security-scan.yml`

**Example:** `actions/kroger/security-scan.yml`

**Written by:** `scan:setup`  
**Deployed to:** `.github/workflows/security-scan.yml` (user commits to each repo)

---

## File Formats

| Extension | Format | Used For |
|-----------|--------|----------|
| `.sarif` | SARIF 2.1.0 | Semgrep, CodeQL scan results |
| `.json` | JSON | Trivy, ZAP, metadata, snapshots |
| `.csv` | CSV | Datasets for Power BI, sprint planning |
| `.md` | Markdown | Evidence docs, gap reports, sprint exports |
| `.yaml` | YAML | Semgrep rules, GitHub Actions workflows |

---

## Cleanup Policy

**Scan results:** Retain last 90 days per repo. Older results auto-archived to `scans-archive/`.

**Datasets:** Retain all versions (timestamped snapshots). CSV is always "latest", JSON snapshots preserve history.

**Generated rules/actions:** Never auto-delete (client-specific config).

**Checkpoint:** Auto-reset to `idle` after 24 hours.

---

## Skill-Specific Paths

| Skill | Reads From | Writes To |
|-------|------------|-----------|
| `scan:setup` | (none) | `rules/{client}/`, `actions/{client}/` |
| `scan:ingest` | GitHub Actions artifacts | `scans/{client}/{repo}/{date}/` |
| `scan:status` | `scans/{client}/` | (none, reports only) |
| `secure` | (inline code diff) | `checkpoint.json` (temp) |
| `mitigate` | `scans/{client}/` | `datasets/{client}/mitigations.*` |
| `comply` | `scans/{client}/` | `datasets/{client}/compliance.*` |
| `dast` | (target URL) | `scans/{client}/{repo}/{date}/zap-report.json` |
| `netcompat` | `scans/{client}/` | `datasets/{client}/netcompat-{date}.json` |
| `binary-scan` | (binary file path) | `binaries/{client}/{filename}-{hash}/` |
| `security-dashboard` | `datasets/{client}/` | `datasets/{client}/dashboard-export-{date}.csv` |
