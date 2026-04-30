# Ship Skill — Complex Example Output

## Pre-Deploy Gate Report

### Phase 1: Audit

**Accessibility:**
- ✅ Payment form has proper labels
- ✅ Error messages announced to screen readers
- ✅ Keyboard navigation through checkout flow
- ✅ Color contrast on all payment UI
- ✅ WCAG 2.1 AA compliant

**Performance:**
- ✅ Pricing page: 1.2s LCP (good)
- ✅ Checkout redirect: 0.3s (excellent)
- ✅ Bundle size delta: +12KB gzipped (acceptable)
- ⚠️  Payment form: 2.1s LCP (needs optimization) — YELLOW
- ✅ No blocking operations in critical path

**Technical:**
- ✅ TypeScript strict mode passing
- ✅ ESLint: 0 errors
- ⚠️  Missing: Rate limiting on checkout endpoint — YELLOW
- ⚠️  Missing: Idempotency keys on Stripe calls — YELLOW
- ✅ Stripe webhook signature verification present
- ✅ Environment variables documented

### Phase 2: Harden

**Error states:**
- ✅ Stripe API error handling
- ✅ Network failure handling in checkout
- ✅ Error boundary around payment form
- ✅ User-friendly error messages

**Loading states:**
- ✅ Checkout button shows spinner
- ✅ Payment form disables during processing
- ✅ Skeleton UI on pricing page

**Empty states:**
- ✅ Empty payment history message
- ✅ No subscription placeholder

### Phase 3: Optimize

**Bundle:**
- ✅ Code splitting for payment routes
- ✅ Stripe.js loaded on-demand
- ✅ Tree-shaking verified

**Render:**
- ⚠️  Payment form re-renders on every keystroke — YELLOW
- ✅ Pricing cards memoized
- ✅ No unnecessary API calls

**Images:**
- N/A (no images in payment flow)

**Animation:**
- ✅ Checkout transition 200ms (smooth)
- ✅ No jank detected

### Phase 4: Test

**E2E tests (Playwright):**
- ✅ Complete payment flow: PASS
- ✅ Payment failure handling: PASS
- ✅ Cancel during checkout: PASS
- ✅ Webhook processing: PASS
- ✅ Subscription status update: PASS

**Regression tests:**
- ✅ Free user flow: PASS
- ✅ Login/logout: PASS
- ✅ Public pages: PASS

**Security tests:**
- ✅ Webhook signature validation: PASS
- ✅ No credit card data stored locally: PASS
- ✅ HTTPS enforced: PASS
- ⚠️  No rate limiting tested — YELLOW

## Gate Decision

🟡 **CONDITIONAL PASS** — 4 YELLOW warnings must be addressed

### Blockers to resolve:

**YELLOW-1: Payment form LCP 2.1s**
- **Impact:** Poor UX on slow connections
- **Fix:** Lazy load Stripe.js, reduce form size
- **Effort:** 30 minutes
- **Blocking:** No (acceptable for v1)

**YELLOW-2: Missing rate limiting**
- **Impact:** Potential abuse of checkout endpoint
- **Fix:** Add rate limit middleware (10 req/min per IP)
- **Effort:** 15 minutes
- **Blocking:** YES (security risk)

**YELLOW-3: Missing idempotency keys**
- **Impact:** Duplicate charges on retry
- **Fix:** Generate and pass idempotency keys to Stripe
- **Effort:** 20 minutes
- **Blocking:** YES (financial risk)

**YELLOW-4: Payment form re-renders**
- **Impact:** Performance degradation
- **Fix:** Debounce input handlers
- **Effort:** 10 minutes
- **Blocking:** No (acceptable for v1)

## Action Required

🔴 **MUST FIX BEFORE DEPLOY:**
- YELLOW-2: Add rate limiting
- YELLOW-3: Add idempotency keys

🟡 **RECOMMENDED (can fix post-deploy):**
- YELLOW-1: Optimize payment form LCP
- YELLOW-4: Debounce form inputs

## Summary
⚠️  BLOCKED — 2 critical issues must be resolved before deploy
Estimated fix time: 35 minutes
Re-run ship after fixes applied
