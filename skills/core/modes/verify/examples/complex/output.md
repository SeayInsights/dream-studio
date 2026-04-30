# Verify Skill — Complex Example Output

## Verification Report

### Environment Setup ✅
- Started dev server on localhost:3000
- Stripe test mode enabled
- Database seeded with test user

### Golden Path Test: Complete Payment Flow ✅

**Step 1: View pricing page**
- Navigate to `/pricing`
- Expected: 3 plans displayed (Free, Pro, Enterprise)
- Actual: ✅ All plans visible
- Evidence: Screenshot `.verification/01-pricing-page.png`

**Step 2: Click "Subscribe to Pro"**
- Click Pro plan button
- Expected: Redirect to Stripe checkout
- Actual: ✅ Redirected to checkout.stripe.com
- Evidence: Screenshot `.verification/02-stripe-checkout.png`

**Step 3: Complete payment (Stripe test card)**
- Enter test card `4242 4242 4242 4242`
- Expected: Payment succeeds
- Actual: ✅ Payment successful
- Evidence: Stripe dashboard screenshot `.verification/03-payment-success.png`

**Step 4: Return to app**
- Stripe redirects to `/checkout/success`
- Expected: Success message displayed
- Actual: ✅ "Payment successful!" message shown
- Evidence: Screenshot `.verification/04-success-page.png`

**Step 5: Webhook processing**
- Stripe sends payment.succeeded webhook
- Expected: Subscription status updated to "active"
- Actual: ✅ Database shows status="active"
- Evidence: Database query log `.verification/05-db-status.log`

**Step 6: UI reflects subscription**
- Check nav bar
- Expected: "Pro" badge displayed
- Actual: ✅ Badge shows "Pro"
- Evidence: Screenshot `.verification/06-pro-badge.png`

**Step 7: Access pro feature**
- Navigate to `/dashboard/analytics` (pro-only)
- Expected: Page loads (not blocked by middleware)
- Actual: ✅ Analytics page accessible
- Evidence: Screenshot `.verification/07-pro-feature.png`

### Edge Case Tests ✅

**Test: Payment failure**
- Used declined test card `4000 0000 0000 0002`
- Expected: Error message, no subscription created
- Actual: ✅ Error displayed, database unchanged
- Evidence: `.verification/edge-payment-failed.png`

**Test: Cancel during checkout**
- Started checkout, clicked "Back to site"
- Expected: Redirect to `/checkout/cancel`, no charge
- Actual: ✅ Redirected correctly, no subscription
- Evidence: `.verification/edge-checkout-cancel.png`

### Regression Tests ✅

**Checked:**
- ✅ Free users still see "Free" badge
- ✅ Login/logout still works
- ✅ Public pages (about, contact) still accessible
- ✅ No console errors on any page

**Evidence:** `.verification/regression-report.json`

### Performance Check ✅

**Metrics:**
- Pricing page: 1.2s load time (acceptable)
- Checkout redirect: 0.3s (fast)
- Webhook processing: 450ms (acceptable)

**Evidence:** `.verification/performance.log`

## Summary
✅ Verification PASS — golden path + edge cases + regressions all pass
📁 Evidence: 15 screenshots, 4 logs in `.verification/`
⚡ Performance within acceptable range
