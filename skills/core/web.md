# Web Access — Core Module

Reusable patterns for web scraping and content fetching with intelligent fallback.

## Usage

When a skill needs web access, reference this module:
```
## Imports
- core/web.md — web access with fallback
```

## Core Principles

- **Silent fallback** — No warnings/errors when using fallback tools (TR-014)
- **Zero external dependencies** — Always provide a fallback to built-in tools
- **Capability detection** — Check what's available before choosing a tool
- **Graceful degradation** — Each fallback tier handles the task, just with different capabilities

## Fallback Chain

```
Firecrawl → scraper-mcp → WebSearch/WebFetch
```

**Tier 1: Firecrawl** (best — full extraction, markdown conversion, link extraction)
**Tier 2: scraper-mcp** (good — structured scraping, API detection, sitemaps)
**Tier 3: WebSearch/WebFetch** (baseline — always available)

## Detection Logic

### Check for Firecrawl
```javascript
// Firecrawl is available if mcp__firecrawl-mcp__* tools are loaded
const hasFirecrawl = typeof mcp__firecrawl-mcp__firecrawl_scrape !== 'undefined'
```

### Check for scraper-mcp
```javascript
// scraper-mcp is available if mcp__scraper-mcp__* tools are loaded
const hasScraperMcp = typeof mcp__scraper_mcp__scrape_url !== 'undefined'
```

### Built-in tools (always available)
```javascript
// WebSearch and WebFetch are always available as fallback
const hasWebFallback = true
```

## JIT Prompt — Firecrawl (as-needed path only)

Before falling back from Tier 1 (Firecrawl) to Tier 2, check the user's onboarding path. If the user chose `as-needed`, offer a just-in-time install prompt via the JIT mode (`skills/setup/modes/jit/SKILL.md`).

**When this fires:**
- Firecrawl is NOT detected (`hasFirecrawl` is `false`)
- `setup-prefs.json` exists and `onboarding_path` is `"as-needed"`

**When this does NOT fire:**
- `onboarding_path` is `"wizard"` — wizard already ran; if Firecrawl wasn't installed then, skip silently
- `onboarding_path` is `"read-docs"` — user prefers manual setup; never prompt inline
- `onboarding_path` is absent or file doesn't exist — treat as no preference, skip prompt
- Firecrawl is already available — no prompt needed

```javascript
// Pseudo-code — JIT check before Tier 1 → Tier 2 fallback
async function checkJitFirecrawl(prefs) {
  if (!prefs || prefs.onboarding_path !== "as-needed") {
    return false  // Not the as-needed path — skip JIT
  }

  // Delegate to JIT mode
  const result = await promptForTool("firecrawl")
  // result: { available: boolean, status: "installed" | "skipped" | "never" | "failed" | "verify_failed" }

  return result.available
}
```

**Integration point in tool selection:**

```javascript
async function selectWebTool(task) {
  let hasFirecrawl = checkFirecrawlAvailable()

  if (!hasFirecrawl) {
    // JIT check: offer install if user is on as-needed path
    const prefs = loadPreference()  // from core/setup.md
    const nowAvailable = await checkJitFirecrawl(prefs)
    if (nowAvailable) {
      hasFirecrawl = true  // User approved + installed — retry with Firecrawl
    }
  }

  // Proceed with updated availability
  if (hasFirecrawl) {
    return useFirecrawl(task)
  } else if (checkScraperMcpAvailable()) {
    return useScraperMcp(task)
  } else {
    return useWebFallback(task)
  }
}
```

**Behavior table:**

| `onboarding_path` | Firecrawl missing | JIT fires? | Outcome |
|---|---|---|---|
| `as-needed` | yes | yes | Prompt user; install if approved; retry Tier 1 |
| `as-needed` | no | no | Use Firecrawl directly |
| `wizard` | yes | no | Fall through to Tier 2 silently |
| `read-docs` | yes | no | Fall through to Tier 2 silently |
| absent / file missing | yes | no | Fall through to Tier 2 silently |

**Reference:** See `skills/setup/modes/jit/SKILL.md` for the full `promptForTool()` contract, preference schema, and error handling rules.

## Tool Selection Pattern

```javascript
// Pseudo-code for tool selection
function selectWebTool(task) {
  // Detect available tools
  const hasFirecrawl = checkFirecrawlAvailable()
  const hasScraperMcp = checkScraperMcpAvailable()
  
  // Select based on capability
  if (hasFirecrawl) {
    return useFirecrawl(task)
  } else if (hasScraperMcp) {
    return useScraperMcp(task)
  } else {
    return useWebFallback(task)
  }
}
```

## Usage Examples

### Scrape a single URL

**Tier 1: Firecrawl**
```javascript
// Load Firecrawl tools if not already loaded
ToolSearch({
  query: "select:mcp__firecrawl-mcp__firecrawl_scrape",
  max_results: 1
})

// Scrape with full extraction
mcp__firecrawl-mcp__firecrawl_scrape({
  url: "https://example.com",
  formats: ["markdown", "links"]
})
```

**Tier 2: scraper-mcp**
```javascript
// Load scraper-mcp tools if not already loaded
ToolSearch({
  query: "select:mcp__scraper-mcp__scrape_url",
  max_results: 1
})

// Scrape URL
mcp__scraper_mcp__scrape_url({
  url: "https://example.com"
})
```

**Tier 3: WebFetch (built-in)**
```javascript
// Load WebFetch if deferred
ToolSearch({
  query: "select:WebFetch",
  max_results: 1
})

// Fetch URL content
WebFetch({
  url: "https://example.com"
})
```

### Extract links from a page

**Tier 1: Firecrawl**
```javascript
mcp__firecrawl-mcp__firecrawl_scrape({
  url: "https://example.com",
  formats: ["links"]
})
```

**Tier 2: scraper-mcp**
```javascript
mcp__scraper_mcp__extract_links({
  url: "https://example.com"
})
```

**Tier 3: WebFetch + manual parsing**
```javascript
// Fetch page
const html = await WebFetch({ url: "https://example.com" })
// Parse links from HTML manually (regex or basic parsing)
```

### Search for content

**Tier 1: Firecrawl**
```javascript
ToolSearch({
  query: "select:mcp__firecrawl-mcp__firecrawl_search",
  max_results: 1
})

mcp__firecrawl-mcp__firecrawl_search({
  query: "dream-studio MCP server"
})
```

**Tier 2: Not applicable**

**Tier 3: WebSearch (built-in)**
```javascript
// Load WebSearch if deferred
ToolSearch({
  query: "select:WebSearch",
  max_results: 1
})

// Search the web
WebSearch({
  query: "dream-studio MCP server",
  num_results: 5
})
```

### Crawl a site (multi-page)

**Tier 1: Firecrawl**
```javascript
mcp__firecrawl-mcp__firecrawl_crawl({
  url: "https://example.com",
  max_depth: 2,
  limit: 10
})
```

**Tier 2: scraper-mcp**
```javascript
mcp__scraper_mcp__crawl_site({
  url: "https://example.com",
  max_pages: 10
})
```

**Tier 3: WebFetch + manual iteration**
```javascript
// Fetch root page
const page1 = await WebFetch({ url: "https://example.com" })
// Parse links manually
// Fetch each link iteratively
```

### Fetch sitemap

**Tier 1: Firecrawl**
```javascript
mcp__firecrawl-mcp__firecrawl_map({
  url: "https://example.com"
})
```

**Tier 2: scraper-mcp**
```javascript
mcp__scraper_mcp__fetch_sitemap({
  url: "https://example.com/sitemap.xml"
})
```

**Tier 3: WebFetch**
```javascript
WebFetch({
  url: "https://example.com/sitemap.xml"
})
// Parse XML manually
```

## Skill Integration Template

When implementing web access in a skill:

```markdown
## Web Access Pattern

This skill uses the web access fallback chain from core/web.md:

1. **Detection phase** — Check which tools are available
2. **Selection phase** — Choose highest-tier available tool
3. **Execution phase** — Execute with selected tool
4. **Silent fallback** — No warnings if using Tier 2 or 3

### Implementation
[paste relevant detection + selection code from core/web.md]
```

## Capability Matrix

| Task | Firecrawl | scraper-mcp | WebSearch/WebFetch |
|------|-----------|-------------|--------------------|
| Single page scrape | ✓ Full markdown | ✓ HTML/text | ✓ Raw HTML |
| Link extraction | ✓ Structured | ✓ Structured | Manual parsing |
| Multi-page crawl | ✓ Depth control | ✓ Page limit | Manual iteration |
| Sitemap fetch | ✓ Auto-discover | ✓ Direct fetch | ✓ Manual parse |
| Web search | ✓ Keyword search | — | ✓ Built-in |
| Structured extraction | ✓ LLM extract | — | — |
| Site mapping | ✓ Auto-discover | ✓ Sitemap fetch | ✓ Manual parse |
| API endpoint detection | — | ✓ JS interception | — |
| Wayback Machine | — | ✓ Archive fetch | — |

## Rules

- **Never fail if Tier 1 unavailable** — Always fall back to next tier
- **Never warn about tier being used** — Silent degradation (TR-014)
- **Check availability before use** — Don't assume external tools are loaded
- **Prefer higher tier when available** — Better extraction = better results
- **Document tier in skill output** — For debugging, note which tier was used in verbose logs

## ToolSearch Pattern

Before using MCP tools, load them via ToolSearch:

```javascript
// Load Firecrawl tools
ToolSearch({
  query: "select:mcp__firecrawl-mcp__firecrawl_scrape,mcp__firecrawl-mcp__firecrawl_crawl,mcp__firecrawl-mcp__firecrawl_map,mcp__firecrawl-mcp__firecrawl_search,mcp__firecrawl-mcp__firecrawl_extract",
  max_results: 5
})

// Load scraper-mcp tools
ToolSearch({
  query: "select:mcp__scraper-mcp__scrape_url,mcp__scraper-mcp__extract_links,mcp__scraper-mcp__crawl_site",
  max_results: 3
})

// Load built-in web tools
ToolSearch({
  query: "select:WebSearch,WebFetch",
  max_results: 2
})
```

**When to load:**
- At skill initialization if web access is core to the skill
- On-demand when first web access is needed
- Load all tiers at once to enable immediate fallback

## Used by

career-scan, career-ops, analyze, security-dast, domains-client-work (research phase)
