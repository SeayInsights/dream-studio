# Security Review Examples

Detailed examples extracted from SKILL.md for reference.

---

## Example 1: PR Security Review

```
User: "Review this PR for security issues"

Steps:
1. Run `gh pr view --json baseRefName` to get base branch
2. Run `git diff origin/main...HEAD`
3. Phase 1: Grep for existing auth/validation patterns
4. Phase 2: Compare new code against patterns
5. Phase 3: Apply filtering rules, score confidence
6. Phase 4: Report findings in markdown format
```

---

## Example 2: Pre-Commit Review with Custom Rules

```
User: "Security review before I commit"

Steps:
1. Run `git diff --staged` for staged changes
2. Check for `.dream/security/false-positives.txt`
3. Check for `.dream/security/custom-categories.txt`
4. Run analysis with custom + default rules
5. Report HIGH/MEDIUM findings only
```

---

## Example 3: Review → Mitigate → Comply Pipeline

```
User: "Security review this feature branch"

Workflow:
1. security:review → finds 3 HIGH findings (SQL injection, XSS, hardcoded key)
2. Create GitHub issue with findings
3. Invoke security:mitigate → generates fixes for each
4. Apply fixes, commit to branch
5. Invoke security:comply → maps findings to SOC 2 controls
6. Export compliance evidence for audit
```

---

## Example 4: Retail-Specific Review (Kroger Client)

```
User: "Review this Power BI dashboard code"

Steps:
1. git diff main...HEAD
2. Load custom-scanning.md → retail analytics categories
3. Check for:
   - Competitive pricing exposure
   - Vendor agreement leaks
   - PII in aggregated reports
   - RLS bypass through DAX injection
4. Apply false-positive filtering (Power BI sanitizes rendering)
5. Report retail-specific findings only
```

---

## Integration with Other Security Modes

### Workflow Positioning
```
scan → review → mitigate → comply
  ↓       ↓        ↓         ↓
Full    Code    Fix      Audit
repo    diffs   vulns    evidence
```

### Mode Interactions

**Before review:**
- `security:scan` — Run organization-wide vulnerability scan first to establish baseline
- Check for existing findings in scan results to avoid duplicates

**After review:**
- `security:mitigate` — Generate remediation code for findings
- `security:comply` — Map findings to compliance frameworks (SOC 2, NIST)
- `security:dashboard` — Export findings to Power BI for exec reporting

**Complementary modes:**
- `security:dast` — Test live web applications (runtime testing vs static code review)
- `security:binary-scan` — Analyze compiled binaries/executables
- `security:netcompat` — Check network/proxy compatibility (Zscaler, corporate firewalls)

### Handoff Pattern
When review finds vulnerabilities:
1. Create GitHub issue with findings
2. Tag issue with `security`, `high-priority` labels
3. Invoke `security:mitigate` to generate fixes
4. Follow Issue → PR workflow (see CLAUDE.md)
