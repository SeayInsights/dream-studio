# Cursor Setup — dream-studio Conventions

This guide shows how to configure Cursor to use dream-studio workflow conventions.

## What is .cursorrules?

`.cursorrules` is a project-level configuration file that provides Cursor AI with context-specific instructions for your codebase. It helps Cursor understand your team's conventions, workflow patterns, and quality standards.

## Installation

### Option 1: Copy to Your Project (Recommended)

1. Download the `.cursorrules` file from `.marketplace/adapters/cursor-rules/.cursorrules`
2. Copy it to the root of your project:
   ```bash
   cp .marketplace/adapters/cursor-rules/.cursorrules /path/to/your/project/.cursorrules
   ```
3. Commit the file to your repository:
   ```bash
   git add .cursorrules
   git commit -m "Add dream-studio Cursor conventions"
   ```

### Option 2: Symlink (For Multiple Projects)

If you work on multiple projects and want consistent rules:

1. Keep the `.cursorrules` file in a central location
2. Symlink it to each project:
   ```bash
   ln -s /path/to/dream-studio/.marketplace/adapters/cursor-rules/.cursorrules /path/to/your/project/.cursorrules
   ```

## What's Included

The `.cursorrules` file provides Cursor with:

- **Skill-based workflow:** Think → Plan → Build → Review → Verify → Ship
- **Trigger keywords:** Recognize intent from your prompts (e.g., "think:", "plan:", "build:")
- **Git workflow conventions:** Branch naming, PR size limits, commit standards
- **Issue → PR workflow:** Systematic approach to feature development
- **Code quality patterns:** Debug, polish, harden, security review
- **Testing guidelines:** When and how to verify changes
- **Deploy safety:** CI/CD first, no manual deploys

## Usage

Once installed, Cursor will automatically apply these conventions when you interact with it:

### Example 1: Feature Development
```
You: "think: Add user authentication to the API"
```
Cursor will:
- Clarify requirements and constraints
- Explore 2-3 implementation approaches with trade-offs
- Write a spec with user stories and success criteria
- Ask for approval before proceeding to implementation

### Example 2: Bug Fix
```
You: "debug: Login button doesn't work on mobile"
```
Cursor will:
- Trace the render pipeline and event handlers
- Identify the root cause
- Create a GitHub issue documenting the bug
- Propose a fix following the Issue → PR workflow
- Verify the fix resolves the issue

### Example 3: Code Review
```
You: "review: Check this PR for quality issues"
```
Cursor will check:
- Code quality (duplication, complexity, readability)
- Security (input validation, auth, secrets)
- Architecture (consistency with patterns)
- Edge cases (error handling)
- Documentation (README, comments)

## Customization

You can customize the `.cursorrules` file for your project:

1. Edit the file directly in your project root
2. Add project-specific conventions
3. Remove sections that don't apply to your workflow
4. Commit changes so your team benefits

### Example Customization

Add project-specific conventions:

```markdown
## Project-Specific Rules

### API Endpoints
- All API routes must include rate limiting
- Use `/api/v1/` prefix for all endpoints
- Document with OpenAPI spec in `/docs/api.yml`

### Database
- All migrations must be reversible
- Use Prisma schema in `/prisma/schema.prisma`
- Never commit `.env` files
```

## Troubleshooting

### Cursor isn't following the rules

1. Verify the file is named exactly `.cursorrules` (note the leading dot)
2. Ensure it's in the project root directory (same level as `.git/`)
3. Restart Cursor to reload the configuration
4. Check file permissions (must be readable)

### Rules conflict with my workflow

The `.cursorrules` file is a guideline, not a strict requirement. You can:
- Edit the file to match your workflow
- Remove sections that don't apply
- Override specific rules in your prompts (e.g., "ignore cursorrules for this task")

### Want to disable temporarily

Rename the file to disable:
```bash
mv .cursorrules .cursorrules.disabled
```

Re-enable:
```bash
mv .cursorrules.disabled .cursorrules
```

## Benefits

Using dream-studio conventions with Cursor provides:

- **Consistency:** Everyone on your team follows the same workflow
- **Quality:** Built-in quality gates reduce bugs
- **Efficiency:** Clear patterns reduce decision fatigue
- **Collaboration:** Standardized PRs and commits improve code reviews
- **Safety:** Deploy safety rules prevent production incidents

## Next Steps

1. Install `.cursorrules` in your project
2. Try a few prompts using trigger keywords (`think:`, `plan:`, `build:`)
3. Observe how Cursor adapts to the workflow
4. Customize the rules to match your team's needs
5. Share with your team and commit to your repository

## Resources

- [Cursor documentation](https://cursor.sh/docs)
- [dream-studio repository](https://github.com/yourusername/dream-studio)
- [.cursorrules examples](https://github.com/topics/cursorrules)
