# Mobile Skill Changelog

## v1.0.0 — 2026-06-03

**Promoted from agent to skill (WO 18.9 Tier 2-3)**

Content transferred verbatim from `canonical/agents/mobile-developer.md` (158 lines).
No content changes — relocation only, per JIT policy: enrich after first real usage.

Files created:
- SKILL.md — patterns (SwiftUI/Compose/RN/Flutter), anti-patterns, gotchas, commands, version notes, cross-platform decision guide
- metadata.yml — skill metadata, jit-pending status
- gotchas.yml — 7 gotchas from agent file, structured with severity/category
- config.yml — invocation type (subagent-target), graceful degradation flag
- changelog.md — this file

Agent file reduced to thin wrapper (~20 lines).

**Platform boundary documented:**
- mobile = native app development (iOS/Android/React Native/Flutter)
- frontend-ux = web/browser interfaces (React, Next.js)
Different platforms entirely — not overlapping.
