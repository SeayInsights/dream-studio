# Plan — Smoke Test

Quick validation test to verify the plan skill works correctly.

## Setup

1. Create a test project directory
```bash
mkdir /tmp/plan-smoke-test
cd /tmp/plan-smoke-test
git init
mkdir -p .planning
```

2. Create a minimal spec
```bash
cat > .planning/spec.md <<'EOF'
# Spec: Add Calculator

## Requirements
1. Create add() function
2. Create subtract() function  
3. Export both functions

## Acceptance
- Functions work correctly
- Functions are type-safe
EOF
```

## Run

Invoke the plan skill:
```
dream-studio:plan break this into tasks
```

## Expected

- ✅ Reads spec from `.planning/spec.md`
- ✅ Creates `.planning/plan.md` with tasks
- ✅ Each task has Files, Acceptance criteria
- ✅ Tasks are atomic and implementable

**Generated plan should contain:**
```markdown
# Plan: Add Calculator

### Task 1: Create add function
Create `src/add.ts` with add() function

**Files:** src/add.ts
**Acceptance:**
- Function accepts two numbers
- Returns sum
- Type-safe (TypeScript)

### Task 2: Create subtract function
...
```

## If It Fails

Check:
1. **Spec file not found** — Ensure `.planning/spec.md` exists
2. **Plan too vague** — Spec may need more detail
3. **No tasks generated** — Check spec has clear requirements
4. **Tasks too large** — Each task should be <1 hour of work
