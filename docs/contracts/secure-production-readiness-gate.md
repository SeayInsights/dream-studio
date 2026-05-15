# Secure Production Readiness Gate

Dream Studio uses `secure_production_readiness_gate` to determine whether a
project has enough evidence to move toward real end-user deployment. It is a
workflow/control framework, not a monolithic skill.

## Authority

The gate reads repo contracts and SQLite authority, classifies applicability,
and persists assessment records only when an approved workflow calls the
SQLite-backed recorder with an injected connection. It does not run scanners,
inspect secrets, mutate external projects, deploy, run Docker, or claim legal
compliance.

SQLite authority records are additive and live in:

- `production_readiness_assessment_runs`
- `production_readiness_control_results`
- `production_readiness_findings`
- `production_readiness_remediation_work_orders`
- `production_readiness_skill_control_mappings`
- `project_health_scorecards`
- `project_readiness_scorecards`
- `release_readiness_records`
- `compliance_review_flags`

## Control Families

The reusable framework includes:

- 47 enterprise security controls
- API resilience
- database readiness
- migration, rollback, and destructive-change readiness
- caching correctness
- privacy/compliance applicability
- accessibility
- observability and logging
- performance and scalability
- backup, restore, and rollback
- dependency and supply-chain risk
- code quality and architecture boundaries
- release and publication readiness

Each control declares its ID, name, category, skill owner, workflow owner,
applicability rules, evidence requirements, allowed states, blocking policy,
remediation path, dashboard visibility, health/readiness/release impact,
Contract Atlas impact, and overlap mapping.

Module contracts are readiness inputs. The gate may use
`core.module_contracts` and `/api/shared-intelligence/module-contracts` to
understand module ownership, optional dependencies, disabled-module behavior,
and install profile membership before deciding which readiness controls apply.
Those contract reads are non-executing and do not write SQLite.

Project Details consumes readiness records as a derived operating view. It may
show readiness score, control coverage, findings, remediation Work Orders,
release blockers, module/runtime profile fit, validation state, stack evidence,
and dependency graph status. Missing readiness or dependency evidence must be
shown as unavailable or partial; manifest-derived dependency names do not become
confirmed graph edges or readiness evidence without source refs.

Contract Atlas lifecycle freshness contributes to release/publication
readiness. The readiness gate can treat the lifecycle manifest as evidence that
the atlas, maturity ledger, docs drift, PRD/README impact detection, dashboard
freshness, and sanitized public export checks were evaluated. The manifest is
derived evidence only; it does not run readiness controls, create findings,
write SQLite, or claim compliance.

Expert workflow catalog status contributes to readiness when process quality is
in scope. The readiness gate can treat
`/api/shared-intelligence/expert-workflows` as evidence that implementation,
quality, debugging, performance, design, SEO/content, documentation, data/API,
case-study, and career/portfolio workflows have owners, input/output
contracts, evidence requirements, validation requirements, scoring rubrics, and
privacy boundaries. The catalog does not execute workflows, create findings,
publish career artifacts, fill applications, or write SQLite.

## Skill And Control Overlap

Existing skills and gates are canonical when they already work:

- security review maps to the 47 enterprise controls.
- quality secure remains OWASP/STRIDE process guidance.
- quality harden and structure-audit map to code quality and architecture.
- `ci_gate.py`, lint baseline, docs drift, and pip-audit map to release and
  supply-chain readiness.
- lightweight GitHub PR smoke maps to remote confidence, while local
  `ci_gate.py` remains the heavy release-readiness evidence layer.
- project intelligence health stays health; production readiness is tracked
  separately.

New specialized owners are declared only where no existing skill has clear
ownership, such as database readiness, API resilience, caching correctness, and
privacy/compliance applicability.

## Run Policy

- Lightweight impact classification always runs.
- Targeted applicable checks run during normal development.
- Full applicable review runs for project intake, release/merge, publication,
  deployment, live cutover, dependency/runtime/security/database/Docker changes,
  major architecture changes, external onboarding, and scheduled dogfood gates.
- Tiny changes do not run all 47 controls unless the classifier or release gate
  requires it.

## Scores

Project health and project readiness are separate:

- health reflects current condition, blockers, stale state, validation health,
  telemetry, dependency evidence, security findings, and operational status.
- readiness reflects whether the project is ready for real users, release,
  deployment, publication, enterprise use, or broader rollout.

Scores must be evidence-backed and include confidence, missing evidence, blocking
factors, and linked controls. If evidence is insufficient, the score is
`partial` or `unavailable` with a reason. Missing evidence is not silently scored
as zero.

## Findings And Remediation

Findings must include project, assessment, control, family, skill owner,
workflow owner, applicability, status, severity, blocking flag, score impact,
evidence refs, source refs, file/line when applicable, remediation Work Order,
and not-applicable reason where applicable.

Remediation Work Orders generated by the gate are proposed records until a
separate Work Order authority approves execution.

## Project Details Integration

Project Details consumes production readiness as a derived read model over the
SQLite-backed readiness authority. It must show the separate project health and
project readiness concepts, control coverage, findings, blockers, remediation
links, missing evidence, and legal/compliance review flags when present.

If no project-scoped readiness assessment exists, Project Details reports
readiness as `unavailable` with missing evidence and a next action rather than
inventing a score. Missing evidence is not zero readiness unless a specific
control declares missing evidence to be a failure.

Analytics-only ingestion may import source-backed readiness assessments,
control results, findings, and health/readiness scorecards into the existing
SQLite authority tables. This supports standalone analytics deployments where
another system produced the evidence. Imported readiness must remain
evidence-backed and partial or unavailable when evidence is insufficient; it
must not claim compliance or release readiness merely because a score field is
present.

## AI Adapter Usage Readiness

Production readiness includes honest AI adapter usage accounting. A project can
use AI outcome quality, validation results, rework, files touched, commands run,
security/readiness findings, and duration as operational value signals. It must
not use fabricated token-to-dollar conversion for health, readiness, or release
decisions.

Readiness records should show cost as `unknown` when provider metadata, usage
exports, billing API data, explicit estimate metadata, or configured
subscription allocation evidence is absent. Missing cost evidence can lower
cost-confidence, but it is not scored as zero spend.

## Career, Scoped Agent, And Repo Intake Readiness

Production readiness treats Career Ops as private operational capability, not
public product evidence. Career scorecards must be evidence-backed or
unavailable, and public/demo outputs must exclude career data unless redacted
and approved.

Scoped agents affect readiness through context minimization, permission
boundaries, output contracts, validation requirements, and result normalization.
An agent result is never source authority by itself.

GitHub repo intake affects supply-chain, license, attribution, maintainability,
and integration readiness. A dependency, fork/vendor, or copied-code path is
not ready unless license/legal/security/maintenance evidence and operator
approval exist.
