---
ds:
  pack: domains
  mode: fullstack/backend
  mode_type: build
  inputs: [api_contract, stack_context, feature_spec]
  outputs: [api_routes, db_schema, auth_config, env_template, api_contract]
  capabilities_required: [Read, Write, Edit, Grep, Bash]
  model_preference: sonnet
  estimated_duration: 1-4hrs
---

# Backend — Stack-Agnostic API Builder

## Stack Auto-Detection (check in this order)

| Signal File | Detected Stack | Action |
|---|---|---|
| `wrangler.toml` | Cloudflare Workers | Delegate entirely to `domains:saas-build` |
| `package.json` contains `express`, `fastify`, or `hono` | Node.js | Use Node preset |
| `requirements.txt` or `pyproject.toml` contains `fastapi`, `flask`, or `django` | Python | Use Python preset |
| `serverless.yml` or `sam-template.yaml` | AWS Serverless | Use serverless preset |
| None of the above + project files exist | Unknown | Ask user before proceeding |
| No project files at all (greenfield) | — | Recommend Cloudflare Workers; ask user to confirm |

DO auto-detect stack from project files before asking.
DON'T guess when signals conflict (e.g., `wrangler.toml` + `requirements.txt`) — ask the user.
DO delegate entirely to `domains:saas-build` for Cloudflare Workers — do not duplicate its patterns here.
DON'T re-implement Workers auth, CORS, or D1 patterns that `saas-build` already handles.

---

## Build Steps

### Step 1 — Stack Detection
Run detection table above. Confirm with user if ambiguous or greenfield.

### Step 2 — API Contract
Check for `.planning/api-contract.json`.
- **Present** → read it; this is the source of truth for every route shape.
- **Missing** → generate one from user requirements before writing any code.

DO generate the API contract if one doesn't exist — never build blind.
DON'T modify an existing contract without flagging the change: state the diff and get confirmation before proceeding.

Contract schema:
```json
{
  "version": "1",
  "endpoints": [
    {
      "method": "POST",
      "path": "/api/resource",
      "request": { "field": "type" },
      "response": { "field": "type" },
      "auth": "bearer | none | session",
      "errors": ["400 validation", "401 unauthorized"]
    }
  ]
}
```

### Step 3 — Generate Backend Artifacts
Produce all four output types for the detected stack:

| Artifact | Description |
|---|---|
| API routes | Route handlers matching every endpoint in the contract |
| Database schema | Migrations or DDL for all data models |
| Auth config | JWT / session / OAuth setup matching the contract's `auth` field |
| Env template | `.env.example` with all required keys (no values) |

DO validate every request body at the API boundary — trust nothing from the client.
DO return error shapes matching the contract's `errors` array exactly.
DON'T implement endpoints not in the contract without updating the contract first.
DON'T store secrets in code — env vars or secret managers only.
DON'T hardcode framework versions — use latest stable at time of build.

### Step 4 — Stack Preset Patterns
Use `references/stack-presets.md` for framework-specific patterns (routers, ORMs, auth libraries, test utilities).

| Stack | Router | ORM / DB layer | Auth |
|---|---|---|---|
| Node / Express | Express Router | Prisma or Drizzle | passport.js or jose |
| Node / Fastify | Fastify routes | Drizzle | @fastify/jwt |
| Node / Hono | Hono router | Drizzle or D1 | hono/jwt |
| Python / FastAPI | APIRouter | SQLAlchemy or SQLModel | python-jose or authlib |
| Python / Flask | Blueprints | SQLAlchemy | Flask-JWT-Extended |
| Python / Django | urls.py + views | Django ORM | djangorestframework-simplejwt |
| AWS Serverless | Lambda handlers | DynamoDB or RDS via SDK | Cognito or custom authorizer |

---

## Security Baseline (all stacks)

DO parameterize all queries — no string-concatenated SQL.
DO check auth before processing the request body on every protected route.
DO set `Access-Control-Allow-Origin` to a specific origin in production, never `*`.
DON'T log PII — log failed auth attempts by IP only.

---

## Outputs Checklist

Before handing off to `fullstack integrate`:

- [ ] Route file for every endpoint in the contract
- [ ] Migration or DDL file for every data model
- [ ] Auth middleware wired to all protected routes
- [ ] `.env.example` with all required keys documented
- [ ] Contract updated if new endpoints were added during build
