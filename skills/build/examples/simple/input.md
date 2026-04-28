# Build Skill — Simple Example Input

## User Request
```
build: execute the plan
```

## Context

**Plan file** (`.planning/plan.md`):
```markdown
# Plan: Add User Authentication

## Tasks

### Task 1: Create user model
Create `models/user.ts` with User interface (id, email, passwordHash, createdAt)

**Acceptance:**
- Interface exported
- All fields typed correctly

### Task 2: Add login endpoint
Create `api/auth/login.ts` POST endpoint that accepts email/password

**Acceptance:**
- Returns JWT token on success
- Returns 401 on invalid credentials
```

**Project structure:**
```
src/
├── models/
└── api/
    └── auth/
```
