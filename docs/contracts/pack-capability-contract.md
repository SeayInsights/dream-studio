# Pack Capability Contract

Status: draft. What "Present today" lists is built and tested, including declaring work-order
types in a pack manifest; everything under "Proposed" is not enforced yet.

A pack is installable content: skills, agents, templates, rules, and the work-order
types and gates a domain needs. This contract defines how a pack reaches governance —
work orders, findings, evidence, review — without importing Dream Studio internals, so
the same pack runs under Dream Studio, under any other backend that implements the
capabilities below, or with no backend at all.

It extends, and does not replace, the [adapter contract](adapter-contract.md)
(optional providers degrade through a documented fallback, never a hidden required
import), the [skill contract](skill-contract.md) (skills are portable primitives that
own no canonical state), and the [MCP server contract](mcp-server-contract.md) (the
transport and the named-capability auth model reused here).

## Principles

1. A pack never imports `core`, `control`, or any other Dream Studio package. It reaches
   governance only through the capabilities in this contract, over MCP or the `ds` CLI
   mirror.
2. Every capability has a standalone fallback. A pack that cannot reach a backend
   degrades to a stated behavior; it never fails silently and never reports an
   unperformed step as done.
3. A pack declares what it needs; the backend answers what it grants. The pack adapts
   to the answer.
4. Capability names are `noun:verb`, as `auth.KNOWN_CAPABILITIES` already spells them.
   The contract version is additive: a capability is added, never redefined.

## Pack manifest

Each pack carries a manifest (today this is spread across `packs.yaml` and each mode's
`metadata.yml`). The capability-relevant fields:

| Field | Meaning |
| --- | --- |
| `requires` | Capabilities the pack cannot work without. If the backend denies one, the pack stops and says which. |
| `uses` | Capabilities the pack uses when present and replaces with a fallback when not. |
| `contributes.work_order_types` | Work-order types the pack adds, each with the artifact class it reviews as. Read from `packs.yaml` today (see "Present today"). |
| `contributes.gates` | Close gates the pack adds, each with its check command. Not read yet; a manifest that declares it is refused. |
| `contributes.finding_categories` | Finding categories the pack emits. Not read yet; a manifest that declares it is refused. |
| `files` | Every template, rule, and script the pack reads, by path inside the pack. A path outside the pack directory is a defect. |

`metadata.yml` today declares `core_modules: []` for 35 of 51 skills, and some skills
(binary-scan) name tools and files they plainly need while declaring none. The
manifest's `requires`/`uses`/`files` replace those fields, and a guard compares them
to what the skill text and scripts actually call.

## Capabilities

### Present today (MCP tools, named-client gated)

| Capability | Tool(s) |
| --- | --- |
| `project:create` | `ds_project_create` |
| `milestone:create` | `ds_milestone_create` |
| `work_order:create` | `ds_work_order_create` |
| `work_order:add_task` | `ds_work_order_add_task` |
| `work_order:start` | `ds_work_order_start` |
| `work_order:task_mutate` | `ds_work_order_task_start`, `ds_work_order_task_done` |
| `work_order:advance` | `ds_work_order_advance` |
| `work_order:close` | `ds_work_order_close` |
| `review:dispatch` / `review:run` / `review:record` | `ds_review_dispatch` / `ds_review_run` / `ds_review_record` |
| `gate:check` | `ds_gate_check`: read-only, no MCP capability, and the non-executing preview only (see below) |
| (read, no capability) | `ds_project_list`, `ds_project_state`, `ds_project_status`, `ds_work_order_list`, `ds_work_order_tasks`, `ds_review_status`, `ds_review_findings`, `ds_skill_list`, `ds_doctor`, `ds_memory_query`, `ds_gate_check` |

`review:dispatch` and `review:record` can never be held by one client (enforced in
`auth.add_client`).

`gate:check` previews a work order's close gates without running them
(`check_close_gates(run_checks=False)`). It evaluates every gate that can be read and
reports each gate as `pass`, `fail`, or `not_run`. Every `SQL-CHECK`, `TEST-CHECK` and
`API-CHECK` criterion, the stored-commit comparison behind the artifact gates, and every gate
that reads `.planning` from disk (the server has no project directory) come back `not_run`
with the reason, never `pass` and never `fail`. It starts no subprocess, makes no request, writes no event, opens the
authority read-only and evaluates no authored query, which is what lets a client with no capability call it. The executing form (the default of
`check_close_gates`, run by the `ds` CLI) stays CLI-only: there is no MCP tool and no
capability that runs a work order's checks. The preview is not a closability verdict;
`close_work_order` enforces gates it does not evaluate (see the MCP server contract). A pack
that contributes a gate gets this preview for the gates the core knows. Previewing a
pack-contributed gate waits on `gate:register`, below.

### Present today (read model, not yet a capability)

| Item | What exists |
| --- | --- |
| Finding honesty fields | The unified `Finding` read model (`core/findings/model.py`) carries `confidence` (`high` \| `medium` \| `low` \| `unknown`), `coverage` (`complete` \| `partial` \| `unknown`) and `limitations` (list, or null when not recorded). They appear in `Finding.to_dict`, `ds render findings --json`, and the HTML page. There is no `finding:record` / `finding:list` capability yet. |

The defaults are `unknown`, `unknown`, and null: a finding whose producer recorded nothing
never reads as high-confidence or complete. Today no producer records them. The
`security_events` table has no column for any of the three (adding one is a schema
migration, not done), so those rows are always unknown. The guard log passes through the
three keys when a log line carries them, and the audit-markdown reader attaches one
limitation to a blocker it had to recover from prose. Every other value is unknown.

### Present today (work-order types: declared in a pack manifest)

| Capability | Surface |
| --- | --- |
| `registry:work_order_type` | A pack declares types under `contributes.work_order_types` in `packs.yaml`; `core.work_orders.type_manifest.load_pack_work_order_types(packs_yaml_path=...)` registers them through `core.work_orders.type_registry.register_work_order_type`, and the registry's accessors load the running install's manifest on first use (`ensure_loaded`). |

The registry holds, per work-order type, the artifact class it reviews as, whether it is
UI-bearing, whether closing it stales the design brief, whether it is exempt from default-on
verification, whether closing it is held to the `dashboard_truth` gate, and the one-line
description and presentation order the generated operator `AGENTS.md` prints. The ten
built-in types are registered at import. `review_rules`, `brief_currency`,
`milestones/close`, `milestones/queries`, `start_brief`, `close_main`, `create_work_order`,
`ds project state`, the CLI `--type` choices, the MCP `ds_work_order_create` enum and the
operator `AGENTS.md` type table all read it. The closed `WORK_ORDER_TYPES` tuple, the four
private subsets, the literal `dashboard_truth` set and the second type list in the AGENTS.md
generator are gone.

A pack declares a type like this (`schema_version: 2`):

```yaml
packs:
  legal:
    contributes:
      work_order_types:
        - name: contract_review           # required: lowercase, digits, underscores, at most 64
          artifact_class: document        # required: code | config | document | data
          description: Reviewing a contract for completeness and accuracy   # required, one line
          ui_bearing: false               # optional flags, all default false
          stales_design_brief: false      #   (stales_design_brief defaults to ui_bearing)
          exempt_from_verification: false
          dashboard_truth_gated: false
```

How it behaves:

- **When it is read.** Lazily, once per process, by the first accessor or registration call;
  never at import, so importing the registry reads no file and writes nothing. The manifest is
  `code_root() / "packs.yaml"`: the checkout's in a checkout, the site-packages copy in an
  installed app (the wheel ships `packs.yaml` at that path), independent of the working
  directory. Registrations are process-local and rebuilt in every process (the CLI, the MCP
  server and each hook read the manifest themselves). A manifest that cannot be read, or that
  declares something invalid, is a `PackManifestError` naming the file and the pack on every
  read until it is fixed: it never silently falls back to the built-ins.
- **What is refused.** An unknown key on a type or under `contributes`, a missing required
  key, an unknown artifact class, a bad name, flag or description, a duplicate across packs,
  and a collision with a built-in or an already registered type. `contributes.gates` and
  `contributes.finding_categories` are refused today, not ignored, because nothing reads them.
  A manifest is applied whole or not at all.
- **Startable without a row.** `ds work-order start` reads `business_work_order_types` for a
  work order's gates, executor and workflow template. A declared type with no row gets a
  profile derived from the declaration (a label, and no pre/post gate, executor or workflow);
  nothing is written, so there is no migration and nothing to drift from the manifest. A
  pack-declared work order is therefore held to the universal close gates (tasks done,
  executable acceptance criteria, change impact, independent review unless the type is
  exempt) and to the registry flags, and to no type-specific gate. A row, where one exists,
  still wins.
- **When the manifest goes away.** Work orders of the type stay readable and listable. Start
  refuses with a message that names the manifest as the likely cause. Close treats the type as
  undeclared: independent review is required, it reviews as code, and the `dashboard_truth`
  gate does not apply, so such a work order can still be closed through the universal gates.
- **For tests.** `type_registry.scoped_registration()` and
  `type_registry.scoped_pack_manifest(path)` restore the registry on exit. There is no public
  unregister.

What is not shipped:

- `gate:register`: a pack cannot contribute a close gate, a pre-build or post-build gate for
  its types, an executor or a workflow template. Close gates are still the fixed set in
  `core.work_orders.close_gates` (`KNOWN_GATES`) bound to types by `business_work_order_types`
  rows. It needs a gate registry (name, check, whether it can be previewed without executing),
  a manifest key, and a decision on whether a type's `pre_build_gate` and `post_build_gate`
  become manifest fields.
- A runtime surface (CLI or MCP) for registering a type. A type exists because a manifest
  declares it, in every process that reads that manifest.
- Persisting a type, or recording which pack a work order's type came from.
- A review of the loader against an installed wheel on a machine other than the one that built
  it: the wheel test checks that `packs.yaml` ships, and `code_root()` is the existing
  resolution for it, but no test installs a wheel and declares a pack type.

### Proposed

| Capability | Purpose | Standalone fallback |
| --- | --- | --- |
| `finding:record`, `finding:list` | Record and read findings in one typed shape: severity, location, `confidence`, `limitations`, `coverage` (`complete` \| `partial` \| `unknown`), evidence refs. The read model carries the three honesty fields (see "Present today"); recording them through a capability, and storing them in `security_events`, are not built. | Append to a JSONL file beside the work; `list` reads it back. |
| `evidence:attach` | Attach a content-hashed artifact (scan output, reproduction log) to a finding or work order. | Write the file next to the work; record its SHA256 in the finding. |
| `gate:register` | Let a pack supply close gates and bind them to its types (work-order types are shipped, see above; gates have no registry yet, and close gates are still the fixed set in `close_gates` bound to types by the `business_work_order_types` rows). | Gates are read from the manifest and applied by the pack's own checklist. |
| `artifact:write`, `artifact:read` | Named working artifacts (plans, audit reports). Replaces `ds files write` calls in skill text. | A project-local directory. |
| `memory:record` | Record a lesson. | Append to a local lessons file. |
| `telemetry:emit` | Emit a usage or cost event. | No-op, logged once. |

A pack that needs a review verdict has no standalone fallback for `review:*`: without a
backend its output is labelled **unverified**, never passed.

### Findings: required honesty fields

A finding recorded through `finding:record` carries:

- `confidence`: `high` \| `medium` \| `low`. A reader that finds none recorded reports
  `unknown`; it never defaults to `high`.
- `coverage`: whether the check examined everything it claims to. A scan that skipped a
  step because a tool was missing records `partial` and names the step.
- `limitations`: what the check cannot establish. Strings are explanatory and do not
  by themselves imply coverage.

A tool that degrades silently (for example a header-parse step run "if Python tools
are available") must record `coverage: partial` when it degrades.

## Session handshake

At session start the pack sends `requires` and `uses`. The backend returns each as
`granted`, `denied`, or `unavailable`, plus the contract version it implements. A
`requires` capability that is not `granted` ends the session with a message naming it.
A `uses` capability that is not `granted` switches to its fallback and says so once.

Authorization stays as in the MCP contract: root token or a named client issued exactly
the capabilities it calls.

## Standalone adapter

A reference adapter implements every capability against local files, so a pack runs
with no backend. It is the conformance baseline: a backend is conformant when a pack
produces the same observable result against it as against the standalone adapter,
apart from the persistence location.

## Boundary map (from the 2026-10-19 import audit)

Static, subpackage-level, AST-based; it does not see dynamic imports, CLI dispatch, or
tests. The classification is a judgment from the graph, directory names, and sizes, and
is a starting point for extraction, not a decision.

| Layer | Contents |
| --- | --- |
| Kernel (stays) | Authority DB and event store; project, milestone, and work-order lifecycle; the generic gate engine; MCP and CLI APIs; auth. |
| Services (candidates for standalone, API-connected) | Review lanes; telemetry, analytics, and cost; guardrails; memory and learning; dashboard (`projections/`, overlapping dream-cmd). |
| Adapters | `integrations/` (installer, compiler, marketplace, targets); `control/session` transcript parsing; `emitters/`. |
| Pack family: software delivery | `release`, `production_readiness`, `prd`, `design_briefs`, the in-repo security review lifecycle, and the `core`, `code-health`, `quality`, `fullstack`, and `release` packs, kept as separately installable units. |
| Packs | `analyze` (with real-estate, career, finance, and design domains); client-facing security scanning (`dast`, `binary-scan`, `comply`, `netcompat`); `data`; `infra`; `apps`; `website`; `domains` (power-platform, dashboard-dev). |

Findings that constrain extraction order:

- 23 `core/` subpackages form one dependency cycle; no single area removes it. The
  capability surface a pack needs is concentrated in `config`, `event_store`,
  `telemetry`, `work_orders`, `gates`, `projects`, and `findings`.
- `core.shared_intelligence` (42 files) imports `release`, `production_readiness`, and
  `security`, and is imported by `projections` (20 times). It is the hub to cut before
  those modules can leave `core`.
- `core.sdlc` (`active_task`, `cwd_resolver`) has seven importers across the platform
  and is session plumbing, not a delivery pack.
- `control/` has three homes: execution (workflow engine, model selector) and skills
  (router, loader) are kernel; `analysis` and `stacks` are the `analyze` pack's
  engine; `context` and `research` are service or legacy candidates. Several of its
  modules are imported back by `core.gates` and `core.projects`, which inverts the
  layering.
- Pack content depends on the checkout: seven skill files hardcode
  a path into one contributor's checkout (`builds/<checkout>/templates/...`), and 26 skill
  docs read the repo-level `templates/` directory.

## Extraction order

1. `analyze`: read-only, no platform imports, already holds the real-estate and career
   domain modules. It tests whether the contract is domain-neutral.
2. Client-facing security scanning: move `templates/security/` into the pack and fix the
   hardcoded paths; the release / production_readiness / security cluster needs a
   registry seam first.
3. Break the `config` back-edges and the `work_orders` / `gates` knot so the capability
   surface is stable.

Packs stay in this repository, each self-contained and built into its own installable
plugin, until one needs its own release cadence, contributors, or license; the split to
a separate repository is then mechanical.

## Open questions

- Does `registry:*` run at install time or per session? For work-order types: per process,
  lazily, from the manifest the process is running (see "Present today"). Gates are open.
- Who owns finding categories: the pack, or a shared vocabulary in the kernel?
- Does standalone mode persist state between sessions, or is it stateless?
- Which of `core.org_intelligence`, `core.pricing`, and `core.ontology` are live? Check
  for invoked-not-imported use before removing or moving anything.
