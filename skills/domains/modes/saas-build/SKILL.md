---
ds:
  pack: domains
  mode: saas-build
  mode_type: build
  inputs: [feature_spec, api_contract, schema_definition, component_requirements]
  outputs: [implementation, tests, migration, deploy_artifact]
  capabilities_required: [Read, Write, Edit, Grep, Bash, LSP]
  model_preference: sonnet
  estimated_duration: 2-8hrs
---

# SaaS Build — React + Cloudflare Stack

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`build feature:`, `build api:`, `build page:`, `build component:`, `build schema:`, `build artifact:`, `deploy:`, `review fullstack:`, `typescript:`, `build astro:`, `build supabase:`, CRO commands, SEO commands, analytics commands

## Stack
- **Frontend**: React 19, React Router 7
- **Backend**: Cloudflare Workers
- **Database**: D1 + Kysely (type-safe query builder)
- **Deployment**: push to GitHub, CI deploys (never run wrangler deploy directly)

## Patterns

### API contract-first
1. Define the API shape (request/response types) before writing implementation
2. Share types between worker and frontend via shared package or barrel export
3. Validate request bodies at the worker boundary — trust nothing from the client

### React 19
- Use `use()` for data fetching in components (replaces useEffect + useState pattern)
- Server components where possible, client components only when interactivity needed
- Error boundaries at route level, not around individual components
- `useTransition` for non-blocking state updates

### React Router 7
- File-based routing with `routes/` convention
- Loaders for data fetching, actions for mutations
- `useNavigation` for pending UI states
- Nested layouts via `Outlet`

### D1 + Kysely
```typescript
// Migration pattern
export async function up(db: Kysely<any>): Promise<void> {
  await db.schema.createTable('table_name')
    .addColumn('id', 'text', (col) => col.primaryKey())
    .addColumn('created_at', 'text', (col) => col.notNull().defaultTo(sql`CURRENT_TIMESTAMP`))
    .execute()
}
```
- Always test migrations against a local D1 instance before pushing
- Text type for dates (D1 stores as text, format as ISO 8601)
- Foreign keys: declare them but D1 doesn't enforce — validate in application code

### Cloudflare Workers
- Workers have 128MB memory, 30s CPU time (unbundled), 50ms CPU (bundled)
- Use `waitUntil()` for fire-and-forget operations (logging, analytics)
- Bindings: D1, KV, R2, Durable Objects — access via `env` parameter
- CORS: handle in worker, not at DNS level

### State management
- URL state for shareable state (search params, filters)
- React Router loaders for server state
- Local state only for truly ephemeral UI state (form inputs, modals, tooltips)
- No global state library unless complexity demands it

### Responsive patterns
- Mobile-first CSS (min-width breakpoints)
- Touch targets: 44x44px minimum
- Test at 320px, 768px, 1024px, 1440px

### Deployment
- Push to GitHub only — CI handles deploys
- Environment variables: set in Cloudflare dashboard, never in code
- Preview deployments: PR branches get preview URLs automatically

## Environment Detection {#env-detection}

Run `shared/version-detection.sh` to detect versions, then use appropriate syntax based on installed versions.

### Python Feature Gates

| Feature | Min Version | Fallback |
|---------|-------------|----------|
| Structural pattern matching (match/case) | 3.10 | if/elif chains |
| Union types (X \| Y) | 3.10 | Union[X, Y] from typing |
| Async with statement groups | 3.9 | Sequential async with |
| Dictionary merge operator (\|\|=) | 3.9 | dict.update() |
| Type hints in standard collections | 3.9 | from typing import List, Dict |
| Walrus operator (:=) | 3.8 | Regular assignment |

### Node Feature Gates

| Feature | Min Version | Fallback |
|---------|-------------|----------|
| Top-level await | 14.8 | Async IIFE wrapper |
| Nullish coalescing (??) | 14.0 | \|\| operator with null checks |
| Optional chaining (?.) | 14.0 | Manual null checks |
| Private class fields (#field) | 12.0 | WeakMap or naming convention |

## Depth Status
JIT-pending — examples and gotchas will be added from the first real SaaS feature build that uses this skill.
