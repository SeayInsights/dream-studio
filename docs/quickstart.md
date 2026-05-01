# Quick Start: Zero to First Spec in < 2 Minutes

⏱️ **Time to complete**: Under 2 minutes

Get from install to your first dream-studio spec in under 2 minutes. This guide takes you through the core workflow: think → plan → build.

---

## Step 1: Install (30 seconds)

### Option A: Install from Claude Marketplace
```bash
# From Claude Code CLI
claude code install dream-studio-core
```

### Option B: Install from GitHub
```bash
git clone https://github.com/SeayInsights/dream-studio.git
cd dream-studio
# Link as Claude Code plugin
claude code link .
```

---

## Step 2: First-Run Setup (30 seconds)

```bash
# Launch setup wizard
/setup:wizard
```

**What it does:**
- Creates `.dream-studio/` directory
- Detects installed tools (git, gh, npm, etc.)
- Populates registry with gotchas and best practices
- Sets up hooks

**Quick tip**: Skip tool installation for now - you can add tools later.

---

## Step 3: Your First Spec (60 seconds)

Let's turn an idea into a detailed spec using `think` mode.

### Example: Add User Authentication

```
think: add user authentication to my app
```

**What happens:**
- Claude analyzes your request
- Generates a comprehensive spec with:
  - User stories
  - Technical approach
  - Edge cases and security considerations
  - Success metrics

**Output location**: `.planning/specs/user-authentication/spec.md`

### Review the Spec

Open the generated spec:
```bash
cat .planning/specs/user-authentication/spec.md
```

You'll see:
- ✅ Clear problem statement
- ✅ User stories ("As a user, I want...")
- ✅ Technical architecture
- ✅ Security considerations
- ✅ Testing strategy

---

## Next Steps (Optional, but Recommended)

### Break It Down: Plan Mode
```
plan: .planning/specs/user-authentication/spec.md
```

Generates a task breakdown with:
- Technical requirements traceability
- File structure
- Complexity tracking
- Dependencies

**Output**: `.planning/specs/user-authentication/plan.md` + `tasks.md`

### Execute: Build Mode
```
build: .planning/specs/user-authentication/tasks.md
```

Implements the tasks in waves:
- Reads the task list
- Executes in dependency order
- Commits after each task
- Reports progress

---

## Core Workflow Summary

```
💡 Idea → think: <your idea>
   ↓
📋 Spec generated (.planning/specs/<name>/spec.md)
   ↓
🗺️  plan: <spec path>
   ↓
📝 Tasks generated (plan.md + tasks.md)
   ↓
🔨 build: <tasks path>
   ↓
✅ Implementation complete
   ↓
🚢 ship: (pre-deploy quality gate)
```

---

## Available Modes

Once you've completed your first spec, explore other modes:

| Mode | Purpose | Example |
|------|---------|---------|
| `think` | Generate specs from ideas | `think: add dark mode` |
| `plan` | Break specs into tasks | `plan: .planning/specs/dark-mode/spec.md` |
| `build` | Execute task lists | `build: .planning/specs/dark-mode/tasks.md` |
| `review` | Code quality check | `review: code` |
| `verify` | Evidence-based validation | `verify: dark mode works` |
| `ship` | Pre-deploy quality gate | `ship:` |

---

## Troubleshooting

### "No such skill: dream-studio:core"
- Ensure plugin is installed: `claude code list`
- Re-link if needed: `claude code link <path-to-dream-studio>`

### "Empty state warnings" during setup
- Run setup wizard again: `/setup:wizard`
- This will hydrate the registry

### Spec generation seems slow
- First run takes longer (warming up context)
- Subsequent runs are faster
- Model usage: `think` mode uses Sonnet by default

---

## What You Just Did

✅ Installed dream-studio  
✅ Ran first-run setup  
✅ Generated your first spec from an idea  
✅ Learned the core workflow (think → plan → build)

**Total time**: < 2 minutes

---

## Next: Go Deeper

- Read the full docs: `docs/README.md`
- Explore quality modes: `debug:`, `polish:`, `harden:`, `secure:`
- Set up team collaboration: `docs/team-setup.md`
- Join the community: [GitHub Discussions](https://github.com/SeayInsights/dream-studio/discussions)

Happy building! 🚀
