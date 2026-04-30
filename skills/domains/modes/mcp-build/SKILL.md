---
name: mcp-build
description: 4-phase MCP server development — research, implement (Zod schemas, structured errors, stdio/SSE transport), test (valid/invalid/edge), evaluate. Trigger on `build mcp:`, `new mcp:`, `extend mcp:`.
pack: domains
---

# MCP Build — Server Development

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`build mcp:`, `new mcp:`, `extend mcp:`

## 4-phase process

### Phase 1: Research
- Check if an existing MCP server covers the use case (search GitHub, npm, community registries)
- If it exists and works: use it. Don't rebuild.
- If it partially works: fork and extend (prefer contribution over fork when possible)
- If nothing exists: proceed to Phase 2

### Phase 2: Implement
Structure:
```
src/
  index.ts          # Entry point, server setup
  tools/            # One file per tool
  resources/        # Resource handlers (if any)
  types.ts          # Shared types
  utils.ts          # Shared utilities
```

#### Schema validation
Every tool must define its input schema using Zod:
```typescript
const toolSchema = z.object({
  param: z.string().describe("What this parameter does"),
})
```
Validate inputs at the tool boundary. Never trust caller input.

#### Error handling
```typescript
try {
  // tool logic
} catch (error) {
  return {
    content: [{ type: "text", text: `Error: ${error.message}` }],
    isError: true,
  }
}
```
Never throw unhandled exceptions. Always return structured error responses.

#### Transport
- **stdio** — default for local servers. Simpler, more reliable.
- **SSE** — for remote servers. Handle: connection drops (reconnect with backoff), stale data (timestamp responses), timeouts (30s default).

### Phase 3: Test
- Call every tool with valid input → verify response format
- Call every tool with invalid input → verify error handling
- Call tools with edge cases (empty strings, huge payloads, special characters)
- For SSE: test connection drop + reconnect

### Phase 4: Evaluate
- Does it handle all expected use cases?
- Are error messages actionable (not just "Error occurred")?
- Is the schema documentation clear enough for an LLM to use the tool correctly?
- Performance: response time under 5s for normal operations?

## Convention
- Package name: `@<your-scope>/mcp-<domain>` for internal servers (pick a scope that matches your org or GitHub handle)
- Always include a README with: purpose, setup, available tools, example usage
- Pin dependency versions — no `^` or `~` ranges for MCP SDK

## Depth Status
JIT-pending — examples and gotchas will be added from the first real MCP build that uses this skill.

## CLI-to-Skill Bridge Pattern

When building an MCP that wraps a CLI tool, follow the **daemon model** — exemplified by `vercel-labs/next-browser`:

### Why daemon instead of per-call spawn
Per-call process spawning adds 200-500ms overhead per command — fine for humans, fatal for agent loops that fire 20 commands in sequence. A daemon starts once and accepts commands over a socket, making each call ~5ms.

### Implementation pattern

**1. Launch daemon once at session start**
```bash
your-tool start  # starts daemon, binds to socket
```
Not per-command. The MCP tool's `initialize` or first-call logic handles this.

**2. Communicate via JSON-RPC over a socket**
- Unix: `/tmp/your-tool.sock`
- Windows: `\\.\pipe\your-tool`
- Protocol: `{"method": "command_name", "params": {...}, "id": 1}`

**3. Design CLI commands to be stateless and machine-readable**
- One command in → structured JSON out
- No interactive prompts, no ANSI color codes in output
- Each command is idempotent (safe to retry)

**4. Expose as typed MCP tools**
```typescript
server.tool("snapshot", { selector: z.string().optional() }, async ({ selector }) => {
  return await sendToSocket({ method: "snapshot", params: { selector } });
});
```

### When to use this pattern
- The CLI tool maintains state between calls (browser session, database connection, file watcher)
- Agent loops need to fire the same tool many times rapidly
- The tool's startup time is >100ms

### Reference implementation
`vercel-labs/next-browser` — exposes React DevTools as agent-callable commands via this exact pattern.
