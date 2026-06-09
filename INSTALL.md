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

The script installs Python dependencies, bootstraps the runtime database, and installs the Claude Code integration.

## Manual Install

### 1. Install dependencies

```bash
py -m pip install -r requirements.txt
```

For reproducible installs with exact version pinning:
```bash
py -m pip install -r requirements.lock
```

### 2. Bootstrap the runtime database

```bash
py -m interfaces.cli.ds rehearsal-install --rehearsal-home ~/.dream-studio
```

Windows:
```powershell
py -m interfaces.cli.ds rehearsal-install --rehearsal-home "$env:USERPROFILE\.dream-studio"
```

### 3. Install the Claude Code integration

```bash
py -m interfaces.cli.ds integrate install claude_code --execute
```

### 4. Verify installation

```bash
py -m interfaces.cli.ds validate   # DB health check
py -m interfaces.cli.ds doctor     # Claude Code integration check
```

Both should return status `pass` / `ready: true`.

## Post-Install

Register your first project:
```bash
py -m interfaces.cli.ds project register --name "My Project"
```

Then invoke `ds-project:resume` in Claude Code to begin.

## Updating

```bash
git pull
py -m interfaces.cli.ds integrate install claude_code --execute
py -m interfaces.cli.ds doctor
```

## Troubleshooting

- `ds doctor` reports stale skills → run `py -m interfaces.cli.ds integrate install claude_code --execute`
- `ds validate` fails → check `~/.dream-studio/state/studio.db` exists; re-run rehearsal-install
- Module not found errors → ensure you're running from the repo root directory

See `docs/setup/` for detailed configuration and hook setup.
