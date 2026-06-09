# agents/

This directory is the bundled specialist layer of dream-studio. Each file here is a
Claude Code sub-agent — a focused persona with deep domain expertise, concrete commands,
gotchas, and anti-patterns. Agents are synthesized by the `domain-ingest` workflow, not
manually authored. Skills orchestrate agents; agents do not invoke skills.

## Two integration modes

**Mode A — Knowledge injection**
A domain YAML from `skills/domains/` is loaded as context by a running skill. No agent
is dispatched. Use this when the task fits an existing dream-studio skill but needs
domain-specific depth (e.g., a `saas-build` task that benefits from Prisma ORM patterns).

**Mode B — Specialist dispatch**
An agent file from `~/.claude/agents/` is dispatched via the Task tool inside a workflow
`type: specialist` node. The skill owns process, gates, and artifacts; the agent supplies
domain expertise. Use this for multi-domain workflows or when no dream-studio skill covers
the domain on its own.

## Install

Copy agents to Claude Code's agent directory. No GitHub auth required — copy straight from
your local clone.

**Unix / macOS**
```bash
cp agents/* ~/.claude/agents/
```

**Windows (PowerShell)**
```powershell
Copy-Item agents\* $HOME\.claude\agents\
```

Run either command from the repo root. Re-run after pulling updates to refresh stale agents.

> **Update notifications:** dream-studio checks GitHub releases once per day and prints an upgrade notice to stderr when a newer version is available. Follow the printed command to pull and re-run setup.

## Adding new specialists

Run the `domain-ingest` workflow with the target domain name:

```
workflow: domain-ingest  domain: <name>
```

The workflow handles everything: GitHub code search + VoltAgent catalog sourcing, scoring
against `skills/domains/eval-rubric.yml`, synthesis into an `agents/` file, and
registration in `skills/domains/ingest-log.yml`. Do not hand-author agent files — the
workflow ensures quality gates and consistent structure.

## Updating stale specialists

Run `workflow: domain-refresh` to re-score and re-synthesize all agents whose source
material has aged past the threshold. Alternatively, the on-pulse hook flags stale entries
automatically; act on those flags by running `domain-refresh` for the listed domains.
