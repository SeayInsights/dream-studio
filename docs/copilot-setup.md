# GitHub Copilot Setup — dream-studio Conventions

This guide shows how to configure GitHub Copilot to use dream-studio workflow conventions.

## What are Copilot Instructions?

Copilot Instructions are custom guidelines that help GitHub Copilot understand your team's coding standards, workflow patterns, and quality requirements. They work at the organization, repository, or user level.

## Installation

### Option 1: Repository-Level (Recommended for Teams)

Repository-level instructions apply to all Copilot users working in your project.

1. Create the `.github` directory in your project root (if it doesn't exist):
   ```bash
   mkdir -p .github
   ```

2. Copy the instructions file:
   ```bash
   cp .marketplace/adapters/copilot-instructions/instructions.md .github/copilot-instructions.md
   ```

3. Commit to your repository:
   ```bash
   git add .github/copilot-instructions.md
   git commit -m "Add dream-studio Copilot conventions"
   git push
   ```

4. GitHub Copilot will automatically load these instructions for anyone working in the repository.

### Option 2: User-Level (Personal Preference)

User-level instructions apply to all your projects. Use this if you want consistent conventions across multiple repositories.

1. Go to your GitHub account settings:
   - Visit https://github.com/settings/copilot
   - Or navigate to: Settings → Copilot → Instructions

2. Paste the content from `.marketplace/adapters/copilot-instructions/instructions.md` into the "Instructions for GitHub Copilot" text box

3. Click "Save"

### Option 3: Organization-Level (Enterprise)

Organization admins can set default instructions for all repositories:

1. Go to your organization settings
2. Navigate to Copilot → Instructions
3. Paste the instructions content
4. Save changes

## What's Included

The Copilot instructions provide GitHub Copilot with:

- **Core workflow:** Think → Plan → Build → Review → Verify → Ship lifecycle
- **Trigger patterns:** Recognize your intent from code comments and prompts
- **Git conventions:** Branch naming, commit standards, PR workflow
- **Code quality patterns:** Debug workflow, UI polish, security review, hardening
- **Testing guidelines:** Verification checklist before pushing changes
- **Deploy safety:** CI/CD first approach, no manual deploys
- **Model usage guidance:** When to use different model capabilities

## Usage

Once installed, GitHub Copilot will follow these conventions when providing suggestions:

### Example 1: Starting a New Feature

Add a comment in your code:
```javascript
// think: Add user authentication with email and password
```

Copilot will suggest code that:
- Validates email format
- Hashes passwords securely (bcrypt/argon2)
- Includes error handling for invalid credentials
- Follows your project's authentication patterns

### Example 2: Creating a Plan

In a markdown file or comment:
```markdown
## Plan: Add user authentication

<!-- plan: Break down authentication feature into atomic tasks -->
```

Copilot will suggest a task breakdown like:
```markdown
### Plan: Add user authentication

**Tasks:**
- T001: Add user schema with email, password_hash, created_at
- T002: Create registration endpoint with validation
- T003: Add password hashing utility (bcrypt)
- T004: Create login endpoint with JWT generation
- T005: Add authentication middleware
- T006: Write tests for registration and login
```

### Example 3: Code Review Comments

When reviewing code, Copilot will check for:
```javascript
// review: Check this authentication code

function login(email, password) {
  // Copilot will flag:
  // - Missing input validation
  // - Password stored in plain text
  // - No rate limiting
  // - SQL injection risk
  // - Missing error handling
}
```

### Example 4: Security Review

Add a comment:
```javascript
// secure: Review this API endpoint for vulnerabilities
```

Copilot will suggest improvements for:
- Input validation (XSS, SQL injection)
- Authentication/authorization checks
- Rate limiting
- HTTPS enforcement
- Secret management

## Customization

### Repository-Specific Additions

Add project-specific conventions to `.github/copilot-instructions.md`:

```markdown
## Project-Specific Conventions

### Technology Stack
- Framework: Next.js 14 (App Router)
- Database: PostgreSQL with Prisma
- Auth: NextAuth.js v5
- Styling: Tailwind CSS
- Testing: Vitest + Playwright

### Code Style
- Use TypeScript strict mode
- Prefer server components over client components
- Keep components under 200 lines
- Use Zod for runtime validation
- Document complex business logic with comments

### File Organization
```
/app         - Next.js app router pages
/components  - React components
/lib         - Utility functions
/prisma      - Database schema and migrations
/tests       - Test files
```

### API Conventions
- All routes under `/api/v1/`
- Use route handlers for API endpoints
- Validate input with Zod schemas
- Return consistent error responses: `{ error: "message", code: "ERROR_CODE" }`
```

### Combining with Team Conventions

If your team has existing conventions, merge them with dream-studio patterns:

```markdown
# Team + dream-studio Conventions

<!-- Include dream-studio workflow -->
[paste dream-studio content]

## Our Team Additions

### PR Review Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No console.log statements
- [ ] Accessibility checked (ARIA labels, keyboard nav)
- [ ] Mobile responsive verified

### Database Changes
- Always create migration files
- Never modify existing migrations
- Include rollback logic
- Test migrations on staging first
```

## Troubleshooting

### Copilot isn't using the instructions

**For repository-level:**
1. Verify file is at `.github/copilot-instructions.md`
2. Ensure file is committed and pushed to GitHub
3. Wait a few minutes for GitHub to index the file
4. Reload your IDE (VS Code, JetBrains, etc.)

**For user-level:**
1. Check https://github.com/settings/copilot to verify instructions are saved
2. Restart your IDE
3. Try opening a new file to trigger fresh suggestions

### Instructions are too long

GitHub Copilot has context limits. If instructions exceed ~8000 tokens:
1. Focus on the most important conventions
2. Remove verbose examples
3. Use concise bullet points instead of paragraphs
4. Link to external documentation for details

### Want different rules per project

Use repository-level instructions for project-specific rules and user-level for personal preferences. Repository-level takes precedence and merges with user-level.

### Need to disable temporarily

**Repository-level:**
```bash
mv .github/copilot-instructions.md .github/copilot-instructions.md.disabled
```

**User-level:**
Go to https://github.com/settings/copilot and clear the instructions field.

## Benefits

Using dream-studio conventions with GitHub Copilot:

- **Higher quality suggestions:** Copilot understands your workflow and quality standards
- **Faster development:** Less time explaining context in prompts
- **Consistent code:** Everyone on the team gets similar suggestions
- **Better security:** Built-in security review patterns
- **Reduced bugs:** Quality gates prevent common mistakes

## Integration with VS Code

GitHub Copilot Chat in VS Code supports custom instructions:

1. Open Copilot Chat (`Ctrl+Shift+I` or `Cmd+Shift+I`)
2. Use trigger keywords in your questions:
   - "think: how should we implement caching?"
   - "plan: break down this feature"
   - "debug: why isn't this working?"
   - "review: check this code for issues"

Copilot will respond following the dream-studio workflow patterns.

## Team Adoption

### Rollout Strategy

1. **Pilot:** One team member tests the instructions for a week
2. **Review:** Gather feedback and refine conventions
3. **Announce:** Share benefits and setup instructions with team
4. **Deploy:** Commit `.github/copilot-instructions.md` to repository
5. **Monitor:** Collect feedback and iterate

### Training

Share these usage examples with your team:

```javascript
// Before (generic prompt)
// add validation

// After (using conventions)
// secure: add input validation for XSS and SQL injection
```

The second prompt triggers Copilot to:
- Escape HTML entities (prevent XSS)
- Use parameterized queries (prevent SQL injection)
- Validate data types and ranges
- Return meaningful error messages

## Next Steps

1. Choose installation method (repository, user, or organization level)
2. Install the instructions
3. Try a few code suggestions using trigger keywords
4. Customize with project-specific conventions
5. Share with your team

## Resources

- [GitHub Copilot documentation](https://docs.github.com/en/copilot)
- [Copilot Instructions guide](https://docs.github.com/en/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot)
- [dream-studio repository](https://github.com/yourusername/dream-studio)
- [VS Code GitHub Copilot extension](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot)
