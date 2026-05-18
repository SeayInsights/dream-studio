# Stack Presets

## Selection Table

| Preset | Stack | DB | Auth | Best For | Detection Signal |
|--------|-------|----|------|----------|-----------------|
| cloudflare | Workers + Hono | D1 (SQLite) | JWT | Edge-first, serverless, existing CF project | wrangler.toml |
| node | Express or Fastify | PostgreSQL | JWT or session | Traditional backend, REST APIs | package.json with express/fastify |
| python | FastAPI | PostgreSQL | JWT | Data-heavy, ML-adjacent, async | requirements.txt/pyproject.toml with fastapi |
| serverless | AWS Lambda | DynamoDB | Cognito/JWT | AWS ecosystem, event-driven | serverless.yml or sam-template.yaml |
| static | None | None | None | Prototype, demo, design review | No backend signals |

---

## cloudflare

**Structure**
```
src/
  index.ts        # Worker entry
  routes/
  middleware/
wrangler.toml
```

**Dependencies:** `hono`, `@cloudflare/workers-types`

**Routing**
```ts
const app = new Hono()
app.get('/api/items', async (c) => c.json(await c.env.DB.prepare('SELECT * FROM items').all()))
export default app
```

**DB access**
```ts
const { results } = await env.DB.prepare('SELECT * FROM items WHERE id = ?').bind(id).all()
```

**Delegation:** Invoke `domains:saas-build` for full Cloudflare implementation.

---

## node

**Structure**
```
src/
  app.ts          # Express/Fastify entry
  routes/
  middleware/
  db/             # Postgres client
.env
```

**Dependencies:** `express` or `fastify`, `pg` or `drizzle-orm`, `jsonwebtoken`

**Routing**
```ts
app.get('/api/items', async (req, res) => {
  const items = await db.query('SELECT * FROM items')
  res.json(items.rows)
})
```

**DB access**
```ts
import { Pool } from 'pg'
const pool = new Pool({ connectionString: process.env.DATABASE_URL })
const { rows } = await pool.query('SELECT * FROM items WHERE id = $1', [id])
```

**Delegation:** Standard Node; implement inline unless scope exceeds 5 routes.

---

## python

**Structure**
```
app/
  main.py         # FastAPI entry
  routers/
  models/
  db.py           # SQLAlchemy session
requirements.txt
```

**Dependencies:** `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `python-jose`

**Routing**
```python
@app.get("/api/items")
async def list_items(db: AsyncSession = Depends(get_db)):
    return await db.execute(select(Item))
```

**DB access**
```python
result = await db.execute(select(Item).where(Item.id == item_id))
item = result.scalar_one_or_none()
```

**Delegation:** Standard Python; implement inline. For ML pipelines escalate to `core:think`.

---

## serverless

**Structure**
```
functions/
  handler.ts      # Lambda entry
serverless.yml
src/
  services/
```

**Dependencies:** `serverless`, `aws-sdk` or `@aws-sdk/client-dynamodb`, `middy`

**Routing**
```ts
export const handler = async (event: APIGatewayEvent) => {
  const path = event.path
  if (path === '/items') return listItems()
  return { statusCode: 404 }
}
```

**DB access**
```ts
const client = new DynamoDBClient({})
const result = await client.send(new GetItemCommand({ TableName: 'items', Key: { id: { S: id } } }))
```

**Delegation:** For full AWS infra (VPC, IAM, multi-function), escalate to `core:plan` first.

---

## static

**Structure**
```
public/
  index.html
  assets/
```

**Dependencies:** None (or `vite` for bundling)

**Routing:** None — flat file serving only.

**DB access:** None — use mock data or localStorage.

**Delegation:** Use `domains:website` for prototypes needing visual polish.

---

## Greenfield Recommendation

- **Default:** Cloudflare Workers — edge-first, zero cold start, generous free tier
- **Complex SQL joins / relational data:** Node + PostgreSQL
- **Python-native team:** FastAPI + PostgreSQL
- **AWS-locked org:** Serverless + DynamoDB

---

## DO / DON'T

- DO detect stack from project files before asking (check `wrangler.toml`, `package.json`, `requirements.txt`, `serverless.yml`)
- DON'T pick a stack when signals conflict — ask the user
- DO delegate Cloudflare implementations to `domains:saas-build`
- DON'T version-lock dependencies in presets (let projects pin their own versions)
