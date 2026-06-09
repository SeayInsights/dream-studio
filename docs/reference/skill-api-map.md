# Skill → API Usage Map

**Status:** CURRENT  
**Last reviewed:** 2026-06-07 (WO-P)

Maps each ds-* skill to the CLI commands, Python APIs, and event types it calls. Use this as the authoritative dependency reference when changing an API, CLI command, or event type.

---

## ds-project

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| scope | `register_project()`, `create_milestone()`, `create_work_order()`, `create_task()` | — | business_projects, business_milestones, business_work_orders, business_tasks |
| resume | `get_project_state()` | — | — (read-only) |
| brief | `ds design-brief show/update/lock` | — | business_design_briefs |
| manage | `py -m interfaces.cli.ds project list/set-active/archive` | — | business_projects |

---

## ds-workorder

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| start | `start_work_order()` (MCP) or `py -m interfaces.cli.ds work-order start` | — | business_work_orders |
| execute (task-done) | `mark_task_done()` or `py -m interfaces.cli.ds work-order task-done` | — | business_tasks |
| close | `close_work_order()` or `py -m interfaces.cli.ds work-order close` | — | business_work_orders |
| status | `py -m interfaces.cli.ds work-order tasks` | — | — (read-only) |
| block | `py -m interfaces.cli.ds work-order block` | — | business_work_orders |

---

## ds-milestone

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| status | `py -m interfaces.cli.ds milestone status` | — | — (read-only) |
| close | `py -m interfaces.cli.ds milestone close` | — | business_milestones |

---

## ds-core

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| think | Claude Code conversation | skill.invoked → spool | — |
| plan | Claude Code conversation | skill.invoked → spool | — |
| build | Claude Code conversation + git | skill.invoked, code.generated → spool | — |
| review | Claude Code conversation | skill.invoked → spool | — |
| verify | `py -m pytest`, `py core/gates/pre_push.py` | gate.pre_push.failed → spool | — |
| ship | `py core/gates/pre_push.py`, `gh pr merge` | gate.pre_push.failed → spool | — |
| explain | Claude Code conversation | skill.invoked → spool | — |

---

## ds-quality

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| debug | Claude Code conversation | skill.invoked → spool | reg_gotchas (on findings) |
| polish | Claude Code conversation + `py -m black .` | skill.invoked → spool | — |
| harden | Claude Code conversation | skill.invoked → spool | reg_gotchas |
| security | Claude Code conversation + `semgrep` / pattern scan | skill.invoked → spool | reg_gotchas |
| database | Claude Code conversation + schema inspection | skill.invoked → spool | reg_gotchas |
| code-quality | Claude Code conversation + `py -m flake8`, `py -m black --check` | skill.invoked → spool | — |
| testing | Claude Code conversation | skill.invoked → spool | — |
| types-deps | Claude Code conversation | skill.invoked → spool | — |
| audit | Claude Code conversation | skill.invoked → spool | reg_gotchas |
| pre-launch | `py core/gates/pre_push.py` + Claude Code | gate.pre_push.failed → spool | reg_gotchas |
| pr-security-scan | Claude Code + `gh pr diff` | skill.invoked → spool | reg_gotchas |

---

## ds-analyze

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| repo | Claude Code file scan | skill.invoked → spool | — |
| intelligence | Claude Code + canonical event queries | skill.invoked → spool | — |
| multi | Claude Code multi-agent | skill.invoked → spool | — |
| domain-re | Claude Code conversation | skill.invoked → spool | — |
| research | External web search + synthesis | skill.invoked → spool | — |
| idea-validation | Claude Code conversation | skill.invoked → spool | — |

---

## ds-setup

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| wizard | `py -m interfaces.cli.ds rehearsal-install` | — | All tables (first-run bootstrap) |
| status | `py -m interfaces.cli.ds project state` | — | — (read-only) |
| jit | Claude Code file generation | skill.invoked → spool | — |

---

## ds-security

| Mode | CLI / API | Events emitted | SQLite tables written |
|------|-----------|---------------|----------------------|
| scan | `semgrep`, pattern scan, Claude Code | skill.invoked → spool | reg_gotchas |
| dast | External tool invocation | skill.invoked → spool | reg_gotchas |
| mitigate | Claude Code conversation | skill.invoked → spool | reg_gotchas |
| comply | Claude Code conversation | skill.invoked → spool | reg_gotchas |
| review | Claude Code conversation | skill.invoked → spool | reg_gotchas |

---

## Pre-push Gate (not a skill — called directly)

| Command | APIs | Events emitted |
|---------|------|---------------|
| `py core/gates/pre_push.py` | `run_pre_push_gates()`, `format_report()` | gate.pre_push.failed → spool (per failed blocking gate) |
| `py interfaces/cli/contract_atlas_lifecycle_gate.py` | Contract registry API | — |
| `py interfaces/cli/contract_docs_drift_gate.py` | Contract registry + git diff | — |
| `py -m core.gates.migration_risk` | git diff HEAD inspection | — |
| `py -m core.gates.skill_sync_source` | Source file grep | — |

---

## Event → API Reverse Map

| Event type | Written by | Read by |
|------------|-----------|---------|
| `skill.invoked` | Skill infrastructure | Dashboard API `/api/v1/skills/activity`, exec_time_ranges |
| `token.consumed` | AI token tracking layer | `token_attribution.py`, dashboard API |
| `gate.pre_push.failed` | `core/gates/pre_push.py` | `reg_gotchas` projection |
| `work_order.started` | Work order lifecycle | Dashboard project status |
| `work_order.closed` | Work order lifecycle | Dashboard project status, milestone close checks |
