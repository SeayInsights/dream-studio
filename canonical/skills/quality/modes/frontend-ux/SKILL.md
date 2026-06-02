# Frontend-UX — React/Next.js Component Quality Audit

## Mode dispatch

0. Apply portable skill contract.
1. Parse mode from argument (first word).
2. Default to `audit` if no mode given.
3. Read `modes/<mode>/SKILL.md` completely.
4. If `gotchas.yml` exists, read it before executing.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, ux audit:, frontend audit:, a11y check: |

## What This Skill Does

`audit` — automated review of React/Next.js components for accessibility, performance patterns, component design, and React hooks correctness. Static detection where patterns are known; LLM confirmation for rules requiring semantic judgment. Never fixes — classifies and reports only.

## Source Authority

Rules defined in `rules.yml`. Phase 1 covers React/Next.js (Next.js 13+, React 18+).

## Supported Frameworks (Phase 1)

**React + Next.js:** Full support (10 rules)  
**React standalone (Vite, CRA):** 9/10 rules (ux-008 skips — Next.js Image specific)  
**Vue, Svelte, Angular:** 5/10 rules (a11y rules ux-001–005 + ux-010; hooks/React-specific rules skip)

## Skill Boundary

**Frontend-UX owns:** JSX component quality — a11y attributes, keyboard accessibility, focus management, React hooks correctness, component structure, i18n gaps.

**Accessibility mode (ds-quality:accessibility)** owns: manual WCAG 2.2 audit, screen reader testing, user flow validation. Complementary — not duplicate.

**Cross-references:**
- `ux-007` ↔ `cq-002` (component LOC vs universal function LOC — dual-angle)
- `ux-010` (client-side i18n gaps): no existing rule covers this
- `ux-015` (form validation feedback, Phase 2) ↔ `api-001` (server-side validation)
