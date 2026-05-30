# Career Ops, Capability Center, And Scoped Agents

Dream Studio treats Career Ops as an optional private module and Capability
Center as a derived intelligence surface over authority records.

## Career Ops

Career Ops is opt-in and private by default. When enabled, profile, resume,
cover-letter, role-target, portfolio, case-study, interview, job-opportunity,
application, browser-automation, evidence, and scorecard records live in the
operator-local SQLite authority tables added by migration 044.

Career data must not appear in public exports, team rollups, sanitized portfolio
outputs, repo docs, or demo packets unless the operator explicitly approves a
redacted output. Missing evidence does not become a fake score; scorecards stay
`unavailable` or `partial` with a reason until supporting evidence exists.

Application automation boundaries are strict:

- no account creation;
- no CAPTCHA bypass;
- no user misrepresentation;
- no application submission without explicit approval or an approved
  per-application policy;
- pause for operator review on ambiguous questions;
- store sensitive fields only in approved local/private storage;
- avoid printing private identifiers unnecessarily;
- record filled, skipped, and operator-input-required fields.

The private dashboard/API status is exposed at
`/api/shared-intelligence/career-ops`.

## Capability Center

Capability Center summarizes skills, workflows, agents, controls, evaluations,
and hardening candidates from SQLite authority and repo-backed contracts. It is
a dashboard surface, not a source of truth. It reads invocation records,
hardening candidates, expert workflow declarations, scoped-agent declarations,
readiness controls, and task-attributed skill/workflow outcomes.

Installed dashboard command modes expose Capability Center only as a derived
view. `ds dashboard --status` reports readiness, `--serve` starts the local
server, `--open` opens the browser, and `--check` probes route health; none of
these modes publish Career Ops data or authorize agent execution.

If invocation or evaluation evidence is missing, Capability Center shows an
honest unavailable state instead of inventing success rates or scores. If task
attribution is missing, outcome counts remain unavailable rather than being
inferred from adapter memory or reports. The dashboard route is
`/api/shared-intelligence/capability-center`.

## Scoped Agents

Agents are scoped workers, not authority. Dream Studio remains canonical.
Agent declarations include purpose, allowed tools, read/write scope, data
sensitivity scope, required and forbidden context, output contract, validation
requirements, approval boundaries, risk level, max context budget, allowed data
classes, and result schema.

Agents do not receive full conversation history, unrelated project details,
private career data, secrets, raw local evidence, all Work Orders, all user
memories, or private operator data by default. Career-private context is
available only when Career Ops is enabled and the specific agent/task scope is
approved. Agent outputs normalize back into authority records rather than
becoming authority themselves.

Scoped agent declarations are exposed at
`/api/shared-intelligence/agents/registry`. Context packet previews are exposed
at `/api/shared-intelligence/agents/context-packet` and do not execute agents.
## Platform Hardening Refresh

Career Ops participates in platform hardening through privacy profiles, policy decisions, capability evaluations, and sanitized demo/export checks. Career data remains opt-in and private by default; public demos, team rollups, and sanitized exports must exclude resumes, applications, compensation strategy, personal notes, and browser automation traces unless explicitly approved and redacted.

## PRD Lifecycle Boundary

Career Ops data is not included in PRD context packets by default. Capability
Center may show that PRD lifecycle workflows exist and are evaluated, but
career/private data must stay out of Project Details, public exports, and
adapter context unless Career Ops is enabled and the task is explicitly scoped.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->
