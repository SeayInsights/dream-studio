# File Structure Authority Policy

## Purpose

This policy defines where Dream Studio canonical artifacts, generated local artifacts, Work Order evidence, approvals, continuity records, reports, handoffs, contracts, security artifacts, and projection outputs belong.

It aligns with:

- `docs/contracts/artifact-format-policy.md`
- `docs/contracts/handoff-packet-contract.md`
- `docs/contracts/work-order-paused-work-contract.md`
- `docs/contracts/security-review-report-artifact-contract.md`

This policy is documentation/static-test guidance only. It does not move files, reorganize the repository, implement an enforcement engine, add runtime behavior, add dashboard builders, create database/event-ledger integration, or authorize target repository access.

## Authority Model

Location authority and format authority are separate but connected:

- The artifact-format policy decides whether an artifact is canonical source or generated/rendered projection.
- This file-structure policy decides where that artifact belongs.
- A correct format in the wrong location is still structure drift.
- A generated artifact in a canonical source location does not become canonical by placement alone.
- A target-repo artifact copied into Dream Studio does not become Dream Studio source unless a later Work Order explicitly creates a redacted, approved, file-backed Dream Studio artifact.

## Canonical Repo-Owned Locations

Repo-owned canonical files belong in the Dream Studio repository when they define source contracts, operations guidance, architecture, code, interfaces, tests, or validation schemas.

| Location | Canonical role | Git ownership |
| --- | --- | --- |
| `docs/contracts/` | Contract and policy source documents. | Commit when changed intentionally. |
| `docs/operations/` | Operational guidance and procedures. | Commit when changed intentionally. |
| `docs/architecture/` | Architecture decisions, diagrams, and design source. | Commit when changed intentionally. |
| `core/` | Dream Studio core source code. | Commit when changed intentionally. |
| `interfaces/` | CLI, adapter, and external interface source code. | Commit when changed intentionally. |
| `tests/` | Static, unit, contract, and regression tests. | Commit when changed intentionally. |
| `schemas/` | Future schema source if contract schemas are introduced. | Commit only when a schema contract or implementation phase explicitly creates it. |

Do not create duplicate contract roots such as `contracts/`, `contract/`, `docs/policies/`, or `docs/specs/contracts/` unless a later Work Order updates this policy and explains the authority split.

## Generated Local Meta Locations

Generated local Work Order artifacts belong under the user's Dream Studio meta root. They are local evidence/projection artifacts by default and are not repo-owned source unless a later Work Order intentionally promotes a redacted fixture or contract example into the repo.

Baseline generated local locations:

| Location | Artifact role |
| --- | --- |
| `~/.dream-studio/meta/audit/` | Phase reports, generated Handoff Packet prompts, audit notes, and local narrative evidence. |
| `~/.dream-studio/meta/work-orders/` | Work Order-specific local artifact storage. |
| `~/.dream-studio/meta/work-orders/<work-order-id>/approvals/` | Approval artifacts and operator decision gates. |
| `~/.dream-studio/meta/work-orders/<work-order-id>/evidence/` | General Work Order evidence and validation evidence. |
| `~/.dream-studio/meta/work-orders/<work-order-id>/continuity/` | PausedWork and other continuity artifacts. |
| `~/.dream-studio/meta/work-orders/<work-order-id>/security/` | Security review reports, findings, evidence, release gates, and accepted risks. |
| `~/.dream-studio/meta/work-orders/<work-order-id>/projections/` | Future generated projection outputs, if projections are generated later. |

Generic public docs should use portable paths. Absolute Windows paths belong only in local file-backed operator reports, handoffs, evidence, or target-specific context that is not published as generic product documentation.

## Work Order Artifact Structure

A Work Order should use one root:

`~/.dream-studio/meta/work-orders/<work-order-id>/`

Recommended child directories:

| Child path | Contents |
| --- | --- |
| `approvals/` | `approval.json`, `request.json`, `operator_decision.json`, and approval evidence. |
| `evidence/` | Validation evidence, mutation evidence, status evidence, and source-proof records. |
| `continuity/` | `paused_work.yaml` and future continuity records. |
| `security/` | Security review artifacts. |
| `security/findings/` | `SecurityFindingRecord` YAML files. |
| `security/evidence/` | `SecurityEvidenceRecord` YAML files. |
| `security/accepted_risks/` | `AcceptedRiskRecord` YAML files. |
| `dashboard/` | Dashboard projection input artifacts created by security reviews. |
| `projections/` | Future generated projection records when the projection contract requires them. |
| `evals/` | Deterministic eval artifacts. |

Do not write Work Order artifacts into target repositories. Do not spread one Work Order's evidence across unrelated local roots unless a report explicitly references the split and explains why.

## Audit Report And Handoff Locations

Phase reports and generated standalone Handoff Packet prompts belong under:

`~/.dream-studio/meta/audit/`

Use these naming patterns:

| Artifact | Naming pattern |
| --- | --- |
| Phase report | `YYYY-MM-DD-phase<phase-id>-<slug>-report.md` |
| Generated handoff prompt | `YYYY-MM-DD-phase<phase-id>-<slug>-prompt.md` |
| Hold or recovery prompt | `YYYY-MM-DD-phase<phase-id>-<slug>-prompt.md` with the handoff type declared inside the packet. |

Reports and Handoff Packets are Markdown source artifacts unless another contract explicitly chooses a different canonical format. Rendered HTML/PDF copies are exports, not report authority.

## Evidence, Approval, Continuity, Security, And Projection Locations

| Artifact family | Required or preferred location | Format authority |
| --- | --- | --- |
| Approval artifact | `~/.dream-studio/meta/work-orders/<work-order-id>/approvals/approval.json` | JSON strict machine/operator gate. |
| Operator decision request | `~/.dream-studio/meta/work-orders/<work-order-id>/decisions/request.json` or `approvals/request.json` when a phase has not yet split decisions. | JSON strict machine/operator gate. |
| Operator decision | `~/.dream-studio/meta/work-orders/<work-order-id>/decisions/operator_decision.json` or `approvals/operator_decision.json` when a phase has not yet split decisions. | JSON strict machine/operator gate. |
| General evidence | `~/.dream-studio/meta/work-orders/<work-order-id>/evidence/` | YAML for operator-facing structured evidence, JSON for strict machine evidence, Markdown for narrative evidence. |
| Paused work | `~/.dream-studio/meta/work-orders/<work-order-id>/continuity/paused_work.yaml` | YAML continuity source. |
| Security review report | `~/.dream-studio/meta/work-orders/<work-order-id>/security/review_report.yaml` | YAML structured security source. |
| Security finding | `~/.dream-studio/meta/work-orders/<work-order-id>/security/findings/<finding-id>.yaml` | YAML finding source. |
| Security evidence | `~/.dream-studio/meta/work-orders/<work-order-id>/security/evidence/<evidence-id>.yaml` | YAML evidence source. |
| Accepted risk | `~/.dream-studio/meta/work-orders/<work-order-id>/security/accepted_risks/<risk-id>.yaml` | YAML risk decision source. |
| Release gate | `~/.dream-studio/meta/work-orders/<work-order-id>/security/release_gate.yaml` | YAML release-gate source. |
| Dashboard projection input | `~/.dream-studio/meta/work-orders/<work-order-id>/dashboard/projection_inputs.yaml` | YAML operator-facing projection input unless the projection contract requires JSON. |
| Projection output | `~/.dream-studio/meta/work-orders/<work-order-id>/projections/<projection-id>.json` | JSON projection record by default. |
| Event export | `~/.dream-studio/meta/work-orders/<work-order-id>/evidence/<export-id>.jsonl` | JSONL/NDJSON replayable stream. |

## What Belongs In Git

Commit these when intentionally changed by an approved Dream Studio Work Order:

- contract and policy source under `docs/contracts/`;
- operations docs under `docs/operations/`;
- architecture docs under `docs/architecture/`;
- Dream Studio source code under `core/` and `interfaces/`;
- static/unit/contract tests under `tests/`;
- future schema source under `schemas/` when introduced by contract.

Do not commit local operator evidence from `~/.dream-studio/meta/` unless a later Work Order intentionally creates a redacted fixture, sample, or contract example inside the repo.

## What Belongs Under Local Meta

Keep these local under `~/.dream-studio/meta/`:

- phase reports;
- generated Handoff Packet prompts;
- approval artifacts;
- operator decision artifacts;
- Work Order evidence;
- mutation and validation evidence;
- paused-work continuity records;
- security review outputs;
- release-gate artifacts;
- dashboard projection inputs generated from a review;
- generated projection records;
- local audit notes.

Local meta artifacts may be referenced by reports and handoffs, but they are not automatically repo-owned source.

## Generated Or Ignored Files

Treat these as generated, local, or export artifacts unless a later contract says otherwise:

- files under `~/.dream-studio/meta/`;
- rendered HTML, PDF, SVG, and PNG exports;
- generated dashboard projection records;
- temporary runtime output;
- build output and dist folders;
- target repo snapshots or copied target files;
- scanner outputs, unless an approved Work Order stores them as redacted evidence under local meta.

Generated files must not become canonical source by accident. If a generated output needs to become a fixture, sample, or contract source, create a separate Work Order that explains the promotion, redaction, validation, and location.

## Naming Conventions

| Artifact | Naming rule |
| --- | --- |
| Work Order ID | `wo-dream-studio-<phase-id>-<short-slug>` for Dream Studio work. |
| Phase report | `YYYY-MM-DD-phase<phase-id>-<short-slug>-report.md`. |
| Handoff prompt | `YYYY-MM-DD-phase<phase-id>-<short-slug>-prompt.md`. |
| Approval artifact | `approval.json` inside the Work Order `approvals/` directory. |
| Operator decision request | `request.json` inside `decisions/` or `approvals/`. |
| Operator decision | `operator_decision.json` inside `decisions/` or `approvals/`. |
| Evidence artifact | `<evidence-id>.yaml`, `<evidence-id>.json`, or `<evidence-id>.md` depending on format authority. |
| Mutation evidence | `mutation_validation_evidence.yaml` when recording a bounded mutation slice. |
| PausedWork continuity | `paused_work.yaml`. |
| Security review report | `review_report.yaml`. |
| Security finding | `<finding-id>.yaml` under `security/findings/`. |
| Security evidence | `<evidence-id>.yaml` under `security/evidence/`. |
| Release gate | `release_gate.yaml`. |
| Dashboard projection input | `projection_inputs.yaml`. |
| Projection output | `<projection-id>.json` unless the projection contract requires another format. |

Use stable lowercase slugs with hyphens for file names. Use stable IDs from the artifact contract inside the file.

## Generated-Vs-Canonical Authority Rules

- Canonical repo-owned contracts live under `docs/contracts/`.
- Canonical local Work Order evidence lives under the specific Work Order root in `~/.dream-studio/meta/work-orders/`.
- Generated reports and handoffs in `~/.dream-studio/meta/audit/` are file-backed evidence for continuity, but they do not replace repo-owned contracts.
- Dashboard, projection, report, and export artifacts must declare or preserve source artifact refs.
- A dashboard projection must not become authority over Work Orders, operator decisions, Handoff Packets, security reports, release gates, or paused-work records.
- Runtime output must not rewrite canonical contracts or local evidence unless a later approved Work Order explicitly grants that mutation.
- If two artifacts disagree, prefer the artifact family authority named in this policy and open a reconciliation Work Order rather than silently choosing the newer file.

## Duplicate Contract Location Rules

- Keep contracts in `docs/contracts/`.
- Keep operational guidance in `docs/operations/`.
- Keep architecture guidance in `docs/architecture/`.
- Do not create parallel contract trees.
- Do not store canonical contracts under `~/.dream-studio/meta/`.
- Do not store target-specific contracts inside target repositories unless a later target-specific Work Order explicitly owns that target contract.
- Samples may live next to the contract they explain, using `.sample.yaml`, `.sample.json`, or a clearly named fixture path.

## Target-Repo Artifact Leakage Rules

Dream Studio must not leak target repository artifacts into Dream Studio source or local meta by accident.

- Do not write generated artifacts inside target repositories unless a later approved Work Order explicitly authorizes target artifact writes.
- Do not copy target source files into Dream Studio contracts, reports, tests, or fixtures unless the copy is explicitly approved, redacted if needed, and necessary for evidence or regression testing.
- Do not commit target repository secrets, `.env` values, private keys, credentials, build outputs, generated dist artifacts, or dependency lockfiles from a target repo into Dream Studio.
- Target file paths may appear in Dream Studio reports and handoffs as references when they are file-backed evidence, but referenced paths are not copied source artifacts.
- Untracked target entries must remain uninspected and unmodified unless a later Work Order explicitly approves that scope.

## Dashboard, Runtime, And Projection Guardrails

- Dashboard HTML, dashboard UI state, projection records, and rendered reports are derived views unless a future contract explicitly says otherwise.
- Projection outputs must read from canonical source artifacts or local operational state and must not create duplicate authority paths.
- Runtime operational stores may be canonical only when the state contract or a later runtime contract names them as authority.
- Dashboard/report output must not approve risk, mutate repos, run scans, run validation, replace Work Order reports, or overwrite operator decisions.
- Projection exports must include source refs and stale/missing evidence markers when inputs are incomplete.

## Lightweight Enforcement Checklist

Each future Work Order that creates or changes artifacts should answer:

- Is this artifact canonical source or generated projection?
- Does the artifact use the correct format?
- Does the artifact live in the correct location?
- Is the artifact allowed to be committed?
- Is this repo-owned, local-meta-owned, target-repo-owned, or generated?
- Does this create a duplicate authority path?
- Does this accidentally make dashboard/report output authoritative?
- Does this leak target-repo artifacts into Dream Studio?
- Does this require schema validation now or later?
- Are forbidden paths excluded?

If any answer is unclear, pause the Work Order or create a small contract-stabilization follow-up before moving or generating artifacts.
