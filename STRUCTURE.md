# Dream Studio Project Structure

Dream Studio is a local-first AI orchestration and operational intelligence platform.

- **Layer architecture** → [`docs/reference/layer-map.md`](docs/reference/layer-map.md)
- **All skills, packs, and routing** → [`docs/reference/skills-index.md`](docs/reference/skills-index.md)

---

<!-- BEGIN DIRECTORY-TREE: hand-maintained, not generated. A pack or top-level
     directory change requires updating this section in the same changeset --
     enforced by the repo_structure_navigation docs-drift domain
     (core/shared_intelligence/contract_registry_domains_ops.py), not by a script.
     Record the review below with a dated HTML comment, the way prior edits have. -->
## Top-Level Layout

```text
dream-studio/
  canonical/                         constitutional source — skills, workflows, adapter authority
    skills/                          skill packs (one subdir per pack, see packs.yaml)
      core/                          build lifecycle (ds-core)
      quality/                       code quality (ds-quality)
      analyze/                       analysis engine (ds-analyze)
      domains/                       domain builders (ds-domains)
      data/                          database quality + data engineering (ds-data)
      workflow/                      workflow orchestration (ds-workflow)
      security/                      security analysis (ds-security)
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
<!-- Last reviewed 2026-07-19 — WO-AUTOACT-B: packs.yaml meta pack hook list gains on-prompt-route (the UserPromptSubmit routing handler under runtime/hooks/meta/). No directory-tree layout change. -->

<!-- Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed. -->
<!-- Reviewed 2026-09-18 - no directory-tree layout change. `control/execution/
dispatch_tracking.py` gains a recorded outcome for a handler whose file is absent, and
`tests/unit/test_hook_exec_stats.py` replaces one test with its inverse. No new module,
package, directory or hook file; no relocation; the handler packs under runtime/hooks/ and
their installed projection are unchanged. Reviewed, no doc content change needed. -->
<!-- Last reviewed 2026-09-18 - skill-card contract: packs.yaml gains an `invariants:` list on every one of the 12 packs (what holds across that pack's modes, under the same enforce-or-declare shape canonical/rules.yml uses). New sibling of packs.yaml: canonical/skill_vocabulary.json, the registry of root input tokens the mode dataflow consumes from outside itself. No directory-tree layout change. -->
<!-- Last reviewed 2026-09-18 - lesson loop: packs.yaml quality pack gains a `groom` mode (canonical/skills/quality/modes/groom/), the terminus that turns promoted lessons into skill-text edits. No directory-tree layout change. -->
<!-- Last reviewed 2026-09-24 - pack-split (first slice): a new data/ pack (ds-data) added under canonical/skills/, splitting database out of quality and data-engineering out of domains -- neither depended on any other content in its origin pack, each already carried its own dedicated subagent. packs.yaml's quality and domains mode lists lost one entry each; a new data pack block was added. Directory-tree layout change: data/ row added above. -->
