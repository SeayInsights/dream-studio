# Build Skill — Simple Example Output

## Execution Steps

**Step 1: Parse plan** ✓
- Loaded `.planning/plan.md`
- Found 2 tasks
- No dependencies (parallel execution possible)

**Step 2: Execute tasks in parallel**

Spawned 2 implementer agents:
- Agent A: Task 1 (models/user.ts)
- Agent B: Task 2 (api/auth/login.ts)

**Step 3: Agent A completed** ✓
Created `models/user.ts`:
```typescript
export interface User {
  id: string;
  email: string;
  passwordHash: string;
  createdAt: Date;
}
```

**Step 4: Agent B completed** ✓
Created `api/auth/login.ts`:
```typescript
import { User } from '@/models/user';

export async function POST(req: Request) {
  const { email, password } = await req.json();
  // ... login logic
  return Response.json({ token: 'jwt-token' });
}
```

**Step 5: Review stage** ✓
- All acceptance criteria met
- No code quality issues
- 2 files created

**Step 6: Commit** ✓
```
feat: add user authentication

- Create User model interface
- Add login endpoint with JWT

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

## Result

✅ Build complete — 2 tasks executed, 2 files created, 1 commit
