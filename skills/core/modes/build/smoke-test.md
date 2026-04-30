# Build — Smoke Test

Quick validation test to verify the build skill works correctly.

## Setup

1. Create a test project directory
```bash
mkdir /tmp/build-smoke-test
cd /tmp/build-smoke-test
git init
```

2. Create a minimal plan
```bash
mkdir -p .planning
cat > .planning/plan.md <<'EOF'
# Plan: Add Hello Function

## Task 1: Create hello function
Create `src/hello.ts` with a hello() function that returns "Hello, World!"

**Files:** src/hello.ts
**Acceptance:**
- Function exported
- Returns string "Hello, World!"
EOF
```

## Run

Invoke the build skill:
```
dream-studio:build execute plan
```

## Expected

- ✅ Reads plan from `.planning/plan.md`
- ✅ Creates `src/hello.ts` with hello() function
- ✅ Function returns correct string
- ✅ Commits with message referencing task
- ✅ Outputs completion summary

**Created files:**
```typescript
// src/hello.ts
export function hello(): string {
  return "Hello, World!";
}
```

**Git log:**
```
feat(task-1): create hello function
```

## If It Fails

Check:
1. **Plan file not found** — Ensure `.planning/plan.md` exists
2. **No git repo** — Run `git init` first
3. **Subagent errors** — Check if Agent tool is available
4. **Commit fails** — Ensure git user.name and user.email are configured
