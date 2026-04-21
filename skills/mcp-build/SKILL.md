---
name: mcp-build
description: 4-phase MCP server development — research, implement (Zod schemas, structured errors, stdio/SSE transport), test (valid/invalid/edge), evaluate. Trigger on `build mcp:`, `new mcp:`, `extend mcp:`.
pack: domains
---

# MCP Build — Server Development

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
