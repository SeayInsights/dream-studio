# Security-By-Default Development Lifecycle Gate

Dream Studio treats security as a lifecycle control, not a standalone tab. Every
goal, milestone, Work Order, and code change receives a lightweight security
impact classification. Targeted controls run when the change signal is narrow;
full applicable review is required for high-risk lifecycle events.

## Canonical Framework

The canonical framework is the 47 enterprise security controls in
`docs/contracts/security-review-source-47-enterprise-scans.md`. The structured
scan catalog and crosswalk map those controls into Dream Studio's security
skill and review surfaces:

- `docs/contracts/security-review-47-scan-crosswalk.md`
- `docs/contracts/security-review-scan-catalog.yaml`
- `skills/security/SKILL.md`

The security skill may satisfy or orchestrate controls, but the 47-control
framework remains the policy authority.

## Lifecycle Policy

Full applicable 47-control review is required at:

- project intake
- release or merge readiness
- publication
- deployment or live cutover
- dependency, runtime, security, database, or Docker changes
- major architecture changes
- external project onboarding
- scheduled dogfood gates

Lightweight classification remains required for ordinary changes. Controls that
do not apply must record a reason. Unknown or deferred controls route to manual
review or dashboard attention; they do not silently pass.

## Finding Contract

Normalized findings must include:

- project
- file
- line
- severity
- control id
- status
- evidence
- remediation path

Live operator views must not include synthetic or demo findings. Derived
dashboard/API views may summarize findings, but the finding authority remains
SQLite evidence or file-backed review artifacts.

## Readiness Effect

Security status affects project health and release readiness:

- `ready`: security lifecycle clear
- `needs_manual_review`: release held for manual control review
- `unknown_requires_review`: release held for unknown control handling
- `blocked_by_open_findings`: release blocked by current findings

The lifecycle gate is non-executing. It classifies, routes, and records the
required control posture; it does not run scans, inspect secrets, mutate repos,
or write SQLite.

The secure production readiness gate consumes this lifecycle gate rather than
forking the 47-control model. Production readiness can add API, database,
caching, accessibility, observability, performance, dependency, code-quality,
privacy, rollback, and release controls, but enterprise security control
authority remains here.

Module boundary contracts provide the dependency context for lightweight
security classification. A change to `security_only`, `analytics_only`,
`adapter_router`, `external_project`, or `docker_optional` can alter which
controls are applicable, but the module contract route remains read-only and
does not execute scans, mutate repositories, run Docker, or write SQLite.

Contract Atlas lifecycle freshness is a release-gate signal, not a security
scan. The `/api/shared-intelligence/contract-atlas/freshness` route may appear
beside the security lifecycle route in the shared-intelligence router; it does
not inspect secrets, create findings, mutate SQLite, or change 47-control
applicability. Security docs still drift with router changes to confirm the
non-execution boundary.

## Project Portfolio Hydration

All Projects and Project Details consume normalized security findings as a
derived view over current security authority. Findings must remain traceable to
their source rows or evidence refs and include project, file, line, severity,
status, control or rule where available, and remediation path where available.

Project Details now exposes the 47-control applicability list, summary counts,
manual-review count, unknown count, and source framework refs alongside project
health, readiness, stack evidence, validation state, and attention items. This
dashboard route is still non-executing: it does not run scans, inspect secrets,
mutate external projects, draw inferred dependency edges as confirmed, or write
SQLite.

Migrated findings may be assigned to current projects only through
high-confidence mapping, such as an exact project id or the legacy
`project_<project_id_with_underscores>` alias. Findings that cannot be assigned
without ambiguity must be classified as `manual_review_required`,
`unassigned_legacy_finding`, `retention_only`, or `not_applicable` and kept out
of normal operator project cards until reviewed.

The 47 enterprise controls must be visible or honestly unavailable at the
project level. Not-applicable controls require reasons, unknown controls route
to manual review or dashboard attention, and synthetic/demo/test findings must
not appear in live operator views.

Analytics-only ingestion may import normalized security findings from approved
external producers into `security_findings`. This is an authority ingestion
path, not a scanner. It must preserve source/evidence refs, project mapping,
severity, status, rule/control where available, and remediation path where
available. Hooks, agents, workflows, Claude, Codex, and Docker are optional
producers, not required security dependencies.

## AI Usage Accounting Impact

Changes to adapter billing mode, token visibility, cost visibility, provider
usage source handling, telemetry collectors, or dashboard cost display receive
lightweight security impact classification. They normally target privacy,
secrets, logging, telemetry integrity, and release-readiness controls rather
than running the full 47-control review on every edit.

Full applicable review is still required if the accounting change affects
provider credentials, billing APIs, deployment, live cutover, external project
onboarding, database schema, or release/merge readiness. Findings must avoid
printing secrets or provider billing credentials.
