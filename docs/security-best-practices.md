# Security Skills Best Practices

Common anti-patterns and best practices for all security skills.

---

## Core Principles

### 1. Never Modify Code Directly
**Rule:** Security skills output recommendations only. Never edit client code files.

**Why:** User must review and approve all security fixes before applying.

**Pattern:**
```
✅ Write fix to: datasets/{client}/mitigations.csv
❌ Edit: {client-repo}/src/auth.py directly
```

---

### 2. Fail Fast on Missing Prerequisites
**Rule:** Stop immediately on validation failure. Don't proceed with partial data.

**Why:** Partial processing produces incomplete/wrong results.

**Pattern:**
```
✅ Client profile missing → STOP with clear error
❌ Client profile missing → Continue with empty defaults
```

---

### 3. Follow Orchestration Order
**Rule:** Execute steps sequentially. Never skip validation gates.

**Why:** Steps have dependencies. Skipping breaks assumptions.

**Pattern:**
```
✅ Parse args → Load profile → Validate → Process → Write
❌ Skip validation → Process with bad data → Fail late
```

---

### 4. Read Client Profile, Never Guess
**Rule:** All client-specific data comes from `clients/{name}.yaml`. Never hardcode or guess.

**Why:** Wrong assumptions break client isolation, compliance, data classification.

**Pattern:**
```
✅ Read isolation.model from client YAML
❌ Assume all clients use multi-tenant isolation
```

---

### 5. Atomic Writes Only
**Rule:** Write to temp file, then atomic rename. Never write partial results.

**Why:** Prevents corrupted files if process crashes mid-write.

**Pattern:**
```
✅ Write to /tmp/file.tmp → mv to final path
❌ Write directly to final path (partial file if crash)
```

---

### 6. Log All Writes for Audit Trail
**Rule:** Every file write logs: timestamp, skill, mode, client, path, row count.

**Why:** Compliance audits require evidence of when/how data was processed.

**Pattern:**
```json
{
  "timestamp": "2026-04-26T21:45:00Z",
  "skill": "mitigate",
  "mode": "findings",
  "client": "kroger",
  "output_path": "~/.dream-studio/security/datasets/kroger/mitigations.csv",
  "row_count": 47
}
```

---

### 7. Clear Error Messages with Fix Instructions
**Rule:** Errors must state what failed + how to fix.

**Why:** User shouldn't guess what went wrong or how to proceed.

**Pattern:**
```
✅ "Client profile not found at ~/.dream-studio/clients/kroger.yaml. Fix: Run `client-work:intake --name kroger`"
❌ "Error: file not found"
```

---

### 8. Validate Templates Before Processing
**Rule:** Check all template files exist and are well-formed before spawning subagents or processing data.

**Why:** Missing templates discovered mid-processing wastes time and leaves partial results.

**Pattern:**
```
✅ Validation gate: Check all 6 Semgrep rule templates exist → Then generate
❌ Start generating → Fail on template 4 of 6 → Partial output
```

---

### 9. Respect Concurrency Checkpoints
**Rule:** For skills with checkpoints (secure, security-dashboard), honor `status` field. Don't overwrite active processing.

**Why:** Concurrent runs corrupt shared state.

**Pattern:**
```
✅ Read checkpoint → status="reviewing" → Ask user: Resume/Restart/Cancel
❌ Ignore checkpoint → Start new run → Corrupt previous run's state
```

---

### 10. Auto-Reset Stale Checkpoints
**Rule:** Checkpoints older than 24 hours auto-reset to `idle`.

**Why:** Crashed processes leave stale locks. Auto-recovery prevents permanent locks.

**Pattern:**
```python
if checkpoint['status'] != 'idle' and (now - checkpoint['started_at']) > 24h:
    checkpoint['status'] = 'idle'  # Auto-reset stale lock
```

---

## Anti-Patterns (What NOT to Do)

| Anti-Pattern | Why Wrong | Fix |
|--------------|-----------|-----|
| Skip validation gates | Fails late with bad error messages | Always validate before processing |
| Guess client profile fields | Breaks isolation, compliance | Read from YAML, fail if missing |
| Continue after hard stop | Produces wrong results | Fail fast, clear error |
| Write partial results | Corrupts downstream processing | Atomic writes only |
| Modify code directly | User loses review control | Output recommendations |
| Hardcode client assumptions | Breaks for other clients | Use client profile |
| Silent failures | User doesn't know what broke | Clear errors with fix instructions |
| Ignore checkpoints | Concurrent runs corrupt state | Respect checkpoint status |

---

## Checklist for New Security Skills

When creating a new security skill, verify:

- [ ] Follows standard orchestration pattern (Parse → Load → Execute → Write)
- [ ] Reads client profile from `~/.dream-studio/clients/{name}.yaml`
- [ ] Validates all prerequisites before processing
- [ ] Uses atomic writes (temp file → rename)
- [ ] Logs all writes with timestamp + metadata
- [ ] Returns clear error messages with fix instructions
- [ ] Never modifies client code directly
- [ ] Respects storage layout (`~/.dream-studio/security/...`)
- [ ] Documents which client profile fields it uses
- [ ] Includes mode descriptions and examples

---

## References

- Storage paths: `docs/security-storage-layout.md`
- Orchestration workflow: `docs/security-orchestration-pattern.md`
- Client profile fields: `docs/client-profile-schema.md`
