# Dream Studio

[![PR Smoke](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/SeayInsights/dream-studio/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.12.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)

## What Dream Studio Is

Dream Studio is a **local-first AI orchestration** platform — not a plugin, not a workflow template library. An operating system that manages the relationship between developer intent and AI execution — providing persistent memory across sessions, enforcing quality standards natively, routing work to the right capability automatically, and accumulating intelligence across sessions and projects.

Dream Studio runs three layers in concert:

- **Capability layer** — skills, agents, and workflows that encode structured development practices
- **Infrastructure layer** — an event pipeline, spool system, SQLite authority database, and provisioner that wire AI sessions to persistent state
- **Intelligence layer** — a project spine with SDLC pipeline, design gates, and session memory that accumulates across every build

When you invoke a Dream Studio skill, you are not calling a function. You are engaging a system that knows your project, your history, your quality standards, and your current work order — and routes execution accordingly.

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
git clone https://github.com/SeayInsights/dream-studio ~/builds/dream-studio-clean
cd ~/builds/dream-studio-clean
```

### 2. Install dependencies
```powershell
py -m pip install -r requirements.txt
```

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

### 6. Run health check
```powershell
ds doctor
```

### 7. Register your first project
```powershell
ds project register --name "My Project"
ds project set-active <project_id>
ds project next <project_id>
ds work-order start <work_order_id>
```

---

## CLI Reference

### Project
| Command | Description |
|---------|-------------|
| `ds project register --name "Name"` | Register a new project |
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
| `ds spool status` | Show spool file status |
| `ds spool flush` | Flush spool events to SQLite |

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

### Doctor / Validate
| Command | Description |
|---------|-------------|
| `ds doctor` | Run read-only runtime health checks |
| `ds validate` | Validate installed runtime readiness |
| `ds version` | Show Dream Studio version |
| `ds status` | Show installed runtime status |

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

### Running ds doctor
```powershell
ds doctor
```

Reports: SQLite health, migration version, spool status, integration status, adapter router state.

### Personalizing from session history
```powershell
ds memory ingest-sessions
```

Dream Studio extracts error patterns, skill usage, architecture documents, and technology signals from your existing Claude Code session history in `~/.claude/projects/`. You will be asked for consent before anything is stored. Raw conversation content is never stored.

---

## Local development on Windows

On Windows, the spool ingestor installs a module-level console control handler that absorbs spurious SIGINT signals delivered during filesystem and SQLite operations. This is fully automatic and requires no setup. Real Ctrl+C is preserved (two signals within 1 second forward to the default handler). On Linux this code is inactive. CI on Linux is unaffected. See `backlog.md` for the investigation history.

---

## License and Publication Boundary

Licensed under **Apache-2.0**. See `LICENSE` for the full text.

Dream Studio maintains a Contract Atlas — a registry of integration boundaries, adapter surface contracts, and stability guarantees for each compiler/installer pair. Adapters that implement the Contract Atlas interface are covered by the Publication Boundary: canonical skill definitions, the packs.yaml schema, the SQLite schema, and the CLI public command surface are stable across minor versions. Private runtime state in `~/.dream-studio/` is not covered.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->
