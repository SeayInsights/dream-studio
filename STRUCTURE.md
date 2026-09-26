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
      code-health/                   quality, architecture, structure, and test discipline (ds-code-health)
      analyze/                       analysis engine (ds-analyze)
      domains/                       domain builders (ds-domains)
      data/                          database quality + data engineering (ds-data)
      infra/                         CI/CD, Kubernetes, and infrastructure as code (ds-infra)
      apps/                          SaaS, mobile, game, and MCP-server builders (ds-apps)
      workflow/                      workflow orchestration (ds-workflow)
      security/                      security analysis (ds-security)
      website/                       website builder (ds-website)
      fullstack/                     fullstack builder (ds-fullstack)
      release/                       release and launch readiness (ds-release)
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
<!-- Last reviewed 2026-09-25 - pack-split (fifth slice): the EXISTING core/ pack (ds-core) gained three sub-modes -- learn and coach (out of quality), technical-writing (out of domains) -- rather than a new pack being created. learn's mode-owned top-level reference dir (canonical/skills/quality/learn/, holding the learn:expand sub-skill) and technical-writing's mode-owned top-level reference dir (canonical/skills/domains/documentation/) moved with them to canonical/skills/core/{learn,documentation}/; a routing-table row in canonical/skills/workflow/examples.md, two forward-looking implementation comments in core/learning/lesson_threshold.py, and a doc reference in interfaces/cli/README.md were updated to match, alongside packs.yaml, coverage.yml, technical-writer.meta.yml, the two moved modes' dream_studio: frontmatter cards (technical-writing carries none), and the learn:expand sub-skill's own self-referential headers. quality/SKILL.md's dispatch table lost the learn/coach rows (technical-writing was never keyword-dispatched, only Task-tool-subagent-dispatched via technical-writer); domains/SKILL.md never had a technical-writing row to remove. CORRECTED post-merge (same PR, before it landed): the "only technical-writer's own row was corrected" claim below did not hold through to what actually shipped -- review found the commit message itself mischaracterized which AGENTS.md row was stale (named data-engineer, which was accurate; missed accessibility-expert, which was genuinely stale since the fourth slice), and since a git-archive lane container has no .git directory and can never verify a claim about commit-message prose, the only way to make the underlying claim durably true was to fix AGENTS.md's table directly: mobile-developer (domains:mobile -> apps:mobile) and accessibility-expert (quality:accessibility -> website:accessibility) were both corrected alongside technical-writer's row, and all 9 rows in that table are now cross-checked against packs.yaml. The "populated via ds-quality:learn" boilerplate comment repeated in 5 unrelated modes' metadata.yml files was also fixed for the same reason (round-1 review caught it as an inconsistency with the STRUCTURE.md fix in this same slice). No directory-tree layout change -- core/ already existed. -->
<!-- Last reviewed 2026-09-25 - pack-split (sixth slice): a new release/ pack (ds-release) added under canonical/skills/, splitting ops and pre-launch out of quality. Both are `no_agent` (below the 5000-byte isolation threshold) and neither declares a keyword trigger. New canonical/skills/release/{SKILL.md,config.yml} created (no prior top-level pack file existed to move) following the apps/data new-pack precedent -- writing a real Mode Routing Table for it turned out to FIX a pre-existing reachability gap rather than just relocate it: quality/SKILL.md never listed ops or pre-launch in its own dispatch table at all (that absence, not a missing keyword, was what made tests/unit/test_skill_reachability.py's KNOWN_UNREACHABLE pin them), and _pack_routed_modes() counts explicit-mode-name dispatch (step 1 of the algorithm) as a real route independent of keyword inference (step 2) -- so both entries were deleted from KNOWN_UNREACHABLE outright rather than renamed. pre-launch's own rules.yml carried 7 self-referential template paths (2 pointing at templates that actually exist, 5 at templates that were never created -- pre-existing, unrelated staleness) -- the pack-name segment was corrected uniformly across all 7. Both modes' metadata.yml pack: field was left at its old value (quality), matching the already-shipped precedent from the fourth and fifth slices (that field is not gate-checked, unlike the dream_studio: SKILL.md frontmatter card, which neither ops nor pre-launch carries). packs.yaml's quality mode list lost two entries; a new release pack block was added. Directory-tree layout change: release/ row added above. -->
<!-- Last reviewed 2026-09-25 - pack-split (seventh slice): a new code-health/ pack (ds-code-health) added under canonical/skills/, splitting code-quality, architecture, structure-audit, audit, groom, testing, and debug out of quality -- the largest slice so far (7 modes). Three of quality's four pack-level hooks moved with it: on-quality-score, on-structure-check, on-agent-correction (runtime/hooks/quality/ -> runtime/hooks/code-health/, plus the on-edit-dispatch.py and on-stop-dispatch.py handler tables that name their literal paths); on-security-scan stayed with quality (harden's concern, not this pack's). quality's two structure rule files (packs/quality/rules/structure/{architecture,fsc}.md) moved to packs/code-health/rules/structure/, their only referrer (structure-audit) having moved. Three mode-owned top-level asset dirs moved with their owning modes: canonical/skills/quality/references/{code-writing-best-practices,testing-best-practices}.md (code-quality's and testing's rule sources; types-deps-best-practices.md stayed, types-deps stayed) and canonical/skills/quality/shared/{flake8_baseline,trust_boundary_detection}.py (both code-quality-only, confirmed by grep -- no core/interfaces/control code imports either, only their own SKILL.md/audit sub-skill and one test file). code-health is the first pack-split target whose real pack name contains a hyphen with an actual importable Python module under it: `from canonical.skills.code-health.shared...` is invalid Python syntax (hyphens aren't legal in dotted-import identifiers), confirmed to matter only for tests/unit/test_flake8_baseline.py, fixed there and in code-quality/audit/SKILL.md's own code sample by switching to `importlib.import_module("canonical.skills.code-health.shared.flake8_baseline")` -- verified importlib handles a hyphenated package path correctly even though the dotted-statement syntax cannot. A fifth hardcoded-quality-root instance of the recurring bug class (see PR #820's note) was found and fixed in tests/conftest.py's `_PACK_NAMES` tuple (missing both "code-health" and, pre-existing, "apps" from the third slice -- neither had ever been added), plus three separate hook-pack-name tuples (interfaces/cli/setup_hooks.py's SYNC_HOOK_PACKS/UNINSTALL_HOOK_PACKS, interfaces/cli/runtime_preflight.py's HOOK_PACKS, core/health/doctor_shared.py's _PROJECTED_HOOK_SUBDIRS) all needed "code-health" added, verified by tests/unit/test_hook_pack_projection_consistency.py which computes the real set from the filesystem. Extensive self-referential `ds-quality:<mode>` mentions inside the seven moved modes' own rules.yml/metadata.yml/SKILL.md/core-imports.md files were corrected to `ds-code-health:<mode>` (each mode had referred to itself, or to a sibling also moving, by its old identity); references to `ds-quality:security` (stays in quality) were left alone, and one pre-existing stale `ds-quality:database` mention (database moved to ds-data in the first slice, never fixed then) was corrected as an adjacent accuracy fix. quality/SKILL.md's dispatch table lost the debug/structure-audit/groom rows; quality/config.yml's description and argument-hint, both already stale from two earlier slices (still listing polish/learn/coach, which left in the fourth and fifth slices), were also corrected while touching this file. packs.yaml's quality mode list lost seven entries and its hooks list lost three; a new code-health pack block was added. Directory-tree layout change: code-health/ row added above. -->

