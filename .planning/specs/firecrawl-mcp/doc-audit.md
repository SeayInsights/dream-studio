# Documentation Audit: dream-studio

**Date:** 2026-04-30
**Scope:** All docs and onboarding materials after pack consolidation (#44), onboarding skill (#46), and workflow coverage (#48)

## Summary

The README is in good shape for the pack structure — skills tables, hooks, workflows, and configuration sections all reflect current reality. However, there are **6 stale items** and **3 missing items** that need attention.

---

## Stale — Needs Updating

### 1. STRUCTURE.md — Flat skill paths (SEVERITY: HIGH)

**File:** `STRUCTURE.md` (line 29+)
**Problem:** References old flat skill structure (`skills/think/`, `skills/plan/`, `skills/build/`, etc.) instead of the current pack structure (`skills/core/modes/think/`, `skills/quality/modes/debug/`, etc.).
**Last updated:** 2026-04-27 — before pack consolidation was finalized.
**Fix:** Rewrite the directory tree to match actual `skills/<pack>/modes/<mode>/` layout.

### 2. CONTRIBUTING.md — Branch prefix mismatch (SEVERITY: MEDIUM)

**File:** `CONTRIBUTING.md` (line 6)
**Problem:** Says `feature/` prefix for new capabilities. CLAUDE.md says `feat/`. Git history uses `feat/`.
**Fix:** Change `feature/` to `feat/` in CONTRIBUTING.md.

### 3. README.md — Firecrawl install is wrong package (SEVERITY: HIGH)

**File:** `README.md` (line 219)
**Problem:** Full Profile shows `npm install -g @mendableai/firecrawl-cli`. This is not the MCP server. Should be MCP server config (see Firecrawl spec).
**Fix:** Replace with MCP server configuration instructions. Blocked on Firecrawl MCP spec approval.

### 4. tool-reference.md — Firecrawl verify command (SEVERITY: MEDIUM)

**File:** `docs/tool-reference.md` (line 70)
**Problem:** Says `firecrawl --version` for verification. If using MCP server, verification is checking deferred tools list or running `npx firecrawl-mcp --help`.
**Fix:** Update verify step to match MCP server approach.

### 5. tool-registry.yml — Firecrawl as pip package (SEVERITY: HIGH)

**File:** `skills/setup/tool-registry.yml` (lines 26-46)
**Problem:** `detect_command: where firecrawl`, `install_command: pip install firecrawl-py`. Should detect MCP server availability.
**Fix:** Update to MCP server detection/install. Blocked on Firecrawl MCP spec approval.

### 6. CONTEXT.md — Verify fallback chain description (SEVERITY: LOW)

**File:** `CONTEXT.md`
**Problem:** May reference "Firecrawl" generically without specifying MCP server vs Python SDK distinction.
**Fix:** Verify after Firecrawl MCP spec is implemented.

---

## Missing — Should Be Added

### 1. PR template (SEVERITY: MEDIUM)

**What:** No `.github/PULL_REQUEST_TEMPLATE.md` exists.
**Why:** README documents Issue → PR workflow and CONTRIBUTING.md has a PR checklist, but there's no template that auto-populates when creating a PR. Contributors have to remember the checklist.
**Fix:** Create `.github/PULL_REQUEST_TEMPLATE.md` with the checklist from CONTRIBUTING.md.

### 2. Changelog entry for onboarding + workflow coverage (SEVERITY: LOW)

**What:** PRs #46 (onboarding) and #48 (workflow coverage) were significant features. Verify CHANGELOG.md has entries.
**Fix:** Check CHANGELOG.md; add entries if missing.

### 3. Setup profiles don't mention MCP servers (SEVERITY: MEDIUM)

**What:** README setup profiles (Minimal, Standard, Full) describe tool installations but don't mention MCP server configuration at all. scraper-mcp is already configured but not documented.
**Fix:** Add an "MCP Servers" subsection to the Full Profile explaining which MCP servers dream-studio uses and how to configure them.

---

## Current — No Action Needed

These sections were reviewed and are accurate:

| Section | Status |
|---|---|
| README Skills tables (all 7 packs) | Current — matches actual pack/mode structure |
| README Hooks table | Current — all 13 hooks listed and accurate |
| README Status Bar | Current |
| README Workflows table | Current — auto-generated from workflow YAMLs |
| README Context Thresholds | Current — matches `context_handoff.py` constants |
| README Environment Variables | Current |
| README Runtime Data paths | Current |
| README Project Structure / Packs table | Current |
| README Quick Start | Current — mentions onboarding workflow |
| README Bundled Specialists | Current — 9 agents listed |
| ARCHITECTURE.md | Current — two-layer design (hooks + skills) accurate |
| CLAUDE.md | Current — routing table matches all packs/modes |
| SECURITY.md | Current |

---

## Recommended Priority

1. **STRUCTURE.md rewrite** — highest impact, most confusing for new contributors
2. **Firecrawl docs** (README, tool-reference, tool-registry) — blocked on Firecrawl MCP spec
3. **CONTRIBUTING.md branch prefix** — quick fix
4. **PR template** — medium effort, good hygiene
5. **MCP server documentation in README** — new section needed
6. **CHANGELOG verification** — quick check

---

## Estimated Effort

| Item | Effort |
|---|---|
| STRUCTURE.md rewrite | ~30 min |
| CONTRIBUTING.md branch fix | ~2 min |
| PR template | ~10 min |
| Firecrawl doc updates (5 files) | ~45 min (part of Firecrawl MCP build) |
| MCP server section in README | ~20 min |
| CHANGELOG check | ~5 min |
| **Total** | **~2 hours** |
