# Dream Studio CLI Reference

The `ds` command is the operator surface over the SQLite authority. Every command reads or
mutates authority state and prints the returned record. This reference is moved out of the
README so the README can stay focused on what the substrate guarantees; it is the complete
command surface.

## Project
| Command | Description |
|---------|-------------|
| `ds project register --name "Name" --path <dir>` | Register a new project and write marker |
| `ds project list` | List registered projects |
| `ds project set-active <id>` | Set the active project |
| `ds project status <id>` | Show milestone and work-order summary |
| `ds project next <id>` | Return the next open work order |
| `ds project deactivate <id>` | Deactivate a project |

## Work Order
| Command | Description |
|---------|-------------|
| `ds work-order start <id>` | Start a work order and write context.md |
| `ds work-order list` | List work orders |
| `ds work-order close <id>` | Close a work order (gate-checked) |
| `ds work-order task-done <wo_id> <task_id>` | Mark a task complete |
| `ds work-order tasks <id>` | List tasks for a work order |
| `ds work-order block <id> --reason "..."` | Block a work order |
| `ds work-order unblock <id>` | Unblock a work order |
| `ds work-order affirm-impact <id> [--auth\|--contract\|--migration\|--changelog\|--note]` | Record the change-impact affirmation the close gate requires |

## Milestone
| Command | Description |
|---------|-------------|
| `ds milestone list <project_id>` | List milestones for a project |
| `ds milestone close <id>` | Close a milestone |
| `ds milestone status <id>` | Show milestone detail and open gate checks |

## Design Brief
| Command | Description |
|---------|-------------|
| `ds design-brief show <project_id>` | Show project design brief |
| `ds design-brief create <project_id>` | Create a draft design brief |
| `ds design-brief lock <brief_id>` | Lock a design brief (human approval gate) |
| `ds design-brief update <id> --field X --value Y` | Update a field |

## Skill
| Command | Description |
|---------|-------------|
| `ds skill invoke ds-project:scope` | Invoke a skill |
| `ds skill list` | List available skills |

## Spool
| Command | Description |
|---------|-------------|
| `ds spool ingest` | Ingest pending spool events into SQLite |
| `ds spool archive` | Archive processed spool events |

## Integrate
| Command | Description |
|---------|-------------|
| `ds integrate detect` | Detect installed AI tools |
| `ds integrate status` | Integration health summary |
| `ds integrate install claude_code --execute` | Install Claude Code integration |
| `ds integrate install claude_code --dry-run` | Simulate install |
| `ds integrate doctor` | Full health report |

## Memory
| Command | Description |
|---------|-------------|
| `ds memory ingest-sessions` | Harvest intelligence from Claude Code session history |
| `ds memory ingest-sessions --dry-run` | Preview harvest counts without writing |

## Verification & enforcement
| Command | Description |
|---------|-------------|
| `ds prove` | Run the four-claim substrate demonstration against a disposable scratch project (CI-usable; non-zero exit on any failure). `--json` for machine output. |
| `ds grader profiles` | Print which provider will grade each verify role (role → provider) |
| `ds enforce tier` | Print the currently resolved enforcement tier (off/observe/warn/enforce) |
| `ds enforce report [--since <iso>]` | What would have been blocked at the observe/warn tier, grouped by rule |

## Health checks
| Command | Plane | Description |
|---------|-------|-------------|
| `ds validate` | DB authority | Schema version, migrations, module profiles |
| `ds doctor` | Claude Code integration | Skills, agents, hooks, routing, version |
| `ds version` | — | Show Dream Studio version |
| `ds status` | — | Show installed runtime status |
