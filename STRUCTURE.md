# Dream Studio Project Structure

Dream Studio is a local-first AI orchestration and operational intelligence platform.

- **Layer architecture** → [`docs/reference/layer-map.md`](docs/reference/layer-map.md)
- **All skills, packs, and routing** → [`docs/reference/skills-index.md`](docs/reference/skills-index.md)

---

<!-- BEGIN DIRECTORY-TREE: auto-generated from packs.yaml — do not edit manually -->
## Top-Level Layout

```text
dream-studio/
  canonical/                         constitutional source — skills, workflows, adapter authority
    skills/                          skill packs (one subdir per pack, see packs.yaml)
      core/                          build lifecycle (ds-core)
      quality/                       code quality (ds-quality)
      analyze/                       analysis engine (ds-analyze)
      domains/                       domain builders (ds-domains)
      workflow/                      workflow orchestration (ds-workflow)
      security/                      security analysis (ds-security)
      project/                       project lifecycle (ds-project)
      workorder/                     work order lifecycle (ds-workorder)
      milestone/                     milestone lifecycle (ds-milestone)
      website/                       website builder (ds-website)
      fullstack/                     fullstack builder (ds-fullstack)
      setup/                         setup (ds-setup)
    workflows/                       YAML workflow definitions (e.g. idea-to-pr.yaml)
  core/                              authority, telemetry, release, work-order, shared-intelligence
  control/                           session, research, execution models
  projections/                       API and dashboard projection surfaces
  interfaces/                        CLI and adapter command surfaces
  spool/                             event ingestion and session harvesting
  runtime/                           hooks, config, release gates
  docs/                              public product and architecture documentation
  tests/                             unit, integration, runtime, and validation tests
  packs.yaml                         single source of truth for pack × mode matrix
```
<!-- END DIRECTORY-TREE -->

---

## Runtime State Boundary

Operator-local runtime state is never committed:

```text
~/.dream-studio/
  state/studio.db     — SQLite authority (work orders, tasks, milestones, projects)
  diagnostics/        — session test output (write here, not to repo root)
  backups/            — DB backups before migration runs
```

## Adapter Boundary

`.claude/` describes the Claude Code adapter projection. Dream Studio supports adapter projections for other tools (Codex, Cursor, Copilot, MCP systems, shell tools). No adapter is the source of truth — `~/.dream-studio/state/studio.db` is.

<!-- Last reviewed 2026-06-13 — WO 20ead828: idea-validation mode removed from ds-domains (packs.yaml line 29); it correctly lives under ds-analyze. No directory-tree layout change. -->
<!-- Last reviewed 2026-07-03 — WO-CI-442-FOLLOWUP (79f56243, #443): packs.yaml meta pack hook list gains on-edit-enforce and on-stop-enforce (the blocking SQLite-enforcement hooks under runtime/hooks/meta/, added by #442). No directory-tree layout change. -->
