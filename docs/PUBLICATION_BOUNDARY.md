# Publication Boundary

Dream Studio is public source plus private local authority. The public GitHub repository should accurately represent the current product without publishing private operational history.

## Public Allowlist

The public repo may contain:

- product source code;
- public documentation;
- schema migrations and tests;
- examples, templates, and synthetic fixtures;
- adapter projection templates;
- sanitized demos;
- sanitized release notes;
- public license, security, and contribution guidance.

## Private By Default

Keep these out of Git unless separately sanitized and approved:

- `.dream-studio/` runtime state;
- SQLite DB files, WAL/SHM files, dumps, and backups;
- local Work Orders, handoffs, continuation packets, approval artifacts, and operator decisions;
- raw telemetry, raw logs, hook traces, dashboard runtime logs, and token traces;
- unsanitized task attribution evidence, including private file paths,
  commands, Work Order context, validation output, adapter traces, or
  security/readiness impact details that expose private operational history;
- cutover, cleanup, rollback, dogfood, release, and local audit evidence;
- generated prompts and private context packets;
- private career profiles, resumes, cover letters, role strategies,
  application records, recruiter/contact notes, compensation strategy,
  browser automation evidence, and career scorecards;
- GitHub repo intake evidence that includes unsanitized adoption analysis,
  license/security notes, private Work Orders, or attribution/legal review
  context;
- external-project details not intentionally public;
- private external-target intake evidence, dirty-state snapshots, Work Orders,
  handoffs, validation reports, and route decisions;
- secret, credential, token, or private data values.

## Current Repo Hygiene

`.gitignore` excludes local runtime state, database files, backups, logs, and local evidence exports. If a private file has been committed in the past, remove it from current tracking without deleting the local copy, then classify whether history rewrite is required.

Repo publication readiness is checked through the repo-owned command:

```powershell
python interfaces\cli\repo_publication_readiness.py --strict
```

The command audits tracked file paths, ignored/untracked boundaries, Git history
path names, Apache-2.0 references, README/PRD product framing, and
private-content/secret-pattern rules without printing matched secret values.
Use `--execute --output-dir docs\publication` only when intentionally
refreshing public publication evidence artifacts.

## Git History Policy

- Non-secret historical product docs can usually remain in history after current-state cleanup.
- Private local DB backups, raw logs, local evidence, or sensitive operator state in history require a history rewrite risk assessment.
- Secrets, credentials, tokens, or sensitive private data in history require immediate operator approval before any rewrite and should trigger rotation guidance.
- Never force-push or rewrite remote history without explicit operator approval.

## Documentation Rule

Public docs should describe Dream Studio as a local-first AI orchestration and operational intelligence platform. Adapter-specific docs may describe Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP, shell, or local-model surfaces, but must not frame any adapter as the product itself.

Installed command docs may include `ds dashboard --status`, `--serve`,
`--open`, and `--check` as public-safe command names. They must not include
private local URLs, local runtime paths, dashboard screenshots from live
operator state, or raw dashboard/API payloads unless separately sanitized.

External project and Docker docs may describe the public-safe policy and module
contracts, but must not publish private target details, local scans, target
dirty-state output, target paths, container runtime evidence, or operational
approval artifacts. Final productization closeout can be summarized publicly
only as sanitized readiness status; private release evidence stays local.

Career Ops may be documented as an optional private module, but resumes,
profile fields, application history, automation traces, and career strategy are
private by default. Public portfolio or case-study outputs require explicit
operator approval and redaction.

GitHub repo intake may be documented as a workflow, but actual evaluation
evidence remains private until license, attribution, security, and publication
boundaries are satisfied.

Task attribution may be documented as a product capability, but live operator
records are private by default. Public examples must be synthetic or sanitized
and must not expose private Work Orders, file paths, command output, raw
validation evidence, security findings, or external-project details.

Platform-hardening may be documented as a product capability, but raw
evaluation evidence, policy decisions, connector payloads, local watch results,
team rollup source material, installer logs, and demo/case-study evidence are
private by default. Public outputs must use the `public_sanitized` visibility
profile and must exclude raw Work Orders, handoffs, operator decisions, local
paths, raw telemetry, local evidence, cutover/rollback details, private project
details, career/application data, compensation strategy, secrets/auth/config
values, and unsanitized security findings.

## Contract Atlas Export Rule

The Contract Atlas is private/local by default. Public atlas exports are allowed
only when sanitized: local paths, live runtime state, local adapter config
contents, private evidence paths, backups, raw telemetry, and operator-specific
metadata must be removed or replaced with non-sensitive placeholders.

`ds contract-atlas-refresh --output-dir <dir> --execute` is the supported export
refresh surface. It writes the public sanitized atlas and freshness manifest to
an explicit directory, and writes a private/internal atlas only when
`--include-private` is supplied. Private/internal exports are not repo-safe and
must remain in operator-local runtime or review locations.

## Release-Gate Runtime Boundary

Release-gate validation evidence may be summarized publicly only after the gate
runs against isolated temporary Dream Studio state and the active installed
SQLite hash remains unchanged. Public pilot or demo packets should reference
sanitized release status, not raw gate output containing local paths, runtime
state locations, or private operational evidence.

## Legacy Upgrade Boundary

Legacy install detection and migration docs may describe the generic safe
upgrade process, but public exports must not include old source paths, backup
paths, launcher contents, Claude/Codex settings, adapter projections, local
runtime paths, or row-level migration evidence. Old Work Orders, handoffs,
reports, evidence folders, audit files, prompts, caches, logs, backups, and
rollback details remain private unless separately sanitized and approved.

## PRD Lifecycle Boundary

PRD lifecycle behavior may be documented publicly, but project-specific PRD
versions, assumptions, open questions, change orders, route reconciliations,
evidence refs, and Work Order details are private unless explicitly exported
through a sanitized profile. Public examples must be synthetic or redacted and
must not expose private operator history, local paths, external-project details,
career data, or unsanitized security/readiness findings.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->

<!-- Last reviewed 2026-05-20 — pipeline optimization landed (migration 057 extends ds_work_order_types with workflow_template, precondition_skill, task_generator, resolution_instructions; CLI gains `ds project state` single-query, auto-advance, gotcha injection, brief mode); doc policy unchanged here. -->
