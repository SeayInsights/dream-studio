---
ds:
  pack: domains
  mode: website/critique
  mode_type: review
  inputs: [html_artifact, direction_lock]
  outputs: [critique_report, fix_instructions]
  capabilities_required: [Read, Bash]
  model_preference: opus
  estimated_duration: 5-15min
---

# Critique — 5-Dimension Design Review

## Purpose
Post-build quality gate. Evaluate any HTML artifact against 5 design dimensions. Scores below 3 trigger mandatory fix instructions. Run after every website build before shipping.

---

## Step 1 — Automated Pre-Check

Run the anti-slop linter first:

```bash
py scripts/lint-artifact.py <artifact.html>
```

List any violations found. Continue to human critique regardless — linter catches mechanical issues (wrong colors, placeholder text); critique catches higher-order design quality (hierarchy, restraint, philosophy fit).

---

## Step 2 — Score 5 Dimensions (1–5 each)

### 1. Philosophy Consistency
Does the design match the locked direction's philosophy school? Does it feel like the school it claims to be?

Look for: consistent visual language, typography aligned with school, color palette adherence, layout patterns matching the school's DNA.

- **5** = Unmistakably this school; could be in a portfolio for this school
- **3** = Generally consistent but with some drift
- **1** = Contradicts the school (e.g., playful typography in a Müller-Brockmann grid)

> If no direction lock exists, skip this dimension and score out of 20 total.

### 2. Visual Hierarchy
Is there a clear reading order? Does the eye know where to go first, second, third?

- **5** = Immediate clarity; one dominant focal point, clear progression
- **3** = Generally clear but competing elements
- **1** = Everything fights for attention; no focal point

### 3. Execution Detail
Polish, alignment, spacing, consistency. The craft.

- **5** = Pixel-perfect; consistent spacing, aligned elements, clean edges
- **3** = Some alignment issues or inconsistent spacing
- **1** = Sloppy; misaligned elements, random spacing, mixed border styles

### 4. Specificity
Is the content real, specific, and relevant? Or generic filler?

- **5** = Every word, image, and metric is specific to this project
- **3** = Mix of specific and generic content
- **1** = "Lorem ipsum", stock photos, "10x faster", fabricated testimonials

### 5. Restraint
Does every element serve a purpose? Or is there decorative noise?

- **5** = Every element earns its place; nothing can be removed without loss
- **3** = Some decorative elements without clear purpose
- **1** = Gratuitous gradients, shadows, animations, borders; decoration for its own sake

---

## Step 3 — Output Critique Report

```markdown
## Critique Report

**Artifact**: [filename]
**Direction**: [locked direction name or "none"]
**Anti-Slop Lint**: [N violations found / clean]

### Scores

| Dimension | Score | Notes |
|-----------|-------|-------|
| Philosophy Consistency | X/5 | [1-sentence justification] |
| Visual Hierarchy | X/5 | [1-sentence justification] |
| Execution Detail | X/5 | [1-sentence justification] |
| Specificity | X/5 | [1-sentence justification] |
| Restraint | X/5 | [1-sentence justification] |

**Overall**: X/25

### Fix Instructions (for scores < 3)

**[Dimension] (X/5)**:
1. [Specific, line-referenced fix]
2. [Specific, line-referenced fix]
```

---

## Step 4 — Auto-Fix Pass

**If ANY dimension scores below 3:**
- Output specific, line-referenced fix instructions
- End with: "Fix these issues and re-run `critique:` to verify improvements"

**If ALL dimensions score 3 or above:**
- Output: "Design passes quality gate. Total: [X]/25"

---

## Scoring Calibration

- Score honestly. A page that's "good enough" should NOT get all 5s.
- The linter handles mechanical checks. Critique handles judgment calls.
- No direction lock = score 4 dimensions out of 20.

## Anti-Patterns

- Giving all 5s — nothing is perfect
- Vague fix instructions ("improve the hierarchy") — always reference specific lines/elements
- Skipping the lint pre-check
- Scoring Specificity high when placeholder content exists
