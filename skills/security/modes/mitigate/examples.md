# mitigate — Detailed Reference

Extracted from SKILL.md to reduce context injection size.

## Mitigation Output Schema

Each mitigation is one JSON object (stored as a row in `mitigations.csv`):

```json
{
  "finding_id": "KRG-001-vendor-portal-auth.py-34",
  "rule_id": "KRG-001",
  "title": "Sensitive data logged without masking",
  "severity": "HIGH",
  "cwe": "CWE-532",
  "owasp_category": "A09:2021",
  "repo": "vendor-portal",
  "file": "auth.py",
  "line": 34,
  "immediate_fix": {
    "description": "Replace raw logging with masked output",
    "code_before": "logger.info(f'Price: {pricing_data}')",
    "code_after": "logger.info(f'Price: {mask(pricing_data)}')"
  },
  "long_term_fix": "Implement centralized logging sanitizer that strips classified fields before any log call",
  "verification_test": "grep -r 'pricing\\|margin\\|cost_data' app/logs/ should return 0 results",
  "effort_estimate": "2h",
  "sprint_label": "security-quick-win",
  "compliance_impact": ["SOC2-CC6.1", "NIST-PR.DS-1"],
  "zscaler_impact": null,
  "template_matched": "secrets-fixes.yaml#KRG-001",
  "generated_at": "ISO-8601"
}
```

### CSV Columns

`finding_id, rule_id, title, severity, cwe, owasp_category, repo, file, line, immediate_fix_description, code_before, code_after, long_term_fix, verification_test, effort_estimate, sprint_label, compliance_impact, zscaler_impact, template_matched, generated_at`

---

## Orchestration Steps

Follow in order for the active mode. Do not skip steps. Do not proceed past a failed gate.

---

### Mode: `findings`

#### Step F0: Parse Arguments

Extract from user input:
- `--client <name>` — required. If absent, list available profiles and ask.
- `--severity <level>` — optional filter (CRITICAL, HIGH, MEDIUM, LOW). If absent, process all severities.
- `--repo <repo>` — optional. If provided, scope to that repo only.

#### Step F1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. If file does not exist: **stop** — "Client profile not found at `~/.dream-studio/clients/{client}.yaml`. Run `client-work:intake` to create it."
3. Extract: `client.name`, `data.classification`, `isolation.model`, `network.proxy.*`, `compliance.frameworks`.

#### Step F2: Load Findings

1. List all directories under `~/.dream-studio/security/scans/{client}/`.
2. For each repo directory (filtered by `--repo` if provided):
   - Find the most recent `{date}/` subdirectory.
   - Check `scan-meta.json`. If `ingested_at` is >7 days old: warn — "Findings for `{repo}` are stale ({age} days). Mitigations may not reflect current code."
   - Parse SARIF files. Extract each `result` entry: `ruleId`, `level`, `locations[].physicalLocation`, `message.text`.
3. Deduplicate by `(ruleId, file, line)`.
4. Apply severity filter if `--severity` was provided.
5. If zero findings after filtering: report — "No findings found for `{client}` with severity `{level}`. Nothing to mitigate." and stop.

#### Step F3: Load Mitigation Templates

1. Read all 5 YAML files from `builds/dream-studio/templates/security/mitigations/`.
2. Build a flat lookup index: `{rule_pattern: template_entry}`.
3. The `rule_pattern` field in each template is a pipe-delimited string of matching patterns (e.g., `"KRG-inj-001|CWE-89|sql-injection"`). Split on `|` and index each token.
4. If a template file fails to load: warn with filename, skip that file, continue.

#### Step F4: Match and Generate Mitigations

For each finding, in batches of up to 10 (process all findings — no cap):

**Simple match (template covers it):**
1. Look up by `ruleId` in template index. If no match, try `cwe`. If no match, try normalized `message.text` (lowercase, hyphens).
2. If match found: fill the output schema from the template. Substitute `{repo}`, `{file}`, `{line}` from the finding. Set `template_matched` to `{filename}#{rule_pattern}`.
3. Infer `sprint_label`: CRITICAL/HIGH → `security-blocker`, MEDIUM → `security-backlog`, LOW → `security-nice-to-have`.
4. Map `compliance_impact` from client `compliance.frameworks` Ã— finding `owasp_category` / `cwe`.

**Complex match (no template or template flags `requires_context: true`):**
1. Spawn a sonnet subagent per finding with this prompt:

```
You are a security engineer generating a targeted code fix.

## Finding
Rule ID: {rule_id}
Title: {message}
File: {file}:{line}
Severity: {severity}
CWE: {cwe}
OWASP: {owasp_category}

## Client Context
Data classification: {data.classification}
Isolation model: {isolation.model}
Network proxy: {network.proxy.host if present}

## Task
Return ONLY a JSON object matching this schema exactly:
{
  "immediate_fix": {
    "description": "one sentence",
    "code_before": "exact code pattern to replace",
    "code_after": "corrected code"
  },
  "long_term_fix": "one sentence architectural recommendation",
  "verification_test": "runnable command or test assertion",
  "effort_estimate": "Xh or Xd",
  "zscaler_impact": "description if proxy-relevant, else null"
}

No preamble. No explanation. JSON only.
```

2. Validate response: parse JSON, check all fields present. Retry once if malformed.
3. If retry fails: write a placeholder — `"immediate_fix": {"description": "Manual review required", "code_before": "", "code_after": ""}`.

#### Step F5: Write Outputs

1. Assemble all mitigations into a list.
2. Write `~/.dream-studio/security/datasets/{client}/mitigations.csv`:
   - Header row: all CSV columns (see Output Schema).
   - One row per mitigation. Escape commas in code fields with double-quote wrapping.
3. Write snapshot `~/.dream-studio/security/datasets/{client}/mitigations-{YYYY-MM-DD}.json` (full JSON array).
4. Write via temp-file-then-rename. Never partially overwrite the live CSV.

#### Step F6: Present Summary

Show:
1. Counts: `{N} findings processed | {N} template-matched | {N} subagent-generated | {N} placeholders`
2. Effort total: sum of all `effort_estimate` values (convert to hours).
3. Sprint breakdown table:

```
| Label               | Count | Total Effort |
|---------------------|-------|--------------|
| security-blocker    |    4  |      16h     |
| security-backlog    |   11  |      22h     |
| security-nice-to-have |  3  |       3h     |
```

4. Output path: "Mitigations written to `~/.dream-studio/security/datasets/{client}/mitigations.csv`"
5. Next step: "Run `mitigate export --client {client}` to generate a sprint-ready markdown report, or `comply: --client {client}` to map findings to compliance controls."

---

### Mode: `single`

#### Step S0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--finding <id>` — required. The `finding_id` string (e.g., `KRG-001-vendor-portal-auth.py-34`).

If either is absent: ask — "Provide `--client <name>` and `--finding <id>` to generate a single mitigation."

#### Step S1: Locate Finding

1. Load client profile (same as F1).
2. Search `~/.dream-studio/security/scans/{client}/` for the finding ID by scanning `scan-meta.json` files and SARIF results.
3. If not found: **stop** — "Finding `{id}` not found in `{client}` scan store. Check the ID with `scan status --client {client}`."

#### Step S2: Generate Mitigation

1. Load templates (same as F3).
2. Run the match logic (same as F4, single finding only).
3. For complex matches: always spawn a sonnet subagent — no batch optimization needed for single mode.

#### Step S3: Present Result

Output the mitigation as formatted markdown:

```markdown
## Mitigation: {finding_id}

**Rule:** {rule_id} | **Severity:** {severity} | **File:** {file}:{line}
**CWE:** {cwe} | **OWASP:** {owasp_category}

### Immediate Fix
{immediate_fix.description}

**Before:**
```{lang}
{code_before}
```

**After:**
```{lang}
{code_after}
```

### Long-Term Fix
{long_term_fix}

### Verification
```
{verification_test}
```

### Effort Estimate
{effort_estimate}

### Compliance Impact
{compliance_impact as bulleted list}

### Zscaler Impact
{zscaler_impact or "None"}
```

Do not write to CSV in `single` mode — output is inline only.

---

### Mode: `export`

#### Step E0: Parse Arguments

Extract from user input:
- `--client <name>` — required.
- `--severity <level>` — optional filter.
- `--format <csv|md|both>` — optional. Default: `both`.

#### Step E1: Load Mitigations

1. Read `~/.dream-studio/security/datasets/{client}/mitigations.csv`.
2. If file does not exist: **stop** — "No mitigations found for `{client}`. Run `mitigate findings --client {client}` first."
3. Parse CSV rows. Apply `--severity` filter if provided.

#### Step E2: Write Export Files

**CSV export** (if `--format csv` or `both`):
- Filter and copy `mitigations.csv` to `~/.dream-studio/security/datasets/{client}/mitigations-export-{YYYY-MM-DD}.csv`.

**Markdown export** (if `--format md` or `both`):
Write `~/.dream-studio/security/datasets/{client}/mitigations.md`:

```markdown
# Security Mitigations — {client}
**Generated:** {date}
**Findings:** {N} | **Total Effort:** {Xh}

---

## Blockers (CRITICAL/HIGH) — {N} findings

### {finding_id}: {title}
**File:** {file}:{line} | **Effort:** {effort_estimate}

**Fix:** {immediate_fix.description}

Before:
```
{code_before}
```

After:
```
{code_after}
```

**Verify:** `{verification_test}`
**Compliance:** {compliance_impact}

---

## Backlog (MEDIUM) — {N} findings
[same format]

## Nice-to-Have (LOW) — {N} findings
[same format]

---
## Sprint Planning Summary

| Sprint Label | Count | Effort |
|---|---|---|
| security-blocker | N | Xh |
| security-backlog | N | Xh |
| security-nice-to-have | N | Xh |
| **Total** | **N** | **Xh** |
```

#### Step E3: Present Output

1. List files written with full paths.
2. Effort summary table (same as F6 sprint breakdown).
3. "Import `mitigations-export-{date}.csv` into Jira/Linear to create sprint tickets."

---

