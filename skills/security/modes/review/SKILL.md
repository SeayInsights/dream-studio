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
1. Run `git diff` to get staged/unstaged changes
2. If reviewing a PR, get diff against base branch: `git diff main...HEAD`
3. If user provides a specific commit range, use that instead

### Phase 2: Analyze for Vulnerabilities
Follow the 3-phase methodology from `security-review-workflow.md`:

#### 2.1 Repository Context Research
- Use Grep/Glob to identify existing security frameworks
- Look for established sanitization patterns
- Understand authentication/authorization models
- Identify ORMs, validation libraries, security middleware in use

#### 2.2 Comparative Analysis
- Compare new code against existing security patterns
- Flag deviations from established secure practices
- Identify new attack surfaces introduced by changes
- Check for inconsistent security implementations

#### 2.3 Vulnerability Assessment
- Examine modified files for security implications
- Trace data flow from user inputs to sensitive operations
- Look for privilege boundaries crossed unsafely
- Identify injection points and unsafe deserialization

**Focus areas** (see full category list in `security-review-workflow.md`):
- Input validation vulnerabilities (SQL injection, command injection, path traversal)
- Authentication/authorization issues (bypass, privilege escalation)
- Crypto & secrets management (hardcoded keys, weak algorithms)
- Injection & code execution (XSS, RCE, deserialization)
- Data exposure (PII leaks, sensitive logging)

### Phase 3: Apply Filtering
Use the false positive filtering rules from `custom-filtering.md`:

1. **Hard exclusions** (18 patterns):
   - DOS/resource exhaustion
   - Secrets on disk (if otherwise secured)
   - Rate limiting concerns
   - Test files only
   - Theoretical race conditions
   - Log spoofing
   - Regex injection/DOS
   - Documentation files

2. **Signal quality criteria**:
   - Is there a concrete, exploitable vulnerability with clear attack path?
   - Does this represent real security risk vs theoretical best practice?
   - Are there specific code locations and reproduction steps?
   - Would this be actionable for a security team?

3. **Confidence scoring** (1-10 scale):
   - Report only findings with confidence ≥8
   - 9-10: Certain exploit path identified
   - 8-9: Clear vulnerability pattern with known exploitation
   - 7-8: Suspicious pattern requiring specific conditions
   - <7: Don't report (too speculative)

### Phase 4: Report Findings
For each HIGH-confidence finding, output in this format:

```markdown
# Vuln N: [Category]: `[file]:[line]`

* Severity: [High/Medium]
* Description: [What the vulnerability is]
* Exploit Scenario: [How an attacker could exploit this]
* Recommendation: [Specific fix guidance]
```

**Severity guidelines:**
- **HIGH**: Directly exploitable → RCE, data breach, auth bypass
- **MEDIUM**: Requires specific conditions but significant impact
- **LOW**: Defense-in-depth issues (do not report unless requested)

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

### Example 1: PR Security Review
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

### Example 2: Pre-Commit Review with Custom Rules
```
User: "Security review before I commit"

Steps:
1. Run `git diff --staged` for staged changes
2. Check for `.dream/security/false-positives.txt`
3. Check for `.dream/security/custom-categories.txt`
4. Run analysis with custom + default rules
5. Report HIGH/MEDIUM findings only
```

### Example 3: Review → Mitigate → Comply Pipeline
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

### Example 4: Retail-Specific Review (Kroger Client)
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
