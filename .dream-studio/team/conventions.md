# Team Coding Conventions

Team-wide coding standards, style guides, and best practices. These conventions are enforced across all dream-studio projects for this team.

## Git Workflow

### Branch Naming
- `feat/<topic>` — new features
- `fix/<topic>` — bug fixes
- `chore/<topic>` — tooling, deps, refactors
- `docs/<topic>` — documentation only

Keep branch names short and descriptive (2-4 words max).

### Commit Messages
- Follow Conventional Commits: `type: description`
- Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`
- First line under 72 characters
- Explain **why**, not what (the diff shows what)
- Reference issues when applicable: `fix: header overflow (fixes #42)`

### Pull Requests
- PR title: short (under 70 characters), descriptive
- PR body: 
  - Summary (1-3 bullet points)
  - Test plan (bulleted checklist)
  - Issue reference if applicable: `Fixes #42`
- Max 120 lines changed per PR (check with `git diff main...HEAD --stat`)
- All CI checks must pass before merge
- Squash-merge for feature branches, regular merge for release branches

## Code Style

### Python
- Black formatter (line length 100)
- Import order: stdlib → third-party → local
- Type hints required for public functions
- Docstrings for modules, classes, and public functions (Google style)

### JavaScript/TypeScript
- Prettier (default config)
- ESLint (Airbnb base)
- Prefer `const` over `let`, avoid `var`
- Named exports over default exports

### General
- Max function length: 50 lines
- Max file length: 500 lines (split into modules if larger)
- Avoid deep nesting (max 3 levels)
- Extract magic numbers to named constants

## Testing

- Unit tests for all business logic
- Integration tests for API endpoints
- E2E tests for critical user paths
- Minimum 80% coverage for new code
- Test file naming: `test_<module>.py` or `<module>.test.ts`

## Documentation

- README.md at repo root (overview + quick start)
- ARCHITECTURE.md for system design (if complex)
- Inline comments for **why**, not what
- Update docs in the same PR as code changes

## Security

- Never commit secrets (.env files gitignored)
- Use environment variables for config
- Dependency updates reviewed weekly
- Security scan on every PR (automated via CI)
