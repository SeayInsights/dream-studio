# Implementation Plan: User Authentication

**Date**: 2026-04-27 | **Spec**: `.planning/specs/sample-user-auth/spec.md`  
**Input**: Feature specification from spec.md

## Summary

Implement user authentication system with email/password login (P1), password reset (P2), and OAuth integration (P3). Tech stack: React 19 frontend, Cloudflare Workers backend, D1 SQLite database, bcrypt for hashing.

## Technical Context

**Language/Version**: TypeScript 5.3, React 19  
**Primary Dependencies**: Hono (Workers), Drizzle ORM, bcrypt, arctic (OAuth)  
**Storage**: Cloudflare D1 (SQLite)  
**Testing**: Playwright (E2E), Vitest (unit)  
**Target Platform**: Cloudflare Workers (edge runtime)  
**Project Type**: Web app with API backend  
**Performance Goals**: <200ms p95 for login, 1000 req/s sustained  
**Constraints**: Edge runtime limits (no Node.js crypto), D1 per-request limits  
**Scale/Scope**: 10k users initially, 3 auth flows (email, password reset, OAuth)

## Constitution Check

*GATE: Must pass before implementation.*

✅ Follows dream-studio principles:
- Modular (auth as separate service)
- Security by default (bcrypt, no plaintext passwords)
- Independent user stories (P1 works without P2/P3)

⚠️ OAuth integration adds complexity — justified because user story is P3 (optional), can ship P1 MVP without it.

## Project Structure

### Documentation (this feature)

```text
.planning/specs/sample-user-auth/
├── spec.md              # User stories, requirements (think output)
├── plan.md              # This file (plan output)
└── tasks.md             # Task breakdown (plan output)
```

### Source Code

```text
src/
├── db/
│   ├── schema.ts        # Drizzle schema (users, sessions, reset_tokens)
│   └── migrations/      # D1 migrations
├── auth/
│   ├── hash.ts          # bcrypt wrapper
│   ├── session.ts       # Session management
│   ├── oauth.ts         # OAuth handlers (Google, GitHub)
│   └── email.ts         # Password reset email sender
├── routes/
│   ├── auth/
│   │   ├── signup.ts    # POST /auth/signup
│   │   ├── login.ts     # POST /auth/login
│   │   ├── reset.ts     # POST /auth/reset (request), PUT /auth/reset (confirm)
│   │   └── oauth.ts     # GET /auth/oauth/:provider, GET /auth/oauth/callback
│   └── protected.ts     # Example protected route
└── components/
    ├── SignupForm.tsx   # Email/password signup
    ├── LoginForm.tsx    # Email/password login
    └── OAuthButtons.tsx # Google/GitHub buttons

tests/
├── e2e/
│   ├── auth-flow.spec.ts  # Full login/signup flow
│   └── reset-flow.spec.ts # Password reset flow
└── unit/
    ├── hash.test.ts       # bcrypt hashing
    └── session.test.ts    # Session token generation
```

**Structure Decision**: Single project with `src/` for backend (Workers) and `src/components/` for frontend (React). Auth logic separated into `src/auth/` module for clear boundaries.

## Complexity Tracking

> **Fill ONLY if there are complexity concerns that must be justified**

| Concern | Why Needed | Simpler Alternative Rejected Because |
|---------|------------|-------------------------------------|
| OAuth integration (P3) | User expectation for modern apps | Email-only sufficient for MVP but limits adoption |

## Requirements Traceability

| Requirement ID | Description | Implemented By |
|---------------|-------------|----------------|
| FR-001 | Bcrypt password hashing | T005 |
| FR-002 | Email validation | T004, T006 |
| FR-003 | Account creation | T004, T006, T007 |
| FR-004 | 7-day session persistence | T008, T009 |
| FR-005 | Reset email within 60s | T011 |
| FR-006 | Google/GitHub OAuth | T014, T015 |
| FR-007 | 1-hour reset token expiry | T011, T012 |

## Dependencies

### External Dependencies
- `hono` — Web framework for Cloudflare Workers
- `drizzle-orm` — TypeScript ORM for D1
- `bcryptjs` — Password hashing (pure JS, works in Workers)
- `arctic` — OAuth 2.0 client library
- `zod` — Runtime validation
- `@react-email/components` — Email templates

### Internal Dependencies
- Existing Cloudflare Workers deployment pipeline
- Email service (SendGrid or Resend) configured

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| bcryptjs performance on edge | Medium | Use cost factor 12 (not 14), cache results, monitor p95 latency |
| D1 concurrent write limits | Medium | Use connection pooling, queue concurrent signups if >100/s |
| OAuth redirect URI changes | Low | Environment variables for redirect URIs (dev vs prod) |
| Email delivery delays | Medium | Queue emails via Cloudflare Queues, 60s SLA tracked |

## Success Metrics

- [ ] All functional requirements (FR-001 through FR-007) implemented
- [ ] User Story 1 (P1) independently testable via E2E test
- [ ] User Story 2 (P2) independently testable via E2E test
- [ ] User Story 3 (P3) independently testable via E2E test
- [ ] Login <200ms p95 latency under load test (1000 req/s)
- [ ] Zero plaintext passwords in database (verified via schema test)

## dream-studio Integration

**Skill Flow**: think → **plan** → build → review → verify → ship

**Output Location**: `.planning/specs/sample-user-auth/plan.md` and `tasks.md`

**Next Steps**: 
1. Review this plan with user for approval
2. Run `dream-studio:build` with the tasks.md file
3. Execute tasks in dependency order (Foundation → US1 → US2 → US3)
