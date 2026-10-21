# Pack Capability Contract

Status: draft (proposed; nothing here is enforced yet)

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
| `contributes.work_order_types` | Work-order types the pack adds, each with the artifact class it reviews as. |
| `contributes.gates` | Close gates the pack adds, each with its check command. |
| `contributes.finding_categories` | Finding categories the pack emits. |
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
| (read, no capability) | `ds_project_list`, `ds_project_state`, `ds_project_status`, `ds_work_order_list`, `ds_work_order_tasks`, `ds_review_status`, `ds_review_findings`, `ds_skill_list`, `ds_doctor`, `ds_memory_query` |

`review:dispatch` and `review:record` can never be held by one client (enforced in
`auth.add_client`).

### Present today (read model, not yet a capability)

| Item | What exists |
| --- | --- |
| Finding honesty fields | The unified `Finding` read model (`core/findings/model.py`) carries `confidence` (`high` \| `medium` \| `low` \| `unknown`), `coverage` (`complete` \| `partial` \| `unknown`) and `limitations` (list, or null when not recorded). They appear in `Finding.to_dict`, `ds render findings --json`, and the HTML page. `security_events` stores them (migration 161: nullable `confidence`, `coverage`, `limitations` columns, the last a JSON array), and `record_finding` / `emit_security_finding` take them as optional parameters. There is no `finding:record` / `finding:list` capability yet. |

The defaults are `unknown`, `unknown`, and null: a finding whose producer recorded nothing
never reads as high-confidence or complete. In `security_events` NULL is unknown: a row written
before migration 161, or by a writer that passed none of the three, reads unknown, and a value
outside the vocabulary is stored as NULL rather than as a certain one (`encode_honesty` uses the
read model's own normalisers). `limitations` of `[]` records "none exist", which is not the same
as NULL. The migration is unreleased, so a live authority that has not applied it records the
finding without the three fields and reads unknown. The guard log passes through the three keys
when a log line carries them, and the audit-markdown reader attaches one limitation to a blocker
it had to recover from prose. The SARIF importer records what the file states
(`properties.precision` as confidence, a failed invocation as partial coverage with that
limitation) and nothing else. Three producers still pass nothing, so their findings read
unknown: `core/projects/intake.py`, `control/analysis/bugs.py` and
`core/analytics_ingestion_rows.py`. A write that cannot encode a value (an object whose
`__str__` raises) records the finding with the three fields unknown and logs it; a finding
is never lost to its annotations. `emit_security_finding` reports whether a row was written:
a failed write returns `emitted=False, failed=True` with a logged reason (the exception class,
never the data) and leaves no row; `failed=False` with `emitted=False` is a skip (telemetry
disabled, or a duplicate id). The SARIF importer uses a result's `ruleIndex` only when the
indexed rule's id matches the result's `ruleId`.

### Present today (Python API only, not yet reachable by a pack)

| Capability | Surface |
| --- | --- |
| `registry:work_order_type` | `core.work_orders.type_registry.register_work_order_type(name, artifact_class=..., ui_bearing=..., stales_design_brief=..., exempt_from_verification=...)` and the read accessors beside it. |

The registry holds, per work-order type, the artifact class it reviews as, whether it is
UI-bearing, whether closing it stales the design brief, and whether it is exempt from
default-on verification. The ten built-in types are registered at import, and
`review_rules`, `brief_currency`, `milestones/close`, `milestones/queries`, `start_brief`,
`close_main`, `create_work_order`, the CLI `--type` choices and the MCP
`ds_work_order_create` enum all read it. The closed `WORK_ORDER_TYPES` tuple and the four
private subsets are gone.

This is a function call inside one process. Nothing reads `contributes.work_order_types`
from a manifest, nothing persists a registration, and there is no MCP or CLI surface for
it, so a pack cannot use it yet. Three gaps remain before a registered type is fully
usable:

- A type needs a `business_work_order_types` row (its gates, executor and workflow
  template) before `ds work-order start` accepts it; the registry does not write one.
- The MCP `ds_work_order_create` enum is built when `integrations.mcp.tools` is imported,
  so a type must be registered before then to appear in it.
- The `dashboard_truth` close gate still names its types in a literal set in
  `close_main`; a pack cannot opt a type into it.

### Proposed

| Capability | Purpose | Standalone fallback |
| --- | --- | --- |
| `finding:record`, `finding:list` | Record and read findings in one typed shape: severity, location, `confidence`, `limitations`, `coverage` (`complete` \| `partial` \| `unknown`), evidence refs. The read model carries the three honesty fields (see "Present today"); storing them in `security_events` is built (migration 161), recording them through a capability is not. The capability needs `record_finding`'s three parameters exposed in `integrations/mcp/tools.py` as a client-gated write tool, and `finding:list` reads `core.findings.collect_findings`. | Append to a JSONL file beside the work; `list` reads it back. |
| `evidence:attach` | Attach a content-hashed artifact (scan output, reproduction log) to a finding or work order. | Write the file next to the work; record its SHA256 in the finding. |
| `gate:check` | Preview close gates for a work order. Exists in the `ds` CLI (`check_close_gates`), not in MCP, and cannot be exposed as a read tool as it stands: the preview runs the work order's `TEST-CHECK` and `API-CHECK` criteria and emits events (see the MCP server contract). It needs a mode that evaluates gates without running checks first. | Run each contributed gate's check command locally and print the results. |
| `registry:work_order_type` (reach), `gate:register` | Let a pack supply work-order types (the registry exists, see above, but nothing loads a manifest into it) and gates (no registry yet; close gates are still bound to types by the `business_work_order_types` rows and literal sets in `close_main`). | Types and gates are read from the manifest and applied by the pack's own checklist. |
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

- Does `registry:*` run at install time or per session?
- Who owns finding categories: the pack, or a shared vocabulary in the kernel?
- Does standalone mode persist state between sessions, or is it stateless?
- Which of `core.org_intelligence`, `core.pricing`, and `core.ontology` are live? Check
  for invoked-not-imported use before removing or moving anything.
