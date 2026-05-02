## Summary

<!-- What changed and why -->

## Checklist

- [ ] Tests pass (`make test`)
- [ ] Lint clean (`make lint`)
- [ ] CHANGELOG updated (entry under `[Unreleased]`)
- [ ] PR uses squash merge

## SKILL.md Quality Checklist (if modifying SKILL.md files)

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

See `.github/SKILL_STANDARDS.md` for details on each rule.
