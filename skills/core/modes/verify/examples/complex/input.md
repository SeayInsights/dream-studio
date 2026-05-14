# Verify Skill — Complex Example Input

## User Request
```
verify: full e2e test of payment flow
```

## Context

**Recent changes:**
- Complete payment system refactor
- 5 new files, 20 files modified
- Backend + frontend integration

**Critical paths to test:**
1. User views pricing page
2. User starts checkout
3. User completes payment (Stripe test mode)
4. Webhook updates subscription
5. User sees "Pro" badge in nav
6. User can access pro features
