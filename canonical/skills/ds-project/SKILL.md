# ds-project — Project Scoping

**Type:** Guided intake  
**Invocation:** `ds project scope`, `scope project:`, `project scope:`  
**Not a CLI command.** Invoked by the AI when a developer signals they want to scope a project.

---

## Mode dispatch

0. **Progressive disclosure check:** Apply the portable skill contract before dispatching.

1. Parse the mode from the argument (first word).
2. Only one mode exists: `scope`. If no mode is specified, default to `scope`.
3. Follow the scope mode instructions in this file exactly — one phase at a time, one question at a time, no skipping.

| Mode  | Keywords |
|-------|----------|
| scope | ds project scope, scope project:, project scope: |

---

## What This Skill Produces

At the end of a scope session the following artifacts exist:

| Artifact | What it is |
|----------|-----------|
| `ds_projects` row | Name, description, status, project_id |
| `ds_milestones` rows | 3–5 milestones with dependency ordering |
| `ds_work_orders` rows | Typed work orders for all milestones; tasks only for milestone 1 |
| `ds_tasks` rows | 3–7 atomic tasks for the first work order of milestone 1 |
| `.planning/PROJECT.md` | Human-readable summary of the full scope |

Work orders for milestone 2+ are recorded as sketches (title + scope boundary + depends_on). They are not fully decomposed until milestone 1 is closed.

---

## Conversation Rules

**These rules apply at every point in the conversation. Violating any of them breaks the scoping process.**

1. **One question at a time.** Never ask more than one question per message. If multiple things need to be clarified, pick the most important one and ask the others after the first is answered.

2. **Multiple choice when the answer set is bounded.** If the answer can only be one of a known set (e.g., yes/no, greenfield/brownfield, choosing a work order type), present it as a numbered or lettered list. Do not ask open-ended questions when closed ones will do.

3. **No jargon without inline definition.** If a technical term is unavoidable, define it in parentheses the first time you use it. Assume the developer may be non-technical. "Work order (a discrete piece of buildable scope, like a page or an API)" is better than assuming the developer knows what a work order is.

4. **Scope assessment is always first.** Before asking anything else, read the project description carefully. If it covers multiple independent subsystems that could each stand alone as separate projects, flag this immediately:
   > "This sounds like it might cover two separate things: [X] and [Y]. Scoping both together will produce an unworkable PRD. Which would you like to scope first?"
   Do not proceed to discovery questions until you have a single, coherent scope.

5. **No placeholders.** If a required field hasn't been answered, ask for it before moving on. Do not write "TBD", "define later", "as needed", or similar into any milestone, work order, or task. Every field must contain real content before Phase 5 writes anything to the database.

6. **Iterate, don't restart.** If the developer rejects a proposal (milestones, work orders, tasks), ask what specifically is wrong and revise only that part. Do not regenerate everything from scratch unless explicitly asked.

7. **Respect brownfield answers.** If the developer says they don't want to run `analyze:intelligence` on an existing codebase, accept that and proceed with what you know. Do not keep pushing.

---

## Brownfield Check

If the developer mentions an existing codebase at any point during Phase 1:

1. Ask: "Has `analyze:intelligence` been run on this codebase? (1) Yes — I have health score and findings. (2) No — run it first. (3) No — skip it, proceed with what we know."

2. **If yes:** Surface the top 3 violations, health score, and detected stack as context before proposing milestones. This changes the milestone structure — a brownfield project almost always needs a stabilization milestone before new feature milestones.

3. **If no — run first:** Pause the scoping conversation. Say: "Run `ds-analyze intelligence: <path>` and come back with the output." Resume at Phase 2 when they return with findings.

4. **If no — skip:** Accept and proceed. Do not raise this again.

---

## Phase 1 — Discovery

**Goal:** Understand what is being built, for whom, and what done looks like. Maximum 5 questions. Do not ask all 5 upfront — work through them one at a time, adapting each question based on the previous answer.

**Required answers before leaving Phase 1:**

| # | Question | Why it matters |
|---|----------|----------------|
| 1 | What are you building and why? | Establishes the problem-solution pair. If the "why" is weak, the scope will drift. |
| 2 | Who is it for? | User type determines work order types — a developer tool needs different work orders than a consumer app. |
| 3 | What does the first usable version look like? What can someone actually do with it? | Forces definition of done. Without this, milestones have no termination condition. |
| 4 | What are the hard constraints? (stack, integrations, security requirements, existing systems it must connect to) | Constraints change which work order types are feasible and in what order. |
| 5 | Is this greenfield (starting fresh) or extending an existing codebase? | Triggers brownfield check if needed. Changes milestone structure. |

**Adapt question 4** based on what you already know. If question 2 revealed it's an internal tool and question 3 revealed it's read-only, you can skip asking about authentication in question 4 — it's obviously not a constraint.

**End of Phase 1:** Summarize what you heard in 3–5 bullet points and ask: "Does this capture what you're building? (1) Yes, proceed. (2) Let me correct something." Do not move to Phase 2 until the summary is confirmed.

---

## Phase 2 — Milestone Decomposition

**Goal:** Propose 3–5 milestones that form a logical delivery sequence. Each milestone must be independently verifiable (someone can demo it or test it in isolation).

**Rules for milestones:**
- Milestone 1 is always the smallest possible thing that proves the core idea works. Not "MVP" — that word is overloaded. The question is: what is the minimum thing that confirms the architecture decision was right?
- Each milestone has a clear deliverable — something that either works or doesn't. "Foundation complete" is not a deliverable. "User can authenticate and see their dashboard" is.
- Dependencies are explicit: milestone 3 cannot start until milestone 2 is complete. Write this as `depends_on: [milestone_1, milestone_2]`.
- Brownfield projects typically need a "stabilization" milestone first: fix critical violations, establish test baseline, resolve the top 3 findings from analyze:intelligence.

**Present milestones as a numbered list:**

```
Proposed milestones:

1. [Title] — [One-sentence deliverable]. Depends on: none.
2. [Title] — [One-sentence deliverable]. Depends on: milestone 1.
3. [Title] — [One-sentence deliverable]. Depends on: milestone 2.
```

Ask: "Does this milestone sequence make sense? (1) Yes, proceed. (2) Change milestone [N]. (3) Add a milestone. (4) Remove a milestone."

**Iteration limit:** Revise at most 3 times before proceeding. If after 3 rounds the developer still isn't satisfied, ask: "What specifically is still wrong? Let me address that one thing." Do not re-decompose everything — surgical edits only.

---

## Phase 3 — Work Order Generation

**Goal:** Decompose milestone 1 into typed, bounded work orders. Work orders for milestones 2+ are recorded as sketches only.

**For each work order in milestone 1, determine:**

| Field | Description | Rules |
|-------|-------------|-------|
| `title` | Short imperative: "Build user authentication API" | No verbs like "Implement", "Create" — use "Build", "Add", "Wire", "Migrate" |
| `work_order_type` | One of the 10 valid types below | Must match exactly |
| `module_boundary` | Specific files or directories this work order owns | No vague answers. "src/auth/" is acceptable. "backend" is not. |
| `depends_on` | Other work order titles in this milestone | Must be a title that appears in the same list, or empty |

**Present as a table:**

```
Work orders for Milestone 1:

| # | Title | Type | Module boundary | Depends on |
|---|-------|------|-----------------|-----------|
| 1 | ...   | ...  | ...             | —         |
| 2 | ...   | ...  | ...             | WO 1      |
```

Ask: "Do these work orders cover milestone 1 completely? (1) Yes, proceed. (2) Change work order [N]. (3) Missing work order — [describe it]. (4) Split work order [N]."

**For milestones 2–N (sketch only):**

```
Milestone 2 sketch — "[Title]":
- WO: [title], type: [type], boundary: [module], depends on: milestone 1
- WO: [title], type: [type], boundary: [module]
```

Sketches are not approved — they are recorded as-is and will be decomposed in a future scoping session when milestone 1 closes.

### Valid Work Order Types

There are exactly 10 valid types. Use the exact string — no abbreviations, no variants.

| Type | Use when |
|------|----------|
| `ui_component` | Building a reusable UI element (button, card, modal, chart) |
| `ui_page` | Building a complete screen/view with navigation and layout |
| `api_endpoint` | Adding or modifying a backend route, including request/response contract |
| `authentication` | Implementing login, session management, OAuth, or token handling |
| `saas_feature` | A user-facing product capability that spans UI + API (e.g., billing, notifications) |
| `data_pipeline` | ETL, ingestion, transformation, or batch processing work |
| `game_mechanic` | A gameplay rule, interaction system, or physics behavior |
| `deployment` | CI/CD pipeline, containerization, infrastructure-as-code, release automation |
| `infrastructure` | Database schema, cloud resource provisioning, network configuration |
| `documentation` | Technical specs, API references, architecture decision records |

**If nothing fits:** The work order is probably too broad. Split it into two work orders that do fit.

---

## Phase 4 — Task Decomposition

**Goal:** Break the first work order of milestone 1 into 3–7 atomic tasks. Each task must be specific enough for an AI agent to execute without asking clarifying questions.

**What "atomic" means:**
- A task has exactly one output. Not "build the auth system" — that is a work order.
- A task is completable in under 2 hours by an AI agent working alone.
- A task names the specific file, function, endpoint, or component being changed.
- A task states the acceptance condition. Not "implement login" — "Add POST /auth/login endpoint that accepts `{email, password}`, validates against `users` table, and returns a signed JWT. Returns 401 on invalid credentials."

**Bad task (do not write):**
> Implement user authentication

**Good task:**
> Create `POST /api/auth/login` in `src/routes/auth.py`. Accept `{email: str, password: str}`. Hash password with bcrypt, compare against `users.password_hash`. Return `{token: <JWT>, expires_at: <ISO timestamp>}` on success, `{error: "invalid_credentials"}` with 401 on failure.

**Present tasks as a numbered list.** Ask: "Are these tasks specific enough to hand to an AI agent without further clarification? (1) Yes, proceed to write output. (2) Task [N] needs more detail — [describe]. (3) Missing task — [describe]."

**Task decomposition applies only to work order 1 of milestone 1.** Remaining work orders get tasks when they are started (via `ds work-order start <id>` in Slice 6).

---

## Phase 5 — Write Output

**Goal:** Persist the scoped project to SQLite and write the human-readable summary.

**Execute in this exact order:**

**Step 1 — Register the project:**
```
ds project register --name "<project name>"
```
Capture the `project_id` from the JSON output. Every subsequent insert references this ID.

**Step 2 — Insert milestones** (in dependency order, parents before children):
```sql
INSERT INTO ds_milestones (milestone_id, project_id, title, description, status, created_at, updated_at)
VALUES ('<uuid>', '<project_id>', '<title>', '<one-sentence deliverable>', 'pending', '<now>', '<now>');
```

**Step 3 — Insert work orders for milestone 1** (in dependency order):
```sql
INSERT INTO ds_work_orders (work_order_id, project_id, milestone_id, title, description, status, work_order_type, created_at, updated_at)
VALUES ('<uuid>', '<project_id>', '<milestone_1_id>', '<title>', '<module boundary and acceptance criteria>', 'open', '<type>', '<now>', '<now>');
```

**Step 4 — Insert work order sketches for milestones 2–N:**
Same INSERT shape, `status = 'open'`, descriptions contain the sketch content. These will be expanded during their milestone.

**Step 5 — Insert tasks for work order 1 of milestone 1:**
```sql
INSERT INTO ds_tasks (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)
VALUES ('<uuid>', '<work_order_1_id>', '<project_id>', '<imperative title>', '<full acceptance criteria>', 'pending', '<now>', '<now>');
```

**Step 6 — Write `.planning/PROJECT.md`:**

```markdown
# <Project Name> — Scoped <date>

## Project ID
<project_id>

## What we're building
<3–5 sentence description from Phase 1 summary>

## Milestones

### Milestone 1 — <Title> (active)
<deliverable>

Work orders:
1. [<title>] (<type>) — <module boundary>
   - Task 1: <title>
   - Task 2: <title>
   ...

### Milestone 2 — <Title> (sketch)
<deliverable>
Work orders: <sketch list>

[... repeat for each milestone ...]

## Constraints
<hard constraints from Phase 1 Q4>

## Next step
Run: `ds project next <project_id>`
```

**Step 7 — Confirm:**
```
Project scoped. Run `ds project next <project_id>` to start the first work order.
```

---

---

## Resume Mode — Project Navigator

> **CRITICAL: This mode is READ-ONLY until the user explicitly confirms an action.**
> It must never invoke `ds work-order start`, `ds project next`, or any command that
> mutates project state as part of its orientation flow. It reads and reports only.
> All state-mutating actions require an explicit instruction from the user after
> this briefing is delivered. "Yes", "ok", "sure", "continue", and "let's go" are
> NOT explicit confirmation — the user must say "start" or give an unambiguous
> instruction naming the action to take.

**Trigger keywords:** resume:, pick up:, get back to:, what's next:, what's active:,
start building:, continue:, where was I:, what am I working on:,
what should I do:

This mode is a **conversational navigator**. It never exposes raw JSON, UUIDs, exit
codes, or internal state to the user. It uses CLI commands as backend tools and
presents results in plain English.

### Rules baked into this mode

- Never show a UUID to the user unless they explicitly ask for it
- Never show ok:true, exit codes, or raw JSON
- Always use the full UUID internally in all CLI commands
- If a command fails, explain what happened in plain English and suggest the fix
- One question at a time — never ask two things in the same message
- **Never run `ds work-order start` automatically.** Always stop and wait after the briefing.

### Flow

**Step 1 — Query active project:**

Run: `ds project list`

- If one active project found: proceed with it
- If no active project: ask "Which project do you want to work on?" and show the list by name
- If multiple active: ask the user to pick one by name

**Step 2 — Query next work order:**

Run: `ds project next <project_id>`

Surface the result as a plain English briefing:
> "You're working on **[Project Name]**.
>
> **Milestone:** [Milestone Name]
> **Next work order:** [Work Order Title] ([work_order_type])
> **Status:** [open / in_progress]"

If no open work orders:
> "You're working on [Project Name] and all work orders are complete. Run `ds milestone list <project_id>` to see milestone status."

**Step 3 — Present gate and stop:**

After the briefing, end with this exact gate — no variations:

> "Type **start** to begin this work order, or ask me anything about it first.
> No changes will be made until you confirm."

**STOP. Do not run any further commands.** Wait for the user's response.

**Step 4 — Start only on explicit confirmation:**

Only proceed if the user typed "start" or gave an unambiguous instruction that
names the action (e.g., "begin this work order", "run the start command").

Do NOT treat the following as confirmation: "yes", "ok", "sure", "continue",
"let's go", "sounds good", "go ahead". These are ambiguous and must prompt:
> "Just to confirm — type **start** to run `ds work-order start` on [Work Order Title]."

When confirmed, run:
```
ds work-order start <work_order_id>
```

Then tell the user:
> "Work order started. Work within [module_boundary from context.md].
> When you're done, run:
> `py -m interfaces.cli.ds work-order close <work_order_id>`"

Present the close command as a copyable line, not as a UUID reference.

### active project query step

The first action in every resume conversation is to determine the active project.
Use `ds project list` to identify it. Never assume a project is active without
checking the database.

---

## Error Recovery

**If the database is missing:**
> "Dream Studio SQLite authority isn't set up yet. Run `ds rehearsal-install --rehearsal-home <path>` to create a local authority database, then come back."

**If `ds project register` returns an error:**
> Capture the error message and report it verbatim. Do not silently swallow errors. Ask the developer to resolve the issue and then continue from Step 1.

**If a milestone INSERT fails because the UUID collides:**
> Generate a new UUID and retry once. If it fails again, report the error and stop.

**If the developer wants to abort after Phase 3:**
> Ask: "Do you want to save the milestone sketches without work orders, or discard everything?" Respect the answer.

---

## Quality Bar

A scoped project passes quality review if:
- Every milestone has a testable deliverable (not "done" or "complete" — something that can be demonstrated)
- Every work order in milestone 1 has a type from the valid list, a specific module boundary, and explicit dependency ordering
- Every task for work order 1 of milestone 1 could be handed to an AI agent with no additional clarification
- `.planning/PROJECT.md` exists and contains all milestone titles, work order titles, and the project_id
- `ds project next <project_id>` returns a valid work order

A scope session that produces "TBD" in any field has failed the quality bar. Ask for the missing information instead.
