# Review Skill — Simple Example Input

## User Request
```
review: check the recent changes
```

## Context

**Git diff:**
```diff
+ src/components/Button.tsx
+ export function Button({ label, onClick }: ButtonProps) {
+   return <button onClick={onClick}>{label}</button>
+ }
```

**Plan task:**
```
Task 1: Create reusable Button component

Acceptance:
- Component accepts label and onClick props
- Types defined
```
