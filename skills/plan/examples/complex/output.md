# Plan Skill — Complex Example Output

## Generated Plan

Saved to `.planning/plan.md`:

```markdown
# Plan: Multi-Tenant SaaS Billing

## Wave 1: Foundation

### Task 1: Create subscription model
Create `models/subscription.ts` with Subscription interface

**Files:** models/subscription.ts, db/schema.sql
**Acceptance:**
- Subscription type (plan, status, stripe_id, user_id)
- Database migration
- Zod schema

### Task 2: Add Stripe integration
Create `lib/stripe.ts` Stripe client wrapper

**Files:** lib/stripe.ts
**Acceptance:**
- Stripe client initialized
- Type-safe API methods
- Error handling

### Task 3: Add env vars
Add STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

**Files:** .env.example, wrangler.toml
**Acceptance:**
- Env vars documented
- CI secrets configured

## Wave 2: Backend API (depends on Wave 1)

### Task 4: Create checkout endpoint
Create `api/checkout.ts` POST endpoint

**Dependencies:** Task 1, Task 2
**Files:** api/checkout.ts
**Acceptance:**
- Creates Stripe checkout session
- Stores pending subscription
- Returns checkout URL

### Task 5: Handle webhook events
Create `api/webhooks/stripe.ts` POST endpoint

**Dependencies:** Task 1, Task 2
**Files:** api/webhooks/stripe.ts
**Acceptance:**
- Verifies webhook signature
- Handles payment.succeeded
- Handles payment.failed
- Updates subscription status

### Task 6: Add subscription middleware
Create `middleware/requireSubscription.ts`

**Dependencies:** Task 1
**Files:** middleware/requireSubscription.ts
**Acceptance:**
- Checks active subscription
- Returns 403 if inactive

## Wave 3: Frontend (depends on Wave 2)

### Task 7: Build pricing page
Create `pages/pricing.tsx`

**Dependencies:** Task 4
**Files:** pages/pricing.tsx, components/PricingCard.tsx
**Acceptance:**
- Displays plans
- Links to checkout

### Task 8: Build checkout flow
Create checkout page and success/cancel handlers

**Dependencies:** Task 4
**Files:** pages/checkout.tsx, pages/checkout/success.tsx, pages/checkout/cancel.tsx
**Acceptance:**
- Redirects to Stripe checkout
- Handles return flow

### Task 9: Build billing dashboard
Create `pages/billing.tsx`

**Dependencies:** Task 5
**Files:** pages/billing.tsx
**Acceptance:**
- Shows subscription status
- Shows payment history
- Cancel subscription button

### Task 10: Add status indicator
Add subscription status to nav

**Dependencies:** Task 1
**Files:** components/Nav.tsx
**Acceptance:**
- Shows "Free" or "Pro" badge
- Links to billing dashboard
```

## Dependency Graph

```
Wave 1:  [1] [2] [3]
          |   |
Wave 2:  [4] [5] [6]
          |   |   |
Wave 3:  [7] [8] [9] [10]
```

## Summary
✅ 10 tasks created across 3 waves
✅ Dependency chain established (backend → API → frontend)
✅ Parallel execution within waves
