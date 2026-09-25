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
      infra/                         CI/CD, Kubernetes, and infrastructure as code (ds-infra)
      apps/                          SaaS, mobile, game, and MCP-server builders (ds-apps)
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
<!-- Last reviewed 2026-09-24 - pack-split (second slice): a new infra/ pack (ds-infra) added under canonical/skills/, splitting devops, kubernetes, and terraform out of domains -- each already carried its own dedicated subagent and no other domains content depended on them. packs.yaml's domains mode list lost three entries; a new infra pack block was added. Directory-tree layout change: infra/ row added above. -->
<!-- Last reviewed 2026-09-24 - pack-split (third slice): a new apps/ pack (ds-apps) added under canonical/skills/, splitting saas-build, mobile, game-dev, and mcp-build out of domains. game-dev's runtime dependencies moved with it -- runtime/hooks/domains/on-game-validate.py, runtime/lib/domains/game_validate*.py, and packs/domains/{agents/game.md,rules/game/} are now under the apps/ equivalents, and the on-edit-dispatch handler table, the installer's hook-pack list, and packs.yaml's agents/hooks/rules fields were updated to match -- domains' game/client agent pair is now client-only (client belongs to power-platform, which stayed). packs.yaml's domains mode list lost four entries; a new apps pack block was added. Directory-tree layout change: apps/ row added above. -->
<!-- Last reviewed 2026-09-25 - pack-split (fourth slice): the EXISTING website/ pack (ds-website) gained three sub-modes -- design (out of domains), accessibility and polish (out of quality) -- rather than a new pack being created. design's two mode-owned top-level reference dirs (canonical/skills/domains/{design,design-systems}/) moved with it to canonical/skills/website/{design,design-systems}/; a live reference in core/work_orders/start_context.py (the locked-design-brief prompt builder) and a routing-table row in canonical/skills/workflow/examples.md were updated to match, alongside packs.yaml, coverage.yml, and the two moved modes' dream_studio: frontmatter cards. domains/SKILL.md and quality/SKILL.md's own dispatch tables lost the design/polish rows (accessibility was never keyword-dispatched, only Task-tool-subagent-dispatched); domains/SKILL.md's pre-existing stale website/fullstack rows (pointing at modes/{website,fullstack}/SKILL.md, which have not existed under domains since those packs went independent) were also removed as part of the same edit. No directory-tree layout change -- website/ already existed. -->
