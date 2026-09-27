---
dream_studio:
  skill_id: ds-security
  pack: security
  mode: dashboard
  mode_type: report
  inputs: [scan_results, compliance_mappings, mitigations, network_compat]
  outputs: [etl_pipeline, powerbi_datasets, risk_score, executive_report]
  capabilities_required: [Read, Write, Bash]
  model_preference: haiku
  estimated_duration: 20-45min
  write_posture: independent
  lifecycle: published
---

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
- `template` — Hand off the Power BI dashboard spec (`templates/security/powerbi/dashboard-spec.md`) and a connection-info README showing the dataset path for this client. No `.pbit` file ships with this repo today; a human builds the actual `.pbit` in Power BI Desktop by following the spec.

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

## Mode: `template`

**This delivers a spec, not a binary template.** No `.pbit` file ships anywhere in
this repo — only `templates/security/powerbi/dashboard-spec.md`, a markdown
specification of the dashboard's data model, DAX measures, page layouts, and M-query
data source configuration. Building the real `.pbit` from that spec is a manual step
in Power BI Desktop; this skill does not automate it.

### Steps
1. Check that the dataset directory exists: `~/.dream-studio/security/datasets/{client}/`
2. Point the user at `templates/security/powerbi/dashboard-spec.md` and the dataset path.
3. Generate a connection-info README summarizing the CSV files and how to wire the
   spec's parameters (`ClientName`, `Enterprise`, `DatasetPath`, `RulePrefix`) to
   this client's data.

## Anti-Patterns

- **Do NOT run scans from this skill.** Scanning is `ds-security scan`'s responsibility. This skill only reads existing scan results.
- **Do NOT modify scan SARIF/JSON files.** The ETL pipeline is read-only over scan data.
- **Do NOT hardcode client names.** Always parameterize from `--client` argument.
- **Do NOT skip the validation step.** If scans directory is empty, abort with a clear message directing the user to run `scan:ingest` first.
- **Do NOT claim a `.pbit` file was produced.** `template` mode hands off the markdown spec and a connection README to `~/Downloads/`; it does not generate or copy a binary Power BI template, because none exists in this repo.
- **Do NOT overwrite trends.csv entirely.** The export script preserves history automatically — only the current date's row is replaced.

---

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
