# Agent Browser MCP - Executable Test Guide

## Quick Start

Ask Claude Code to execute this test:

```
Run the agent browser integration test from shared/mcp-integrations/
```

## What Gets Tested

1. **Browser Session Creation** - Creates a CDP browser session
2. **Navigation** - Opens https://example.com
3. **Snapshot** - Captures accessibility tree
4. **Screenshot** - Saves PNG to Downloads folder
5. **Cleanup** - Destroys browser session

## Expected Results

**Pass Criteria:**
- Browser session created with valid session ID
- Page loads successfully (status code 200)
- Snapshot returns accessibility tree with elements
- Screenshot file appears in Downloads folder
- Session cleanup completes without errors

**Execution Time:** ~30-60 seconds

## Manual Execution (via Claude Code)

If running step-by-step, use these commands:

### Step 1: Create Session
```json
mcp__firecrawl-mcp__firecrawl_browser_create({
  "ttl": 300,
  "activityTtl": 60
})
```
**Expected output:** Session ID, CDP URL

### Step 2: Navigate
```json
mcp__firecrawl-mcp__firecrawl_browser_execute({
  "sessionId": "<session-id-from-step-1>",
  "code": "agent-browser open https://example.com",
  "language": "bash"
})
```
**Expected output:** Exit code 0, page loaded confirmation

### Step 3: Snapshot
```json
mcp__firecrawl-mcp__firecrawl_browser_execute({
  "sessionId": "<session-id>",
  "code": "agent-browser snapshot -i -c",
  "language": "bash"
})
```
**Expected output:** Accessibility tree with element references (@e1, @e2, etc.)

### Step 4: Screenshot
```json
mcp__firecrawl-mcp__firecrawl_browser_execute({
  "sessionId": "<session-id>",
  "code": "agent-browser screenshot C:/Users/Dannis Seay/Downloads/test-screenshot.png",
  "language": "bash"
})
```
**Expected output:** Screenshot saved confirmation

### Step 5: Cleanup
```json
mcp__firecrawl-mcp__firecrawl_browser_delete({
  "sessionId": "<session-id>"
})
```
**Expected output:** Session destroyed confirmation

## Verification Checklist

- [ ] Session created without errors
- [ ] example.com loaded successfully
- [ ] Snapshot contains element references
- [ ] Screenshot file exists in Downloads
- [ ] Screenshot shows example.com page
- [ ] Session cleanup completed
- [ ] No orphaned browser processes

## Troubleshooting

**Session creation fails:**
- Check firecrawl-mcp server is running
- Verify API key is configured
- Check network connectivity

**Navigation times out:**
- Increase activityTtl parameter
- Check target URL is accessible
- Verify no firewall blocking

**Screenshot not found:**
- Check Downloads folder permissions
- Verify path uses forward slashes (C:/Users/...)
- Check disk space available

**Session cleanup fails:**
- Session may have already expired (TTL)
- Manual cleanup: check for orphaned Chrome processes
