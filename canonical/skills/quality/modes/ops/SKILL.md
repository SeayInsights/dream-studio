# Ops — Operational Quality Audit

## Mode dispatch

0. Apply portable skill contract.
1. Parse mode from argument (first word).
2. Default to `audit` if no mode given.
3. Read `modes/<mode>/SKILL.md` completely.
4. If `gotchas.yml` exists, read it before executing.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, ops audit:, operational audit:, health check: |

## What This Skill Does

`audit` — automated review of operational readiness. Static detection for structural
patterns (logging imports, signal handlers, health routes, Dockerfile stages). LLM
confirmation for semantic rules (config validation, retry discipline, correlation IDs).
Never fixes — classifies and reports only.

## Source Authority

Rules defined in `rules.yml`. 13 Phase 1 rules.

## Supported Languages (Phase 1)

**Python:** Full support (all 13 rules)
**TypeScript / JavaScript:** Full support (all 13 rules; deployment rules conditional on Dockerfile/k8s presence)
**Go / Rust:** Universal rules apply; language-specific logging detection included

## Deferred Rules (not owned by this skill)

**Rate limiting:** owned by `sec-016` (security skill) and `api-005` (backend-api skill). Adding a third rule would create duplicate findings on the same code. Both existing rules fire from different angles (security hardening vs API design). Ops does not add a rate-limiting rule.

**Backup strategy:** owned by `db-016`, `db-017`, `db-018` (database skill). Database skill owns the full backup triad (scheduled + restore-tested + RTO/RPO documented).

**CVE gate:** owned by `dep-001` (types-deps skill). Dependency vulnerability scanning is fully covered.

## Skill Boundary

**Ops skill owns:** operational readiness patterns — structured logging, correlation IDs, health/metrics endpoints, config validation at startup, SIGTERM handling, retry/backoff patterns, timeout discipline, Dockerfile quality, k8s resource limits.

**Cross-references:**
- `ops-003` ↔ `sec-013` (PII in log statements vs PII in any runtime output — dual-angle; different detection surface)
- `ops-010` ↔ `sec-001` (secrets in deployment artifacts vs secrets in source/git — dual-angle; different gate)

## Stack-Aware Dispatch

Deployment rules (ops-012, ops-013) auto-skip when no Dockerfile or k8s manifests detected.
Service rules (ops-005, ops-006, ops-008) auto-skip when `is_service=False` (CLI tool or library).
All code-level rules (ops-001–004, ops-007, ops-009, ops-011) apply universally.
