---
ds:
  pack: domains
  mode: website/brand
  mode_type: build
  inputs: [brand_url, brand_guidelines, direction_lock]
  outputs: [brand_tokens_json, brand_css, brand_summary]
  capabilities_required: [Read, Write, Bash, WebSearch]
  model_preference: sonnet
  estimated_duration: 15-30min
---

# Brand — Extract, Generate, Validate

Extract brand identity, generate 3-layer design tokens, and score compliance against existing artifacts.

---

## Input Modes

**Mode A — Extract from URL:** WebSearch to verify assets, then scrape logo/favicon, CSS colors, font links (Google Fonts, `@font-face`), og:image, theme-color. Read hero copy for voice/tone. Proceed to 5-Step Protocol.

**Mode B — Extract from Guidelines:** Parse document for hex/RGB/Pantone values, font families, spacing scales, logo usage rules, and do/don'ts. Proceed to 5-Step Protocol.

**Mode C — Build from Direction Lock:** Read `.planning/direction-lock.json`. Use locked palette as primitive layer and locked typography as font stack — do not override. Skip Steps 1–2 of protocol; proceed from Step 3.

---

## 5-Step Brand Asset Protocol

### Step 1 — Fact Verification
If the brand is a real company, run WebSearch for `"[brand name] brand guidelines"` and `"[brand name] color palette"`. Use only verified current values. Flag any discrepancy between scraped values and official guidelines.

### Step 2 — Primary Extraction
Capture these fields before proceeding:

```
primary_color:     # dominant brand color (hex)
secondary_color:   # supporting brand color (hex)
accent_color:      # highlight/CTA color (hex)
surface_color:     # background/card surface (hex)
text_color:        # primary text color (hex)
display_font:      # heading font family + weight
body_font:         # body text font family + weight
logo_url:          # direct URL or local path to logo asset
```

### Step 3 — Semantic Extension
Map additional semantic roles. Each must harmonize with the brand palette (adjust lightness/saturation, do not introduce unrelated hues unless brand has no green/amber/red):

```
success_color:  # green family
warning_color:  # amber family
error_color:    # red family
info_color:     # blue family
```

### Step 4 — Token Generation
Run the token generator with extracted values:

```bash
py scripts/generate-tokens.py \
  --primary "$primary_color" \
  --secondary "$secondary_color" \
  --accent "$accent_color" \
  --surface "$surface_color" \
  --text "$text_color" \
  --display-font "$display_font" \
  --body-font "$body_font" \
  --output .planning/brand/
```

Outputs three files (see Token Output section below). Token structure follows the 3-layer W3C DTCG format defined in `skills/domains/modes/design/references/token-architecture.md`.

### Step 5 — Compliance Scoring
If HTML artifacts exist in the project, run:

```bash
py scripts/brand-compliance.py \
  --tokens .planning/brand/brand-tokens.json \
  --artifacts dist/ \
  --output .planning/brand/compliance-report.json
```

Score 0–100. Report how many color/font violations were found. Flag critical violations (colors outside palette, unlisted fonts).

---

## Token Output Format

Three files written to `.planning/brand/`:

**brand-tokens.json** — W3C DTCG 3-layer structure:
- Layer 1: Primitives (raw hex values, font names, numeric scales)
- Layer 2: Semantics (role-based aliases: `color.background.primary`, `color.text.default`)
- Layer 3: Components (component-specific tokens: `button.background`, `input.border`)

**brand.css** — CSS custom properties (`--color-primary`, `--color-surface`, `--font-display`, etc.) derived from token Layer 2+3.

**brand-summary.md** — Color palette with hex values, font stacks with fallbacks, voice/tone notes, logo usage rules, compliance score.

---

## SSoT Sync Pipeline

```
Brand Source (URL / Guidelines / Direction Lock)
    ↓  brand-summary.md (human reference)
    ↓  brand-tokens.json (3-layer DTCG)
    ↓  brand.css (CSS custom properties)
```

Changes flow ONE DIRECTION only. Never edit `brand.css` directly — update the source and regenerate via `generate-tokens.py`.

---

## Integration Points

| Connects to | How |
|---|---|
| Direction Lock | Palette + typography inherit from `.planning/direction-lock.json` (Mode C) |
| Token Architecture | 3-layer structure in `skills/domains/modes/design/references/token-architecture.md` |
| Page / Prototype / Deck | All downstream modes consume `brand.css` — no inline color/font values |
| Brand Compliance | `brand-compliance.py` scores HTML artifacts against generated tokens |

---

## Anti-patterns

- Assuming brand colors from memory instead of using WebSearch verification
- Generating token JSON manually instead of running `generate-tokens.py`
- Editing `brand.css` directly instead of updating source and regenerating
- Introducing colors outside the brand palette in downstream modes
- Skipping semantic extension (success/warning/error/info assignments)
- Overwriting a Direction Lock palette with URL-scraped values
