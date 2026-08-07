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

## gh CLI Detection

Skills should detect whether `gh` CLI is available before attempting GitHub operations. If unavailable, fall back to GitHub API or prompt user for manual action.

### Detection pattern (cross-platform)

```bash
# Windows (bash/git-bash)
command -v gh > /dev/null 2>&1 && echo "available" || echo "not found"

# Windows (PowerShell)
Get-Command gh -ErrorAction SilentlyContinue

# Unix/Linux/macOS
which gh > /dev/null 2>&1 && echo "available" || echo "not found"
```

### Fallback strategy

When `gh` is not detected:

1. **GitHub API fallback** — Use MCP GitHub tools if available:
   - `mcp__github__create_pull_request` instead of `gh pr create`
   - `mcp__github__list_pull_requests` instead of `gh pr list`
   - `mcp__github__issue_write` instead of `gh issue create`
   - Requires GitHub MCP server configured in user environment

2. **User prompt fallback** — If GitHub API also unavailable:
   ```
   gh CLI not detected. To enable GitHub operations:
   1. Install gh CLI: https://cli.github.com/
   2. Run: gh auth login
   
   Alternative: I can use GitHub API via MCP if configured.
   Would you like to:
   - Install gh CLI now
   - Configure GitHub MCP server
   - Continue with manual GitHub operations
   ```

3. **Manual operations** — Provide user with:
   - Branch name to push manually
   - Commit SHA for reference
   - Suggested PR title and body text
   - Link to create PR via web UI

### Integration in skills

When a skill needs GitHub operations:

```markdown
## Before GitHub operations
1. Detect gh CLI availability
2. If not available, check for GitHub MCP tools
3. If neither available, prompt user for preferred fallback
4. Proceed with detected method

## Example flow
- gh available → use gh commands
- gh unavailable + MCP available → use mcp__github__* tools
- gh unavailable + no MCP → prompt user, provide manual steps
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
