# scan — Detailed Reference

Extracted from SKILL.md to reduce context injection size. The `setup`, `ingest`, and `status`
mode step-by-step instructions live in `SKILL.md` itself; this file covers the output schema,
generated-file locations, and anti-patterns.

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
