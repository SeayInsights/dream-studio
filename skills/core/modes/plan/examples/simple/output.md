# Plan Skill — Simple Example Output

## Generated Plan

Saved to `.planning/plan.md`:

```markdown
# Plan: Add Dark Mode

## Tasks

### Task 1: Create theme context
Create `contexts/ThemeContext.tsx` with theme state and localStorage persistence

**Files:** contexts/ThemeContext.tsx
**Acceptance:**
- useState hook for theme ('light' | 'dark')
- useEffect to load from localStorage
- useEffect to save on change

### Task 2: Add dark mode CSS
Create `styles/dark-theme.css` with dark mode variables

**Files:** styles/dark-theme.css
**Acceptance:**
- CSS variables for dark colors
- Applied when data-theme="dark"

### Task 3: Add theme toggle button
Create `components/ThemeToggle.tsx` in header

**Dependencies:** Task 1
**Files:** components/ThemeToggle.tsx, components/Header.tsx
**Acceptance:**
- Toggle button in header
- Uses ThemeContext
- Accessible (aria-label, keyboard support)
```

## Summary
✅ 3 tasks created, dependency chain established
