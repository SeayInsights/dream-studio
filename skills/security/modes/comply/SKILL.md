---
name: comply
description: "Map findings to SOC 2, NIST CSF, OWASP ASVS controls. Identify coverage gaps. Generate audit-ready evidence. Trigger on comply:, compliance map, audit evidence."
user_invocable: true
args: mode
argument-hint: "[map | gaps | evidence] [--client <name>]"
pack: quality
---

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

## Orchestration Steps

Follow in order for the active mode. Do not skip steps. Do not proceed past a failed gate.

---

### Step 0: Parse Arguments

Extract from user input:
- `mode` — one of: `map`, `gaps`, `evidence`. If absent, default to `map`.
- `--client <name>` — required. If absent, list available profiles (`~/.dream-studio/clients/`) and ask.

---

### Step 1: Load Client Profile

1. Read `~/.dream-studio/clients/{client}.yaml`.
2. If file does not exist: **stop** — "Client profile not found at `~/.dream-studio/clients/{client}.yaml`. Run `client-work:intake` to create it."
3. Extract `compliance.frameworks` — list of enabled frameworks (e.g., `["soc2", "nist-csf", "owasp-asvs", "cwe-top25"]`).
4. If `compliance.frameworks` is empty or missing: warn — "No compliance frameworks declared in client profile. Defaulting to all four frameworks (soc2, nist-csf, owasp-asvs, cwe-top25)." Set frameworks to all four.

---

### Step 2: Load Framework Definitions

For each framework in the resolved list:

1. Map framework name to definition file:
   - `soc2` → `templates/security/compliance/soc2-mapping.yaml`
   - `nist-csf` → `templates/security/compliance/nist-csf-mapping.yaml`
   - `owasp-asvs` → `templates/security/compliance/owasp-asvs-mapping.yaml`
   - `cwe-top25` → `templates/security/compliance/cwe-top25-mapping.yaml`
2. Read each YAML file. Validate structure: each entry must have `control_id`, `framework`, `mapped_cwes`, `mapped_owasp`.
3. If a file is missing or malformed: **stop** — "Framework definition not found: `{path}`. Run `harden` to restore missing templates."
4. Build an in-memory lookup: `{ "CWE-89": [CC6.1, PR.DS-1, V5.3, ...], ... }` — mapping each CWE and OWASP category to all controls that reference it.

---

### Step 3: Load Scan Findings

1. Glob `~/.dream-studio/security/scans/{client}/` for all `scan-meta.json` files.
2. For each scan:
   - Read `scan-meta.json`. Extract `date`, `repo`, `finding_counts`.
   - Detect SARIF file: look for `*.sarif` or `semgrep.sarif` in the same directory.
   - If SARIF present: parse `runs[].results[]` — extract `ruleId`, `message.text`, `locations[].physicalLocation`, and any `tags` from `properties`.
   - Extract CWE codes from `properties.cwe` or rule ID pattern (e.g., `KRG-inj-001` → injection rules → `CWE-89`, `CWE-77`).
   - Extract OWASP category from `properties.owasp` or rule tags.
3. If no SARIF files found at all: **stop** — "No scan results found for client `{client}`. Run `scan ingest --client {client}` first."
4. Collect all findings into a flat list:

```
[
  {
    "repo": "repo-name",
    "date": "YYYY-MM-DD",
    "rule_id": "KRG-inj-001",
    "severity": "HIGH",
    "cwe": ["CWE-89"],
    "owasp": ["A03:2021"],
    "message": "...",
    "location": "file:line"
  },
  ...
]
```

---

### Mode: `map`

#### Step M1: Cross-Reference Findings to Controls

For each finding in the flat list:
1. Look up `cwe` values in the control lookup. Collect all matching control IDs.
2. Look up `owasp` values in the control lookup. Collect all matching control IDs (union).
3. Look up `rule_id` against `mapped_rule_patterns` in each framework definition (glob match).
4. Produce a row per (finding Ã— control) pair.

#### Step M2: Write compliance.csv

Create directory `~/.dream-studio/security/datasets/{client}/` if absent.

Write `compliance.csv` with columns:

```
framework,control_id,control_title,repo,date,rule_id,severity,cwe,owasp,finding_location,remediation_status
```

- `remediation_status`: default `open`. If a finding has a suppression comment or was marked `status: fixed` in the SARIF properties, set `fixed`.
- Sort by: `framework`, `control_id`, `severity` (critical first), `repo`.

#### Step M3: Present Summary

Render a table grouped by framework:

```
## Compliance Mapping — {client} ({date})

### SOC 2 Type II
| Control | Title | Findings | Severity Breakdown |
|---------|-------|----------|--------------------|
| CC6.1 | Logical Access Controls | 3 | HIGH:1 MEDIUM:2 |
| CC6.7 | Data Transmission Protection | 0 | — |

### NIST CSF
...

**Total:** {N} finding-to-control mappings across {M} frameworks
**Output:** ~/.dream-studio/security/datasets/{client}/compliance.csv
```

Next step: "Run `comply gaps --client {client}` to see which controls have zero scan coverage."

---

### Mode: `gaps`

#### Step G1: Identify Uncovered Controls

1. Load all framework definitions (Step 2).
2. Load compliance.csv if it exists (from a prior `map` run). If absent: run `map` first, then continue.
3. For each control across all enabled frameworks:
   - Check if any row in compliance.csv has `control_id = this control` with finding count > 0.
   - If zero findings mapped to this control: mark as **GAP**.
4. Also flag controls where `mapped_cwes` and `mapped_owasp` are both empty — structural gaps in the mapping definition itself.

#### Step G2: Render Gap Report

```
## Coverage Gaps — {client}

### Controls with Zero Scan Coverage
These controls are in scope but no scanner rule maps to them.

| Framework | Control | Title | Gap Type |
|-----------|---------|-------|----------|
| soc2 | CC7.1 | Monitoring and Detection | No mapped rules |
| nist-csf | RC.RP-1 | Recovery Planning | No mapped rules |
...

### Structural Gaps (mapping definitions)
These controls exist in the definition YAML but have no CWE or OWASP entries.
Fix by adding entries to the appropriate mapping file.

**Gap count:** {N} controls uncovered out of {M} total controls
**Coverage:** {X}% of controls have at least one mapped finding
```

Next step: "Add Semgrep rules covering the gap areas, or accept the gap with a documented compensating control. Then re-run `comply map` to refresh coverage."

---

### Mode: `evidence`

#### Step E1: Build Evidence Per Control

1. Load all framework definitions (Step 2).
2. Load compliance.csv. If absent: run `map` first.
3. For each control across all enabled frameworks:
   - Collect all finding rows where `control_id = this control`.
   - Group by `repo` and `severity`.
   - Compute: total findings, open findings, fixed findings.

#### Step E2: Write Evidence Document

Write `~/.dream-studio/security/datasets/{client}/evidence-{YYYY-MM-DD}.md`:

```markdown
# Audit Evidence — {client}
**Generated:** {ISO-8601}
**Frameworks:** {list}
**Scan period:** {earliest date} to {latest date}
**Repos covered:** {N}

---

## SOC 2 Type II Controls

### CC6.1 — Logical and Physical Access Controls
**Description:** The entity implements logical access security software, infrastructure, and architectures over protected information assets.

**Scan Evidence:**
- Scanner: Semgrep (custom rules KRG-ac-001 through KRG-ac-010)
- Rules mapped: KRG-ac-001, KRG-ac-003, KRG-sec-002
- CWEs covered: CWE-284, CWE-285, CWE-639

**Findings (as of {date}):**
| Repo | Rule | Severity | Status |
|------|------|----------|--------|
| repo-a | KRG-ac-001 | HIGH | open |
| repo-b | KRG-ac-003 | MEDIUM | fixed |

**Finding count:** 2 total (1 open, 1 fixed)
**Remediation status:** In progress

---

### CC6.6 — System Boundaries and Protection
...

---

## NIST CSF Controls

...

---

## Evidence Summary

| Framework | Controls in Scope | Controls with Evidence | Coverage |
|-----------|------------------|----------------------|----------|
| SOC 2 | 5 | 4 | 80% |
| NIST CSF | 11 | 9 | 82% |
| OWASP ASVS | 14 | 11 | 79% |
| CWE Top 25 | 25 | 18 | 72% |
```

#### Step E3: Present Output

Show:
1. Evidence document path.
2. Coverage table (same as in evidence doc).
3. Any controls with zero evidence — highlighted for manual documentation.
4. "For controls with no automated evidence, add compensating control documentation manually to the evidence file."

---

## Output Schema

### `compliance.csv`

Path: `~/.dream-studio/security/datasets/{client}/compliance.csv`

| Column | Type | Description |
|--------|------|-------------|
| `framework` | string | soc2, nist-csf, owasp-asvs, cwe-top25 |
| `control_id` | string | CC6.1, PR.AC-1, V4.1.1, CWE-89 |
| `control_title` | string | Human-readable control name |
| `repo` | string | GitHub repo name |
| `date` | YYYY-MM-DD | Scan date |
| `rule_id` | string | Semgrep rule ID (e.g., KRG-inj-001) |
| `severity` | string | CRITICAL, HIGH, MEDIUM, LOW |
| `cwe` | string | Semicolon-separated CWE IDs |
| `owasp` | string | Semicolon-separated OWASP categories |
| `finding_location` | string | file:line |
| `remediation_status` | string | open, fixed, suppressed |

### `evidence-{YYYY-MM-DD}.md`

Path: `~/.dream-studio/security/datasets/{client}/evidence-{YYYY-MM-DD}.md`

Audit-ready markdown. Per control: control ID, description, scan evidence (rules, CWEs), findings table (repo, rule, severity, status), finding count, remediation status.

---

## Anti-patterns

- **Treating zero findings as compliance** — a control with zero findings mapped to it is a coverage gap, not a clean bill of health. Always distinguish between "no findings because we scanned and found none" vs. "no findings because we have no rule covering this control."
- **Mapping without loading SARIF** — do not generate compliance.csv from finding_counts alone. Counts don't carry CWE/OWASP metadata needed for cross-reference. Always parse SARIF.
- **Running gaps without a prior map** — always run `map` first. `gaps` depends on compliance.csv to know which controls have evidence.
- **Presenting evidence without a scan date range** — every evidence document must state the scan period. An undated evidence doc is inadmissible. Always include `earliest_date` to `latest_date` in the header.
- **Overwriting fixed status** — if a finding is marked `fixed` in SARIF properties or has a suppression comment, preserve that status in compliance.csv. Never reset fixed findings to open on re-import.
- **Mixing framework controls across clients** — compliance.csv is per-client. Never merge datasets across clients. Each client has independent scope, frameworks, and remediation status.
- **Generating evidence from stale scans** — if the most recent scan is >7 days old, warn before generating the evidence document: "Scan results are {N} days old. Evidence may not reflect current codebase state."
