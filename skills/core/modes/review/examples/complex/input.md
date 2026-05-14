# Review Skill — Complex Example Input

## User Request
```
review: full review of the payment refactor
```

## Context

**Git diff** (20 files changed, 450 lines):
- `types/payment.ts` — new types
- `services/payment.ts` — refactored service
- `api/payments.ts` — updated endpoints
- `api/webhooks/stripe.ts` — new webhook handler
- `components/PaymentForm.tsx` — updated UI
- ... (15 more files)

**Plan acceptance criteria:**
```
Task 1: Types exported, Zod schemas included
Task 2: Uses new types, type-safe
Task 3: No breaking changes
Task 4: Handles events, updates status
Task 5: Type-safe form, shows status
```
