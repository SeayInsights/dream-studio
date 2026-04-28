# Plan Skill — Complex Example Input

## User Request
```
plan: break this into implementable tasks with dependency tracking
```

## Context

**Spec file** (`.planning/spec.md`):
```markdown
# Spec: Multi-Tenant SaaS Billing

## Overview
Add subscription billing with Stripe integration

## Requirements

### Backend
1. Create subscription model (plan, status, stripe_id)
2. Add Stripe API integration
3. Create checkout endpoint
4. Handle webhook events (payment success/failure)
5. Add subscription middleware (check active subscription)

### Frontend
6. Build pricing page
7. Build checkout flow
8. Add billing dashboard
9. Show subscription status in nav

### Infrastructure
10. Add Stripe env vars
11. Deploy webhook endpoint

## Constraints
- Webhook must be deployed before Stripe dashboard config
- Middleware depends on subscription model
- All UI depends on backend API
```
