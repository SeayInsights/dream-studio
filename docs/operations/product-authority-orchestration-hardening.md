# Product Authority, Workflow Architecture, and Orchestration Hardening

Dream Studio is moving repeatable work out of long procedural prompts and into
repo-owned contracts. The first slice defines `workflow_contract` and
`skill_contract` models in source code so workflows and skills can be evaluated,
routed, versioned, learned from, deprecated, and promoted through stable rules.

## Why These Contracts Exist

Agents, adapters, skills, and workflows produce candidate outputs. They are not
authority by themselves. Dream Studio authority remains in PRDs, stage gates,
milestone state, Work Orders, approved operator decisions, validation evidence,
and current SQLite authority records.

Workflow and skill contracts make repeatable work explicit:

- what triggers the workflow or skill;
- what inputs and outputs are expected;
- what context is required, allowed, or forbidden;
- what evidence must be captured;
- what actions are allowed or forbidden;
- what stop gates and approvals are required;
- what validation, tests, and evals prove the result;
- what learnings and failure classes should be emitted;
- when a skill can be deprecated, removed, retained, or superseded.

The goal is not to add another report. The goal is to make workflow behavior
machine-checkable before it becomes runtime authority.

## Repo-Owned Contract Authority First

This slice is source-only. The canonical contract definitions live in:

`core/shared_intelligence/workflow_skill_contracts.py`

That module does not import SQLite, inspect runtime state, run migrations, or
write to `C:\Users\Dannis Seay\.dream-studio`. Runtime persistence can be added
later through an explicitly approved additive migration, but this first slice
keeps contract authority in repo source so tests can enforce the shape before
any database writes exist.

## Workflow Contracts

A `workflow_contract` describes a repeatable operating path such as analyze-repo,
security review, polish review, CI/CD feedback analysis, whole-system review, or
multi-agent orchestration. It includes:

- identity and lifecycle state;
- triggers and non-triggers;
- input and output contracts;
- required, allowed, and forbidden context;
- allowed and forbidden actions;
- evidence, validation, tests, and evals;
- stop gates and approval requirements;
- mutation risk;
- learning emissions and failure classes;
- downstream action classes;
- privacy and Contract Atlas impact.

Mutation-capable workflows must declare stop gates and approval requirements.
Runtime, SQLite, and migration risks require explicit runtime or database stop
gates. External-project mutation requires explicit external-project approval.
Secrets or sensitive access requires an explicit approval boundary.

## Skill Contracts

A `skill_contract` describes a reusable skill family such as planning, design
review, debugging, security review, career operations, or implementation
support. It includes:

- identity, version, family, lifecycle state, and owner;
- capabilities;
- when to use and when not to use;
- input and output contracts;
- required, allowed, and forbidden context;
- allowed and forbidden actions;
- evidence expectations and validation requirements;
- tests, evals, gotcha inputs, and learning inputs;
- emitted learning types;
- versioning, deprecation, removal, rollback, and supersession policy;
- privacy boundary.

Removal-candidate or removed skills must include a removal policy. Mutation-
capable skills must include forbidden actions. Skills that could access secrets
or sensitive material must declare explicit forbidden-action and approval
boundaries.

## How This Supports Later Milestones

The contract module provides a foundation for:

- analyze-repo profile hardening and downstream action classification;
- design skill and polish-review hardening;
- skill lifecycle and removal planning;
- learning candidate extraction and promotion;
- gate evolution;
- CI/CD and GitHub feedback ingestion;
- global and project-specific security learning;
- build intent classification;
- whole-system review;
- multi-agent work graph orchestration;
- scoped context packets;
- agent result envelopes;
- verification and reconciliation before authority updates.

Each later slice should consume these contracts instead of expanding procedural
prompts. If a workflow repeatedly fails, the failure should map to a contract
field: missing context, weak evidence, missing gate, missing eval, unclear owner,
or missing operator question.

## Current Validation

Focused tests live in:

`tests/unit/test_workflow_skill_contracts.py`

They validate:

- valid read-only workflow contracts;
- valid mutation-capable workflow contracts;
- invalid missing evidence requirements;
- mutation risk without stop gates or approval requirements;
- runtime/SQLite/migration risk without explicit stop gates;
- external-project mutation without explicit approval;
- active and removal-candidate skill contracts;
- invalid lifecycle states;
- removal policy requirements;
- secret/sensitive access approval boundaries;
- structured validation output shape;
- absence of runtime SQLite dependency.

## Future Slices

Recommended next bounded slices:

1. Harden analyze-repo with profile contracts and downstream action classes.
2. Add execution outcome, failure classification, and learning candidate
   contracts that reference workflow and skill contracts.
3. Add learning promotion and gate recommendation decisions.
4. Add CI/CD and GitHub failure ingestion contracts.
5. Add build intent and whole-system review gates.
6. Add multi-agent work graph, context packet, result envelope, verification,
   and reconciliation contracts.

No future slice should mutate runtime SQLite, external projects, dependencies,
or live adapter state without a separate explicit approval boundary.
