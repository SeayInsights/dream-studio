# Build Skill — Complex Example Input

## User Request
```
build: execute the plan, watch for dependency conflicts
```

## Context

**Plan file** (`.planning/plan.md`):
```markdown
# Plan: Refactor Payment System

## Tasks

### Task 1: Create payment types
File: `types/payment.ts`
Define PaymentMethod, PaymentStatus, Transaction types

**Acceptance:**
- All types exported
- Zod schemas included

### Task 2: Refactor payment service
File: `services/payment.ts`
Update PaymentService to use new types

**Dependencies:** Task 1
**Acceptance:**
- Uses new types from task 1
- All methods type-safe

### Task 3: Update payment API
File: `api/payments.ts`
Update endpoints to use PaymentService

**Dependencies:** Task 2
**Acceptance:**
- All endpoints updated
- No breaking changes

### Task 4: Add payment webhooks
File: `api/webhooks/stripe.ts`
Handle Stripe webhook events

**Dependencies:** Task 1
**Acceptance:**
- Handles payment.succeeded, payment.failed
- Updates transaction status

### Task 5: Update payment UI
File: `components/PaymentForm.tsx`
Use new payment types in form

**Dependencies:** Task 1
**Acceptance:**
- Type-safe form
- Shows payment status
```

**Project structure:**
```
src/
├── types/
├── services/
├── api/
│   └── webhooks/
└── components/
```

**Complexity factors:**
- 5 tasks total
- Dependency chain: 1 → 2 → 3
- Parallel branch: 1 → 4
- UI task depends on types: 1 → 5
