# Contributing to dream-studio

## Branch Naming

| Prefix | When to use |
|--------|-------------|
| `feat/` | New capabilities |
| `fix/` | Bug fixes |
| `chore/` | Maintenance, docs, deps |

## Commit Message Format

```
type: short description
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

Examples:
```
feat: add /harden skill audit phase
fix: correct UTC timestamp in on-pulse hook
chore: update requirements-dev.txt with freezegun
```

## Pull Request Checklist

- [ ] Tests pass (`make test` or `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 test`)
- [ ] Lint clean (`make lint` or `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 lint`)
- [ ] CHANGELOG updated (add entry under `[Unreleased]`)
- [ ] PR uses squash merge

## Code Style

Run before every PR:

```bash
make fmt    # auto-format with black
make lint   # check black + flake8
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 fmt
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 lint
```

Line length: 100. Config in `pyproject.toml`.

## Running Tests

```bash
make test
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 test
```

Requires Python 3.12 and dev dependencies:

```bash
make install-dev
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 install-dev
```

## Security Issues

Do **not** open GitHub Issues for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the responsible disclosure process.
