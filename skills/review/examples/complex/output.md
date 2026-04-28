# Review Skill — Complex Example Output

## Review Report

### Stage 1: Spec Compliance

**Task 1 — Payment types:**
- ✅ All types exported
- ✅ Zod schemas included
- ✅ Matches spec

**Task 2 — Payment service:**
- ✅ Uses new types from Task 1
- ✅ All methods type-safe
- ✅ Matches spec

**Task 3 — Payment API:**
- ✅ All endpoints updated
- ✅ No breaking changes (response shape preserved)
- ✅ Matches spec

**Task 4 — Webhooks:**
- ✅ Handles payment.succeeded
- ✅ Handles payment.failed
- ✅ Updates transaction status
- ✅ Matches spec

**Task 5 — Payment UI:**
- ✅ Type-safe form
- ✅ Shows payment status
- ✅ Matches spec

**Verdict:** Spec compliance PASS (all 5 tasks met acceptance criteria)

### Stage 2: Code Quality

**Checklist:**
- ✅ TypeScript strict mode compliance
- ✅ No type `any` usage
- ✅ Consistent naming conventions
- ✅ Error handling present
- ⚠️  Missing: Error boundary around PaymentForm (medium)
- ⚠️  Missing: Retry logic in webhook handler (medium)
- ✅ Zod validation on API inputs
- ✅ No console.log statements
- ✅ Imports organized

**Findings:**

**MEDIUM — Missing error boundary**
- **File:** components/PaymentForm.tsx
- **Issue:** No error boundary wrapping payment form
- **Impact:** Uncaught errors could crash entire page
- **Fix:** Wrap in <ErrorBoundary> or add try/catch in component
- **Blocking:** No (can fix post-merge)

**MEDIUM — No retry logic in webhooks**
- **File:** api/webhooks/stripe.ts
- **Issue:** Webhook handler doesn't retry on transient failures
- **Impact:** Failed webhook processing might not recover
- **Fix:** Add exponential backoff retry logic
- **Blocking:** No (Stripe retries by default)

**Verdict:** Code quality PASS (findings are non-blocking improvements)

## Summary
✅ Review PASS — ready to merge
⚠️  2 medium-priority improvements recommended:
  1. Add error boundary to PaymentForm
  2. Add retry logic to webhook handler

Estimated effort for improvements: 30 minutes
