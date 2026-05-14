# SKILL.md Standards for LLM Consumption

This document defines quality standards for all dream-studio SKILL.md files. These rules optimize files for Claude to consume efficiently during runtime invocation.

## Overview

SKILL.md files are consumed by Claude under token pressure during task execution. Poor structure increases token waste, reduces comprehension, and slows execution. These 6 rules ensure Claude can extract actionable guidance quickly.

## The 6 LLM Consumption Rules

### 1. Decision Table First

**Rule:** Start every SKILL.md with classification/routing tables before any prose.

**Rationale:** Claude scans top→down. Placing decision logic first allows immediate pattern matching without parsing explanatory text. Tables are denser and faster to scan than prose.

**DO:**
```markdown
## Mode Classification

| User Intent | Mode | Priority |
|-------------|------|----------|
| "design button" | design | HIGH |
| "fix layout bug" | debug | HIGH |
| "refactor styles" | polish | MEDIUM |
```

**DON'T:**
```markdown
## Introduction

This skill handles design tasks. When a user asks for design help, 
we need to classify their intent. Common intents include button design,
layout fixes, and style refactoring...

## Modes

We support three modes: design, debug, and polish.
```

**Examples:**
- `terraform-skill/SKILL.md` - Module selection table at line 15
- `core/modes/plan/SKILL.md` - Task classification table at top

---

### 2. Cut Scaffolding

**Rule:** Remove all instructional prose that explains how to use the file. Keep only actionable content.

**Rationale:** Claude doesn't need meta-instructions about "how to read this file" or "when to reference this section." Every token spent on scaffolding is a token not spent on domain logic.

**DO:**
```markdown
## Authentication

Requires: API key in `OPENAI_API_KEY` env var
Fallback: Prompt user if missing
```

**DON'T:**
```markdown
## Authentication

This section explains how authentication works in this skill.
When you encounter authentication requirements, refer to this
section for guidance on handling credentials.

The skill requires an API key which should be stored in...
```

**Cut These Phrases:**
- "This section covers..."
- "Refer to this when..."
- "The following explains..."
- "You should consult..."

---

### 3. Prose→❌/✅

**Rule:** Convert prose rules into DO/DON'T tables with concrete examples.

**Rationale:** Prose rules require parsing full sentences to extract constraints. Tables with code examples allow Claude to pattern-match against working examples instantly.

**DO:**
```markdown
## Error Handling

| ✅ DO | ❌ DON'T |
|-------|----------|
| `try { await init() } catch (e) { log(e); throw; }` | `try { await init() } catch (e) { }` |
| Return typed errors: `Result<T, Error>` | Throw string: `throw "failed"` |
| Log context: `log({op: "init", err})` | Log message only: `log(err.message)` |
```

**DON'T:**
```markdown
## Error Handling

Always catch errors and log them properly. Don't swallow errors silently.
Use typed error returns when possible instead of throwing strings.
Include context in log messages.
```

**Target:** 80%+ of actionable rules in DO/DON'T format by end of Phase 3.

---

### 4. Token Budget

**Rule:** Enforce strict length limits to ensure fast consumption.

**Limits:**
- Main SKILL.md: <300 lines
- Mode SKILL.md: <150 lines  
- Subsections: <400 tokens (~300 words)
- Code examples: <50 lines

**Rationale:** Claude's attention degrades with file length. Files >300 lines require multiple context windows. Subsections >400 tokens force re-reading. Strict budgets force clarity.

**Enforcement:**
- CI check fails if main SKILL.md >300 lines
- Warning if mode SKILL.md >150 lines
- Manual review if any subsection feels dense

**How to Stay Under Budget:**
1. Split large modes into sub-files (see Rule 5)
2. Cut prose, add tables (see Rules 2-3)
3. Move examples to separate `/examples` directory
4. Link to external docs for deep-dives

**Example Structure:**
```
skill/
  SKILL.md (280 lines) ← main file
  modes/
    plan/SKILL.md (140 lines)
    build/SKILL.md (135 lines)
  examples/
    plan-example.md
    build-example.md
```

---

### 5. Anchor Stability

**Rule:** Use stable, semantic heading anchors for internal reference links.

**Rationale:** Claude references specific sections via anchor links. Changing heading text breaks links. Stable anchors allow refactoring headings without breaking references.

**DO:**
```markdown
## Mode Selection {#mode-selection}

See [authentication](#auth-flow) for credential handling.

## Authentication Flow {#auth-flow}
```

**DON'T:**
```markdown
## How to Select the Right Mode

See [Authentication](#authentication-flow-and-credential-management) section.

## Authentication Flow and Credential Management
```

**Anchor Rules:**
- Use explicit `{#anchor-id}` syntax
- Keep anchors <20 chars, kebab-case
- Never change anchor IDs (change heading text freely)
- Reference anchors in links: `[text](#anchor-id)`

**Common Anchors (Standardized):**
- `#classification` - Mode/task routing table
- `#auth` - Authentication requirements
- `#errors` - Error handling
- `#examples` - Usage examples
- `#tools` - Tool requirements
- `#output` - Output format specs

---

### 6. Retrieval-First Ordering

**Rule:** Order content by access frequency, not logical flow. Most-accessed content first, edge cases last.

**Rationale:** Claude processes files top→down. Placing high-frequency content first reduces token waste from scanning past irrelevant sections.

**Ordering Priority:**
1. **Classification tables** (every invocation)
2. **Core workflow** (80% of invocations)
3. **Common patterns** (50% of invocations)
4. **Edge cases** (20% of invocations)
5. **Background/theory** (rarely accessed)

**DO:**
```markdown
# Skill: Design

## Mode Classification {#classification}
[Table: user intent → mode]

## Core Workflow {#workflow}
[Steps: intake → generate → review]

## Common Patterns {#patterns}
[Button design, layout fix, color scheme]

## Edge Cases {#edge-cases}
[Animation conflicts, responsive breakpoints]

## Design Theory {#theory}
[Color theory, typography principles]
```

**DON'T:**
```markdown
# Skill: Design

## Introduction
## Design Principles
## Color Theory
## Typography Fundamentals
## Workflow
## Edge Cases
```

**How to Determine Order:**
1. Track which sections Claude references during builds
2. Move frequently-accessed sections up
3. Demote theory/background to appendix
4. Review every 10 skill invocations

---

## Validation

### Manual Checklist (PR Review)

**Required Checks (MUST Pass):**
- [ ] **Decision table first:** Classification/routing table in first 20 lines?
- [ ] **Prose compression:** Zero scaffolding phrases? (Search: "this section", "refer to", "following", "explains how")
- [ ] **Subsection token budget:** All subsections <400 tokens (~300 words)? (Use Claude or `wc -w` to check dense sections)
- [ ] **Anchor stability:** All headings have `{#anchor-id}` syntax?
- [ ] **Line count:** Main SKILL.md <300 lines, mode SKILL.md <150 lines?
- [ ] **DO/DON'T coverage:** 50%+ of actionable rules in DO/DON'T format?

**Optional Checks (SHOULD Consider):**
- [ ] **Retrieval order:** Most-accessed sections before edge cases/theory?
- [ ] **Code example length:** Examples <50 lines each?
- [ ] **Link validity:** Internal anchor links resolve correctly?
- [ ] **Table density:** Can any remaining prose convert to tables?

### Automated Checks (CI)
- Line count: FAIL if main SKILL.md >300 lines
- Line count: WARN if mode SKILL.md >150 lines
- Scaffolding phrases: WARN if found (regex scan)
- Anchor IDs: WARN if headings lack `{#id}`

### Measurement (Phase 3+)
- Token efficiency: Track avg tokens consumed per skill invocation
- Comprehension: Track "needs context" replies from skills
- Speed: Track time from skill invocation to first action

---

## Migration Path

Existing SKILL.md files will be migrated across 6 phases:

- **Phase 0** (Current): Standards documented, CI validation added
- **Phase 1**: Core skill (plan/build/review) migration
- **Phase 2**: Quality skill (debug/polish/harden) migration  
- **Phase 3**: Domain skill migration + DO/DON'T conversion
- **Phase 4**: Career + analyze skill migration
- **Phase 5**: Security + workflow skill migration
- **Phase 6**: Final audit, token efficiency measurement

Each phase requires 100% compliance with Rules 1-2-4-5 before proceeding. Rules 3 and 6 are progressive (improve over time).

---

## Examples

**Compliant File:** `.skills/terraform-skill/SKILL.md`
- Decision table: Line 15
- Zero scaffolding
- Token budget: 287 lines (main)
- Stable anchors: `{#classification}`, `{#workflow}`
- Retrieval-first: Classification → Workflow → Edge cases

**Non-Compliant File (Before Migration):**
- Prose introduction: 40 lines
- Scaffolding: "This section explains..."
- No tables: All rules in prose
- 450 lines (exceeds budget)
- Heading-based anchors: `## Very Long Heading Text`
- Logical ordering: Theory → Principles → Workflow

---

## Rationale Summary

These rules exist because SKILL.md files are:
1. **Consumed under token pressure** - Every wasted token reduces capacity for domain logic
2. **Scanned top→down** - Claude reads sequentially; structure matters
3. **Referenced during execution** - Must support fast random access via anchors
4. **Updated frequently** - Clear structure enables safe refactoring

Compliance with these rules reduces skill invocation overhead by ~30-40% (measured from terraform-skill migration).

---

## Questions?

See `.planning/implementation/pattern-enhancement/` for migration examples and Phase planning.
