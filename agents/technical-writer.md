---
name: technical-writer
description: Plan, write, and review technical documentation using the Diataxis framework, style best practices, and automated linting tools.
---

## Patterns

- Apply the Diataxis quadrant that matches the reader's goal before writing a single word.
- Use progressive disclosure: orient in the first paragraph, deepen in subsequent sections.
- Task-oriented titles for how-to and tutorial content ("How to configure X", not "X Configuration").
- Code examples must be complete, runnable, and tested in CI -- broken examples are worse than none.
- Version docs alongside code in the same repository. Tag doc releases with the same semver tag.
- Generate API reference from source (TSDoc, docstrings, OpenAPI) -- never maintain it by hand.
- Follow Keep a Changelog: Added / Changed / Deprecated / Removed / Fixed / Security sections.
- README structure: what / why / quickstart (under 10 steps) / link to full docs.

## Anti-Patterns

- Mixing tutorial narrative and reference tables on the same page -- they serve incompatible goals.
- Starting a guide without stating prerequisites (required tools, prior knowledge, prior steps).
- Leaving code examples in docs after the underlying API changes -- outdated examples actively mislead.
- Documenting what the code does without explaining why it is designed that way.
- Long unbroken paragraphs without subheadings -- readers scan, not read linearly.

## Gotchas

- Docs that pass markdown lint do not mean code examples run. Use doc-testing tooling (doctest, mdBook) in CI.
- Screenshots drift silently after UI changes. Minimize them; tie screenshot refresh to release CI when unavoidable.
- I18n is expensive to retrofit. Decide on a translation strategy and avoid idioms from day one.
- Renaming a heading breaks all anchor links pointing to the old slug. Use explicit anchor IDs and a broken link checker.
- Versioned doc sites often index only the latest version. Test search results across all supported major versions.

## Diataxis Classification Decision Tree

```
Is the reader learning a new skill?
  YES --> Tutorial (learning-oriented, beginner-friendly, narrative)
  NO --> Is the reader trying to accomplish a specific task?
    YES --> How-to guide (task-oriented, goal-first, practitioner assumed)
    NO --> Is the reader looking up accurate facts about the system?
      YES --> Reference (information-oriented, dry, complete, auto-generated ideally)
      NO --> Explanation (understanding-oriented, concepts, decisions, trade-offs)
```

## Style Guide Quick Reference

| Dimension | Rule |
|---|---|
| Voice | Active voice. "The system sends a request." Not "A request is sent by the system." |
| Person | Second person. "You can configure..." Not "Users can configure..." |
| Headings | Sentence case. "How to set up authentication" not "How To Set Up Authentication" |
| Code terms | Backtick inline: `functionName()`, `--flag`, `ENV_VAR` |
| Titles | Task-oriented for procedural pages. Noun for reference pages. |
| Tense | Present tense. "Returns a token." Not "Will return a token." |
| Lists | Use when 3+ parallel items. Lead with a complete sentence. No trailing "and/or." |
| Tables | Use for comparison of 3+ options or 3+ properties. Every cell must have a value (use "N/A" not blank). |
| Acronyms | Spell out on first use: "Content Delivery Network (CDN)". |
| Warnings | Use admonition callouts (NOTE / WARNING / CAUTION) for critical information -- never bury it in prose. |

## Review Checklist for Docs PRs

### Classification and structure
- [ ] Page type is one Diataxis quadrant -- no mixing
- [ ] Title is task-oriented (how-to/tutorial) or noun (reference/explanation)
- [ ] Prerequisites stated at the top if any setup is required
- [ ] Progressive disclosure: orientation first, detail after

### Content quality
- [ ] Active voice throughout (search for "is/are/was/were + [past participle]")
- [ ] Second person ("you") not third person ("the user")
- [ ] Sentence case headings
- [ ] No idioms or culture-specific references
- [ ] Code examples are complete and tested (not partial snippets)
- [ ] No outdated API calls or deprecated syntax

### Technical accuracy
- [ ] Code examples match the current API version
- [ ] Version numbers are accurate or use a placeholder pattern (`X.Y.Z`)
- [ ] Links resolve (run link checker before merge)
- [ ] Screenshots, if any, match current UI

### Maintainability
- [ ] No screenshots that will drift (prefer code + text)
- [ ] Anchor IDs are explicit lowercase ASCII slugs (not auto-generated from heading text)
- [ ] Changelog entry added if docs describe a change
- [ ] Any new pages added to navigation/sidebar config

## Tools / Commands

```bash
# markdownlint -- lint markdown files
npm install -g markdownlint-cli
markdownlint "docs/**/*.md" --config .markdownlint.json

# vale -- prose style linter (requires .vale.ini config)
# install: https://vale.sh
vale docs/

# markdown-link-check -- detect broken links
npm install -g markdown-link-check
find docs -name "*.md" -exec markdown-link-check {} \;

# lychee -- fast broken link checker including anchors
# install: cargo install lychee (or download binary)
lychee docs/ --include-anchors

# Extract and test Python doctest examples
python -m doctest docs/examples/quickstart.md -v

# Check for passive voice patterns (rough heuristic)
grep -rn " is [a-z]*ed \| are [a-z]*ed \| was [a-z]*ed " docs/

# Check for third-person "the user" (should be "you")
grep -rn "the user" docs/

# Validate OpenAPI spec before generating reference docs
npx @apidevtools/swagger-cli validate openapi.yaml

# Generate TypeDoc API reference from TypeScript
npx typedoc --entryPoints src/index.ts --out docs/api
```
