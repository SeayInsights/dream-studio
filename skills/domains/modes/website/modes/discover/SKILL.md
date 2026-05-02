---
ds:
  pack: domains
  mode: website/discover
  mode_type: discovery
  inputs: [user_request, project_context]
  outputs: [discovery_brief_json]
  capabilities_required: [Read, Write]
  model_preference: sonnet
  estimated_duration: 5-15min
---

# Discover — Structured Project Discovery

This is the FIRST mandatory stage of the website pipeline. Do NOT start designing or
building anything during this mode. Complete discovery first.

---

## Skip Condition

If the user provides a pre-existing brief, validate it contains at minimum:
`purpose`, `audience`, and `tone`. If all three are present, skip to Completion.
If any are missing, ask only for the missing fields.

---

## Turn 1 — Question Form

Present these questions in a single, readable block. All 9 max — no more.

```
WEBSITE DISCOVERY

1. Purpose — What is this site/page for?
   (sell product · showcase portfolio · capture leads · inform/docs · other)

2. Audience — Who visits? Age range? Technical level?
   (developers · executives · consumers · students · general public)

3. Content Inventory — What do you already have?
   (copy · images · logo · data · testimonials · case studies · nothing yet)

4. References — Name or link 2–3 sites you admire or compete with.

5. Brand — Do you have: logo? color palette? font choices? brand guidelines URL?

6. Constraints — Timeline? Budget tier?
   (free · low · mid · high) Must-haves vs nice-to-haves?

7. Tone — Pick one or describe:
   (professional · playful · bold · minimal · technical · editorial)

8. Pages — Single page or multi-page? Which pages do you need?

9. Special — Animations? Dark mode? Accessibility target?
   (WCAG A · AA · AAA)

Skip any question you don't have an answer for.
```

---

## Turn 2 — Compile Brief

After the user responds, compile answers into this JSON structure. Fill unknowns
with `null` or reasonable defaults. Present the brief to the user for approval.

```json
{
  "project": {
    "purpose": "...",
    "type": "landing | portfolio | saas | docs | blog | dashboard | multi-page",
    "pages": ["home", "about", "pricing"]
  },
  "audience": {
    "primary": "...",
    "secondary": "...",
    "technical_level": "low | medium | high"
  },
  "content": {
    "available": ["copy", "images", "data"],
    "needed": ["testimonials", "case studies"],
    "placeholder_strategy": "draft | label | skip"
  },
  "brand": {
    "exists": true,
    "logo": true,
    "colors": ["#hex1", "#hex2"],
    "fonts": ["Font Name"],
    "guidelines_url": "..."
  },
  "references": [
    {"url": "...", "what_to_take": "layout structure"},
    {"url": "...", "what_to_take": "color palette vibe"}
  ],
  "constraints": {
    "timeline": "...",
    "budget_tier": "free | low | mid | high",
    "must_haves": ["responsive", "fast"],
    "nice_to_haves": ["animations", "dark mode"]
  },
  "tone": "professional | playful | bold | minimal | technical | editorial",
  "accessibility": "A | AA | AAA",
  "special": []
}
```

---

## Turn 3+ — Refinement

If answers are too vague to fill key fields, ask targeted follow-ups — one or two
specific questions, not the full form again. Examples:

- "You said 'make it look good' — closest match: bold/editorial, minimal, or playful?"
- "You listed 3 pages — do you have any copy written, or should I draft placeholders?"

Stop when the brief is clear enough to proceed.

---

## Completion

When the user approves the brief:

1. Hold the brief in session context — do NOT write it to disk (it's pipeline state).
2. Set pipeline flag: `discovery_complete = true`
3. Output exactly:

```
Discovery complete. Run `direction` to pick a visual direction.
```

---

## Anti-patterns

- Writing any HTML, CSS, or component code during this mode
- Asking more than 9 questions on Turn 1
- Accepting "make it look good" as a complete brief — always resolve tone
- Proceeding without at minimum: purpose, audience, and tone
- Saving the brief to disk — it lives in session context only
