# Contributing to {{project_name}}

## Branch Naming

| Prefix | When to use |
|--------|-------------|
| `feature/` | New capabilities |
| `fix/` | Bug fixes |
| `hotfix/` | Urgent production fixes |

## Commit Message Format

```
type: short description
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

## Pull Request Checklist

- [ ] Tests pass (`make test`)
- [ ] Lint clean (`make lint`)
- [ ] CHANGELOG updated
- [ ] PR uses squash merge

## Running Tests

```bash
make install-dev
make test
```

## Security Issues

See [SECURITY.md](SECURITY.md).
