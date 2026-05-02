---
ds:
  pack: domains
  mode: website/cip
  mode_type: build
  inputs: [brand_context, industry, audience, budget_tier]
  outputs: [cip_brief, deliverable_list]
  capabilities_required: [Read, Bash]
  model_preference: sonnet
  estimated_duration: 10-20min
---

# CIP — Corporate Identity Package Generator

## Purpose
Generate a comprehensive brand identity deliverable list tailored to the client's industry, size,
and budget. Uses BM25 keyword search across a 50+ deliverable catalog.

---

## Step 1 — Collect Brand Context
From user or from prior discovery brief:
- **Company/project name**
- **Industry** — tech, finance, retail, healthcare, creative, food, real estate, etc.
- **Company size** — startup, small, medium, enterprise
- **Audience** — B2B, B2C, internal, government
- **Budget tier** — essential, standard, premium, enterprise

---

## Step 2 — Search Deliverables
Run the catalog search with context keywords:

```bash
py scripts/cip-brief.py "fintech startup B2B premium"
```

The script searches `data/deliverables.csv` using BM25-style keyword matching and returns ranked
deliverables. Pass all known context as a single quoted string.

---

## Step 3 — Filter by Budget Tier

| Tier | Count | Core Deliverables |
|------|-------|-------------------|
| **Essential** | 5–10 | Logo, business cards, letterhead, email signature, brand guidelines (1-page) |
| **Standard** | 10–20 | Essential + social media kit, presentation template, website design, branded stationery |
| **Premium** | 20–35 | Standard + packaging, signage, merchandise, video intro/outro, advertising templates |
| **Enterprise** | 35–50+ | Premium + environmental graphics, vehicle wraps, trade show booth, annual report, internal comms templates |

---

## Step 4 — Generate Brief

Output a structured CIP brief using the following template:

```markdown
# CIP Brief: [Company Name]

## Overview
- Industry: [industry]
- Size: [size]
- Audience: [audience]
- Budget Tier: [tier]
- Estimated Deliverables: [count]

## Deliverable List

### Priority 1 — Must-Have
| # | Deliverable | Category | Specs | Est. Hours |
|---|------------|----------|-------|------------|
| 1 | Primary Logo | Identity | SVG + PNG (1x, 2x, 3x), horizontal + stacked | 8-12h |
| 2 | Business Cards | Print | 3.5"×2", front+back, CMYK | 2-3h |

### Priority 2 — Should-Have
...

### Priority 3 — Nice-to-Have
...

## Dependencies
- Logo must complete before any branded materials
- Color palette must be finalized before social media kit
- Brand guidelines must be written before handing off to vendors

## Timeline Estimate
- Essential: 1-2 weeks
- Standard: 2-4 weeks
- Premium: 4-8 weeks
- Enterprise: 8-16 weeks
```

---

## Anti-patterns
- Generating deliverables without considering budget tier
- Including deliverables the client doesn't need (e.g., vehicle wraps for a SaaS startup)
- No dependency ordering — logo must come before everything else
- Missing specifications (dimensions, formats, color modes)
