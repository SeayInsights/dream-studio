# Repo Map — Core Module

Generates a compact symbol index of the codebase for pre-inlining into subagent context.
Gives agents structural awareness without requiring them to read every file.

## Usage

When a skill needs to provide repo-wide context to subagents:
```
## Imports
- core/repo-map.md — compact symbol index for subagent context
```

## Purpose

Subagents dispatched with only a task description have no structural awareness of the codebase.
Pre-inlining a repo map gives them the shape of the project (what exists, where) without the
weight of full file content. Claude's prompt caching caches this static prefix automatically
across consecutive dispatches in the same session.

## Generation

Run once at build Step 0. Store as `$REPO_MAP`. Paste identically into every subagent dispatch.

### Step 1 — Find source files
```bash
find . \
  -not -path '*/.git/*' \
  -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' \
  -not -path '*/dist/*' \
  -not -path '*/build/*' \
  \( -name "*.ts" -o -name "*.tsx" -o -name "*.py" -o -name "*.go" \
     -o -name "*.md" -o -name "*.yaml" -o -name "*.yml" \) \
  | sort
```

### Step 2 — Extract exported symbols
For TypeScript/JavaScript:
```bash
grep -rn "^export " --include="*.ts" --include="*.tsx" . \
  | grep -v node_modules \
  | sed 's|./||' \
  | awk -F: '{print $1 ":" $3}'
```

For Python:
```bash
grep -rn "^def \|^class \|^async def " --include="*.py" . \
  | grep -v "__pycache__" \
  | sed 's|./||' \
  | awk -F: '{print $1 ":" $3}'
```

For YAML skills (dream-studio):
```bash
grep -rn "^name:" --include="*.yml" --include="*.yaml" skills/ \
  | sed 's|./||' \
  | awk -F: '{print $1 ": " $NF}'
```

### Step 3 — Output format

One line per symbol: `path → type: name`

```
skills/build/SKILL.md → skill: build
skills/core/orchestration.md → module: orchestration
src/auth/service.ts → export: AuthService
src/auth/service.ts → export: validateToken
src/models/user.ts → export: User, UserSchema
workflows/idea-to-pr.yaml → workflow: idea-to-pr
```

### Step 4 — Size control

If output exceeds ~150 lines, filter to the most relevant layer:
- For skill edits: only `skills/` tree
- For web app: only `src/` tree
- For workflow edits: only `workflows/` tree

## In subagent prompt

Place the repo map in the static prefix (before task-specific content):

```
## Repo Map (generated 2026-04-28, build session)
skills/build/SKILL.md → skill: build
skills/core/orchestration.md → module: orchestration
...

## Task
[task-specific content here]
```

## Used by
build

## Notes

- Generate ONCE per build session — not per task. The map is static within a session
  (commits happen after each task, but the map reflects the pre-build state, which is sufficient)
- For projects with CONSTITUTION.md: the repo map supplements it, not replaces it
- For projects without CONSTITUTION.md: the repo map is the primary structural context
