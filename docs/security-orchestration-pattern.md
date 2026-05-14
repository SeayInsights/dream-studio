# Security Skills Orchestration Pattern

All security skills follow the same 4-phase workflow. This doc describes the common pattern to avoid repeating it in every SKILL.md.

---

## Standard Workflow

```
1. Parse Arguments → 2. Load Client Profile → 3. Execute Mode → 4. Write Output
```

Every security skill follows this sequence. Mode-specific logic goes in phase 3.

---

## Phase 1: Parse Arguments

**Extract from user input:**
- `mode` — Which operation to run (e.g., `setup`, `ingest`, `status`)
- `--client <name>` — Target client (usually required)
- Additional flags (skill-specific, e.g., `--repo`, `--severity`, `--quick`)

**Validation:**
- If `mode` is missing → use default or list available modes and ask
- If `--client` is missing → list available profiles (`ls ~/.dream-studio/clients/*.yaml`) and ask
- If unknown flag → warn and ignore, or fail if strict mode

**Example:**
```
User: "scan setup --client kroger --repo vendor-portal"
Parsed: mode="setup", client="kroger", repo="vendor-portal"
```

---

## Phase 2: Load Client Profile

**Standard steps for ALL skills:**

1. **Read client YAML:**
   ```bash
   ~/.dream-studio/clients/{client}.yaml
   ```

2. **Validate file exists:**
   - If missing → **STOP** with error: `"Client profile not found at ~/.dream-studio/clients/{client}.yaml. Run client-work:intake to create it."`

3. **Extract required fields:**
   - Every skill reads `client.name` and `client.github_org` (identity)
   - Additional fields depend on skill (see skill-specific docs)

4. **Validate required fields present:**
   - If any required field missing → **STOP** with error: `"Client profile missing required field '{field}'. Add to {client}.yaml and retry."`
   - If optional field missing → warn and use default, or skip dependent functionality

**Common fields across all skills:**
| Field | Type | Required | Default |
|-------|------|----------|---------|
| `client.name` | string | Yes | (none) |
| `client.github_org` | string | Yes | (none) |
| `data.critical` | list | No | `[]` |
| `data.sensitive` | list | No | `[]` |
| `isolation.model` | enum | No | `"none"` |
| `network.proxy.vendor` | enum | No | `null` |
| `compliance.frameworks` | list | No | `["soc2"]` |
| `stack.languages` | list | No | Auto-detect |

**Skill-specific fields:**
- See `docs/client-profile-schema.md` for complete reference
- Each skill's SKILL.md lists which fields it uses

---

## Phase 3: Execute Mode

**Mode-specific logic goes here.**

Each skill implements 2-5 modes (e.g., `setup`, `ingest`, `status`). Mode logic varies per skill but generally follows:

1. **Validation gate** — Verify prerequisites (templates exist, input files readable, etc.)
2. **Data collection** — Read scan results, load templates, fetch external data
3. **Processing** — Generate configs, match findings to templates, compute scores
4. **Transformation** — Format output (CSV, JSON, markdown, YAML)

**Common mode patterns:**

| Mode | Purpose | Input | Output |
|------|---------|-------|--------|
| `setup` | Generate scanner config | Client profile | Rules + workflow YAML |
| `ingest` | Import scan results | SARIF/JSON files | Structured storage |
| `status` | Report coverage | Existing scans | Summary report |
| `export` | Format for external tool | Datasets | CSV/markdown |

---

## Phase 4: Write Output

**Standard write pattern:**

1. **Validate output directory exists:**
   ```bash
   mkdir -p ~/.dream-studio/security/{scans|datasets|rules|actions}/{client}/
   ```

2. **Write with atomic rename:**
   ```bash
   # Write to temp file first
   output > /tmp/{file}.tmp
   # Atomic move when complete
   mv /tmp/{file}.tmp ~/.dream-studio/security/{path}/{file}
   ```

3. **Set permissions:**
   ```bash
   chmod 600 ~/.dream-studio/security/**/*.{csv,json,yaml}  # Data files
   chmod 644 ~/.dream-studio/security/**/*.md               # Docs
   ```

4. **Log write:**
   ```json
   {
     "timestamp": "ISO-8601",
     "skill": "{skill-name}",
     "mode": "{mode}",
     "client": "{client}",
     "output_path": "{full-path}",
     "row_count": 123
   }
   ```

5. **Report to user:**
   ```
   ✓ Written: ~/.dream-studio/security/datasets/kroger/mitigations.csv (47 rows)
   ```

---

## Error Handling

**All skills follow same error handling:**

### Hard Stops (Fail Fast)
- Client profile not found → STOP
- Required field missing → STOP
- Template file missing → STOP
- Input file unreadable → STOP
- Write permission denied → STOP

**Example error format:**
```
❌ ERROR: Client profile not found
Path: ~/.dream-studio/clients/kroger.yaml
Fix: Run `client-work:intake --name kroger` to create profile
```

### Soft Warnings (Continue with Defaults)
- Optional field missing → WARN + use default
- Stale scan results (>7 days) → WARN + continue
- Extra fields in input → WARN + ignore

**Example warning format:**
```
⚠ WARNING: Client profile missing optional field 'compliance.frameworks'
Default: Using ["soc2"] as fallback
```

### Validation Gates
Some skills have multi-step validation before executing:
- `secure` — Validate all analyst YAML files exist before spawning subagents
- `comply` — Validate all framework mapping files exist before cross-referencing

**Pattern:**
```markdown
### Step 1: Validation Gate
1. Check prerequisite A exists
2. Check prerequisite B is valid
3. If ANY check fails → STOP with specific error
4. If ALL pass → continue
```

---

## Concurrency

**Single-instance enforcement (where needed):**

Skills that spawn subagents or write to shared state use checkpoint files:

```json
{
  "status": "idle|reviewing|processing",
  "started_at": "ISO-8601",
  "input_summary": "brief description",
  "mode": "{mode}"
}
```

**Pattern:**
1. Read `checkpoint.json`
2. If `status != "idle"` → ask user: "Already in progress. Resume, restart, or cancel?"
3. If `status == "idle"` → set to active, proceed
4. On completion → reset to `idle`
5. Auto-reset after 24 hours (stale detection)

**Skills using checkpoints:** `secure`, `security-dashboard` (ETL)

---

## Best Practices

### DO
✅ Fail fast on missing prerequisites  
✅ Validate client profile before processing  
✅ Use atomic writes (temp file → rename)  
✅ Log all writes for audit trail  
✅ Report clear error messages with fix instructions  

### DON'T
❌ Modify client code directly (output recommendations only)  
❌ Skip validation gates (always fail fast)  
❌ Guess client profile fields (read from YAML, fail if missing)  
❌ Write partial results (atomic writes only)  
❌ Continue after hard stop (error → abort immediately)  

---

## Summary

**Every security skill follows:**
1. Parse args (mode, client, flags)
2. Load client profile (validate required fields)
3. Execute mode (skill-specific logic)
4. Write output (atomic, logged, reported)

**Exceptions logged as anti-patterns in:** `docs/security-best-practices.md`
