# Plan Output Format

Save the generated plan to `.planning/plan.md` in this format:

```markdown
# Plan: [Feature Name]

## Overview
[1-2 sentence summary of what this plan implements]

## Wave 1: [Phase Name] (optional — only if dependencies create waves)

### Task 1: [Task Name]
[Detailed description of what needs to be done]

**Files:** [list of files to create/modify]
**Dependencies:** [Task N, Task M] (omit if no dependencies)
**Acceptance:**
- [Specific criterion 1]
- [Specific criterion 2]
- [Specific criterion 3]

### Task 2: [Task Name]
...

## Wave 2: [Phase Name] (if multi-wave)

### Task 3: [Task Name]
...

## Dependency Graph (optional — for complex plans)
```
Wave 1:  [1] [2]
          |   |
Wave 2:  [3] [4]
          |
Wave 3:  [5]
```

## Summary
- Total tasks: [N]
- Waves: [N] (sequential execution groups)
- Parallel opportunities: [list which tasks can run in parallel]
```

## Guidelines

**Task naming:**
- Action verb + what: "Create login form", "Add error handling", "Refactor user service"

**Acceptance criteria:**
- Specific and verifiable
- 3-5 criteria per task
- Use checkboxes (- [ ] format)

**Dependencies:**
- Only list if task actually depends on another
- Use task numbers (Task 1, Task 2)

**Files:**
- List specific file paths
- Include new and modified files

## Example

```markdown
# Plan: Add User Authentication

## Overview
Implement JWT-based authentication with email/password login and signup.

## Wave 1: Foundation

### Task 1: Create user model
Create `models/user.ts` with User interface and database schema

**Files:** models/user.ts, db/schema.sql
**Acceptance:**
- User interface with id, email, passwordHash, createdAt
- Database migration creates users table
- Zod schema for validation

### Task 2: Add JWT utilities
Create JWT token generation and verification utilities

**Files:** lib/jwt.ts
**Acceptance:**
- sign() function creates JWT with payload
- verify() function validates and decodes JWT
- Error handling for expired/invalid tokens

## Wave 2: API Endpoints

### Task 3: Create signup endpoint
Create POST /api/auth/signup endpoint

**Dependencies:** Task 1, Task 2
**Files:** api/auth/signup.ts
**Acceptance:**
- Accepts email and password
- Hashes password with bcrypt
- Creates user record
- Returns JWT token

### Task 4: Create login endpoint
Create POST /api/auth/login endpoint

**Dependencies:** Task 1, Task 2
**Files:** api/auth/login.ts
**Acceptance:**
- Accepts email and password
- Validates credentials
- Returns JWT token on success
- Returns 401 on invalid credentials

## Wave 3: Middleware

### Task 5: Add auth middleware
Create middleware to protect routes

**Dependencies:** Task 2
**Files:** middleware/auth.ts
**Acceptance:**
- Extracts JWT from Authorization header
- Verifies token
- Attaches user to request
- Returns 401 if no/invalid token

## Dependency Graph
```
Wave 1:  [1] [2]
          |\ /|
Wave 2:  [3] [4]
           \ /
Wave 3:    [5]
```

## Summary
- Total tasks: 5
- Waves: 3
- Parallel opportunities: Tasks 3 and 4 can run in parallel (different files)
```
