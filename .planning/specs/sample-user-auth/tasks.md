---

description: "Task list for user authentication feature"
---

# Tasks: User Authentication

**Input**: Design documents from `.planning/specs/sample-user-auth/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create project structure with `src/db/`, `src/auth/`, `src/routes/`, `src/components/`, `tests/`
- [ ] T002 Initialize TypeScript project with Hono, Drizzle ORM, bcryptjs, arctic, zod dependencies
- [ ] T003 [P] Configure Vitest and Playwright test frameworks

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Setup Drizzle schema in `src/db/schema.ts` (users, sessions, password_reset_tokens tables)
- [ ] T005 [P] Implement bcrypt wrapper in `src/auth/hash.ts` (hash, verify functions)
- [ ] T006 [P] Implement email validation with Zod in `src/auth/validate.ts`
- [ ] T007 Setup D1 database migrations in `src/db/migrations/`
- [ ] T008 Implement session token generation in `src/auth/session.ts` (UUID tokens, 7-day expiry)
- [ ] T009 Create session middleware in `src/auth/middleware.ts` (validate session from header)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Email/Password Login (Priority: P1) 🎯 MVP

**Goal**: Users can create accounts and log in with email/password

**Independent Test**: Signup → Login → Access protected route

### Implementation for User Story 1

- [ ] T010 [P] [US1] Create SignupForm component in `src/components/SignupForm.tsx`
- [ ] T011 [P] [US1] Create LoginForm component in `src/components/LoginForm.tsx`
- [ ] T012 [US1] Implement POST /auth/signup route in `src/routes/auth/signup.ts` (validate email, hash password, insert user, create session)
- [ ] T013 [US1] Implement POST /auth/login route in `src/routes/auth/login.ts` (find user, verify password, create session)
- [ ] T014 [US1] Create protected route example in `src/routes/protected.ts` (requires session middleware)
- [ ] T015 [US1] Add error handling for duplicate email (409 Conflict) and invalid credentials (401 Unauthorized)

**Checkpoint**: At this point, User Story 1 should be fully functional - users can signup, login, and access protected routes

---

## Phase 4: User Story 2 - Password Reset (Priority: P2)

**Goal**: Users can reset forgotten passwords via email

**Independent Test**: Request reset → Click email link → Set new password → Login

### Implementation for User Story 2

- [ ] T016 [P] [US2] Implement email sender in `src/auth/email.ts` (SendGrid/Resend client, reset email template)
- [ ] T017 [US2] Implement POST /auth/reset route in `src/routes/auth/reset.ts` (generate token, insert reset_token, send email)
- [ ] T018 [US2] Implement PUT /auth/reset route in `src/routes/auth/reset.ts` (validate token, check expiry, hash new password, update user, mark token used)
- [ ] T019 [US2] Add token expiry check (1 hour) and error handling for expired/invalid tokens

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - OAuth Integration (Priority: P3)

**Goal**: Users can log in with Google or GitHub

**Independent Test**: Click "Sign in with Google" → Authorize → Redirect back logged in

### Implementation for User Story 3

- [ ] T020 [P] [US3] Configure arctic OAuth clients in `src/auth/oauth.ts` (Google and GitHub providers)
- [ ] T021 [P] [US3] Create OAuthButtons component in `src/components/OAuthButtons.tsx`
- [ ] T022 [US3] Implement GET /auth/oauth/:provider route in `src/routes/auth/oauth.ts` (redirect to provider)
- [ ] T023 [US3] Implement GET /auth/oauth/callback route in `src/routes/auth/oauth.ts` (exchange code for token, fetch user email, find or create user, create session)
- [ ] T024 [US3] Add environment variable configuration for OAuth client IDs and secrets

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Testing & Polish

**Purpose**: Validate all user stories work end-to-end

- [ ] T025 [P] [US1] E2E test for signup/login flow in `tests/e2e/auth-flow.spec.ts`
- [ ] T026 [P] [US2] E2E test for password reset flow in `tests/e2e/reset-flow.spec.ts`
- [ ] T027 [P] [US3] E2E test for OAuth flow in `tests/e2e/oauth-flow.spec.ts`
- [ ] T028 Unit test for bcrypt hashing in `tests/unit/hash.test.ts`
- [ ] T029 Unit test for session token generation in `tests/unit/session.test.ts`
- [ ] T030 Load test login endpoint (verify <200ms p95 at 1000 req/s)
- [ ] T031 Verify zero plaintext passwords in database (schema assertion test)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Testing (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Reuses user table from US1 but is independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Reuses user and session tables but is independently testable

### Within Each User Story

- Components before routes (UI ready before API)
- Email sender before reset routes (US2 dependency)
- OAuth config before OAuth routes (US3 dependency)

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T003)
- All Foundational tasks marked [P] can run in parallel (T005, T006)
- Once Foundational phase completes, all user stories can start in parallel (US1, US2, US3 simultaneously if team capacity allows)
- All tests marked [P] can run in parallel (T025-T029)

---

## Parallel Example: Foundational Phase

```bash
# Launch all foundational tasks together after setup:
Task T005: "Implement bcrypt wrapper in src/auth/hash.ts"
Task T006: "Implement email validation with Zod in src/auth/validate.ts"
```

## Parallel Example: User Story 1

```bash
# Launch all components together:
Task T010: "Create SignupForm component in src/components/SignupForm.tsx"
Task T011: "Create LoginForm component in src/components/LoginForm.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently (signup → login → protected route)
5. Deploy/demo if ready (email/password auth fully functional)

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP: email/password login works!)
3. Add User Story 2 → Test independently → Deploy/Demo (password reset added!)
4. Add User Story 3 → Test independently → Deploy/Demo (OAuth added!)
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With 3 developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (T010-T015)
   - Developer B: User Story 2 (T016-T019)
   - Developer C: User Story 3 (T020-T024)
3. Stories complete and integrate independently

---

## dream-studio Integration

**Execution via**: `dream-studio:build` skill

**Task Tracking**: Use TaskCreate/TaskUpdate to track progress

**Checkpoints**: Pause at each checkpoint to verify independently

**Commit Strategy**: Commit after each task

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
