# MCP Integration Tests

Executable test scripts for validating MCP server integrations.

## Quick Start

### 1. Run Pre-Test Verification

```bash
bash test-agent-browser.sh
```

This checks:
- Downloads folder exists
- MCP configuration (optional)
- Previous test artifacts
- Test documentation present

### 2. Execute Integration Test

Ask Claude Code:
```
Run the agent browser integration test
```

Or execute manually via Claude Code using the tools in `EXECUTE_TEST.md`.

## Files

| File | Purpose | How to Use |
|------|---------|------------|
| `test-agent-browser.sh` | Pre-test verification (executable) | `bash test-agent-browser.sh` |
| `test-agent-browser.py` | Python test documentation | Reference for test structure |
| `run-browser-test.md` | Manual test guide | Follow step-by-step MCP calls |
| `EXECUTE_TEST.md` | Claude Code execution template | Copy/paste for Claude to execute |
| `README.md` | This file | Overview and usage |

## Test Coverage

### Agent Browser MCP (firecrawl-mcp)

**Capabilities Tested:**
1. Browser session creation (`firecrawl_browser_create`)
2. Page navigation (`agent-browser open`)
3. Accessibility snapshot (`agent-browser snapshot`)
4. Screenshot capture (`agent-browser screenshot`)
5. Session cleanup (`firecrawl_browser_delete`)

**Test URL:** https://example.com

**Artifacts:** Screenshots saved to `C:/Users/Dannis Seay/Downloads/agent-browser-test-*.png`

## Pass/Fail Criteria

### PASS
- All 5 test steps complete without errors
- Screenshot file created in Downloads
- Session cleanup successful
- No orphaned browser processes

### FAIL
- Session creation error
- Navigation timeout
- Empty snapshot
- Missing screenshot file
- Cleanup failure

## Troubleshooting

### "Config file not found"
This is informational only. MCP tools are accessible via Claude Code regardless of config file location.

### "firecrawl-mcp not found in config"
This is a warning. If you can see `mcp__firecrawl-mcp__*` tools in Claude Code, the integration works.

### "Previous test screenshots found"
This is informational. Shows that tests have run successfully before.

### Test execution fails
1. Check firecrawl-mcp server is running
2. Verify API key configured
3. Check network connectivity
4. See `run-browser-test.md` for detailed troubleshooting

## Adding New MCP Tests

1. Create `test-<mcp-name>.sh` for pre-test verification
2. Create `test-<mcp-name>.py` for test documentation
3. Create `run-<mcp-name>-test.md` for manual execution guide
4. Update this README with test coverage details

## Integration with dream-studio

These tests validate that MCP tools work correctly before using them in dream-studio workflows:
- `dream-studio:quality` uses browser automation for UI verification
- `dream-studio:security` uses DAST tools via browser control
- `dream-studio:domains` uses browser for web scraping tasks

Run tests after:
- Installing new MCP servers
- Updating MCP server versions
- Changing API keys or credentials
- Troubleshooting MCP connectivity issues
