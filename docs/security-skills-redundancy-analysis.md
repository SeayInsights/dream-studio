# Security Skills Redundancy Analysis

**Date:** 2026-04-26  
**Scope:** 8 security pack skills (scan, mitigate, comply, secure, dast, netcompat, binary-scan, security-dashboard)  
**Total lines:** 2,576 lines across 8 SKILL.md files  
**Compression target:** ~30% reduction (~770 lines)

---

## Line Counts

| Skill | Lines | Primary Function |
|-------|-------|------------------|
| security-dashboard | 389 | ETL orchestration + Power BI export |
| mitigate | 377 | Per-finding fix recommendations |
| scan | 312 | Generate scanners + ingest results |
| secure | 308 | Parallel security review (OWASP + STRIDE) |
| dast | 306 | Web app dynamic testing (ZAP/Nuclei) |
| netcompat | 302 | Zscaler/proxy compatibility analysis |
| binary-scan | 291 | Binary/executable analysis (checksec, YARA) |
| comply | 291 | Compliance framework mapping |
| **Total** | **2,576** | |

---

## Redundancy Patterns Found

### Pattern 1: Boilerplate Sections (Low Value, High Repetition)

**All 8 skills have identical structure:**

```markdown
## Trigger
`{skill}:`, `/{skill}`, {other triggers}

## Purpose
{1-2 paragraph description}

## Modes
- `{mode1}` — description
- `{mode2}` — description

## Storage Layout
```
~/.dream-studio/security/
├── {paths}
```

## Templates Referenced
```
builds/dream-studio/templates/security/
├── {template paths}
```

## Client Profile Fields Used
| Profile field | Used by |
|---|---|
```

**Redundancy:** This structure repeats 8 times with minor variations.

**Lines per skill:** ~60-80 lines of boilerplate  
**Total redundant:** ~500-640 lines across all 8 skills

**Compression opportunity:**
1. **Storage Layout** — All point to `~/.dream-studio/security/`. Could reference external doc instead of repeating tree structure.
2. **Templates Referenced** — All point to `builds/dream-studio/templates/security/`. Could reference external template registry.
3. **Client Profile Fields** — Mostly same fields (client.name, data.*, isolation.*, network.proxy.*). Could reference common schema doc.

**Proposed compression:**
```markdown
## Storage
See `docs/security-storage-layout.md`. This skill uses:
- `scans/{client}/{repo}/` — ingested findings
- `datasets/{client}/mitigations.csv` — output

## Templates
See `templates/security/README.md`. This skill uses:
- `mitigations/*.yaml` — fix templates by CWE/OWASP

## Client Profile
See `docs/client-profile-schema.md`. Required fields:
- `client.name`, `data.classification`, `isolation.model`
```

**Savings:** 40-60 lines per skill × 8 = **320-480 lines**

---

### Pattern 2: Verbose Orchestration Steps (Medium Value, Medium Repetition)

**All skills have "## Orchestration Steps" with similar structure:**

```markdown
## Orchestration Steps

Follow in order for the active mode. Do not skip steps. Do not proceed past a failed gate.

### Step 0: Parse Arguments
Extract from user input:
- `mode` — one of: {modes}. If absent, default to {default}.
- `--client <name>` — required. If absent, list available profiles and ask.
- `--flag <value>` — optional.

### Step 1: Load Client Profile
1. Read `~/.dream-studio/clients/{client}.yaml`.
2. If file does not exist: **stop** — "Client profile not found..."
3. Extract `{fields}`.
4. If `{field}` is missing: warn — "..."
```

**Redundancy:** Steps 0 and 1 are nearly identical across all 8 skills. Only the specific fields and modes differ.

**Lines per skill:** ~40-60 lines for Step 0-1  
**Total redundant:** ~320-480 lines across all 8 skills

**Compression opportunity:**
1. **Step 0 (Parse Arguments)** — Template can be: "Parse mode, --client, --flags. See orchestration pattern."
2. **Step 1 (Load Client Profile)** — Template can be: "Load client YAML, validate required fields."

**Proposed compression:**
```markdown
## Orchestration

**Standard pattern:** Parse args → Load client → Execute mode → Write output. See `docs/orchestration-pattern.md`.

**Mode-specific steps:**

### Mode: `findings`
1. Glob scan results from `scans/{client}/`
2. For each finding: match to template, generate fix
3. Write to `datasets/{client}/mitigations.csv`
```

**Savings:** 30-40 lines per skill × 8 = **240-320 lines**

---

### Pattern 3: JSON Schema Definitions (Low Value, High Verbosity)

**Most skills include verbose JSON schemas:**

```markdown
## {Schema Name}

Each {entity} is one JSON object:

```json
{
  "field1": "value",
  "field2": 123,
  "field3": {
    "nested": "object"
  },
  // 20+ more fields with inline comments
}
```

Field descriptions:
- `field1` — description of field1
- `field2` — description of field2
- ...
```

**Example:**
- `mitigate/SKILL.md` has 42-line mitigation schema
- `comply/SKILL.md` has 35-line compliance mapping schema
- `secure/SKILL.md` has 28-line analyst output schema
- `security-dashboard/SKILL.md` has 50+ line dataset schema

**Lines per skill:** ~30-50 lines for schemas  
**Total verbose:** ~240-400 lines across all 8 skills

**Compression opportunity:**
Move schemas to external JSON schema files, reference them:

**Proposed compression:**
```markdown
## Output Schema
See `schemas/security/mitigation.schema.json`. Key fields:
- `finding_id`, `severity`, `immediate_fix`, `verification_test`
```

**Savings:** 20-40 lines per skill × 6 skills with schemas = **120-240 lines**

---

### Pattern 4: Detailed Examples (Low Value for Skill Invocation)

**Many skills have multi-line example outputs:**

```markdown
**Example finding:**
```
KRG-001-vendor-portal-auth.py-34
SEVERITY: HIGH
CWE: CWE-532
OWASP: A09:2021
MESSAGE: Sensitive data logged without masking
LOCATION: vendor-portal/auth.py:34
FIX: Replace raw logging with masked output
  BEFORE: logger.info(f'Price: {pricing_data}')
  AFTER: logger.info(f'Price: {mask(pricing_data)}')
EFFORT: 2h
COMPLIANCE: [SOC2-CC6.1, NIST-PR.DS-1]
```
```

**Lines per skill:** ~15-30 lines for examples  
**Total verbose:** ~120-240 lines across all 8 skills

**Compression opportunity:**
Remove examples from SKILL.md, keep in separate `examples/` directory or reference actual test outputs.

**Proposed compression:**
```markdown
## Output Format
Structured CSV/JSON. See `examples/security/mitigate-output.md` for sample.
```

**Savings:** 15-25 lines per skill × 8 = **120-200 lines**

---

### Pattern 5: Anti-Patterns Sections (Redundant Across Skills)

**6 of 8 skills have "## Anti-patterns" sections with similar warnings:**

Common anti-patterns repeated:
- "Do not modify client code directly — output recommendations only"
- "Do not proceed past validation gate — stop immediately on missing files"
- "Do not skip steps in orchestration — follow in order"
- "Do not guess client profile fields — read from YAML, fail if missing"

**Lines per skill:** ~8-15 lines  
**Total redundant:** ~48-90 lines across 6 skills

**Compression opportunity:**
Move to `docs/security-best-practices.md`, reference once.

**Proposed compression:**
```markdown
## Best Practices
See `docs/security-best-practices.md`. Key: never modify code directly, follow orchestration order, fail fast on missing data.
```

**Savings:** 8-12 lines per skill × 6 = **48-72 lines**

---

## Compression Strategy

### Tier 1: Extract to External Docs (Highest Impact)

**Create reference docs:**
1. `docs/security-storage-layout.md` — Single source for all security storage paths
2. `docs/security-orchestration-pattern.md` — Standard parse → load → execute → write pattern
3. `docs/client-profile-schema.md` — Complete field reference for client YAML
4. `docs/security-best-practices.md` — Anti-patterns and best practices
5. `schemas/security/*.schema.json` — JSON schemas for outputs

**Update all 8 skills to reference docs instead of repeating content.**

**Estimated savings:** 320-480 (storage) + 240-320 (orchestration) + 120-240 (schemas) + 48-72 (anti-patterns) = **728-1,112 lines**

**Compression percentage:** 28-43% reduction

---

### Tier 2: Compress Mode-Specific Steps (Medium Impact)

**For each skill:**
- Keep mode descriptions brief (1-2 sentences max)
- Remove verbose "what this does" paragraphs
- Keep "how to invoke" (triggers, args) and "what it outputs" (paths, formats)

**Example (mitigate/SKILL.md):**

**Before (verbose):**
```markdown
### Mode: `findings`

Process ALL findings for a client. This mode reads from the scan results directory, iterates through every finding, matches each to a mitigation template by rule ID, CWE, or OWASP category, generates code before/after examples, creates verification tests, estimates effort, maps to compliance controls, and writes the results to a structured CSV file for sprint planning and dashboard export.

This is the primary mode for bulk mitigation generation after running a full security scan.
```

**After (compressed):**
```markdown
### Mode: `findings`
Process all findings for client. Match to templates, generate fixes, write to `datasets/{client}/mitigations.csv`.
```

**Estimated savings:** 10-20 lines per skill × 8 = **80-160 lines**

---

### Tier 3: Remove Redundant Examples (Low Impact)

Move all examples to `examples/security/{skill}-examples.md`.

**Estimated savings:** 120-200 lines

---

## Total Compression Estimate

| Tier | Strategy | Lines Saved |
|------|----------|-------------|
| 1 | Extract to external docs | 728-1,112 |
| 2 | Compress mode descriptions | 80-160 |
| 3 | Remove examples | 120-200 |
| **Total** | | **928-1,472 lines** |

**Total current:** 2,576 lines  
**Total after compression:** 1,104-1,648 lines  
**Reduction:** 36-57%

**Target:** 30% reduction = 773 lines saved ✓ achievable with Tier 1 alone

---

## What Gets Removed vs Retained

### Removed (Low Runtime Value)
❌ Repeated storage layout trees (external doc)  
❌ Repeated template registry (external doc)  
❌ Repeated client profile field tables (external doc)  
❌ Verbose orchestration boilerplate (external pattern doc)  
❌ Multi-line JSON schema examples (external .schema.json files)  
❌ Detailed example outputs (external examples/ directory)  
❌ Anti-patterns sections (external best practices doc)  
❌ Verbose "what this does" paragraphs (keep 1-2 sentence summaries)  

### Retained (High Runtime Value)
✅ Trigger keywords (for routing)  
✅ Mode list and descriptions (1-2 sentences each)  
✅ Mode-specific orchestration steps (condensed)  
✅ Output paths and formats (where results go)  
✅ Required vs optional arguments  
✅ Error conditions and failure modes  
✅ Integration points with other skills  

---

## Implementation Plan

### Phase 1: Create External Docs (~1 hour)
1. `docs/security-storage-layout.md` — Consolidate all storage paths
2. `docs/security-orchestration-pattern.md` — Standard workflow
3. `docs/client-profile-schema.md` — Field reference
4. `docs/security-best-practices.md` — Anti-patterns
5. `schemas/security/` — Move JSON schemas

### Phase 2: Compress Each Skill (~2 hours)
For each of 8 skills:
1. Replace storage layout with reference
2. Replace template registry with reference
3. Replace client profile table with reference
4. Compress mode descriptions (verbose → 1-2 sentences)
5. Remove anti-patterns section, add reference
6. Remove examples, add reference

### Phase 3: Verify & Test (~30 minutes)
1. Spot-check compressed skills load correctly
2. Verify external docs render properly
3. Ensure all references resolve

**Total time:** ~3.5 hours  
**Expected reduction:** 30-40% (~770-1,000 lines)

---

## Risk Assessment

**Low risk:**
- Extracting boilerplate (storage, templates, schemas) — no logic change
- Removing examples — they're illustrative, not functional
- Compressing verbose descriptions — 1-2 sentences is enough

**Medium risk:**
- Compressing orchestration steps — need to retain all failure modes
- Ensure external docs are discoverable (good references in SKILL.md)

**Mitigation:**
- Keep external docs in `docs/` (already loaded in context when needed)
- Retain all error conditions and failure gates in compressed form
- Test 1-2 skills before compressing all 8

---

## Recommendation

**Proceed with Tier 1 (extract to external docs) for all 8 skills.**

**Expected outcome:**
- 2,576 lines → ~1,800 lines (30% reduction)
- Same capability, less overhead per invocation
- Better maintainability (update storage layout once, not 8 times)

**Ready to compress?**
