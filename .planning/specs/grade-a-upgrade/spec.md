# Feature Specification: Grade-A Upgrade — Memory, CI, Token Efficiency

**Topic Directory**: `.planning/specs/grade-a-upgrade/`
**Created**: 2026-04-29
**Status**: Awaiting Director Approval
**Scope**: Four independent deliverables — P0 Setup, Memory/Persistence (C→A), CI Integration (D→A), Token Efficiency (Unknown→A)

---

## Context

Competitive analysis of dream-studio v0.10.0 against the Claude Code ecosystem
identified three below-A grades (excluding Discoverability and Community Adoption,
deferred). Each upgrade is independently shippable.

---

## Upgrade 1 — Semantic Memory Retrieval (C → A)

### Problem
MEMORY.md is a linear index loaded into every session context. It truncates at
200 lines. All memories load regardless of relevance. At scale this degrades
context quality and burns tokens on irrelevant entries. `claude-mem` (69.6k ⭐)
solves this with ChromaDB+RAG — the market has proven this is a valued capability.

### What "A-grade" looks like
- Relevance-filtered: only memories pertinent to the current session load
- No truncation ceiling: archive mechanism keeps MEMORY.md under ~100 active entries
- Zero new infrastructure: no ChromaDB, no external embedding API calls
- Human-readable: MEMORY.md format unchanged, still writable/readable by Claude
- Measured: memory health (count, staleness, retrieval hit rate) in pulse report

### Approaches

**Option A — SQLite FTS5 retrieval (recommended)**
Build a SQLite-backed memory store at `~/.claude/projects/.../memory/memory.db`.
On each UserPromptSubmit hook, score all memory files against the current prompt
using SQLite FTS5 (Python stdlib `sqlite3`, BM25 ranking built in). Inject the
top-5 scoring memories as a `<relevant-context>` block into the hook output.
MEMORY.md stays as the human-readable index and write surface — the DB is a
read-only search index, rebuilt from the markdown files on first run and
refreshed when files change. Index persists on disk — no rebuild on every run.

- Pros: Zero new dependencies (stdlib only), fast (<50ms), offline, no API cost,
  inverted index identical to Elasticsearch/Instagram's approach
- Cons: BM25 is keyword-based — misses semantic synonyms ("context" vs "conversation")
- Risk: Hook output injection may not be respected by Claude Code runtime (needs validation)

**Option B — Tiered archival only (minimal)**
No retrieval layer. Instead: auto-archive memories older than 90 days to
`memory/archive/`. Add a `memory-health` metric to on-pulse. Cap MEMORY.md at
80 active entries by moving oldest to archive when limit is hit.

- Pros: Zero new code surface, no runtime risk
- Cons: Still loads all 80 entries every session, no relevance filtering
- This is a C+ not an A

**Option C — Embedding API retrieval**
Call `text-embedding-3-small` or Anthropic embeddings on each prompt +
each memory, cosine-rank, inject top-5. Matches claude-mem's approach.

- Pros: True semantic matching, catches synonyms
- Cons: API call on every single prompt (latency + cost), network dependency,
  breaks offline usage
- Not recommended unless BM25 recall proves insufficient

**Recommendation: Option A (SQLite FTS5)**

### Functional Requirements
- **FR-M01**: A `hooks/lib/memory_search.py` module MUST index all `.md` files
  in the memory directory using SQLite FTS5 (Python stdlib `sqlite3`, zero new
  dependencies; BM25 ranking is built into FTS5)
- **FR-M02**: Index MUST rebuild automatically when any memory file's mtime changes
- **FR-M03**: On UserPromptSubmit, MUST score current prompt against index and
  return top-5 file paths (or fewer if index is small)
- **FR-M04**: on-pulse MUST report: active memory count, archive count, index age,
  last retrieval scores (top match score as health signal)
- **FR-M05**: Archive hook MUST move memories with `last_accessed` > 90 days to
  `memory/archive/` and remove from MEMORY.md index
- **FR-M06**: All index operations MUST complete in < 100ms on 500 memory entries

### Success Criteria
- **SC-M01**: Session startup injects ≤ 5 memories, not all N memories
- **SC-M02**: MEMORY.md stays under 100 active entries (archive kicks in at 90)
- **SC-M03**: BM25 index rebuild completes in < 100ms for 500 entries
- **SC-M04**: Memory retrieval adds < 200 tokens overhead per session
- **SC-M05**: Pulse report shows memory health without manual inspection

### User Stories
**P1 — Relevant memories load automatically**
As a developer, when I start working on a Power BI task, only Power BI-related
memories inject — not career-ops, not game-dev memories.
Given: 150 memories across 8 domains; When: prompt mentions "DAX" or "Power BI";
Then: top-5 memories by BM25 score are injected, not all 150.

**P2 — MEMORY.md never truncates**
As a developer with 200+ memories, MEMORY.md never hits the 200-line truncation.
Given: 95 active memories; When: a new memory is written; Then: the oldest
accessed memory auto-archives, keeping active count ≤ 90.

**P3 — Memory health visible in pulse**
Given: pulse runs; Then: output includes `memory_active: 47`, `memory_archived: 23`,
`memory_index_age_secs: 14`.

---

## Upgrade 2 — CI Gate Enforcement (D → A)

### Problem
dream-studio's quality gates (review, verify, ship) are session-local. A developer
can push to a branch without running any gates. Continue.dev and GitHub Copilot
both enforce checks at the PR level. Nothing blocks a broken merge today.

### What "A-grade" looks like
- Gates run automatically on every PR as required status checks
- Hard block: PRs cannot merge if any gate fails
- Local-first: same checks run locally before push (`make ci-gate`)
- LLM-independent core: the Python checks (test, lint, fmt, security) run without Claude
- Extensible: a slot exists for LLM-powered checks when Claude Code CLI is available

### Approaches

**Option A — `scripts/ci_gate.py` + GitHub Actions (recommended)**
A single Python script wraps all checks: `make test`, `make lint`, `make fmt --check`,
`make security`. Callable locally (`py scripts/ci_gate.py`) and from CI
(`.github/workflows/ci-gate.yml`). Reports JSON results, exits non-zero on any
failure. The Actions workflow registers as a required status check. A separate
optional step uses Claude Code CLI (`claude --print`) for LLM-powered review —
skipped if `ANTHROPIC_API_KEY` is absent.

- Pros: Single source of truth for local + CI, testable in isolation, no new deps
- Cons: LLM-powered checks require API key in CI secrets

**Option B — GitHub Actions only (no local script)**
Move the make commands directly into the workflow YAML. No Python wrapper.

- Pros: Minimal code
- Cons: Local developers can't run the same check before push, divergence risk

**Option C — Pre-push git hook + GitHub Actions**
Add a git `pre-push` hook that runs the same checks. Blocks the push if any fail.

- Pros: Gates enforced before the branch even hits GitHub
- Cons: Pre-push hooks can be bypassed (`git push --no-verify`), harder to maintain

**Recommendation: Option A + Option C together** — CI gate script used by both
the GitHub Actions workflow (hard block) and a pre-push hook (local enforcement).

### Functional Requirements
- **FR-C01**: `scripts/ci_gate.py` MUST run test, lint, fmt-check, pip-audit
  and exit with code 0 (all pass) or 1 (any fail)
- **FR-C02**: Script MUST produce a structured JSON result to stdout:
  `{"status": "pass|fail", "checks": [{"name": ..., "passed": bool, "output": ...}]}`
- **FR-C03**: `.github/workflows/ci-gate.yml` MUST register as a required status check
  and run `py scripts/ci_gate.py` on every PR and push
- **FR-C04**: A `make ci-gate` target MUST invoke `scripts/ci_gate.py` locally
- **FR-C05**: `.claude/hooks/pre-push` MUST run `make ci-gate` and block push on failure
- **FR-C06**: If `ANTHROPIC_API_KEY` is set in CI, an optional LLM-review step
  MUST run `claude --print "review: check this PR for regressions"` and append
  results to the check output (advisory, non-blocking for now)

### Success Criteria
- **SC-C01**: A PR with failing tests cannot be merged (GitHub branch protection required)
- **SC-C02**: `make ci-gate` runs in < 60 seconds locally on the dream-studio repo
- **SC-C03**: CI gate output is human-readable in the GitHub Actions log without
  needing to download artifacts
- **SC-C04**: Pre-push hook catches failures before they hit GitHub 95% of the time
  (bypass via --no-verify is the 5% escape valve, by design)

### User Stories
**P1 — CI blocks broken PRs**
As a contributor, if I push a PR where tests fail at 68% coverage, the CI gate
fails and the PR is blocked from merging until I fix it.

**P2 — Local gate before push**
As a developer, running `make ci-gate` locally produces the same output as CI —
no "works on my machine" surprises.

**P3 — LLM review in CI (optional)**
As a reviewer, when the CI gate runs on a PR with `ANTHROPIC_API_KEY` configured,
I see a dream-studio review summary in the Actions log as an advisory comment.

---

## Upgrade 3 — Token Efficiency Benchmarking & Optimization (Unknown → A)

### Problem
dream-studio loads 13 hooks, a routing table in CLAUDE.md, skill frontmatter,
and memory files on every session. The actual per-session token overhead is
unknown. The top community pain point for Claude Code is cost. Without
benchmarking, dream-studio cannot claim efficiency or identify where to optimize.

### What "A-grade" looks like
- Measured: exact overhead numbers published in README (tokens/session at startup)
- Segmented: overhead broken into categories (hooks, routing table, memories, skills)
- Optimized: at least one measurable reduction based on benchmark findings
- Ongoing: the on-token-log hook distinguishes overhead from user work per-session

### The Benchmark Methodology

**What to measure:**

| Category | How to measure | Expected range |
|---|---|---|
| Hook output overhead | Sum of all hook JSON outputs per turn (bytes → tokens ÷ 4) | 500–2,000 tokens/turn |
| Routing table (CLAUDE.md) | `wc -c ~/.claude/CLAUDE.md` ÷ 4 | 3,000–8,000 tokens (loaded once) |
| MEMORY.md + active memories | Sum of all memory file sizes ÷ 4 | 2,000–15,000 tokens |
| Skill SKILL.md on load | Individual SKILL.md file size ÷ 4 | 500–3,000 tokens per skill |
| Status bar | Status bar command output length ÷ 4 | 20–50 tokens/turn |
| System prompt | `CLAUDE_SYSTEM_PROMPT` env or equivalent | Varies by project |

**Controlled experiment design:**

```
Run A (baseline):    Empty settings.json, no hooks, minimal CLAUDE.md
Run B (hooks only):  Full hooks, empty CLAUDE.md
Run C (full):        Full hooks + full CLAUDE.md + memory files
```

Each run: execute the same 5 standard prompts ("what does this file do?", 
"fix a typo", "run tests", "create a feature branch", "summarize session").
Compare total tokens per run. Delta B-A = hook overhead. Delta C-B = CLAUDE.md + memory.

**Instrumentation:**

Extend `on-token-log` to capture per-turn segmentation:
```json
{
  "turn": 3,
  "prompt_tokens": 4821,
  "completion_tokens": 312,
  "hook_output_bytes": 847,
  "hook_output_tokens_est": 212,
  "session_id": "abc123"
}
```

A new `scripts/benchmark_tokens.py` script:
1. Reads token-log.md from a benchmark run
2. Groups by run label (baseline / hooks-only / full)
3. Computes overhead delta per category
4. Produces a markdown report to `~/.dream-studio/meta/token-benchmark.md`

**Optimization targets (post-measurement):**

| Likely finding | Optimization |
|---|---|
| Hook JSON outputs are verbose | Compress hook outputs to minimal JSON (remove nulls, abbreviate keys) |
| Routing table is large | Move rarely-used routes to a separate file, load on-demand |
| Memory files load all at once | Upgrade 1 (BM25) solves this |
| Skill gotchas.yml injected unnecessarily | Only inject gotchas when skill is actively running |

### Approaches

**Option A — Benchmark script + README publish (recommended)**
Build `scripts/benchmark_tokens.py`. Run the three controlled experiments. Publish
results in `docs/token-overhead.md` and link from README. Update on-token-log to
capture per-turn segmentation. This gives us the number, the breakdown, and
an ongoing monitoring signal.

- Pros: Accurate, reproducible, defensible numbers; creates ongoing monitoring
- Cons: Requires running controlled experiments (30–60 minutes of setup)

**Option B — Estimate from file sizes only**
Count bytes in all loaded files, divide by 4, publish as "estimated overhead."
No controlled experiments.

- Pros: 10 minutes of work
- Cons: Estimates are wrong (tokenization varies, not all files load every turn).
  Would be embarrassing to publish numbers that a user can easily disprove.

**Option C — Hook-level instrumentation only**
Add per-turn overhead tracking to on-token-log without running controlled experiments.
Wait until real session data accumulates, then analyze.

- Pros: Zero setup effort
- Cons: Confounded by user work — hard to isolate dream-studio overhead from
  actual session tokens. Takes weeks to accumulate clean data.

**Recommendation: Option A**

### Functional Requirements
- **FR-T01**: `scripts/benchmark_tokens.py` MUST accept `--run-label` and produce
  a `token-benchmark.md` report
- **FR-T02**: `on-token-log` MUST be extended to capture `hook_output_bytes` and
  estimated hook overhead tokens per turn
- **FR-T03**: Benchmark report MUST include: per-category overhead table,
  total startup overhead (tokens loaded before first user input), per-turn
  marginal overhead (tokens added by hooks each turn)
- **FR-T04**: README MUST be updated with a "Token Overhead" section linking
  to `docs/token-overhead.md`
- **FR-T05**: At least one measurable optimization MUST be implemented based on
  benchmark findings before publishing numbers
- **FR-T06**: `docs/token-overhead.md` MUST be regeneratable by running
  `py scripts/benchmark_tokens.py --publish`

### Success Criteria
- **SC-T01**: Startup overhead (tokens before first user input) is measured and
  documented to within ±10% accuracy
- **SC-T02**: Per-turn hook overhead is < 500 tokens/turn (if > 500, optimize first)
- **SC-T03**: Total session overhead for a 20-prompt session is < 8% of total tokens
  (dream-studio adds < 1-in-12 tokens vs. user work)
- **SC-T04**: Published numbers are reproducible by any user running the benchmark script

---

## P0 — First-Run Setup Experience (New → A)

### Problem
A developer who downloads dream-studio from GitHub hits an invisible wall: Python
version check, venv creation, dependency install, settings.json merge, and first-run
validation are all manual and undocumented. This is the #1 friction point for cold
GitHub downloads, and it creates support burden for every new user.

### What "A-grade" looks like
- One command gets a new user fully configured: `make setup` (Mac/Linux) or
  `install.ps1` (Windows)
- Python version is checked; clear error if unsupported version detected
- venv created and deps installed without manual steps
- `settings.json` merged non-destructively (user's existing settings preserved)
- First-run validation confirms hooks are wired, memory dir exists, pulse runs

### Approach (single option)
`scripts/setup.py` — a single Python script callable by both `make setup` and
`install.ps1`. Platform detection built in. Merge logic for settings.json is
additive only (never overwrites existing user keys).

### Functional Requirements
- **FR-S01**: `scripts/setup.py` MUST check Python version (≥ 3.11 required) and
  exit with a clear error message if the requirement is not met
- **FR-S02**: Script MUST create a venv at `.venv/` if one does not exist, then
  install all deps from `requirements.txt` into it
- **FR-S03**: Script MUST merge dream-studio hooks into `~/.claude/settings.json`
  non-destructively — existing keys are never overwritten, only new keys are added
- **FR-S04**: Script MUST create `~/.claude/projects/.../memory/` directory if it
  does not exist and write a starter `MEMORY.md` with placeholder header
- **FR-S05**: `Makefile` MUST expose a `setup` target that calls `py scripts/setup.py`
  (or `python` on non-Windows)
- **FR-S06**: `install.ps1` MUST call `py scripts/setup.py` after verifying
  PowerShell execution policy is not blocking execution
- **FR-S07**: Script MUST print a checklist summary at the end: each step marked
  ✓ (passed) or ✗ (failed with reason)

### Success Criteria
- **SC-S01**: A brand-new clone of the repo is fully configured in < 2 minutes
  via a single command
- **SC-S02**: Running setup a second time is idempotent — no overwrites, no errors
- **SC-S03**: Python version mismatch produces a human-readable error with the
  minimum version requirement stated

---

## Implementation Order

These four deliverables are independent and can ship in any order. Recommended sequence:

0. **P0 Setup first** — unblocks any contributor; small scope, high user-facing impact
1. **Token Benchmark second** — informs whether memory (Upgrade 1) is actually the
   biggest overhead culprit before we build a FTS5 layer to fix it
2. **CI Gate third** — pure Python, no new deps, highest confidence delivery
3. **Memory Retrieval last** — builds on token benchmark findings; SQLite FTS5
   is stdlib-only, zero new dependencies

---

## Assumptions

- MEMORY.md format stays unchanged — BM25 layer is additive, not a migration
- CI gate is a required status check enforced via GitHub branch protection rules
  (separate manual step to configure in GitHub repo settings)
- Memory retrieval uses SQLite FTS5 (Python stdlib `sqlite3`) — zero new dependencies,
  BM25 ranking is built in, index persists on disk; `rank-bm25` is NOT added
- Benchmark experiments can be run manually by the Director (not automated in CI)
- LLM-powered CI review step is advisory only for now (non-blocking)

---

**Spec path**: `.planning/specs/grade-a-upgrade/spec.md`
Waiting for Director approval before plan.
