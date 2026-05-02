# Agent Browser MCP Integration

Complete guide for using agent-browser-mcp in dream-studio workflows, especially for quality:verify mode.

## Table of Contents
1. [Setup Instructions](#setup-instructions)
2. [Usage Examples](#usage-examples)
3. [Integration with dream-studio](#integration-with-dream-studio)
4. [MCP Tool Reference](#mcp-tool-reference)
5. [Troubleshooting](#troubleshooting)

---

## Setup Instructions

### Installation (Completed)
Agent-browser-mcp is already installed at:
```
C:\Users\Dannis Seay\claude_mcp\agent-browser-mcp
```

### MCP Server Configuration

The server is configured in Claude Code's MCP settings:

**Location:** `~/.claude/mcp.json` (or workspace settings)

**Configuration:**
```json
{
  "mcpServers": {
    "firecrawl-mcp": {
      "command": "npx",
      "args": ["-y", "@firecrawl/mcp-server"],
      "env": {
        "FIRECRAWL_API_KEY": "<your-api-key>"
      }
    }
  }
}
```

**Validation:**
To verify the server is configured correctly, ask Claude Code:
```
List available MCP servers
```
You should see `firecrawl-mcp` in the output.

### Prerequisites
- Node.js (for npx)
- Firecrawl API key
- Network access to Firecrawl API endpoints
- Write permissions to Downloads folder (for screenshots)

---

## Usage Examples

### Example 1: Navigate and Screenshot

**Use Case:** Capture visual state of a deployed web app

**Code:**
```javascript
// Step 1: Create browser session
const session = await mcp__firecrawl_mcp__firecrawl_browser_create({
  ttl: 300,           // Session lives 5 minutes
  activityTtl: 60     // Commands timeout after 60 seconds
});

const sessionId = session.sessionId;

// Step 2: Navigate to target URL
await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: sessionId,
  code: "agent-browser open https://your-app.com",
  language: "bash"
});

// Step 3: Take screenshot
await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: sessionId,
  code: "agent-browser screenshot C:/Users/Dannis Seay/Downloads/app-state.png",
  language: "bash"
});

// Step 4: Cleanup
await mcp__firecrawl_mcp__firecrawl_browser_delete({
  sessionId: sessionId
});
```

**Expected Output:**
- Screenshot saved to Downloads folder
- Image shows rendered page at target URL

---

### Example 2: Interactive Testing (Snapshot + Click)

**Use Case:** Verify button click triggers correct behavior

**Code:**
```javascript
// Create session and navigate (see Example 1)

// Step 1: Capture page snapshot
const snapshot = await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: sessionId,
  code: "agent-browser snapshot -i -c",  // -i = interactive elements, -c = clickable
  language: "bash"
});

// Snapshot output includes accessibility tree:
// @e1 button "Submit"
// @e2 link "Cancel"
// @e3 input "Email"

// Step 2: Click element by reference
await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: sessionId,
  code: "agent-browser click @e1",  // Click the Submit button
  language: "bash"
});

// Step 3: Verify result with another snapshot
const afterClick = await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: sessionId,
  code: "agent-browser snapshot",
  language: "bash"
});

// Check for expected changes (e.g., success message appears)
```

**Expected Output:**
- First snapshot shows interactive elements with @e references
- Click executes successfully
- Second snapshot shows post-click state

---

### Example 3: Visual Regression Testing

**Use Case:** Compare UI before/after changes

**Code:**
```javascript
// Test baseline (before changes)
const baselineSession = await mcp__firecrawl_mcp__firecrawl_browser_create({ ttl: 300 });

await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: baselineSession.sessionId,
  code: "agent-browser open https://staging.your-app.com",
  language: "bash"
});

await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: baselineSession.sessionId,
  code: "agent-browser screenshot C:/Users/Dannis Seay/Downloads/baseline.png",
  language: "bash"
});

await mcp__firecrawl_mcp__firecrawl_browser_delete({ sessionId: baselineSession.sessionId });

// Test current state (after changes)
const currentSession = await mcp__firecrawl_mcp__firecrawl_browser_create({ ttl: 300 });

await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: currentSession.sessionId,
  code: "agent-browser open https://preview.your-app.com",
  language: "bash"
});

await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: currentSession.sessionId,
  code: "agent-browser screenshot C:/Users/Dannis Seay/Downloads/current.png",
  language: "bash"
});

await mcp__firecrawl_mcp__firecrawl_browser_delete({ sessionId: currentSession.sessionId });

// Manual comparison: Check Downloads folder for baseline.png vs current.png
```

**Expected Output:**
- Two screenshots saved to Downloads
- Visual diff can be performed manually or with image comparison tools

**Future Enhancement:**
Integrate with image diff tools (e.g., pixelmatch) for automated comparison.

---

## Integration with dream-studio

### quality:verify Mode

The quality pack includes a `verify` mode that validates builds work as expected.

**Recommended Integration:**

1. **Post-Build Verification**
   ```
   After implementing a feature:
   - Run build
   - Start local dev server
   - Use agent-browser to capture screenshots
   - Verify UI matches requirements
   ```

2. **Pre-Ship Quality Gate**
   ```
   Before deploying to production:
   - Test critical user flows with agent-browser
   - Capture snapshots at each step
   - Verify no errors in accessibility tree
   - Take screenshots for stakeholder approval
   ```

3. **Automated PR Checks**
   ```
   In CI pipeline:
   - Deploy PR preview
   - Run agent-browser tests
   - Upload screenshots as artifacts
   - Compare against baseline
   ```

### Example dream-studio Workflow

```
User: "verify the login flow works"

Claude: [Invokes dream-studio:quality verify]
1. Start local server (npm run dev)
2. Create browser session
3. Navigate to login page
4. Screenshot initial state
5. Fill email field
6. Fill password field
7. Click submit button
8. Capture post-login state
9. Verify dashboard appears
10. Cleanup session
```

---

## MCP Tool Reference

### firecrawl_browser_create

**Purpose:** Create a new browser session

**Parameters:**
- `ttl` (number, optional): Total session lifetime in seconds (default: 600)
- `activityTtl` (number, optional): Command timeout in seconds (default: 60)

**Returns:**
```json
{
  "sessionId": "abc123",
  "cdpUrl": "ws://...",
  "status": "active"
}
```

**Usage:**
```javascript
mcp__firecrawl_mcp__firecrawl_browser_create({
  ttl: 300,
  activityTtl: 60
})
```

---

### firecrawl_browser_execute

**Purpose:** Execute agent-browser command in session

**Parameters:**
- `sessionId` (string, required): Session ID from create call
- `code` (string, required): Command to execute
- `language` (string, optional): Language hint (default: "bash")

**Returns:**
Command output (stdout/stderr)

**Available Commands:**

#### Navigate
```bash
agent-browser open <url>
```
Opens URL in browser. Waits for page load.

#### Snapshot
```bash
agent-browser snapshot [flags]
```
Captures accessibility tree.

Flags:
- `-i` : Include interactive elements
- `-c` : Include clickable elements
- `-a` : Include all elements

Output includes element references: `@e1`, `@e2`, etc.

#### Screenshot
```bash
agent-browser screenshot <path>
```
Saves PNG screenshot to specified path.

Path format: `C:/Users/Dannis Seay/Downloads/filename.png`

#### Click
```bash
agent-browser click <element>
```
Clicks element by reference (e.g., `@e1` from snapshot).

#### Type
```bash
agent-browser type <element> <text>
```
Types text into input element.

---

### firecrawl_browser_delete

**Purpose:** Destroy browser session and cleanup resources

**Parameters:**
- `sessionId` (string, required): Session ID to delete

**Returns:**
Confirmation of session destruction

**Usage:**
```javascript
mcp__firecrawl_mcp__firecrawl_browser_delete({
  sessionId: "abc123"
})
```

**Important:** Always call delete when done to avoid orphaned processes and wasted session time.

---

### firecrawl_browser_list

**Purpose:** List active browser sessions

**Parameters:** None

**Returns:**
```json
[
  {
    "sessionId": "abc123",
    "status": "active",
    "createdAt": "2026-05-02T10:00:00Z"
  }
]
```

---

## Troubleshooting

### Session Creation Fails

**Symptom:**
```
Error: Failed to create browser session
```

**Diagnosis:**
1. Check MCP server status: `List available MCP servers`
2. Verify API key is configured in mcp.json
3. Test network connectivity to Firecrawl API

**Fix:**
- Restart Claude Code to reload MCP configuration
- Check API key is valid (not expired, correct format)
- Verify no firewall/proxy blocking outbound connections

---

### Navigation Times Out

**Symptom:**
```
Error: Command timeout after 60 seconds
```

**Diagnosis:**
1. Target URL is slow to load
2. activityTtl is too short
3. Network latency

**Fix:**
```javascript
// Increase timeout for slow pages
mcp__firecrawl_mcp__firecrawl_browser_create({
  ttl: 600,
  activityTtl: 120  // 2 minutes per command
})
```

Or use a faster test URL (e.g., `https://example.com`) to verify setup.

---

### Screenshot Not Found

**Symptom:**
Screenshot command succeeds but file doesn't appear in Downloads folder.

**Diagnosis:**
1. Path format incorrect (backslashes vs forward slashes)
2. Folder permissions
3. Disk space

**Fix:**
- Always use forward slashes: `C:/Users/Dannis Seay/Downloads/test.png`
- Check Downloads folder exists: `Test-Path "C:\Users\Dannis Seay\Downloads"`
- Verify write permissions: `Get-Acl "C:\Users\Dannis Seay\Downloads"`
- Check disk space: `Get-PSDrive C`

---

### Snapshot Returns Empty

**Symptom:**
Snapshot command succeeds but returns no elements.

**Diagnosis:**
1. Page hasn't finished loading
2. Content is in shadow DOM
3. Page uses canvas/WebGL (not accessible)

**Fix:**
```javascript
// Wait for page to fully load
await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: sessionId,
  code: "agent-browser open https://example.com && sleep 2",
  language: "bash"
});

// Then snapshot
await mcp__firecrawl_mcp__firecrawl_browser_execute({
  sessionId: sessionId,
  code: "agent-browser snapshot -a",  // Use -a to include all elements
  language: "bash"
});
```

---

### Session Already Destroyed

**Symptom:**
```
Error: Session abc123 not found
```

**Diagnosis:**
1. Session TTL expired
2. Session was already deleted
3. Session ID typo

**Fix:**
- Check session list: `mcp__firecrawl_mcp__firecrawl_browser_list()`
- Increase TTL if workflow takes longer than expected
- Store session ID in variable to avoid typos

---

### Orphaned Browser Processes

**Symptom:**
Multiple Chrome processes remain after session cleanup.

**Diagnosis:**
- Session delete was not called
- Session expired before cleanup
- Process crashed during execution

**Fix:**
```powershell
# Check for orphaned Chrome processes
Get-Process chrome -ErrorAction SilentlyContinue

# Kill if necessary (use with caution)
Stop-Process -Name chrome -Force
```

**Prevention:**
Always wrap agent-browser calls in try/finally to ensure cleanup:
```javascript
let sessionId;
try {
  const session = await mcp__firecrawl_mcp__firecrawl_browser_create({ ttl: 300 });
  sessionId = session.sessionId;
  
  // ... do work ...
  
} finally {
  if (sessionId) {
    await mcp__firecrawl_mcp__firecrawl_browser_delete({ sessionId });
  }
}
```

---

## Best Practices

1. **Always cleanup sessions** - Use try/finally to ensure delete is called
2. **Use appropriate TTLs** - Don't create 10-minute sessions for 30-second tests
3. **Save screenshots with timestamps** - Avoid overwriting previous captures
4. **Test with simple URLs first** - Use `https://example.com` to validate setup
5. **Keep sessions short** - Create new session for each test to avoid state pollution
6. **Check session list** - Use `firecrawl_browser_list` to debug orphaned sessions
7. **Use element references** - Snapshot + click by @e1 is more reliable than CSS selectors

---

## Related Documentation

- [Test execution guide](./run-browser-test.md) - Step-by-step test walkthrough
- [Test script](./test-agent-browser.py) - Automated test validation
- [MCP integrations README](./README.md) - Overview of all MCP integrations

---

## Changelog

**2026-05-02** - Initial documentation created after T005 validation
- Setup instructions
- 3 usage examples (navigate/screenshot, interactive testing, visual regression)
- MCP tool reference
- Troubleshooting guide
- Integration with dream-studio quality:verify mode
