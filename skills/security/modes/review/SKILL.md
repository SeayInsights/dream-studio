# Security Review — Code-Level Vulnerability Analysis

## Metadata
- **Pack:** security
- **Mode:** review
- **Type:** analysis
- **Model:** opus (complex security reasoning required)

## Trigger

Use `dream-studio:security review` when:
- Reviewing pull requests for security vulnerabilities
- Analyzing code changes before merge
- Performing pre-commit security checks
- Investigating potential security issues in diffs
- Running security-focused code review

**NOT for:**
- Full codebase scans (use `security:scan`)
- Live web application testing (use `security:dast`)
- Binary/executable analysis (use `security:binary-scan`)
- Compliance mapping (use `security:comply`)

## Workflow

### Phase 1: Get Git Diff
- `git diff` for staged/unstaged, or `git diff main...HEAD` for PR

### Phase 2: Analyze (3-phase methodology from `security-review-workflow.md`)
1. **Context Research** — Grep/Glob for security frameworks, sanitization patterns, auth models
2. **Comparative Analysis** — Compare new code vs existing patterns, flag deviations
3. **Vulnerability Assessment** — Trace data flow, identify injection points, privilege boundaries

**Focus:** Input validation, auth/authz, crypto/secrets, injection/RCE, data exposure

### Phase 3: Apply Filtering (`custom-filtering.md`)
- **Hard exclusions:** DOS, test files, theoretical race conditions, docs
- **Confidence ≥8 only:** 9-10 (certain exploit), 8-9 (known pattern), <8 (skip)

### Phase 4: Report Findings
```markdown
# Vuln N: [Category]: `[file]:[line]`
* Severity: High/Medium
* Description: [What]
* Exploit Scenario: [How]
* Recommendation: [Fix]
```

**Severity:** HIGH (RCE/breach/bypass) | MEDIUM (conditional + significant impact)

## Custom Filtering & Scanning

Users can customize security reviews for their environment by creating project-level config files:

### `.dream/security/false-positives.txt`
Exclude findings that don't apply to your environment. See `custom-filtering.md` for templates covering:
- Technology stack (ORMs, frameworks, auth providers)
- Infrastructure (k8s, API gateway, cloud security controls)
- Compliance requirements (HIPAA, PCI DSS, SOC 2)
- Development practices (SAST/DAST, code review, security training)

### `.dream/security/custom-categories.txt`
Add organization-specific vulnerability categories. See `custom-scanning.md` for templates covering:
- Industry-specific (retail, financial services, healthcare)
- Technology-specific (GraphQL, gRPC, Power BI, cloud providers)
- Compliance-focused (GDPR, CCPA, state privacy laws)

If these files exist, read them before analysis and apply the custom rules alongside defaults.

## Integration with Other Security Modes

**Workflow:** `scan → review → mitigate → comply`

**Before:** `security:scan` to establish baseline
**After:** `security:mitigate` to fix, `security:comply` for audit, `security:dashboard` for reporting

See `references/examples.md` for mode interactions and handoff patterns.

## References

This mode integrates three reference documents:

1. **`security-review-workflow.md`** — Complete methodology from Anthropic's claude-code-security-review
   - 3-phase analysis approach
   - Vulnerability categories (input validation, auth, crypto, injection, data exposure)
   - Severity & confidence scoring
   - Output format requirements

2. **`custom-filtering.md`** — False positive reduction templates
   - Hard exclusion patterns (DOS, test files, theoretical issues)
   - Signal quality criteria
   - Technology-specific precedents (ORMs, frameworks, cloud providers)
   - Industry examples (retail, Power BI, compliance)

3. **`custom-scanning.md`** — Organization-specific vulnerability categories
   - Technology-specific checks (GraphQL, gRPC, Power BI, Power Apps)
   - Industry-specific checks (retail, financial services, e-commerce)
   - Compliance-focused checks (GDPR, HIPAA, PCI DSS, SOC 2)
   - PLMarketing/Kroger examples (retail analytics, vendor data, loyalty programs)

## Examples

See `references/examples.md` for:
- PR security review workflow
- Pre-commit review with custom rules
- Review → mitigate → comply pipeline
- Retail-specific review (Kroger client)

## Important Notes

### Do NOT Run Code
- Never execute `bash` commands to reproduce vulnerabilities
- Never write test files or exploit POCs
- Analysis is static code review only

### Focus on Changes
- Review ONLY what's NEW in the diff
- Don't report existing code vulnerabilities (unless context matters)
- Better to miss theoretical issues than flood with false positives

### Confidence Over Coverage
- Each finding must be something a senior security engineer would raise
- Minimize false positives (>80% confidence threshold)
- Avoid noise (style, theoretical, low-impact issues)

### Model Selection
Always use **opus** model for security review (set in metadata above). Security reasoning requires:
- Complex data flow tracing
- Multi-step attack path analysis
- Nuanced false positive filtering
- Context-aware severity assessment

Haiku/Sonnet lack the reasoning depth for high-confidence security analysis.
