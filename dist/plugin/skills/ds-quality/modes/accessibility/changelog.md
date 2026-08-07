# Accessibility Skill Changelog

## v1.0.0 — 2026-05-28

**Promoted from agent to skill (WO 18.4.2b)**

Content transferred verbatim from `canonical/agents/accessibility-expert.md` (89 lines).
No content changes — relocation only, per JIT policy: enrich after first real usage.

Files created:
- SKILL.md — all patterns, anti-patterns, gotchas, checklist, tools
- metadata.yml — skill metadata, jit-pending status
- gotchas.yml — 6 gotchas from agent file, structured with severity/category
- config.yml — invocation type (subagent-target), graceful degradation flag
- changelog.md — this file

Agent file reduced to thin wrapper (~20 lines).
Wrapper pattern documented in canonical/skills/STRUCTURE.md.

**Establishes the "subagent-target skill" pattern for 18.9 (8 remaining agents).**
