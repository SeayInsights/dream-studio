# DevOps Skill Changelog

## v1.0.0 — 2026-06-03

**Promoted from agent to skill (WO 18.9 Tier 1)**

Content transferred verbatim from `canonical/agents/devops-engineer.md` (91 lines).
No content changes — relocation only, per JIT policy: enrich after first real usage.

Files created:
- SKILL.md — patterns, anti-patterns, gotchas, commands, version notes
- metadata.yml — skill metadata, jit-pending status
- gotchas.yml — 5 gotchas from agent file, structured with severity/category
- config.yml — invocation type (subagent-target), graceful degradation flag
- changelog.md — this file

Agent file reduced to thin wrapper (~20 lines).

**Scope boundary documented:**
devops covers PRE-DEPLOY pipeline concerns (CI/CD, OIDC, release automation, Docker builds,
branch protection, deployment gates). The `ops` skill covers POST-DEPLOY runtime health
(logging discipline, health endpoints, signal handling, config validation, runtime artifacts).
Boundary is intentional — devops = before the process runs; ops = while the process runs.
