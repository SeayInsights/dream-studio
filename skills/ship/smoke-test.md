# Ship — Smoke Test

Quick validation test to verify the ship skill works correctly.

## Setup

1. Create a test project with completed work
```bash
mkdir /tmp/ship-smoke-test
cd /tmp/ship-smoke-test
git init
npm init -y
npm install typescript --save-dev

# Create a simple component
cat > Button.tsx <<'EOF'
interface ButtonProps {
  label: string;
  onClick: () => void;
}

export function Button({ label, onClick }: ButtonProps) {
  return (
    <button onClick={onClick} aria-label={label}>
      {label}
    </button>
  );
}
EOF

# Create tsconfig
cat > tsconfig.json <<'EOF'
{
  "compilerOptions": {
    "strict": true,
    "jsx": "react"
  }
}
EOF

git add .
git commit -m "Add Button component"
```

## Run

Invoke the ship skill:
```
dream-studio:ship ready to deploy
```

## Expected

- ✅ Phase 1: Audit (accessibility, performance, technical)
- ✅ Phase 2: Harden (error states, loading states)
- ✅ Phase 3: Optimize (bundle, render)
- ✅ Phase 4: Test (unit, regression)
- ✅ Outputs gate decision (PASS/FAIL)

**Ship report should show:**
```
## Phase 1: Audit ✅
- ✅ Accessibility: ARIA labels present
- ✅ Performance: Component size acceptable
- ✅ Technical: TypeScript strict mode passing

## Phase 2: Harden ✅
- ✅ Error states handled
- ✅ Props validated

## Phase 3: Optimize ✅
- ✅ Component tree-shakeable
- ✅ No unnecessary re-renders

## Phase 4: Test ✅
- ✅ TypeScript compiles

## Gate Decision
🟢 PASS — All gates passed, safe to deploy
```

## If It Fails

Check:
1. **Audit failures** — Fix accessibility, performance, or technical issues
2. **Missing error handling** — Add error states
3. **Build fails** — Fix TypeScript errors
4. **Gate blocked** — Address blocking issues before deploy
