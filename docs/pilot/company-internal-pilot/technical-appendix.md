# Dream Studio Internal Pilot Technical Appendix

## Runtime Model

Dream Studio runs as an installed local platform. Product source, installed state, dashboard/API read models, adapter projections, and sanitized exports are separate surfaces with different authority levels.

For the internal pilot:

- source code remains in the Dream Studio repo;
- installed runtime state remains local;
- SQLite-backed authority is the durable operational store;
- dashboard/API output is derived;
- sanitized exports are generated artifacts;
- adapters and context packets are not source authority.

## Pilot Profile

Recommended profile: `analytics_only_observe`

Profile behavior:

- reads installed runtime and module status;
- supports normalized evidence ingestion when explicitly provided;
- exposes dashboard/API read models;
- shows honest empty states when no data exists;
- does not require hooks, agents, workflows, Claude, Codex, Docker, repo mutation, or provider API keys.

## Module Scope

Enabled:

- core runtime checks;
- analytics-only ingestion and read models;
- dashboard derived views;
- security/readiness summaries;
- telemetry summaries;
- adapter router status;
- context-packet fallback;
- Contract Atlas and maturity views;
- optional token/usage read models when approved data exists.

Disabled by default:

- full local dogfood;
- Docker profiles;
- external project mutation;
- cleanup/delete/archive/dedup/compaction;
- push/tag/merge/deploy;
- secret/sensitive access;
- Career Ops;
- browser automation.

## Data Ingestion Contract

Pilot data should be normalized before ingestion. Acceptable inputs include project summaries, CI/test/security/coverage summaries, dependency manifests, PRD excerpts approved for pilot use, readiness controls, adapter usage summaries, and manual evidence packets.

Ingestion rules:

- source refs should identify the supplied packet or report without exposing private paths;
- records must preserve unknown, partial, unavailable, and manual-review states;
- token usage must not be converted into cost unless provider billing metadata or approved allocation exists;
- findings should include severity, status, control or rule where available, evidence refs, and remediation path when applicable;
- low-confidence data should be marked manual-review or omitted from shared views.

## Security And Readiness Gates

The pilot can show:

- security-by-default lifecycle gate;
- 47-control enterprise security applicability model;
- production readiness controls;
- project health and readiness separation;
- missing evidence and manual-review states;
- release readiness and blocker summaries where evidence exists.

The pilot must not claim:

- legal compliance;
- regulatory certification;
- production deployment readiness without evidence;
- cost accuracy without a cost source;
- live adapter execution proof beyond recorded status.

## Adapter Runtime

Adapter status can be explained through:

- supported CLI/app/configured surfaces where validated;
- unsupported or unproven surfaces marked honestly;
- MCP-capable clients where router contracts exist;
- context-packet-only fallback for plain chat or unsupported tools.

Adapter rules:

- adapters do not own authority;
- private model memory is not authority;
- adapter results must normalize back into Dream Studio records;
- context packets should include only scoped task context;
- cost and token visibility must be classified honestly.

## Public Demo Materials

Use only sanitized packet artifacts for shared pilot materials:

- `docs/demo/sanitized/README.md`
- `docs/demo/sanitized/5-minute-script.md`
- `docs/demo/sanitized/15-minute-technical-walkthrough.md`
- `docs/demo/sanitized/fallback-plan.md`
- synthetic screenshots in `docs/demo/sanitized/screenshots/`

These materials are public-sanitized and do not include live operator dashboard views.

## Private-Live Walkthrough Review

Before any private-live walkthrough:

1. Define audience.
2. Define whether recording is allowed.
3. List screens and data classes to show.
4. Confirm no secrets or sensitive values are displayed.
5. Confirm no private records are copied into shared materials.
6. Confirm no external mutation, push, deploy, Docker, cleanup, or secret access occurs.
7. Record a private-live verdict: approved, needs redaction, or use sanitized packet only.

## Validation Commands

Suggested private operator checks:

- `ds status`
- `ds validate`
- `ds modules`
- `ds adapters`
- `ds router`
- `ds contract-atlas`
- `ds context-packet`
- `ds dashboard --status`
- `ds dashboard --serve`
- `ds dashboard --check`

Do not paste raw outputs into public or pilot-facing materials if they contain local runtime details. Summarize pass/fail and sanitize before sharing.

## Acceptance Criteria

The pilot is successful when:

- participants understand the local-first authority model;
- analytics-only observe mode is clear and useful;
- security/readiness gates are understandable;
- adapter boundaries are understood;
- privacy boundaries are trusted;
- no forbidden action is required;
- feedback identifies a clear next route.
