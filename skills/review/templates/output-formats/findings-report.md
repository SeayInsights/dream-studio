# Review Findings Report Format

Output format for code review findings.

```markdown
# Review Report — [Feature/PR Name]

Generated: [timestamp]

---

## Stage 1: Spec Compliance

### Task 1: [Task Name]
- [✅ | ❌] [Acceptance criterion 1]
- [✅ | ❌] [Acceptance criterion 2]
- [✅ | ❌] [Acceptance criterion 3]

**Verdict:** [PASS | FAIL]
**Issues:** [List if FAIL]

### Task 2: [Task Name]
...

**Overall Spec Compliance:** [PASS | FAIL]

---

## Stage 2: Code Quality

### Checklist
- [✅ | ❌ | ⚠️] TypeScript strict mode compliance
- [✅ | ❌ | ⚠️] Error handling present
- [✅ | ❌ | ⚠️] No console.log statements
- [✅ | ❌ | ⚠️] Security (XSS, injection, etc.)
- [✅ | ❌ | ⚠️] Performance acceptable
- [✅ | ❌ | ⚠️] Follows project conventions

### Findings

[If no findings: "None — code quality acceptable"]

[If findings found, list each:]

**[CRITICAL | HIGH | MEDIUM | LOW] — [Short title]**
- **File:** [file path:line number]
- **Issue:** [Detailed description]
- **Impact:** [What happens if not fixed]
- **Fix:** [Specific recommended fix]
- **Blocking:** [Yes | No]

**[Severity] — [Title]**
...

**Overall Code Quality:** [PASS | FAIL]

---

## Summary

**Spec Compliance:** [PASS | FAIL]
**Code Quality:** [PASS | FAIL]

**Final Verdict:** [✅ PASS | ⚠️ CONDITIONAL PASS | ❌ FAIL]

**Blocking Issues:** [Count] (must be fixed before merge)
**Non-Blocking Suggestions:** [Count] (can fix post-merge)

**Recommended Action:**
[Merge | Fix blocking issues then merge | Major rework needed]
```

## Severity Guidelines

**CRITICAL:** Security vulnerability, data loss risk, service outage
**HIGH:** Breaks functionality, violates spec, major performance issue
**MEDIUM:** Code quality issue, minor performance concern, missing error handling
**LOW:** Style nit, optimization opportunity, suggestion

## Example

```markdown
# Review Report — Add User Authentication

Generated: 2026-04-28 15:30

---

## Stage 1: Spec Compliance

### Task 1: Create user model
- ✅ User interface with required fields
- ✅ Database migration present
- ✅ Zod schema for validation

**Verdict:** PASS

### Task 2: Add JWT utilities
- ✅ sign() function creates JWT
- ✅ verify() function validates JWT
- ⚠️ Error handling present but could be improved

**Verdict:** PASS (with minor note)

### Task 3: Create signup endpoint
- ✅ Accepts email and password
- ✅ Hashes password
- ✅ Creates user
- ✅ Returns JWT

**Verdict:** PASS

**Overall Spec Compliance:** PASS

---

## Stage 2: Code Quality

### Checklist
- ✅ TypeScript strict mode compliance
- ⚠️ Error handling (some cases missing)
- ✅ No console.log statements
- ❌ Security issue found
- ✅ Performance acceptable
- ✅ Follows project conventions

### Findings

**HIGH — SQL injection vulnerability**
- **File:** api/auth/signup.ts:15
- **Issue:** Email parameter not sanitized before database query
- **Impact:** Attacker could inject SQL and access/modify database
- **Fix:** Use parameterized queries or ORM (Kysely)
- **Blocking:** Yes

**MEDIUM — Missing rate limiting**
- **File:** api/auth/signup.ts
- **Issue:** No rate limiting on signup endpoint
- **Impact:** Vulnerable to spam/DoS
- **Fix:** Add rate limit middleware (10 req/min per IP)
- **Blocking:** No (can add post-merge)

**LOW — JWT expiry time**
- **File:** lib/jwt.ts:10
- **Issue:** Token expiry set to 30 days (long)
- **Impact:** Compromised token valid for long period
- **Fix:** Reduce to 7 days or implement refresh tokens
- **Blocking:** No

**Overall Code Quality:** FAIL (1 blocking issue)

---

## Summary

**Spec Compliance:** PASS
**Code Quality:** FAIL

**Final Verdict:** ❌ FAIL

**Blocking Issues:** 1 (SQL injection)
**Non-Blocking Suggestions:** 2

**Recommended Action:**
Fix SQL injection vulnerability then re-review. Other issues can be addressed post-merge.
```
