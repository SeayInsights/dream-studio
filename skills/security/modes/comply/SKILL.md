# Comply — Compliance Framework Mapping

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`comply:`, `compliance map`, `audit evidence`, `/comply`

## Purpose
Map security scan findings to compliance framework controls, identify controls with no automated scan coverage, and generate audit-ready evidence documents. This skill bridges the gap between raw Semgrep findings and the compliance frameworks clients must satisfy — SOC 2 Type II, NIST CSF, OWASP ASVS, and CWE Top 25.

This skill never modifies findings. It reads, cross-references, and reports. All writes go to `~/.dream-studio/security/datasets/{client}/`.

## Modes
- `map` — Map all ingested findings to the compliance frameworks configured in the client profile. Reads findings from `~/.dream-studio/security/scans/{client}/`. Cross-references against mapping definitions in `templates/security/compliance/`. Writes to `~/.dream-studio/security/datasets/{client}/compliance.csv`.
- `gaps` — Identify controls with no automated scan coverage. Shows which framework controls have zero findings mapped to them — i.e., compliance obligations the current scanner configuration cannot satisfy.
- `evidence` — Generate an audit-ready evidence document (markdown). Per control: control ID, description, scan evidence, finding count, and remediation status.

---

## Anti-patterns

- **Treating zero findings as compliance** — a control with zero findings mapped to it is a coverage gap, not a clean bill of health. Always distinguish between "no findings because we scanned and found none" vs. "no findings because we have no rule covering this control."
- **Mapping without loading SARIF** — do not generate compliance.csv from finding_counts alone. Counts don't carry CWE/OWASP metadata needed for cross-reference. Always parse SARIF.
- **Running gaps without a prior map** — always run `map` first. `gaps` depends on compliance.csv to know which controls have evidence.
- **Presenting evidence without a scan date range** — every evidence document must state the scan period. An undated evidence doc is inadmissible. Always include `earliest_date` to `latest_date` in the header.
- **Overwriting fixed status** — if a finding is marked `fixed` in SARIF properties or has a suppression comment, preserve that status in compliance.csv. Never reset fixed findings to open on re-import.
- **Mixing framework controls across clients** — compliance.csv is per-client. Never merge datasets across clients. Each client has independent scope, frameworks, and remediation status.
- **Generating evidence from stale scans** — if the most recent scan is >7 days old, warn before generating the evidence document: "Scan results are {N} days old. Evidence may not reflect current codebase state."

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
