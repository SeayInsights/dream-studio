# Security Dashboard — ETL Orchestration + Power BI Export

## Before you start
Read `gotchas.yml` in this directory before every invocation.

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

## Anti-Patterns

- **Do NOT run scans from this skill.** Scanning is `dream-studio:scan`'s responsibility. This skill only reads existing scan results.
- **Do NOT modify scan SARIF/JSON files.** The ETL pipeline is read-only over scan data.
- **Do NOT hardcode client names.** Always parameterize from `--client` argument.
- **Do NOT skip the validation step.** If scans directory is empty, abort with a clear message directing the user to run `scan:ingest` first.
- **Do NOT write the Power BI .pbit file to the project directory.** Always write to `~/Downloads/` per the file output rule.
- **Do NOT overwrite trends.csv entirely.** The export script preserves history automatically — only the current date's row is replaced.

---

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
