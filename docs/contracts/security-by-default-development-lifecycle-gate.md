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
