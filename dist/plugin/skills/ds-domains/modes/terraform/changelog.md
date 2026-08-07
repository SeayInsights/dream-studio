# Terraform Skill Changelog

## v1.0.0 — 2026-06-03

**Promoted from agent to skill (WO 18.9 Tier 2-3)**

Content transferred verbatim from `canonical/agents/terraform-architect.md` (108 lines).
No content changes — relocation only, per JIT policy: enrich after first real usage.

Files created:
- SKILL.md — patterns, anti-patterns, gotchas, commands, version notes
- metadata.yml — skill metadata, jit-pending status
- gotchas.yml — 6 gotchas from agent file, structured with severity/category
- config.yml — invocation type (subagent-target), graceful degradation flag
- changelog.md — this file

Agent file reduced to thin wrapper (~20 lines).

**Three-way scope boundary documented:**
- terraform = IaC provisioning (writing and applying infrastructure config)
- devops = CI/CD pipelines that build and deploy that infrastructure
- ops = runtime health of the resulting services (health checks, logging, signals)
Three distinct concerns — complementary, not overlapping.
