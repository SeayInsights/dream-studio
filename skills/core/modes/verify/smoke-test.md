# Verify — Smoke Test

Quick validation test to verify the verify skill works correctly.

## Setup

1. Create a test project with a runnable app
```bash
mkdir /tmp/verify-smoke-test
cd /tmp/verify-smoke-test
npm init -y
npm install typescript tsx --save-dev

# Create a simple function to verify
cat > hello.ts <<'EOF'
export function hello(name: string = "World"): string {
  return `Hello, ${name}!`;
}

// Test it
console.log(hello());
console.log(hello("Alice"));
EOF
```

## Run

Invoke the verify skill:
```
dream-studio:verify test the hello function
```

## Expected

- ✅ Runs the code (using tsx hello.ts)
- ✅ Checks output matches expected behavior
- ✅ Tests edge cases (with/without parameter)
- ✅ Creates `.verification/` directory with evidence
- ✅ Outputs verification report

**Verification report should show:**
```
## Test 1: Default greeting ✅
Expected: "Hello, World!"
Actual: "Hello, World!"

## Test 2: Custom name ✅
Expected: "Hello, Alice!"
Actual: "Hello, Alice!"

## Summary
✅ Verification PASS — all tests passed
📁 Evidence: .verification/
```

## If It Fails

Check:
1. **Can't run code** — Ensure runtime available (Node.js, tsx, etc.)
2. **Output doesn't match** — Bug in implementation
3. **No evidence directory** — Verify skill should create `.verification/`
4. **Crashes** — Check code for syntax errors
