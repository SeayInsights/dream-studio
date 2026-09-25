---
name: ds-website
description: 'Website build pipeline — discovery through delivery, 12 sub-modes. Use for: discover:, direction:, page:, prototype:, animate:, brand:, cip:, critique:, deck:, design:, accessibility audit:, polish:'
---

# Website — End-to-End Design Pipeline

## Before You Start

Read `skills/website/gotchas.yml` before every invocation. It contains known failure modes, scope traps, and pipeline sequencing errors to avoid.

---

## Trigger Keywords

| Keyword | Routes to |
|---|---|
| `website:` | Auto-detect pipeline stage |
| `build website:` | Auto-detect pipeline stage |
| `landing page:` | page mode |
| `build page:` | page mode |
| `build site:` | discover → direction → page |
| `prototype app:` | prototype mode |
| `pitch deck:` | deck mode |
| `animate:` | animate mode |
| `design art:`, `canvas:`, `generative art:` | design mode |
| `polish ui:`, `critique design:`, `make it premium:` | polish mode |

---

## Pipeline Overview

```
MANDATORY                         OPTIONAL (pick as needed)
─────────                         ──────────────────────────
discover → direction ──┬──────── page
                       ├──────── prototype
                       ├──────── deck
                       ├──────── animate
                       └──────── cip (brand package)
                                    │
                                    └── critique  (recommended post-build)
```

**Mandatory stages**: `discover` → `direction`
**Optional build stages**: `page`, `prototype`, `deck`, `animate`, `cip` (one or many)
**Recommended post-build**: `critique`

Discovery may be skipped ONLY if the user provides a written discovery brief covering goals, audience, and brand direction.

---

## Anti-Slop Enforcement

Every HTML artifact produced by ANY sub-mode MUST be run through `scripts/lint-artifact.py` before delivery.

```bash
python scripts/lint-artifact.py <artifact.html>
```

If violations are found, fix them before presenting to the user. This rule is non-negotiable. See `references/anti-slop-linter.md` for the full rule catalog.

---

## Mode Routing Table

| Mode | Trigger Keywords | Sub-mode File | Description |
|---|---|---|---|
| discover | `discover:`, first invocation without prior brief | `modes/discover/SKILL.md` | Stakeholder goals, audience, constraints, brand inputs |
| direction | `direction:`, `pick direction:` | `modes/direction/SKILL.md` | 3 visual directions → user selects one to lock |
| brand | `brand:`, `extract brand:`, `brand from url:` | `modes/brand/SKILL.md` | Extract or build brand tokens from URL/assets |
| prototype | `prototype:`, `mobile app:`, `app prototype:` | `modes/prototype/SKILL.md` | Interactive HTML/CSS app prototype with navigation |
| page | `page:`, `landing page:`, `build page:`, `dashboard page:` | `modes/page/SKILL.md` | Full-fidelity HTML page built to locked direction |
| deck | `deck:`, `pitch deck:`, `presentation:`, `slides:` | `modes/deck/SKILL.md` | HTML slide deck using Duarte Sparkline methodology |
| animate | `animate:`, `animation:`, `hero animation:` | `modes/animate/SKILL.md` | CSS/JS animations for hero, transitions, scroll |
| cip | `cip:`, `brand package:`, `identity package:` | `modes/cip/SKILL.md` | Complete identity package: logo, colors, typography, usage |
| critique | `critique:`, `review design:`, `score:` | `modes/critique/SKILL.md` | 5-dimension design score + prioritized fix list |
| design | `design art:`, `design poster:`, `canvas:`, `generative art:`, `brand:` (outside a pipeline), `ad creative:` | `modes/design/SKILL.md` | Visual design capability — design systems, brand tokens, generative art, ad creative |
| accessibility | dispatched via the `accessibility-expert` subagent, not a keyword trigger | `modes/accessibility/SKILL.md` | WCAG 2.2 Level AA audit and remediation |
| polish | `polish ui:`, `critique design:`, `redesign:`, `make it premium:` | `modes/polish/SKILL.md` | UI critique + fixes against design intent |

---

## Shared References (from design mode)

These files are maintained by the `design` mode and are REUSED here — do not duplicate them.

| File | Contents |
|---|---|
| `modes/design/references/font-pairings.md` | 75 curated font pairings |
| `modes/design/references/anti-patterns.md` | 99 UX anti-patterns |
| `modes/design/references/token-architecture.md` | 3-layer W3C DTCG token system |
| `modes/design/references/design-philosophies.md` | 20 design philosophy schools |
| `modes/design/references/semantic-colors.md` | 30+ semantic color tokens |
| `modes/design/references/component-composition.md` | 14 composition patterns |

---

## New References (website mode only)

| File | Contents |
|---|---|
| `references/anti-slop-linter.md` | Lint rule catalog — all rules enforced by lint-artifact.py |
| `references/animation-pitfalls.md` | 16 battle-tested animation rules and failure modes |
| `references/slide-strategies.md` | Duarte Sparkline methodology for narrative slide structure |
| `references/craft-rules.md` | Universal design quality rules applied across all build modes |

---

## Scripts

| Script | Usage | Description |
|---|---|---|
| `scripts/lint-artifact.py` | `python scripts/lint-artifact.py <file.html>` | Anti-slop linter — HTML in, findings out |
| `scripts/generate-tokens.py` | `python scripts/generate-tokens.py <brand-input>` | Brand input → 3-layer token JSON |
| `scripts/brand-compliance.py` | `python scripts/brand-compliance.py <tokens.json> <file.html>` | Brand tokens + HTML → compliance score |
| `scripts/cip-brief.py` | `python scripts/cip-brief.py <brief.md>` | BM25 brief generator for identity packages |

---

## Pipeline Enforcement Rules

1. **Discovery is mandatory** on first invocation unless the user provides a written discovery brief (goals, audience, brand direction).
2. **Direction lock before build** — `direction` mode must complete and user must confirm a selection before any of: `page`, `prototype`, `deck`, `animate`.
3. **Anti-slop lint before delivery** — every HTML artifact must pass `scripts/lint-artifact.py` with zero violations before presenting to the user.
4. **Critique is recommended** after any build mode but is not blocking. Prompt the user: "Run `critique:` to score and get a fix list?"

---

## Integration with the design Sub-mode

`design` is a sibling sub-mode in this pack (`modes/design/SKILL.md`), not a separate
pack — it moved here from `domains` because its own subject (design systems, brand
assets, generative art) is website/visual work, but it keeps its own independent
identity and dispatch, the same way `page`, `deck`, and the other build stages do.

When a trigger keyword overlaps between the `website` pipeline stages and `design`
(e.g., `brand:`):

- **In a website pipeline context** (prior discover/direction output exists in session) → route to
  the pipeline stage's own `modes/<mode>/SKILL.md` (`brand`, `critique`, etc.)
- **Outside a website pipeline** (standalone brand/visual work) → route to `modes/design/SKILL.md`

`design` handles: design systems, brand assets, visual artifacts, standalone UI components,
generative art. `website`'s pipeline stages handle: end-to-end website creation with full
lifecycle orchestration (discovery through delivery).

These are sub-modes of one pack, not substitutes for each other.
