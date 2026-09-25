# Pre-Launch — Launch Readiness Audit

## Mode dispatch

0. Apply portable skill contract.
1. Parse mode from argument (first word).
2. Default to `audit` if no mode given.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, pre-launch audit:, launch readiness:, ship check: |

## What This Skill Does

`audit` — launch readiness check. Verifies legal documents, release documentation,
operational readiness, security/privacy sign-off, and feature deployment safety.
T1 findings block launch; T2 are warnings; T3 are advisory.

## Service-Type-Aware Detection (Load-Bearing)

Rules calibrate by service type. Default detection uses stack signals; projects override
via `pre_launch_config.yml` at project root.

| Service Type | pl-001/002 (Legal Docs) | pl-003 (Cookie) | Other rules |
|-------------|------------------------|-----------------|-------------|
| `consumer` | T1 — FIRE (required) | T1 — FIRE | All rules, full severity |
| `internal-service` | T2 — warning | T3 — advisory | All rules, reduced severity |
| `developer-tool` | SILENT | SILENT | Release docs, ops docs still apply |
| `library` | SILENT | SILENT | Release docs only (pl-007–010) |

**Inference signals:**
- `consumer`: has PII schema (contacts/users) + auth patterns + public-facing pages + payment
- `developer-tool`: CLI entry points + no public UI + package-focused (pyproject, npm lib)
- `internal-service`: has API but no public consumer surface
- `library`: pure code artifact, no service runtime

**Override:** create `pre_launch_config.yml` at project root:
```yaml
service_type: consumer   # consumer | developer-tool | internal-service | library
```

## Tier System

| Tier | Meaning | Action |
|------|---------|--------|
| T1 | Launch blocking | Must fix before launch; CLI exit 1 |
| T2 | Launch warning | Should fix; surfaced in report |
| T3 | Advisory | Nice-to-have; informational only |

## Phase 2 (Deferred — 18.8.x)

Phase 2 adds an orchestration wrapper that calls all 10+ quality skills under launch
thresholds, maps their findings to T1/T2/T3, and produces a `LAUNCH_READY /
LAUNCH_BLOCKED / LAUNCH_WARNING` verdict as a CLI exit code and dashboard surface.

Phase 1 (this skill) covers only own rules — document presence, release hygiene, and
feature safety patterns not covered by any existing skill.

## Skill Boundary

**This skill owns:** Legal docs, release documentation, operational readiness documents,
security/privacy sign-off docs, feature flag discipline, migration safety (release angle).

**Cross-references (dual-angle, not duplicates):**
- `pl-015` ↔ `sec-*`: pl-015 checks for sign-off document; sec-* checks for findings
- `pl-017` ↔ `dbc-*`: pl-017 checks for privacy review doc; dbc-* checks for code patterns
- `pl-012` ↔ `ops-*`: ops-* covers operational readiness; pl-012 covers rollback documentation
- `pl-019` ↔ `db-*`: db-* covers schema migrations; pl-019 covers release readiness of migrations
