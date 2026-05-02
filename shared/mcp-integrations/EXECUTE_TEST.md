# Execute Agent Browser Test

## For Claude Code to Execute

When the user requests to run the agent-browser test, execute these steps:

### Test Execution Flow

```
1. Create browser session
2. Navigate to test URL
3. Capture snapshot
4. Take screenshot
5. Verify screenshot exists
6. Cleanup session
7. Report results
```

### Implementation

Use the following MCP tool sequence:

```python
# Test configuration
test_url = "https://example.com"
timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
screenshot_path = f"C:/Users/Dannis Seay/Downloads/agent-browser-test-{timestamp}.png"

# Step 1: Create session
session_response = mcp__firecrawl-mcp__firecrawl_browser_create({
    "ttl": 300,
    "activityTtl": 120
})
session_id = session_response["sessionId"]

# Step 2: Navigate
nav_response = mcp__firecrawl-mcp__firecrawl_browser_execute({
    "sessionId": session_id,
    "code": f"agent-browser open {test_url}",
    "language": "bash"
})

# Step 3: Snapshot
snapshot_response = mcp__firecrawl-mcp__firecrawl_browser_execute({
    "sessionId": session_id,
    "code": "agent-browser snapshot -i -c",
    "language": "bash"
})

# Step 4: Screenshot
screenshot_response = mcp__firecrawl-mcp__firecrawl_browser_execute({
    "sessionId": session_id,
    "code": f"agent-browser screenshot {screenshot_path}",
    "language": "bash"
})

# Step 5: Verify
screenshot_exists = Path(screenshot_path).exists()

# Step 6: Cleanup
cleanup_response = mcp__firecrawl-mcp__firecrawl_browser_delete({
    "sessionId": session_id
})

# Step 7: Report
print("Test Results:")
print(f"  Session created: {session_id}")
print(f"  Navigation: {'PASS' if nav_response['exitCode'] == 0 else 'FAIL'}")
print(f"  Snapshot: {'PASS' if snapshot_response['exitCode'] == 0 else 'FAIL'}")
print(f"  Screenshot: {'PASS' if screenshot_exists else 'FAIL'} - {screenshot_path}")
print(f"  Cleanup: {'PASS' if cleanup_response else 'FAIL'}")
```

### Pass/Fail Criteria

**PASS if:**
- All steps complete without exceptions
- Navigation returns exit code 0
- Snapshot returns accessibility tree
- Screenshot file exists at expected path
- Cleanup completes successfully

**FAIL if:**
- Session creation throws error
- Navigation times out or returns non-zero exit
- Snapshot is empty or malformed
- Screenshot file not created
- Cleanup fails

### Expected Output

```
Agent Browser MCP Integration Test
====================================
[1/5] Creating browser session... PASS (session_id: abc123)
[2/5] Navigating to https://example.com... PASS
[3/5] Capturing snapshot... PASS (found 15 elements)
[4/5] Taking screenshot... PASS (saved to Downloads)
[5/5] Cleaning up session... PASS

TEST SUMMARY
============
Total: 5 | Passed: 5 | Failed: 0

Screenshot: C:/Users/Dannis Seay/Downloads/agent-browser-test-20260502-103045.png
```
