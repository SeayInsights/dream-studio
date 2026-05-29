# Dream Studio

[![PR Smoke](https://github.com/SeayInsights/dream-studio-clean/actions/workflows/ci.yml/badge.svg)](https://github.com/SeayInsights/dream-studio-clean/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-2026.5.17-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](pyproject.toml)

## What Dream Studio Is

Dream Studio is a **local-first AI orchestration** platform — not a plugin, not a workflow template library. An operating system that manages the relationship between developer intent and AI execution — providing persistent memory across sessions, enforcing quality standards natively, routing work to the right capability automatically, and accumulating intelligence across sessions and projects.

Dream Studio runs three layers in concert:

- **Capability layer** — skills, agents, and workflows that encode structured development practices
- **Infrastructure layer** — an event pipeline, spool system, SQLite authority database, and provisioner that wire AI sessions to persistent state
- **Intelligence layer** — a project spine with SDLC pipeline, design gates, and session memory that accumulates across every build

When you invoke a Dream Studio skill, you are not calling a function. You are engaging a system that knows your project, your history, your quality standards, and your current work order — and routes execution accordingly.

> **Architecture note (TA0b):** canonical_events is the single authoritative event store.
> execution_events is a projection rebuilt from canonical events. See docs/architecture/event-store.md.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      CAPABILITY LAYER                           │
│                                                                  │
│   Skills (ds-core, ds-quality, ds-security, ds-analyze, ...)   │
│   Agents (director, engineering, chief-of-staff, specialists)   │
│   Workflows (idea-to-pr, comprehensive-review, security-audit)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                          │
│                                                                  │
│   Event Pipeline   →   Spool (JSONL)   →   SQLite-backed authority  │
│   Hook Dispatcher  →   Telemetry API   →   Dashboard            │
│   Provisioner      →   Compiler        →   Installer            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     INTELLIGENCE LAYER                           │
│                                                                  │
│   Project Spine (milestones → work orders → tasks)              │
│   SDLC Pipeline (scope → design brief → build → gates → close)  │
│   Design Gates (post-build, anti-slop, CWV results)             │
│   Memory (gotchas, lessons, session harvest, tech signals)       │
│   ML Analytics (forecasting, pattern detection, recommendations) │
│   Org Intelligence (multi-repo graph, capability normalization)  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### One-line install (recommended)

After cloning the repo, run the install script for your platform:

**Mac/Linux:**
```bash
bash install.sh
```

**Windows (PowerShell):**
```powershell
.\install.ps1
```

The script checks for Python 3.12+, installs it if missing, runs the Dream Studio installer, and verifies with `ds doctor`.

### Manual install (if you have Python 3.12+)

### Prerequisites
- Python 3.12 — use the `py` launcher on Windows
- Claude Code or another supported AI tool
- jq (optional, used by some shell operations):
    Windows: `winget install jqlang.jq`
    Mac:     `brew install jq`
    Linux:   `apt-get install jq`

### 1. Clone the repository
```powershell
git clone https://github.com/SeayInsights/dream-studio-clean ~/builds/dream-studio-clean
cd ~/builds/dream-studio-clean
```

### 2. Install dependencies
```powershell
py -m pip install -r requirements.txt
```

> **Reproducible installs:** `requirements.lock` pins all transitive dependencies to the exact versions
> verified at release time. For strict reproducibility, use `pip install -r requirements.lock`.
> For patch-version flexibility, use `pip install -r requirements.txt`.

### 3. Bootstrap the runtime database
```powershell
py -m interfaces.cli.ds rehearsal-install --rehearsal-home "$env:USERPROFILE\.dream-studio"
```

### 4. Install the integration
```powershell
py -m interfaces.cli.ds integrate install claude_code --execute
```

This writes `~/.claude/CLAUDE.md`, `~/.claude/canonical/skills/ds-bootstrap/SKILL.md`, and hook entries to `~/.claude/settings.json`. It also writes a global `ds` launcher to `~/.dream-studio/bin/`.

### 5. Add ds to PATH (Windows)
```powershell
$env:PATH += ";$env:USERPROFILE\.dream-studio\bin"
```

To make permanent, add to your PowerShell profile (`notepad $PROFILE`):
```
$env:PATH += ";$env:USERPROFILE\.dream-studio\bin"
```

After adding to PATH, run `ds` from any directory.

### 6. Run health checks

```powershell
ds validate   # DB health: schema version, migrations, module profiles
ds doctor     # Integration health: skills, agents, hooks, routing
```

Both must pass before first use. See [Health checks](#health-checks) for when to run each.

### 7. Register your first project

The `--path` flag writes a `.dream-studio-project` marker for token attribution:

```powershell
ds project register --name "My Project" --path C:\path\to\your\project
ds project set-active <project_id>
ds project next <project_id>
ds work-order start <work_order_id>
```

### 8. Token attribution setup (optional but recommended)

Token attribution tracks which Claude Code tool calls belong to which project, work order,
and task. After registering a project, install the PostToolUse hook to start capturing data:

Add to `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "py C:\\Users\\<YOUR_USERNAME>\\builds\\dream-studio-clean\\runtime\\hooks\\core\\on-post-tool-use.py"
          }
        ]
      }
    ]
  }
}
```

Then set the active task before working:
```powershell
ds task set-active <task_id>
```

See [docs/setup/claude-code-hooks.md](docs/setup/claude-code-hooks.md) for full setup and troubleshooting.

---

## CLI Reference

### Project
| Command | Description |
|---------|-------------|
| `ds project register --name "Name" --path <dir>` | Register a new project and write marker |
| `ds project list` | List registered projects |
| `ds project set-active <id>` | Set the active project |
| `ds project status <id>` | Show milestone and work-order summary |
| `ds project next <id>` | Return the next open work order |
| `ds project deactivate <id>` | Deactivate a project |

### Work Order
| Command | Description |
|---------|-------------|
| `ds work-order start <id>` | Start a work order and write context.md |
| `ds work-order list` | List work orders |
| `ds work-order close <id>` | Close a work order (gate-checked) |
| `ds work-order task-done <wo_id> <task_id>` | Mark a task complete |
| `ds work-order tasks <id>` | List tasks for a work order |
| `ds work-order block <id> --reason "..."` | Block a work order |
| `ds work-order unblock <id>` | Unblock a work order |

### Milestone
| Command | Description |
|---------|-------------|
| `ds milestone list <project_id>` | List milestones for a project |
| `ds milestone close <id>` | Close a milestone |
| `ds milestone status <id>` | Show milestone detail and open gate checks |

### Design Brief
| Command | Description |
|---------|-------------|
| `ds design-brief show <project_id>` | Show project design brief |
| `ds design-brief create <project_id>` | Create a draft design brief |
| `ds design-brief lock <brief_id>` | Lock a design brief (human approval gate) |
| `ds design-brief update <id> --field X --value Y` | Update a field |

### Skill
| Command | Description |
|---------|-------------|
| `ds skill invoke ds-project:scope` | Invoke a skill |
| `ds skill list` | List available skills |

### Spool
| Command | Description |
|---------|-------------|
| `ds spool ingest` | Ingest pending spool events into SQLite |
| `ds spool archive` | Archive processed spool events |

### Integrate
| Command | Description |
|---------|-------------|
| `ds integrate detect` | Detect installed AI tools |
| `ds integrate status` | Integration health summary |
| `ds integrate install claude_code --execute` | Install Claude Code integration |
| `ds integrate install claude_code --dry-run` | Simulate install |
| `ds integrate doctor` | Full health report |

### Memory
| Command | Description |
|---------|-------------|
| `ds memory ingest-sessions` | Harvest intelligence from Claude Code session history |
| `ds memory ingest-sessions --dry-run` | Preview harvest counts without writing |

### Health checks
| Command | Plane | Description |
|---------|-------|-------------|
| `ds validate` | DB authority | Schema version, migrations, module profiles |
| `ds doctor` | Claude Code integration | Skills, agents, hooks, routing, version |
| `ds version` | — | Show Dream Studio version |
| `ds status` | — | Show installed runtime status |

---

## How a Build Works

```
scope → register → set-active → next → start → [build] → task-done (×N) → close → milestone close
```

1. **Scope** — run `ds skill invoke ds-project:scope` for a guided intake conversation. Dream Studio produces a machine-executable PRD from your answers.

2. **Register** — `ds project register --name "My Project"` creates the project record in SQLite. The PRD populates milestones, work orders, and tasks.

3. **Set active** — `ds project set-active <project_id>` marks this as the current project.

4. **Next** — `ds project next <project_id>` returns the first open work order.

5. **Start** — `ds work-order start <work_order_id>` writes `context.md` to `.planning/` with the module boundary, task list, gate requirements, and design brief.

6. **Build** — work against the context. Claude Code reads context.md and stays within the module boundary.

7. **Task done** — `ds work-order task-done <wo_id> <task_id>` marks each task complete and updates context.md.

8. **Close** — `ds work-order close <work_order_id>` checks post-build gates. If gates pass, the work order closes. If they fail, address the failures and retry.

9. **Milestone close** — when all work orders in a milestone are complete, `ds milestone close <milestone_id>` runs the milestone verification sequence.

---

## Directory Structure

Dream Studio uses three directories with distinct purposes:

```
~/builds/dream-studio-clean/    # SOURCE — repo you cloned
  canonical/                    # Skill and workflow definitions
  core/                         # Event store, config, shared intelligence
  integrations/                 # Compilers and installers per AI tool
  interfaces/                   # CLI and API surface
  spool/                        # Event spool (writes events to disk)
  hooks/                        # Claude Code hook scripts
  docs/                         # Schema docs, authoring guides, contracts
  adapter-projections/          # Per-tool CLAUDE.md/AGENTS.md templates

~/.dream-studio/                # RUNTIME — local state, never committed
  state/studio.db               # SQLite authority database
  bin/ds.cmd (or ds)            # Global ds launcher
  backups/                      # Install backups
  integrations/                 # Integration manifests

~/.claude/                      # CLAUDE CODE CONFIG — managed by installer
  CLAUDE.md                     # Enforcement block + routing table (auto-generated)
  canonical/skills/ds-bootstrap/SKILL.md  # Bootstrap skill context
  settings.json                 # Hook entries (added by installer)
```

---

## Skill Packs

Each pack is a single skill with multiple modes. Invoke via `Skill(skill="ds-<pack>", args="<mode>")`.

| Skill ID | Pack | Description |
|----------|------|-------------|
| `ds-core` | Build lifecycle | think, plan, build, review, verify, ship, handoff, recap, explain |
| `ds-quality` | Code quality | debug, polish, harden, pr-security-scan, structure-audit, learn, coach, audit |
| `ds-career` | Career pipeline | ops, scan, evaluate, apply, track, pdf |
| `ds-analyze` | Analysis engine | multi, domain-re, repo, intelligence |
| `ds-domains` | Domain builders | game-dev, saas-build, mcp-build, dashboard-dev, client-work, design |
| `ds-security` | Security analysis | scan, dast, binary-scan, mitigate, comply, netcompat, dashboard, review |
| `ds-project` | Project lifecycle | scope |
| `ds-domains-website` | Website builder | discover, direction, page, prototype, animate, brand, cip, critique, deck |
| `ds-domains-fullstack` | Fullstack builder | frontend, backend, integrate, secure |
| `ds-setup` | Platform setup | wizard, status, jit |
| `ds-workflow` | Workflow orchestration | (meta pack — hook infrastructure) |

**Note:** `ds-domains-website` and `ds-domains-fullstack` are top-level packs, not sub-modes of `ds-domains`. Invoke them directly.

---

## Adding a New AI Tool Target

Dream Studio supports multiple AI tool adapter surfaces through a compiler/installer/emitter pattern. To add support for a new tool:

1. **Compiler** — create `integrations/compiler/<tool>.py` that reads `canonical/` and produces a pack dict with files and settings
2. **Installer** — create `integrations/installer/<tool>.py` implementing `InstallerBase` with `plan()` and `install()` methods
3. **Emitter** — create a spool emitter that writes events from the tool's session format into the Dream Studio event format

See `integrations/compiler/claude_code.py` and `integrations/installer/claude_code.py` as the reference implementation.

---

## Development and Testing

### Running tests (batched — never run the full suite at once)
```powershell
# Single test file
py -m pytest tests/unit/test_work_order_executor.py -v

# WS 8c test battery
py -m pytest tests/unit/test_global_ds_entry.py tests/unit/test_compiler_routing.py tests/unit/test_stale_references.py -v
py -m pytest tests/unit/canonical/test_documentation.py tests/unit/test_session_harvester.py -v
```

### One accepted baseline failure
The test suite has one pre-existing expected failure. All other tests must be green.

### Adding a new skill
1. Create `canonical/skills/<pack>/modes/<mode>/SKILL.md`
2. Add the mode to `packs.yaml` under the appropriate pack's `modes` list
3. The compiler picks up the change automatically — no manual routing table edits required

### Health checks

Dream Studio has two health-check planes. Run both when investigating any issue; run one when you know which plane the issue lives in.

#### `ds validate` — DB authority plane
Checks the SQLite database is healthy: schema version matches latest migration, no pending migrations, no module profile errors. Run after:
- `ds migrate` (verify migrations applied)
- Manual DB changes or backup restore

Returns `ready: true` when the DB is at the current schema version with no profile errors.

#### `ds doctor` — Claude Code integration plane
Checks the Claude Code integration is wired correctly: dispatcher hooks present, skills installed and current, agents deployed, routing triggers covered, installed version current. Run after:
- `ds integrate install claude_code --execute`
- Manual edits to `~/.claude/settings.json` or `CLAUDE.md`
- Upgrading Dream Studio or before starting a new session

Returns `status: pass` when the integration layer is fully wired and current.

These commands are independent. A passing `ds validate` does NOT mean the integration is wired; a passing `ds doctor` does NOT mean the DB schema is current. Use both for full coverage.

```powershell
ds validate
ds doctor
```

### Personalizing from session history
```powershell
ds memory ingest-sessions
```

Dream Studio extracts error patterns, skill usage, architecture documents, and technology signals from your existing Claude Code session history in `~/.claude/projects/`. You will be asked for consent before anything is stored. Raw conversation content is never stored.

---

## Platform detection

Dream Studio detects the host OS, shell, Python version, and terminal at install time and persists the profile at `~/.dream-studio/state/platform.json`. This lets the product surface shell-correct commands in error messages and diagnostic output. To refresh the profile (e.g. after switching shells), run `ds doctor`.

---

## CI/CD

Pull requests run a multi-OS smoke gate (Linux, macOS, Windows) that checks:

- **Format** (`black --check`)
- **Lint** (flake8 baseline)
- **Contract docs drift** — detects domain doc staleness on impacted files
- **Contract Atlas lifecycle** — verifies contract Atlas publication state
- **Dependency scan** (`pip-audit`) — flags known CVEs in requirements

The full test suite (with coverage gate) runs via the **Full CI** workflow on every push to `main` and can be triggered manually from GitHub Actions.

Release candidates are validated via the **Release Validation** workflow before any tag is created.

---

## Local development on Windows

On Windows, the spool ingestor installs a module-level console control handler that absorbs spurious SIGINT signals delivered during filesystem and SQLite operations. This is fully automatic and requires no setup. Real Ctrl+C is preserved (two signals within 1 second forward to the default handler). On Linux this code is inactive. The CI matrix includes Windows runners so cross-platform regressions are caught automatically. See `backlog.md` for the investigation history.

---

## License and Publication Boundary

Licensed under **Apache-2.0**. See `LICENSE` for the full text.

Dream Studio maintains a Contract Atlas — a registry of integration boundaries, adapter surface contracts, and stability guarantees for each compiler/installer pair. Adapters that implement the Contract Atlas interface are covered by the Publication Boundary: canonical skill definitions, the packs.yaml schema, the SQLite schema, and the CLI public command surface are stable across minor versions. Private runtime state in `~/.dream-studio/` is not covered.

See [INSTALL.md](INSTALL.md) for a standalone installation reference.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->
<!-- Last reviewed 2026-05-27 — Phase 18.1.18: INSTALL.md added. Node.js 24 CI opt-in applied. -->

<!-- Last reviewed 2026-05-27 — fix/ci-gate-db-path-collision: ci_gate.py _isolated_test_env() now uses separate mkdtemp calls for HOME and DREAM_STUDIO_DB_PATH so conftest.guard_real_homedir's _db_redirected check returns True and the CI abort guard does not fire on test DB writes. No release gate policy change; this is a CI isolation bug fix only. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: 37 Linux CI failures repaired. Changes span: canonical_events table isolation, migration 078 (memory_entries), adapter projection file generation (7 new), publication readiness scan exclusions, cloud backup test mock, TA6 milestone direct SQL, context threshold hook _emit_harvest, ML routes sqlite3 import cleanup. No README policy change required. -->

<!-- Last reviewed 2026-05-29 — Phase 18.4.6 migration-risk gate: flake8-baseline.txt stale-entry cleanup + pre-push migration-risk gate added. The migration-risk gate is described in docs/operations/lightweight-github-ci-strategy.md. No README content change required; gate is an internal pre-push enforcement mechanism. -->
