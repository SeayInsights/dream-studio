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

### 3. Verify DB health

```bash
py -m interfaces.cli.ds validate
```

Expected: `"ready": true`, `"schema_version"` matches `"latest_migration_version"`, `"module_profile_errors": []`.

### 4. Verify integration health

```bash
py -m interfaces.cli.ds doctor
```

Expected: all checks pass, no missing required skills.

### 5. Register a test project

```bash
py -m interfaces.cli.ds project register --name "Test Project" --path .
```

Expected: project registered, `project_id` returned.

### 6. Verify exit codes

Every command in steps 3-5 should return exit code 0 on success.

## Pass criteria

- All steps complete without manual intervention beyond what is documented
- `ds validate` reports `"ready": true`
- `ds doctor` reports all skills present (missing skills from the career pack are expected — that pack requires an external service)
- No tracebacks, `ImportError`, or `ModuleNotFoundError` at any step
- Exit codes are 0 for all successful commands

## If any step fails

1. Document the failure in `.planning/install-validation-failures.md`
2. File a GitHub issue
3. Do not mark Phase 18.1.13 complete until the procedure passes on both Windows and Linux

## Re-run requirement

This procedure must be re-run before any Phase 18.8 public release sign-off.

---

## ds validate vs ds doctor — when to use which

These two commands check different things and are both valuable:

| Command | What it checks | When to run |
|---------|---------------|-------------|
| `ds validate` | SQLite DB exists and is at the correct schema version; module profiles are valid | After DB migrations, to verify the database is healthy |
| `ds doctor` | Skills, agents, and hooks are correctly installed in Claude Code | After `integrate install`, to verify the integration is correct |

Run `ds validate` to diagnose database problems. Run `ds doctor` to diagnose missing skill or hook problems. A healthy install shows both passing.
