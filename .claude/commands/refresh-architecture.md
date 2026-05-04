# /refresh-architecture

Regenerate architecture documentation from current codebase state.

## What this command does

This command re-explores the dream-studio codebase and regenerates the three architecture documentation files (`docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/WORKFLOWS.md`) based on the current code, ensuring they stay in sync with reality.

---

## Instructions

Follow these steps to regenerate the architecture documentation:

### Step 1: Explore System Overview

Scan the codebase to identify:
- **Entry points:** Look for `main.py`, `__main__.py`, CLI scripts in `scripts/`, and hook dispatchers in `packs/meta/hooks/on-*-dispatch.py`
- **Directory structure:** Scan top-level directories and document what each contains
- **Major components:** Identify hook system (`packs/`, `hooks/`), skills (`skills/`), workflow engine (`hooks/lib/workflow_*.py`), analytics (`analytics/`), database (`hooks/lib/studio_db.py`)
- **Communication patterns:** Trace how components talk (hooks → SQLite, analytics API ← SQLite, skills → Claude context)
- **SQLite usage:** Find all files importing `studio_db` or directly using sqlite3
- **External services:** Check for API calls (GitHub API in `on-pulse.py` is the only one)
- **Runtime stack:** Read `requirements.txt` and `pyproject.toml` for dependencies

**Important:** Every component you name must map to a real file or directory. Don't describe features that aren't in the code. If you're uncertain about something, note it as "unclear" in your findings.

---

### Step 2: Explore Database Schema

Find every SQLite schema definition:
- **Migration files:** Read all `hooks/lib/migrations/*.sql` files in order (001-009+)
- **Parse schema:** For each table, extract:
  - Table name and source file
  - Columns with types and constraints
  - Primary keys, foreign keys, unique constraints
  - Indexes and their purpose
  - Views and their definitions
  - Triggers (especially FTS5 sync triggers)
- **Document purpose:** For each table, write a one-sentence description of what it stores based on column names and context

**Constraints:**
- Only document tables that actually exist in migration files
- Include schema version from `_schema_version` table
- Note FTS5 tables separately (they require extension)
- Document graceful degradation (e.g., FTS5 → LIKE fallback in `studio_db.py`)

---

### Step 3: Map Workflows

Identify the distinct workflows by examining hooks and their execution order:

1. **Read hook registration:** Check `hooks/hooks.json` for event → hook mappings
2. **Read dispatchers:** Examine `on-prompt-dispatch.py` and `on-stop-dispatch.py` for hook execution order
3. **For each workflow:**
   - **Trigger:** What Claude Code event fires it?
   - **Sequence:** Ordered steps with actor (hook name, API, database, external service)
   - **State transitions:** What database tables/rows are created/updated?
   - **Failure paths:** How does the workflow handle errors? (check try/except, retry logic)
   - **Implementation:** Map each step to file path and function name

**Workflows to document:**
- Session Lifecycle (UserPromptSubmit → Stop)
- Skill Invocation (Skill tool → on-skill-load → telemetry)
- YAML Workflow Execution (workflow_state.py CLI)
- Analytics Generation (script or API mode)
- Health Monitoring (on-pulse.py with GitHub API)

**Important:** Don't invent workflows. If a workflow isn't clear from the code, mark it as "unclear" and describe what you found.

---

### Step 4: Generate docs/ARCHITECTURE.md

Write a comprehensive architecture document with:

1. **Overview** (2-3 paragraphs):
   - What the system does (event-driven plugin with hooks + skills)
   - High-level shape (two-layer: Python runtime + markdown guidance)
   - Why it's structured this way (local-first, portable, no external deps)

2. **System Diagram** (Mermaid):
   - LR (left-to-right) flowchart
   - Every major component as a node with directory path subtitle
   - SQLite database as central node
   - External services (GitHub API) if present
   - Arrows showing data flow
   - Use `style` for visual grouping

3. **Components** (one section per component):
   - What it does
   - Files that implement it (with paths)
   - What it depends on
   - What depends on it
   - Key invariants (e.g., "hooks never block session", "skills are stateless markdown")

4. **Key Architectural Decisions** (3-5 decisions):
   - Decision: brief statement
   - Why: rationale with context
   - Tradeoff: what we gave up
   - Impact on modifications: what developers need to know

**Constraints:**
- Every file path must be real (verified against glob results)
- Mermaid in triple-backtick code fence with language `mermaid`
- No assumptions - if you're guessing, say "unclear" instead

---

### Step 5: Generate docs/DATABASE.md

Write complete database schema documentation with:

1. **Overview:**
   - Database location (production vs dev paths)
   - Mode (WAL, synchronous, foreign keys, busy_timeout)
   - Schema version tracking
   - Access patterns (who reads, who writes)

2. **ERD** (Mermaid erDiagram):
   - All tables with relationships
   - Foreign key cardinality
   - Primary keys marked
   - Major columns shown with types

3. **Tables** (one section per table):
   - Defined in (migration file reference)
   - Purpose (what it stores)
   - Column reference table (name, type, constraints, description)
   - Indexes and what queries they support
   - Non-obvious constraints or invariants

4. **Migrations:**
   - How they work (auto-applied via `_run_migrations()`)
   - Naming convention
   - List of migration files with brief description
   - How to add new migrations
   - Rollback strategy (forward-only, new migration to undo)

5. **Query Patterns:**
   - Common query examples with SQL
   - Dashboard queries
   - Workflow analysis queries
   - Handoff recovery queries

**Constraints:**
- Only document tables that exist in migration files
- Include actual SQL from migrations (copy-paste DDL)
- Mermaid ERD in triple-backtick code fence

---

### Step 6: Generate docs/WORKFLOWS.md

Write workflow documentation with sequence diagrams and state machines:

**For each workflow:**

1. **Overview:**
   - Name and purpose (one paragraph)
   - Triggers (what Claude Code event or user action starts it)

2. **Sequence Diagram** (Mermaid):
   - Actors and participants
   - Messages in execution order
   - Database writes as messages to SQLite participant
   - External service calls shown
   - Alt/opt/loop blocks for conditionals

3. **Implementation Table:**
   - Step | File | Function
   - Map each sequence diagram step to code

4. **State Transitions** (Mermaid stateDiagram-v2):
   - States and transitions
   - Include retry and failure states
   - Terminal states marked

5. **Failure Handling:**
   - What happens on transient errors?
   - What happens on permanent errors?
   - Retry limits
   - Cleanup on failure

**Constraints:**
- One workflow per section
- Sequence diagrams must match actual code execution order
- State machines must reflect actual state field values (check database schema)
- File paths in implementation table must be real

---

### Step 7: Update README.md

Add or update the Architecture section in README.md:

1. **Location:** After "Token Overhead" section, before "Requirements"
2. **Content:**
   - 2-3 paragraph summary of architecture (two-layer, local-first, SQLite-backed)
   - Link list to the three docs with brief descriptions
3. **Table of Contents:** Add `- [Architecture](#architecture)` entry

**Important:** Don't duplicate content from the docs in README - it's a pointer only.

---

### Step 8: Verify and Commit

1. **Verify changes:**
   - Check that all Mermaid diagrams render correctly (use GitHub preview or Markdown preview)
   - Verify all file paths exist (spot-check a few in each doc)
   - Ensure no placeholder text remains (e.g., "TODO", "???")

2. **Commit:**
   ```bash
   git add docs/ARCHITECTURE.md docs/DATABASE.md docs/WORKFLOWS.md README.md
   git commit -m "docs: refresh architecture documentation

   Regenerated from current codebase state. Updated:
   - Component diagram with current directory structure
   - Database schema (N migrations)
   - Workflow sequences with latest hook execution order
   "
   ```

---

## Output

When complete, you should have:
- `docs/ARCHITECTURE.md` - Updated system overview with current components
- `docs/DATABASE.md` - Current schema with all tables from latest migrations
- `docs/WORKFLOWS.md` - Current workflow sequences
- `README.md` - Updated Architecture section

**Note:** This command does NOT push to GitHub - just commits locally. Push manually when ready.

---

## Grounding Rules

These rules prevent documentation drift:

1. **Every component must map to a real file** - Use Glob to verify paths before writing them
2. **Every table must exist in migrations** - Read migration files, don't guess schema
3. **Every workflow step must have code** - Trace execution in hooks, don't invent steps
4. **No assumptions** - If something is unclear from code, write "unclear" and describe what you found
5. **Mermaid in code fences** - Always use triple-backtick with `mermaid` language tag
6. **File paths are absolute from repo root** - Write `hooks/lib/studio_db.py`, not `studio_db.py`

**When in doubt:** Read the file. If you can't find it, grep for keywords. If grep fails, note it as unclear.
