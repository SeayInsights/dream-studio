# agents/

Role definitions for dream-studio subagents. Each file describes what an agent does, what it owns, and how it should behave when invoked.

## What this directory provides

Markdown role cards — one per agent persona. These are loaded by the skill system to give spawned subagents their identity, responsibilities, and decision authority.

## Entry point

`chief-of-staff.md` — the orchestrator that coordinates other agents. Read it first to understand the overall agent hierarchy.

## Public interfaces

Agent files are referenced by name in `SKILL.md` files via the `subagent_type` field (e.g., `dream-studio:director`). The filename (without `.md`) is the subagent type identifier.

## What should never be imported directly

The `context/` subdirectory contains ephemeral context injection files — these are assembled at runtime and should not be treated as stable references.

## Key invariants

- Each agent file must define: role, owned domain, decision authority, and escalation path
- Agent files are read-only contracts — runtime state goes in `~/.dream-studio/state/`, never here
- Agent hierarchy: Director → Chief-of-Staff → Engineering / Game / Client
