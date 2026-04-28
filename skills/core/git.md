# Git Operations — Core Module

Reusable git patterns used across dream-studio skills.

## Usage

When a skill needs git operations, reference this module in the skill's SKILL.md with:
```
## Imports
- core/git.md — git operations
```

## Patterns

### Check branch status
```bash
gh pr list --json state,headRefName
```
Returns list of open PRs. Check before pushing to prevent pushing to merged/closed branches.

### Get current branch
```bash
git branch --show-current
```

### Create feature branch
```bash
git checkout -b feat/<topic>
# or fix/<topic>, chore/<topic>
```

### Read git diff
```bash
# Unstaged changes
git diff

# Staged changes
git diff --cached

# Between commits
git diff <base-sha>..<head-sha>

# Since divergence from branch
git diff main...HEAD
```

### Commit with standard format
```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <description>

<optional body>

[<optional TR-IDs>]
EOF
)"
```

**Types:** feat, fix, chore, docs, refactor, test, perf
**Scope:** component/area being changed (optional)
**TR-IDs:** If `.planning/traceability.yaml` exists, reference implemented requirements

### Commit referencing plan task
```bash
# With traceability
git commit -m "feat(task-3): implement login form [TR-001, TR-002]"

# Without traceability  
git commit -m "feat(task-3): implement login form"
```

### Get commit SHA
```bash
git rev-parse HEAD
```

### Get commit log
```bash
# Recent commits
git log --oneline -10

# Since divergence from main
git log main..HEAD --oneline

# Full log with stats
git log --stat
```

### Check for uncommitted changes
```bash
git status --porcelain
```
If output is non-empty, there are uncommitted changes.

### Stage files
```bash
# Specific files (preferred)
git add file1.ts file2.ts

# All changes (use cautiously)
git add -A
```

### Push to remote
```bash
# New branch
git push -u origin <branch-name>

# Existing branch
git push
```

## Rules (from CLAUDE.md)

- **Never push directly to main** — always create feature branch first
- **Check open PRs before starting work** — `gh pr list`
- **Before pushing to a branch with existing PR** — check if merged/closed:
  ```bash
  gh pr view <branch> --json state
  ```
  If merged/closed → create new branch, don't push to dead branch
- **Branch naming:** `feat/<topic>`, `fix/<topic>`, `chore/<topic>`
- **Never force-push** without explicit user approval
- **Never add Co-Authored-By** attribution to commits

## Used by
build, review, verify, ship, plan, handoff, recap
