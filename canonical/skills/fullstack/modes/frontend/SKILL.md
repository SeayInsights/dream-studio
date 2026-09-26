# Frontend — Website Delegate + Component Quality Audit

## Mode dispatch

1. Parse the mode from the argument (first word). Default to `build` when the input looks
   like a build request and no mode is named explicitly.
2. If no mode is given and the input doesn't obviously match one, list the two below and ask.
3. Read `<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing (shared across both
   modes).
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| build | build/SKILL.md | (default — invoked as `fullstack frontend`, `fullstack front`, `fullstack ui`) |
| audit | audit/SKILL.md | audit:, ux audit:, frontend audit:, a11y check: |

## Which mode

Two different questions, not two names for the same thing:

- **`build`** — "Build the UI for this API contract." Delegates all design and build work to
  `website:`, injecting endpoint awareness (fetch calls matching the contract's method/path)
  into the page step.
- **`audit`** — "Does this codebase's existing React/Next.js UI meet the component quality
  baseline?" Retrospective scan of components for accessibility, performance patterns,
  component design, and React hooks correctness. Static detection where patterns are known;
  LLM confirmation for rules requiring semantic judgment. Classifies and reports only —
  never fixes.

## Source Authority

`audit` reads `rules.yml` in this directory (10 Phase 1 rules, React/Next.js). `build` has
no rule file — its patterns live in `build/SKILL.md` and the delegated `website:` pipeline.

## Supported Frameworks (audit, Phase 1)

**React + Next.js:** Full support (10 rules)
**React standalone (Vite, CRA):** 9/10 rules (ux-008 skips — Next.js Image specific)
**Vue, Svelte, Angular:** 5/10 rules (a11y rules ux-001–005 + ux-010; hooks/React-specific
rules skip)

## Skill Boundary (audit)

**Frontend audit owns:** JSX component quality — a11y attributes, keyboard accessibility,
focus management, React hooks correctness, component structure, i18n gaps.

**Accessibility mode (`ds-website:accessibility`)** owns: manual WCAG 2.2 audit, screen
reader testing, user flow validation. Complementary — not duplicate.

**Mobile (`ds-apps:mobile`)** owns: native iOS/Android/React Native/Flutter interfaces —
different platform, not overlapping.

**Cross-references:**
- `ux-007` ↔ `cq-002` (component LOC vs universal function LOC — dual-angle, `ds-code-health:code-quality`)
- `ux-010` (client-side i18n gaps): no existing rule covers this
- `ux-015` (form validation feedback, Phase 2) ↔ `api-001` (server-side validation, sibling `backend:audit`)

## Integration with Other Fullstack Modes

**Pipeline:** `spec → (frontend || backend) → integrate → secure`. `build` is the pipeline's
frontend stage. `audit` is a standalone, on-demand check — not part of that pipeline; run it
against an existing frontend at any time.

See `../../SKILL.md` for the orchestrator's full mode routing and auto-detection.
