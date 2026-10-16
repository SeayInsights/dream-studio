# Installation

## Requirements

- Python 3.12+
- Git
- Claude Code (for Claude Code integration)

## Quick Install

```bash
git clone https://github.com/SeayInsights/dream-studio ~/builds/dream-studio
cd ~/builds/dream-studio

# macOS / Linux
bash install.sh

# Windows (PowerShell)
.\install.ps1
```

The script installs the Python dependencies, then runs
`ds self-install --config-root <root> --execute`: it builds Dream Studio from the
committed checkout into `~/.dream-studio` as a versioned app, creates or migrates the
authority, and installs the Claude Code integration into `CLAUDE_CONFIG_DIR` (or
`~/.claude`). pip needs network access or a warm cache. Running it again upgrades.

## Manual Install

### 1. Install dependencies

```bash
py -m pip install -r requirements.txt
```

For reproducible installs with exact version pinning:
```bash
py -m pip install -r requirements.lock
```

### 2. Install Dream Studio into its home

```bash
py -m interfaces.cli.ds self-install --config-root ~/.claude --execute
```

This builds the committed state of the checkout (it refuses a dirty tree) into
`~/.dream-studio/app/<version>-<sha>/venv` and installs the Claude Code integration from
that app into each `--config-root`. pip fetches the pinned dependencies: the first run needs
network access or a warm pip cache. `--dry-run` in place of `--execute` prints every write first.

### 3. Put ds on PATH

Add `~/.dream-studio/bin` to PATH, ahead of any older `ds` launcher. `ds.cmd` (Windows) or
`ds` there runs the current app with `--home` pinned. An older `ds.cmd` in `~/.local/bin`
that ran a checkout against this home is rewritten by `self-install` to call it (the
previous file is kept in the install's backup directory); one pinned to another home is left alone.

### 4. Verify installation

```bash
ds validate   # DB health check
ds doctor     # Claude Code integration check
```

Both should return status `pass` / `ready: true`.

## Post-Install

Register your first project:
```bash
py -m interfaces.cli.ds project register --name "My Project"
```

Then run `ds project state` to see where the work stands. In Claude Code, `resume:`
or `what's next:` routes you there.

## Updating

```bash
git pull
py -m interfaces.cli.ds self-install --config-root ~/.claude --execute
ds doctor
```

`ds self-install --rollback --execute` returns to the previous app.

## Troubleshooting

- `ds doctor` reports stale skills → run `ds integrate install claude_code --config-root ~/.claude --execute` (the installed app), or `py -m interfaces.cli.ds self-install --config-root ~/.claude --execute`
- `ds validate` reports no authority in an installed home → restore it from a backup (`ds --home ~/.dream-studio restore <dir> --execute`); see docs/operations/troubleshooting.md. Never re-create it.
- Module not found errors from a checkout → run from the repo root directory, or use the installed `ds`

See `docs/setup/` for detailed configuration and hook setup.
