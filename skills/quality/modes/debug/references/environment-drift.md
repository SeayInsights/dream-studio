---
title: Environment Drift
description: Resolving issues caused by configuration mismatch, dependency conflicts, and environment inconsistencies
---

# Environment Drift

"Works on my machine" bugs caused by environment-specific differences.

## Environment Variables

### Missing Variables
```bash
# Trace all env vars referenced in code
grep -r "process.env\." src/
grep -r "os.environ\[" src/
grep -r "\$env:" src/

# Check if var exists
echo $MY_VAR          # bash
echo $env:MY_VAR      # PowerShell
```

### Wrong Values
```bash
# Compare local vs CI
printenv | sort > local-env.txt
# (in CI) printenv | sort > ci-env.txt
diff local-env.txt ci-env.txt

# Check specific vars
echo "NODE_ENV: $NODE_ENV"
echo "PATH: $PATH"
```

### Common Gotchas
- `.env` files not loaded (missing dotenv package)
- `.env.local` gitignored (not in CI)
- Variable expansion differences (bash vs PowerShell)
- Case sensitivity on Linux vs Windows

## OS Differences

### File Paths
```bash
# Windows uses backslashes, Unix uses forward slashes
# WRONG: hardcoded separators
filePath = "src\\components\\Button.tsx"

# RIGHT: use path library
import path from 'path'
filePath = path.join('src', 'components', 'Button.tsx')
```

### Line Endings
```bash
# Check line endings
file myfile.txt              # Unix
Get-Content -Raw file.txt | Format-Hex  # PowerShell (0D 0A = CRLF, 0A = LF)

# Git handling
git config core.autocrlf     # true on Windows, input on Unix
```

### Case Sensitivity
```bash
# Windows: case-insensitive, Linux: case-sensitive
# File exists as "Button.tsx" but imported as "button.tsx" → works on Windows, fails on Linux

# Find case mismatches
find . -name "*.ts*" | sort | uniq -d
```

### Permissions
```bash
# Linux/Mac require execute permissions
chmod +x scripts/build.sh

# Check permissions
ls -la scripts/

# Windows: no execute bit (WSL may differ)
```

## Version Mismatches

### Language Versions
```bash
# Check installed versions
node --version
python --version
py --version     # Windows launcher

# CI vs local
# Local: Python 3.14
# CI: Python 3.12
# → syntax/library differences

# Lock versions
echo "python-version: '3.12'" >> .github/workflows/ci.yml
```

### Dependency Versions
```bash
# Compare lockfiles
diff package-lock.json <(git show origin/main:package-lock.json)
diff poetry.lock <(git show origin/main:poetry.lock)

# Check for range specifiers allowing drift
# BAD: "^2.0.0" (allows 2.x.x)
# GOOD: "2.0.0" (exact version)

# Audit installed vs declared
npm list --depth=0
pip list
```

### Build Tool Versions
```bash
# Check toolchain
npm --version
npx tsc --version
npx vite --version

# CI may use different npm version
# Local: npm 10.x
# CI: npm 9.x
```

## Path Differences

### Absolute vs Relative
```bash
# Trace all absolute paths in code
grep -r "C:\\\\Users" .
grep -r "/home/" .
grep -r "/Users/" .

# Check current working directory assumptions
pwd
echo $PWD
echo (Get-Location)
```

### Build Artifact Paths
```bash
# Output directory differences
# Local: dist/
# CI: build/
# Vite: check vite.config.ts outDir

# Temp directory
# Windows: C:\Users\<user>\AppData\Local\Temp
# Linux: /tmp
# Mac: /var/folders/...
```

### Module Resolution
```bash
# TypeScript path aliases
# tsconfig.json: "@/*": ["./src/*"]
# Works in dev, breaks in prod if not compiled correctly

# Check resolution
npx tsc --traceResolution | grep "myModule"
```

## Debugging Workflow

### 1. Reproduce Locally
```bash
# Run in CI-like environment
docker run -it node:18 bash
# Install dependencies, run build

# Use act to run GitHub Actions locally
act -j build
```

### 2. Capture Environment State
```bash
# Dump all environment info
echo "OS: $(uname -s)"
echo "Node: $(node --version)"
echo "PWD: $(pwd)"
printenv | sort > env-snapshot.txt
```

### 3. Compare Environments
```bash
# Side-by-side comparison
diff local-env.txt ci-env.txt
diff local-versions.txt ci-versions.txt
```

### 4. Isolate Variable
```bash
# Test one difference at a time
# Example: if CI uses NODE_ENV=production
NODE_ENV=production npm run build
```

### 5. Fix Root Cause
- Add missing env vars to CI config
- Lock dependency versions
- Use cross-platform path libraries
- Document required OS/versions in README

## Prevention

### CI Configuration
```yaml
# .github/workflows/ci.yml
env:
  NODE_ENV: production
  DATABASE_URL: ${{ secrets.DATABASE_URL }}

runs-on: ubuntu-latest
steps:
  - uses: actions/setup-node@v3
    with:
      node-version: '18.17.0'  # exact version
```

### Local Setup Documentation
```markdown
# README.md
## Prerequisites
- Node.js 18.17.0 (use nvm: `nvm install 18.17.0`)
- Python 3.12 (not 3.14 due to library incompatibility)
- Copy `.env.example` to `.env.local`
```

### Cross-Platform Testing
```bash
# Test matrix in CI
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    node-version: [18, 20]
```

## Common Patterns

### "Import not found" (case mismatch)
```bash
# Find mismatched imports
# Look for import "./Button" when file is "button.tsx"
```

### "Module not found" (path separator)
```bash
# Check for hardcoded backslashes in imports
grep -r "import.*\\\\" src/
```

### "Permission denied" (missing chmod)
```bash
# Add to git
git update-index --chmod=+x scripts/build.sh
```

### "Env var undefined" (missing dotenv)
```bash
# Check if .env loaded
console.log('ENV CHECK:', process.env.MY_VAR)

# Load explicitly
import 'dotenv/config'
```

## Tools

- **env-cmd**: Run with specific env file (`env-cmd -f .env.ci npm test`)
- **cross-env**: Set env vars cross-platform (`cross-env NODE_ENV=prod npm build`)
- **Docker**: Reproduce exact CI environment locally
- **act**: Run GitHub Actions locally
- **nvm/pyenv**: Version management for Node/Python
