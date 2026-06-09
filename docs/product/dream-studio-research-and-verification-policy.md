# Dream Studio Research And Verification Policy

Status: draft_generated
Authority role: research and source-verification policy

## Decision Classes

- no_research_needed
- research_allowed
- research_required
- operator_verification_required
- blocked_due_to_source_uncertainty
- blocked_due_to_safety_or_sensitive_context

## When AI May Research

AI may research when information is missing, current, niche, source-attributed,
or useful for milestone execution, and the research does not require sensitive
access, target repo inspection, broad scans, or external service mutation.

## When AI Must Research

AI must research when a milestone depends on current facts, changing vendor or
tool behavior, laws/rules/standards, security guidance, API documentation,
product compatibility, pricing, schedules, or precise source attribution.

## When AI Must Stop For User Verification

AI must stop when research affects architecture direction, PRD/stage gates,
business requirements, security posture, legal/financial interpretation,
privacy/sensitive data handling, external project resume, or when sources are
conflicting, low-confidence, or materially incomplete.

## Source Recording

Research outputs must include:

- question being researched;
- sources used;
- source summary;
- confidence;
- relevance to the milestone;
- decision impact;
- whether operator verification is required;
- evidence refs.

## Confidence Classes

- high: primary or official sources agree and are current enough for the
  decision.
- medium: sources are credible but incomplete, secondary, or require context.
- low: sources are stale, conflicting, indirect, or insufficient.

## Straightforward Research

Straightforward research may be documented and used without stopping when the
source is official or primary, the decision is low-risk, no sensitive context is
involved, and PRD/stage gates already authorize the route.

## Nuanced Or High-Risk Research

Nuanced, source-conflicted, security-sensitive, legal, financial, business,
architecture, or operator-preference research must route to the operator before
being treated as authority.

## Evidence And Routing

Research decisions are stored as evidence refs and may influence milestone
routing. Research can trigger continue_internal, require_operator_approval,
hard_stop, generate_handoff, complete_milestone, or start_next_milestone through
the same policy engine used by PRD/stage gates.
