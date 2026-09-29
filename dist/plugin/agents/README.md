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

## Round-table reviewers vs. domain specialists

The `review-*.md` files in this directory are a different thing from the domain
specialists above: they're compiled from `canonical/review_lanes.yml` by
`integrations.compiler.reviewers`, one per round-table seat, not synthesized by
`domain-ingest`. Do not hand-edit a `review-*.md` file directly — change the seat's
lanes in the registry and recompile with `py -m integrations.compiler.reviewers --write`.

### A project's own seats

A project can add its own round-table seats without touching Dream Studio's own
registry, by committing a `.ds-review-lanes.yml` marker at its repo root — see
`core/work_orders/project_review_lanes.py` for the schema (`mode: add|replace`, a
`lanes:` list in the same shape `review_lanes.yml` uses) and
`core/work_orders/review_rules.py`'s `.ds-review-rules.md` for the established sibling
pattern this mirrors.

A project seat compiles the same way Dream Studio's own do, but the compiled file is
never written into this directory — it's cached under
`<repo_root>/dream-studio-cache/compiled-agents/`, re-derived on demand rather than
checked in (the same "render fresh, don't commit the output" choice
`review_rules.py` makes for review rules). `ds integrate install <tool>` picks it up
automatically alongside the bench in this directory whenever the install target is the
project's own tree; `--agents "<seat name>"` can also name it explicitly.

**V1 limits:** project-root only (no per-folder lanes yet, unlike `.ds-review-rules.md`);
a project seat cannot declare `detector:` or `eval:` — only the judgment-lane shape. A
project's seat name cannot collide with one of Dream Studio's own reserved seats.
