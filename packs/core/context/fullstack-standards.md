# Full Stack — Code Patterns and Standards Reference

Read when you need implementation details for Next.js, FastAPI, Supabase, or Vercel patterns. Engineering agent loads this on demand, not by default.

---

## Next.js App Router patterns

### Server Component with data fetch
```tsx
import { createClient } from '@/lib/supabase/server'

export default async function DashboardPage() {
  const supabase = createClient()
  const { data, error } = await supabase.from('projects').select('*')
  if (error) throw error
  return <ProjectList projects={data} />
}
```

### Client Component
```tsx
'use client'
import { useState } from 'react'

export function EditableField({ initialValue, onSubmit }: { initialValue: string; onSubmit: (v: string) => Promise<void> }) {
  const [value, setValue] = useState(initialValue)
  const [loading, setLoading] = useState(false)
  const handleSubmit = async () => { setLoading(true); await onSubmit(value); setLoading(false) }
  return (
    <div className="flex gap-2">
      <input value={value} onChange={e => setValue(e.target.value)} className="border rounded px-3 py-2 text-sm" />
      <button onClick={handleSubmit} disabled={loading} className="bg-brand text-white px-4 py-2 rounded text-sm disabled:opacity-50">
        {loading ? 'Saving...' : 'Save'}
      </button>
    </div>
  )
}
```

### API Route
```ts
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(req: NextRequest) {
  const supabase = createClient()
  const { data, error } = await supabase.from('projects').select('*')
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ data, status: 200 })
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const supabase = createClient()
  const { data, error } = await supabase.from('projects').insert(body).select().single()
  if (error) return NextResponse.json({ error: error.message }, { status: 400 })
  return NextResponse.json({ data, status: 201 }, { status: 201 })
}
```

### React Hook Form + Zod
```tsx
'use client'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const schema = z.object({ name: z.string().min(1), email: z.string().email() })
type FormData = z.infer<typeof schema>

export function ContactForm() {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({ resolver: zodResolver(schema) })
  const onSubmit = async (data: FormData) => {
    await fetch('/api/v1/contact', { method: 'POST', body: JSON.stringify(data) })
  }
  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <input {...register('name')} placeholder="Name" className="border rounded px-3 py-2 w-full" />
      {errors.name && <p className="text-red-500 text-sm">{errors.name.message}</p>}
      <input {...register('email')} placeholder="Email" className="border rounded px-3 py-2 w-full" />
      <button type="submit" disabled={isSubmitting} className="bg-brand text-white px-4 py-2 rounded">
        {isSubmitting ? 'Sending...' : 'Send'}
      </button>
    </form>
  )
}
```

---

## FastAPI patterns

### Router with Pydantic
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    id: int; name: str; description: Optional[str]; created_at: datetime
    class Config: from_attributes = True

@router.get("/", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project))
    return result.scalars().all()

@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(**payload.model_dump())
    db.add(project); await db.commit(); await db.refresh(project)
    return project
```

### Async SQLAlchemy
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session: yield session
```

### Global error handler
```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500,
        content={"error": str(exc), "code": "INTERNAL_ERROR", "status": 500})
```

---

## Supabase

### Server client
```ts
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export function createClient() {
  const cookieStore = cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { get: (name) => cookieStore.get(name)?.value } }
  )
}
```

### RLS policy
```sql
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_projects" ON projects FOR ALL USING (auth.uid() = user_id);
```

---

## Brand tokens (fill in your own)

Document your project's color tokens here so Engineering doesn't invent new ones per build. Example:

```
primary:   #<hex>
accent:    #<hex>
background:#<hex>
```

## Hard rules (non-negotiable)

**Lint integrity (L2):** Never downgrade ESLint or TypeScript rules from `error` to `warn`
to make CI pass. If lint has errors, fix the errors. Downgrading hides real bugs silently.
Only acceptable with an explicit inline comment + an immediate follow-up task.

**Local validation before push (L3):** Before any `git push`, run the full chain locally:
```bash
npm run lint && npx tsc --noEmit && npm run build
```
All three must exit 0. Never push and let CI tell you what a local run would have caught.

## Vercel pre-deploy checklist
- [ ] All env vars set in Vercel dashboard (never committed)
- [ ] `npm run lint` exits 0 — zero errors, rules at `error` level (no downgrades)
- [ ] `npm run build` passes locally
- [ ] `npx tsc --noEmit` clean
- [ ] No console errors in production build
