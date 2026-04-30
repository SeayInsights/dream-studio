# Review — Smoke Test

Quick validation test to verify the review skill works correctly.

## Setup

1. Create a test project with changes
```bash
mkdir /tmp/review-smoke-test
cd /tmp/review-smoke-test
git init
git config user.name "Test"
git config user.email "test@test.com"

# Create a file
cat > hello.ts <<'EOF'
export function hello(): string {
  return "Hello, World!";
}
EOF

git add hello.ts
git commit -m "Add hello function"
```

2. Create a plan with acceptance criteria
```bash
mkdir -p .planning
cat > .planning/plan.md <<'EOF'
# Plan: Add Hello Function

## Task 1: Create hello function
Create hello.ts with hello() function

**Acceptance:**
- Function exported
- Returns "Hello, World!"
- Type-safe
EOF
```

## Run

Invoke the review skill:
```
dream-studio:review review code
```

## Expected

- ✅ Reads recent git diff
- ✅ Stage 1: Checks spec compliance against plan
- ✅ Stage 2: Checks code quality
- ✅ Outputs review report with verdict

**Review report should show:**
```
## Stage 1: Spec Compliance
- ✅ Function exported
- ✅ Returns "Hello, World!"
- ✅ Type-safe

Verdict: PASS

## Stage 2: Code Quality
- ✅ TypeScript types present
- ✅ Clean code

Verdict: PASS

## Summary
✅ Review PASS — ready to merge
```

## If It Fails

Check:
1. **No git history** — Need at least 1 commit
2. **Plan not found** — Create `.planning/plan.md`
3. **No changes to review** — Make a code change first
4. **Review fails** — Check if code actually meets acceptance criteria
