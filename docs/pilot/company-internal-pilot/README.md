# Dream Studio Company Internal Pilot Packet

Status: `pilot_packet_ready`

Recommended pilot mode: `analytics_only_observe`

Demo path: `docs/demo/sanitized/README.md`

This packet describes a controlled internal pilot for Dream Studio using installed local runtime behavior, sanitized demo artifacts, analytics-only ingestion, observe-mode dashboard review, Contract Atlas maturity views, security/readiness gates, and adapter/context-packet boundaries.

The pilot is local-first and non-invasive. It does not require push, deploy, cloud hosting, Docker, external project mutation, secret access, AI provider API keys, or broad organization integration unless a separate approval expands the scope.

## Target Audience

- Engineering leaders evaluating AI-assisted development governance.
- Platform, DevOps, security, and data leaders who need evidence-backed operational visibility.
- Product and operations leaders who want safer AI work loops without turning dashboards or adapters into authority.
- Pilot operators who can run installed Dream Studio locally and provide structured feedback.

## Pilot Goals

- Prove Dream Studio can observe project, validation, security, readiness, adapter, telemetry, and Contract Atlas state without exposing private operational history.
- Prove analytics-only and observe-mode use cases can run without hooks, agents, workflows, Claude, Codex, Docker, repo mutation, or provider API keys.
- Demonstrate how sanitized demo artifacts explain observe, assist, and operate modes.
- Validate that missing evidence is shown honestly instead of converted into fake confidence.
- Collect feedback on usefulness, clarity, setup friction, privacy posture, and pilot fit.

## Pilot Non-Goals

- No production deployment.
- No public release.
- No cloud-hosted service.
- No organization-wide integration.
- No automatic remediation or cleanup.
- No external project mutation.
- No secret inspection.
- No browser automation against job applications or private accounts.
- No use of private operator history as pilot evidence.
- No compliance certification claims.

## Recommended Mode

Use `analytics_only_observe` for the first pilot.

This mode enables:

- installed command health checks;
- analytics-only normalized ingestion;
- dashboard/API read models;
- project and readiness summaries where data is provided;
- Contract Atlas maturity and docs/export freshness views;
- security/readiness status;
- adapter and context-packet status;
- sanitized demo walkthrough.

This mode disables:

- external project mutation;
- repo mutation by default;
- push, deploy, tag, or merge actions;
- Docker execution;
- secret or credential inspection;
- live adapter execution requirements;
- autonomous cleanup, archive, deduplication, or compaction.

Assist or full local dogfood mode can be considered only after the first pilot proves value and receives separate scope approval.

## Enabled Modules

| Module | Pilot Status | Reason |
| --- | --- | --- |
| core | enabled | Required for installed runtime and command health. |
| analytics_only | enabled | Primary pilot mode for normalized evidence ingestion and read models. |
| dashboard_only | enabled | Derived dashboard review with honest empty states. |
| security_only | enabled | Security posture summaries and finding visibility where evidence exists. |
| telemetry_only | enabled | Runtime and validation telemetry summaries where available. |
| adapter_router_only | enabled | Adapter status and context-packet fallback without making adapters authority. |
| shared_intelligence_only | enabled | Contract Atlas, module profiles, and capability status. |
| token_only | optional | Enabled only when usage data is provided without inventing cost. |

## Disabled Modules

| Module Or Capability | Default Status | Boundary |
| --- | --- | --- |
| full local dogfood | disabled | Requires separate operator approval for broader local operations. |
| Docker profiles | disabled | Optional runtime boundary, not core authority. |
| external project mutation | disabled | Requires explicit target and scoped approval. |
| cleanup/delete/archive/dedup/compaction | disabled | Requires separate approval and rollback plan. |
| push/tag/merge/deploy | disabled | Requires separate release approval. |
| secret/sensitive access | denied | Do not inspect without explicit approval. |
| Career Ops | disabled | Private and opt-in only; excluded from pilot outputs by default. |
| browser automation | disabled | Requires separate target, purpose, and review boundary. |

## Allowed Data Sources

Allowed data must be intentionally provided for the pilot and should be sanitized when possible:

- project inventory summaries;
- package manifests and dependency summaries;
- CI status summaries;
- JUnit or test report summaries;
- SARIF or security report summaries;
- coverage summaries;
- validation results;
- readiness control summaries;
- stack and dependency evidence summaries;
- PRD or product summary excerpts approved for pilot use;
- adapter usage summaries where token and cost visibility are clearly classified;
- manual evidence packets with private details redacted.

## Forbidden Data Sources

Do not provide or ingest:

- private Work Orders;
- handoffs;
- raw local evidence;
- raw telemetry;
- operator decisions;
- career data;
- application data;
- compensation strategy;
- private external-project details;
- sensitive project details;
- secrets, credentials, tokens, keys, or auth files;
- live local runtime paths;
- backup or rollback internals;
- unsanitized security findings;
- customer, employee, health, financial, child, or regulated personal data unless a separate legal/privacy review approves the scope.

## Privacy And Security Boundaries

- Dream Studio remains local-first.
- SQLite-backed authority stays local to the installed runtime.
- Dashboard/API output is derived and not the source of truth.
- Adapter results must normalize back into Dream Studio records.
- Unsupported adapters use context-packet fallback.
- Public or pilot-facing materials use sanitized packet artifacts.
- Live dashboard review is private-only until separately sanitized.
- Missing evidence is shown as missing or partial.
- Token usage is usage telemetry, not cost, unless an approved source provides billing metadata.
- Security/readiness results are evidence-backed and must not overclaim compliance.

## Install And Setup Checklist

1. Confirm the installed `ds` command works from outside the repo.
2. Run `ds status`.
3. Run `ds validate`.
4. Run `ds modules` and confirm `analytics_only` is available.
5. Run `ds adapters` and confirm unsupported adapters are represented honestly.
6. Run `ds contract-atlas` or use the sanitized Contract Atlas export.
7. Use the sanitized demo packet for the public pilot walkthrough.
8. If importing pilot data, use normalized, approved, sanitized evidence only.
9. Do not enable Docker, external mutation, secret access, or push/deploy actions.
10. Capture feedback with `feedback-template.md`.

## Demo Script

Use the sanitized public packet:

- `docs/demo/sanitized/5-minute-script.md`
- `docs/demo/sanitized/15-minute-technical-walkthrough.md`
- `docs/demo/sanitized/fallback-plan.md`
- `docs/demo/sanitized/screenshots/observe-mode.png`
- `docs/demo/sanitized/screenshots/assist-mode.png`
- `docs/demo/sanitized/screenshots/operate-mode.png`

Public pilot narration should emphasize:

- Observe mode: dashboard, projects, Contract Atlas, telemetry, evidence, readiness, and security.
- Assist mode: context packet, adapter/manual result import, evidence capture, attribution, usage honesty.
- Operate mode: route decision, scoped work, validation, approval boundary, safe continuation.

## Optional Private-Live Walkthrough

Private-live walkthroughs are allowed only after a separate privacy review.

The private-live plan must confirm:

- audience and recording policy;
- screens allowed;
- data classes visible;
- private data excluded or intentionally approved;
- local paths hidden where possible;
- no raw private records displayed;
- no secret files inspected;
- no external project mutation;
- no push, deploy, or cleanup.

If the review cannot prove the live view is safe for the audience, use only the sanitized packet.

## Success Metrics

| Metric | Target |
| --- | --- |
| Setup clarity | Pilot operator can run health checks without internal architecture help. |
| Privacy confidence | Reviewers agree no private operational history appears in pilot materials. |
| Analytics-only independence | Observe mode works without hooks, agents, workflows, Claude, Codex, Docker, repo mutation, or provider API keys. |
| Evidence clarity | Reviewers can distinguish known, missing, partial, and manual-review evidence. |
| Security/readiness usefulness | Reviewers can explain what the gates show and what they do not claim. |
| Adapter boundary clarity | Reviewers understand adapters are workers, not authority. |
| Decision usefulness | Reviewers identify at least three realistic pilot use cases or blockers. |
| No-go boundary adherence | No forbidden action is required to complete the pilot. |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Pilot audience expects cloud/SaaS behavior | Medium | Medium | State local-first scope and non-goals at the opening. |
| Sanitized demo feels less concrete than live state | Medium | Medium | Offer private-live review only after separate privacy approval. |
| Ingested data contains private details | Medium | High | Require sanitized inputs and reject forbidden data sources. |
| Security/readiness outputs are mistaken for compliance certification | Low | High | State evidence-backed status only; no compliance claims. |
| Adapter token/cost data is misread as billing proof | Medium | Medium | Mark unknown cost as unknown and plan-based usage as plan-based. |
| Pilot expands into mutation or deployment | Low | High | Keep policy boundaries disabled unless separately approved. |

## Rollback And Offboarding

- Stop the pilot by pausing further ingestion and closing the dashboard.
- Retain only approved local evidence summaries needed for evaluation.
- Do not delete, archive, compact, or deduplicate any state unless separately approved.
- Remove pilot-specific imported datasets only through a scoped offboarding plan.
- If any private data appears in pilot materials, stop distribution and regenerate sanitized artifacts.
- Keep feedback summaries sanitized before sharing beyond the pilot group.

## Support And Troubleshooting

- If dashboard is unavailable, use sanitized screenshots and installed command summaries.
- If adapter status is unavailable, use context-packet-only fallback.
- If evidence is missing, mark it unavailable; do not invent status.
- If policy denies an action, treat it as a successful guardrail demonstration.
- If setup fails, collect command name, high-level error class, environment profile, and whether any forbidden data was involved. Do not paste secrets.

## Feedback Collection

Use `feedback-template.md` after the pilot session.

Collect feedback on:

- value clarity;
- setup friction;
- privacy confidence;
- dashboard usefulness;
- analytics-only usefulness;
- security/readiness clarity;
- adapter boundary clarity;
- risks, blockers, and next-step interest.

## Packet Index

- `executive-summary.md`
- `technical-appendix.md`
- `feedback-template.md`
- `validation-manifest.json`
