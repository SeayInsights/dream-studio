---
name: explain
model_tier: haiku
description: Trace how X works — from entry point through layers to output, at the depth the Director needs. Trigger on `explain:`, `how does X work`, `walk me through`, `what is this doing`.
pack: core
chain_suggests: []
---

# Explain — Trace How It Works

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`explain:`, `how does X work`, `walk me through`, `what is this doing`, `why does X behave like Y`

## Purpose
Trace a system, feature, or piece of code from its entry point through its layers to its output.
Not a line-by-line code reading — a structural explanation of WHY it's built this way.

## Scaling
- Single function → one paragraph + file:line reference
- Feature / module → layered explanation (entry → logic → output)
- System / architecture → component map with data flow

## Steps
1. **Identify entry point** — Where does the thing start? (function call, route, trigger, event)
2. **Trace 1-3 hops** — Follow the call chain. Read only the files you land on — no speculative reads.
3. **Identify SSOT** — For each layer, name the file that owns that behavior.
4. **Explain WHY, not WHAT** — Focus on design decisions, constraints, and invariants. The code already shows what; explain why it's structured that way.
5. **Offer depth** — After the first explanation, ask: "Want to go deeper on any layer, or a different angle?"

## Depth levels
- **Surface** (default): Entry point + 2 hops + purpose of each layer
- **Deep**: Full call chain + key decisions at each hop
- **Architecture**: Component map, data flow, boundaries, trade-offs

## Output format
```
## [Topic]: How X works

**Entry point**: `file:line` — [one-line description]

**Layer 1 — [name]**: `file:line`
[2-3 sentences: what this layer does, why it exists, what constraint it handles]

**Layer 2 — [name]**: `file:line`
[2-3 sentences]

**Output**: [what comes out and where it goes]

**Key design decision**: [the non-obvious thing — why this approach vs. alternatives]
```

## Rules
- Never read a file speculatively — only read what you land on in the trace
- Never explain line-by-line — explain layers and decisions
- Never claim to know something you didn't trace — say "I didn't follow that branch"
- Max 3 hops by default unless Director asks deeper

## Next in pipeline
→ `debug` (if explaining to diagnose a problem)
→ `think` (if explaining to inform a design decision)

## Anti-patterns
- Reading every file in a directory to "understand the codebase"
- Line-by-line code narration
- Explaining WHAT the code does without explaining WHY
- Going more than 3 hops without checking if Director wants that depth
