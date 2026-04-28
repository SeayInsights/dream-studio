# Build Skill — Complex Example Output

## Execution Steps

**Step 1: Parse plan and analyze dependencies** ✓
- Loaded `.planning/plan.md`
- Found 5 tasks
- Dependency graph:
  ```
  Task 1 (types)
    ├─> Task 2 (service)
    │    └─> Task 3 (API)
    ├─> Task 4 (webhooks)
    └─> Task 5 (UI)
  ```
- Execution waves:
  - Wave 1: Task 1
  - Wave 2: Tasks 2, 4, 5 (parallel)
  - Wave 3: Task 3

**Step 2: Wave 1 — Execute Task 1** ✓
Spawned implementer agent for Task 1
Created `types/payment.ts` with PaymentMethod, PaymentStatus, Transaction + Zod schemas

**Step 3: Wave 2 — Execute Tasks 2, 4, 5 in parallel** ✓
Spawned 3 implementer agents:
- Agent A: Task 2 (services/payment.ts)
- Agent B: Task 4 (api/webhooks/stripe.ts)
- Agent C: Task 5 (components/PaymentForm.tsx)

**Agent A completed** ✓
Refactored `services/payment.ts` to use new types

**Agent B completed** ✓
Created `api/webhooks/stripe.ts` with event handlers

**Agent C completed** ✓
Updated `components/PaymentForm.tsx` with type-safe form

**Step 4: Wave 3 — Execute Task 3** ✓
Spawned implementer agent for Task 3
Updated `api/payments.ts` endpoints

**Step 5: Two-stage review** ✓

**Stage 1 — Spec compliance:**
- ✅ All 5 tasks completed
- ✅ All acceptance criteria met
- ✅ Dependency order respected

**Stage 2 — Code quality:**
- ✅ Types properly exported and imported
- ✅ No type errors
- ✅ Consistent naming
- ⚠️  Minor: PaymentService could use error handling (non-blocking)

**Step 6: Commit** ✓
```
refactor: modernize payment system with type safety

- Add payment types with Zod validation
- Refactor PaymentService to use new types
- Update payment API endpoints
- Add Stripe webhook handlers
- Update PaymentForm with type-safe form

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

**Step 7: Update traceability** ✓
Added TR-IDs to `.planning/traceability.yaml`:
```yaml
TR-001: types/payment.ts (Task 1)
TR-002: services/payment.ts (Task 2)
TR-003: api/payments.ts (Task 3)
TR-004: api/webhooks/stripe.ts (Task 4)
TR-005: components/PaymentForm.tsx (Task 5)
```

## Result

✅ Build complete — 5 tasks executed in 3 waves, 5 files created, 1 commit, traceability updated
⚠️  1 minor code quality note (non-blocking)
