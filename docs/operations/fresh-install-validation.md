# Fresh-machine install validation

This procedure validates that Dream Studio installs cleanly on a fresh machine.
Run on Windows 11 AND on Ubuntu 22.04 LTS (or equivalent). VMs preferred to ensure clean state.

## Prerequisites

- Fresh OS install (no prior Python, no prior Claude Code config)
- Git available
- Internet connectivity (for pip and Python install)

## Steps

### 1. Clone the repo

```bash
git clone https://github.com/SeayInsights/dream-studio-clean.git ~/builds/dream-studio-clean
cd ~/builds/dream-studio-clean
```

### 2. Run the install script

Windows:
```powershell
.\install.ps1
```

Linux/Mac:
```bash
bash install.sh
```

### 3. Verify DB health (DB authority plane)

```bash
py -m interfaces.cli.ds validate
```

Expected: `"ready": true`, `"schema_version"` matches `"latest_migration_version"`, `"module_profile_errors": []`.

A passing `ds validate` confirms the SQLite database is healthy and all migrations have been applied. It does NOT confirm that skills, agents, or hooks are installed.

### 4. Verify integration health (Claude Code integration plane)

```bash
py -m interfaces.cli.ds doctor
```

Expected: `"status": "pass"`, all skills installed and current, dispatcher hooks wired.

A passing `ds doctor` confirms the Claude Code integration layer is fully wired. It does NOT substitute for `ds validate` — both must pass.

**Both steps are required.** Do not mark a fresh install as passing unless both `ds validate` returns `"ready": true` and `ds doctor` returns `"status": "pass"`.

### 5. Register a test project

```bash
py -m interfaces.cli.ds project register --name "Test Project" --path .
```

Expected: project registered, `project_id` returned.

### 6. Verify exit codes

Every command in steps 3-5 should return exit code 0 on success.

## Pass criteria

- All steps complete without manual intervention beyond what is documented
- `ds validate` reports `"ready": true` (DB authority plane)
- `ds doctor` reports `"status": "pass"` (Claude Code integration plane; missing career pack skills are expected — that pack requires an external service)
- No tracebacks, `ImportError`, or `ModuleNotFoundError` at any step
- Exit codes are 0 for all successful commands

## If any step fails

1. Document the failure in `.planning/install-validation-failures.md`
2. File a GitHub issue
3. Do not mark Phase 18.1.13 complete until the procedure passes on both Windows and Linux

## Re-run requirement

This procedure must be re-run before any Phase 18.8 public release sign-off.

---

## Health checks

Dream Studio has two health-check planes. Run both when investigating any issue; run one when you know which plane the issue lives in.

### `ds validate` — DB authority plane
Checks the SQLite database is healthy: schema version matches latest migration, no pending migrations, no module profile errors. Run after:
- `ds migrate` (verify migrations applied)
- Manual DB changes
- Backup restore

Returns `ready: true` when the DB is at the current schema version with no profile errors.

### `ds doctor` — Claude Code integration plane
Checks the Claude Code integration is wired correctly: dispatcher hooks present, skills installed and current, agents deployed, routing triggers covered, installed version current. Run after:
- `ds integrate install claude_code --execute`
- Manual edits to `~/.claude/settings.json` or `CLAUDE.md`
- Upgrading Dream Studio
- Before starting a new session

Returns `status: pass` when the integration layer is fully wired and current.

These commands are independent. A passing `ds validate` does NOT mean the integration is wired; a passing `ds doctor` does NOT mean the DB schema is current. Use both for full coverage.
