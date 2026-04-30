# Spec: Firecrawl MCP Integration

**Status:** Draft — awaiting Director approval
**Date:** 2026-04-30

## Problem Statement

dream-studio's `skills/core/web.md` defines a 3-tier web access fallback chain (Firecrawl → scraper-mcp → WebSearch/WebFetch). A previous session already configured the Firecrawl MCP server in global settings:

```json
// ~/.claude/settings.json — already present
"firecrawl": {
  "command": "C:\\Program Files\\nodejs\\node.exe",
  "args": ["C:\\Users\\Dannis Seay\\AppData\\Roaming\\npm\\node_modules\\firecrawl-mcp\\dist\\index.js"],
  "env": { "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}" }
}
```

**Package:** `firecrawl-mcp` v3.11.0 installed, starts without error, API key is set.

However, there are still gaps between the MCP config and dream-studio's documentation/detection:

1. **Tools not loading reliably** — Firecrawl MCP is configured but `mcp__firecrawl__*` tools do not appear in the deferred tools list in the current session (works intermittently?). Needs debugging.
2. **Tool name mismatch** — web.md references `mcp__firecrawl-mcp__*` but the server is registered as `"firecrawl"`, so actual tool prefix (when it loads) would be `mcp__firecrawl__*`. Need to verify and align.
3. **tool-registry.yml still says `pip install firecrawl-py`** — doesn't reflect MCP server reality.
4. **README.md Full Profile** references `@mendableai/firecrawl-cli` — wrong package entirely.
5. **docs/tool-reference.md** says `firecrawl --version` for verification — doesn't match MCP server.
6. **Firecrawl MCP exposes 14 tools** including `firecrawl_search`, `firecrawl_extract`, and `firecrawl_agent` — capabilities web.md doesn't document yet.

The result: Tier 1 may be silently failing, and dream-studio docs don't match the actual setup.

## User Stories

### US-1 (P1): Firecrawl MCP works as Tier 1
As a dream-studio user with a Firecrawl API key, I want Firecrawl MCP to be configured and available so that `web.md` Tier 1 activates and skills get clean markdown output from web pages.

### US-2 (P1): Tool registry reflects MCP server
As a contributor reading tool-reference.md, I want the Firecrawl entry to accurately describe MCP server setup (not pip install) so the docs match reality.

### US-3 (P2): New Firecrawl capabilities are exposed
As a skill author, I want web.md to document `firecrawl_search`, `firecrawl_extract`, and `firecrawl_map` so skills can use these capabilities when Firecrawl is available (with fallback when it's not).

### US-4 (P2): JIT install configures MCP server
As a user on the "as-needed" onboarding path, I want the JIT prompt for Firecrawl to configure the MCP server (not just pip install) so Tier 1 actually activates after install.

### US-5 (P3): Scraper-mcp stays as Tier 2 for unique capabilities
As a security analyst using DAST mode, I want scraper-mcp to remain available for `intercept_api_calls`, `extract_js_endpoints`, and `fetch_wayback` — capabilities Firecrawl MCP doesn't provide.

## Approaches

### Approach A: Debug + Doc Alignment (Recommended)

MCP server is already configured. Focus on:
1. Debug why tools aren't loading reliably (startup timing? node path? server self-reporting name?)
2. Verify the actual tool prefix when it does load and align web.md
3. Update all dream-studio docs to reflect MCP server reality
4. Add new Firecrawl-only capabilities (search, extract, agent) to web.md
5. Update JIT/wizard to detect existing MCP config rather than offering pip install

**Pros:**
- Minimal config changes — MCP server already works
- Fixes the real problem (doc mismatch + intermittent loading)
- Adds new capabilities (search, extract, agent)

**Cons:**
- Debugging intermittent MCP loading may require trial-and-error
- Need to identify the actual tool name prefix empirically

**Complexity:** Low-Medium.

### Approach B: Rename Server to `firecrawl-mcp`

Change the MCP server name in settings.json from `"firecrawl"` to `"firecrawl-mcp"` so tool names become `mcp__firecrawl-mcp__*` — matching what web.md already expects.

**Pros:**
- web.md detection logic works without changes
- Consistent naming with `scraper-mcp`

**Cons:**
- May not fix the loading reliability issue
- Server name in settings may not control the tool prefix (server self-reports its name)
- Would need to add `mcp__firecrawl-mcp__*` to allowedTools

**Complexity:** Low, but may not solve the naming issue.

### Approach C: Replace scraper-mcp with Firecrawl

Remove scraper-mcp, make Firecrawl the only external web tool (Tier 1), with WebSearch/WebFetch as Tier 2.

**Pros:**
- Fewer MCP servers to maintain
- Firecrawl covers most scraper-mcp capabilities

**Cons:**
- Loses scraper-mcp unique features: `intercept_api_calls`, `extract_js_endpoints`, `fetch_wayback`
- Single point of failure for web scraping if Firecrawl is down
- Security DAST mode uses scraper-mcp for API interception

**Complexity:** Low, but loses capabilities.

## Recommendation

**Approach A: Debug + Doc Alignment.**

Rationale:
- MCP server is already installed and configured — don't redo what's done
- The real gap is docs + detection logic + reliability
- scraper-mcp has unique capabilities worth keeping as Tier 2
- Once we verify the actual tool prefix, web.md alignment is straightforward

## Functional Requirements

| ID | Requirement |
|---|---|
| FR-001 | Debug Firecrawl MCP loading — identify why tools don't appear in deferred list and fix |
| FR-002 | Verify actual tool name prefix when Firecrawl loads (e.g., `mcp__firecrawl__firecrawl_scrape` vs `mcp__firecrawl-mcp__firecrawl_scrape`) |
| FR-003 | web.md MUST update detection logic to use the verified tool name prefix |
| FR-004 | web.md MUST add capabilities for `firecrawl_search`, `firecrawl_extract`, `firecrawl_map` with fallback behavior |
| FR-005 | web.md capability matrix MUST add rows for Search (Firecrawl + WebSearch) and Extract (Firecrawl-only) |
| FR-006 | tool-registry.yml MUST be updated from `pip install firecrawl-py` to reflect MCP server detection |
| FR-007 | README.md Full Profile MUST show MCP server setup (already configured) instead of CLI install |
| FR-008 | tool-reference.md MUST update Firecrawl entry with MCP server verify steps |
| FR-009 | scraper-mcp MUST remain as Tier 2 — do not remove it |
| FR-010 | Setup wizard/JIT MUST detect existing MCP server config instead of offering pip install |

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | Firecrawl tools appear in deferred tools list on session start (verified across 2+ sessions) |
| SC-002 | Skills using web.md fallback chain activate Tier 1 when Firecrawl tools are present |
| SC-003 | `dream-studio:setup status` reports Firecrawl MCP as installed/not-installed accurately |
| SC-004 | All doc references to Firecrawl are consistent (MCP server, not pip/CLI) |
| SC-005 | web.md detection logic uses verified tool name prefix |

## Edge Cases

- **No API key set:** Firecrawl MCP server will fail to start. Detection returns false → fall through to Tier 2. No error shown (silent fallback per TR-014).
- **Node.js not installed:** `npx` unavailable. JIT should detect this and skip Firecrawl MCP offer.
- **Rate limited:** Firecrawl free tier limits apply (10 scrapes/min, 5 searches/min). Skills should not retry on 429 — fall through to Tier 2.
- **scraper-mcp also missing:** Both Tier 1 and Tier 2 unavailable. Fall through to WebSearch/WebFetch (always available).
- **Server loads but tools fail to register:** MCP server may start but not appear in deferred tools — current observed behavior. Detection must handle this gracefully.

## Assumptions

- User has Node.js installed (required for MCP server). Already true (Firecrawl is installed).
- Firecrawl API key is stored in `FIRECRAWL_API_KEY` environment variable. Already true.
- MCP server is already configured in `~/.claude/settings.json`. Already true.
- Tool name prefix needs empirical verification — assumed `mcp__firecrawl__firecrawl_<action>` based on server name `"firecrawl"`, but could differ.

## Files Affected

| File | Change |
|---|---|
| `skills/core/web.md` | Update tool names to verified prefix, add search/extract/map capabilities |
| `skills/setup/tool-registry.yml` | Update Firecrawl entry: pip → MCP server detection |
| `docs/tool-reference.md` | Update Firecrawl install + verify instructions |
| `README.md` | Update Full Profile Firecrawl section |
| `skills/setup/modes/wizard/SKILL.md` | Update to detect existing MCP config |
| `skills/setup/modes/jit/SKILL.md` | Update to detect existing MCP config |

## Related: Documentation Audit

See `doc-audit.md` in this directory for 6 stale + 3 missing doc items identified during this spec. These should be addressed alongside the Firecrawl work:

**Stale (non-Firecrawl):**
1. STRUCTURE.md — flat skill paths → pack structure
2. CONTRIBUTING.md — `feature/` → `feat/` branch prefix

**Missing:**
1. `.github/PULL_REQUEST_TEMPLATE.md`
2. CHANGELOG entries for PRs #46, #48
3. MCP servers section in README setup profiles
