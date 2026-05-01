# dream-studio Scripts

Standalone CLI tools for studio intelligence, analytics, and maintenance.
All scripts are run from the repo root with `py scripts/<name>.py`.

---

## Quick Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `session_analytics.py` | Parse session history for trends | `py scripts/session_analytics.py [--days 90]` |
| `memory_audit.py` | Scan memory files for staleness/conflicts | `py scripts/memory_audit.py [--days 60]` |
| `research_cache.py` | Manage the persistent research cache | `py scripts/research_cache.py <command>` |
| `source_ranker.py` | Score research source quality | `py scripts/source_ranker.py --sources <file>` |
| `resume_from_handoff.py` | Generate a session resume briefing | `py scripts/resume_from_handoff.py [file]` |
| `spec_risk_check.py` | Pre-populate spec edge cases from prior experience | `py scripts/spec_risk_check.py <topic>` |
| `lesson_queue.py` | Triage draft lessons | `py scripts/lesson_queue.py list` |
| `lint_skills.py` | Validate SKILL.md structure | `py scripts/lint_skills.py` |
| `benchmark_tokens.py` | Compute per-category token overhead | `py scripts/benchmark_tokens.py --run-label <label>` |
| `ci_gate.py` | Run all quality checks (CI) | `py scripts/ci_gate.py` |
| `generate_routing.py` | Regenerate routing table in CLAUDE.md | `py scripts/generate_routing.py` |
| `build_adapters.py` | Build multi-AI adapter configs from SKILL.md | `py scripts/build_adapters.py` |
| `validate_client_profile.py` | Validate a client profile YAML | `py scripts/validate_client_profile.py <profile.yaml>` |
| `validate_analysts.py` | Check coach analyst YAML coverage | `py scripts/validate_analysts.py` |
| `init_security_state.py` | Initialize security directory tree | `py scripts/init_security_state.py` |
| `setup.py` | First-run setup and post-pull updates | `py scripts/setup.py` |
| `sync_docs.py` | Regenerate workflow table in README.md | `py scripts/sync_docs.py` |
| `sync-cache.ps1` | Mirror skills into Claude plugin cache | `pwsh -File scripts/sync-cache.ps1` |
| `bom.py` | Emit a build snapshot as bom.json | `py scripts/bom.py [output.json]` |

---

## Detailed Usage

### session_analytics.py

Parses historical session data from `.sessions/` directories, detects patterns, and produces trend reports.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--days N` | 90 | Look-back window in days |
| `--project PATH` | (all) | Limit to a specific project directory |
| `--json` | off | Print raw JSON only (skip formatted table) |

**Output:** `~/.dream-studio/state/session-analytics.json` plus a formatted summary table on stdout.

**Examples:**
```
py scripts/session_analytics.py
py scripts/session_analytics.py --days 30
py scripts/session_analytics.py --project C:\Users\Dannis Seay\builds\dream-studio --json
```

---

### memory_audit.py

Scans Claude memory files (`~/.claude/projects/*/memory/`) for staleness, conflicts, and gaps.
Parses YAML frontmatter from each `.md` file to detect outdated entries.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--days N` | 60 | Files not updated within N days are flagged stale |
| `--memory-path PATH` | (auto-discover) | Scan a specific memory directory instead of all |
| `--verbose` | off | Show details for every file, not just flagged ones |
| `--json` | off | Output results as JSON |

**Examples:**
```
py scripts/memory_audit.py
py scripts/memory_audit.py --days 30 --verbose
py scripts/memory_audit.py --memory-path ~/.claude/projects/my-project/memory/
py scripts/memory_audit.py --json
```

---

### research_cache.py

CLI for managing the dream-studio persistent research cache (`~/.dream-studio/state/`).
Research entries are keyed by topic and have automatic staleness by domain prefix:
- `security-*`, `vuln-*`, `cve-*` → 30-day TTL
- `market-*`, `competitive-*`, `competitor-*` → 90-day TTL
- `tech-*`, `architecture-*`, `arch-*` → 180-day TTL
- All others → 90-day TTL

**Commands:**

| Command | Description |
|---------|-------------|
| `save <topic> --sources '<json>'` | Store research for a topic |
| `get <topic>` | Retrieve cached research for a topic |
| `stale` | List topics past their refresh date |
| `refresh <topic>` | Update the refresh-due date for a topic |
| `prune --days N` | Delete entries older than N days |
| `list [--json]` | List all cached topics |
| `stats` | Show cache summary counts |

**Examples:**
```
py scripts/research_cache.py save "security-owasp" --sources '[{"url":"https://owasp.org","tier":"1","date":"2026-05-01","key_findings":"Top 10 list"}]'
py scripts/research_cache.py get "security-owasp"
py scripts/research_cache.py stale
py scripts/research_cache.py list
py scripts/research_cache.py prune --days 180
py scripts/research_cache.py stats
py scripts/research_cache.py list --json
```

---

### source_ranker.py

Scores a list of research sources against methodology rules from `skills/domains/research/analysis.yml`.
Checks for triangulation coverage, source independence, bias, and counter-arguments.

**Arguments:**

| Flag | Description |
|------|-------------|
| `--sources <file>` | Path to a JSON file containing sources list |
| `--stdin` | Read sources JSON from stdin |
| `--json` | Output results as JSON |

**Input format** (JSON array):
```json
[{"url": "https://example.com", "name": "Source Name", "tier": "1", "findings": "..."}]
```

**Output fields:** `triangulation_score`, `source_count`, `tier1_count`, `tier1_pct`, `domains`,
`shared_domains`, `independence` (OK/SUSPECT), `bias_flag` (PASS/FLAG),
`counter_argument` (PRESENT/MISSING), `confidence` (LOW/MEDIUM/HIGH), `gaps`.

**Examples:**
```
py scripts/source_ranker.py --sources sources.json
cat sources.json | py scripts/source_ranker.py --stdin
py scripts/source_ranker.py --sources sources.json --json
```

---

### resume_from_handoff.py

Reads a handoff JSON file from `.sessions/` and produces a structured briefing for resuming a session.
Auto-discovers the most recent `handoff-*.json` if no file is specified.

**Arguments:**

| Flag | Description |
|------|-------------|
| `[handoff.json]` | Explicit handoff file path (optional) |
| `--brief` | Output only the one-line resume command |
| `--checkout` | Also run `git checkout` to the handoff's branch |

**Output:** A formatted session briefing with branch, open tasks, and context summary.

**Examples:**
```
py scripts/resume_from_handoff.py
py scripts/resume_from_handoff.py .sessions/2026-05-01/handoff-build-api.json
py scripts/resume_from_handoff.py --brief
py scripts/resume_from_handoff.py --checkout
```

**Used by:** `workflows/daily-standup.yaml` — runs with `--brief` as the final standup step.

---

### spec_risk_check.py

Scans prior experience for a topic before writing a spec. Searches three sources:
1. `gotchas.yml` entries across all skills (keyword match)
2. Past handoff/recap sessions in `~/.dream-studio/.sessions/`
3. Draft lessons in `~/.dream-studio/meta/draft-lessons/`

Outputs at most 5 gotchas, 3 sessions, and 3 lessons.

**Arguments:**

| Flag | Description |
|------|-------------|
| `<topic>` | Required. Topic string to search (space-separated keywords) |
| `--json` | Output results as JSON |

**Examples:**
```
py scripts/spec_risk_check.py "auth token refresh"
py scripts/spec_risk_check.py "security scan integration" --json
```

**Used by:** `dream-studio:core think` — mandated in the gotcha `run spec_risk_check.py before writing Edge Cases`.

---

### lesson_queue.py

CLI for triaging draft lessons stored in `~/.dream-studio/meta/draft-lessons/`.

**Commands:**

| Command | Description |
|---------|-------------|
| `list` | List all draft lessons (default: pending only) |
| `list --pending` | List DRAFT status lessons |
| `list --promoted` | List PROMOTED lessons |
| `list --rejected` | List REJECTED lessons |
| `promote <file> --target <skill/gotchas.yml>` | Mark a lesson promoted and record its target |
| `reject <file>` | Mark a lesson rejected |
| `stats` | Show summary counts by status |

**Examples:**
```
py scripts/lesson_queue.py list
py scripts/lesson_queue.py list --pending
py scripts/lesson_queue.py promote lesson-2026-05-01.md --target skills/core/modes/build/gotchas.yml
py scripts/lesson_queue.py reject lesson-2026-04-15.md
py scripts/lesson_queue.py stats
```

**Used by:** `workflows/daily-standup.yaml` — runs `list --pending` to surface unreviewed lessons.

---

### lint_skills.py

Validates all `SKILL.md` files for structural correctness: required frontmatter fields,
required sections, and `gotchas.yml` schema if present.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--path PATH` | `skills/` | Directory to scan (scans all SKILL.md files recursively) |
| `--verbose` | off | Show pass details in addition to failures |

**Exit codes:** 0 = all pass, 1 = one or more failures.

**Examples:**
```
py scripts/lint_skills.py
py scripts/lint_skills.py --path skills/core
py scripts/lint_skills.py --verbose
```

---

### benchmark_tokens.py

Computes per-category token overhead from `~/.dream-studio/meta/token-log.md`.
Groups rows by run label, estimates overhead per category (routing table, memories, SKILL.md, etc.),
and writes a report to `~/.dream-studio/meta/token-benchmark.md`.

**Arguments:**

| Flag | Description |
|------|-------------|
| `--run-label <label>` | Required. Session label prefix to group rows by |
| `--publish` | Copy report to `docs/token-overhead.md` in the repo |

**Examples:**
```
py scripts/benchmark_tokens.py --run-label "build-api-v2"
py scripts/benchmark_tokens.py --run-label "build-api-v2" --publish
```

---

### ci_gate.py

Runs all quality checks (test, lint, fmt, security via `make`) and reports pass/fail as JSON.
If `ANTHROPIC_API_KEY` is set, adds a non-blocking advisory review step.

**Exit codes:** 0 = all pass, 1 = any failure.

**Examples:**
```
py scripts/ci_gate.py
make ci-gate
```

---

### generate_routing.py

Reads each skill's `metadata.yml` and regenerates the routing table between
`<!-- BEGIN AUTO-ROUTING -->` and `<!-- END AUTO-ROUTING -->` sentinels in `CLAUDE.md`.
Idempotent — running twice produces byte-identical output.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--claude-md PATH` | `CLAUDE.md` | Target file to update |
| `--skills-dir PATH` | `skills/` | Root directory for skill metadata |
| `--dry-run` | off | Print diff without writing |

**Examples:**
```
py scripts/generate_routing.py
py scripts/generate_routing.py --dry-run
py scripts/generate_routing.py --claude-md ~/.claude/CLAUDE.md
```

---

### build_adapters.py

Generates platform-specific config files from `SKILL.md` sources using Jinja2 templates
in `scripts/adapter_templates/`. Adapter targets are defined in `scripts/adapters_config.yml`.

Requires: `pip install pyyaml jinja2`

**Examples:**
```
py scripts/build_adapters.py
```

---

### validate_client_profile.py

Validates a client profile YAML against the dream-studio client profile schema.

Requires: `pip install pyyaml`

**Arguments:** `<profile.yaml>` — path to the YAML file to validate.

**Exit codes:** 0 = valid, 1 = validation errors found.

**Examples:**
```
py scripts/validate_client_profile.py clients/kroger.yaml
```

---

### validate_analysts.py

Verifies that every known skill (from `skills/*/metadata.yml`) has analyst coverage
in `skills/quality/modes/coach/analysts/*.yml`. Used to keep the coach skill complete.

**Exit codes:** 0 = all covered, 1 = gaps found.

**Examples:**
```
py scripts/validate_analysts.py
```

---

### init_security_state.py

Idempotent initializer for `~/.dream-studio/security/` — creates the directory tree
and empty seed files needed by the enterprise security pack. Safe to re-run.

**Examples:**
```
py scripts/init_security_state.py
```

---

### setup.py

First-run setup and post-`git pull` updater. Configures hooks, settings, and the Python venv.
Requirements: Python 3.11+, no third-party dependencies.

**Examples:**
```
py scripts/setup.py
```

---

### sync_docs.py

Regenerates the Workflows table in `README.md` between `<!-- workflows-table-start -->`
and `<!-- workflows-table-end -->` sentinels from all `workflows/*.yaml` files.

Requires: `pip install pyyaml`

**Arguments:**

| Flag | Description |
|------|-------------|
| `--check` | Exit 1 if README is out of date (CI mode); do not write |

**Examples:**
```
py scripts/sync_docs.py
py scripts/sync_docs.py --check
```

---

### sync-cache.ps1

PowerShell script. Mirrors the `skills/` directory into the Claude plugin cache
(`~/.claude/plugins/cache/dream-studio/`). Removes cache-only directories that
no longer exist in the build (full mirror).

Run from the repo root:
```powershell
pwsh -File scripts/sync-cache.ps1
```

---

### bom.py

Emits a build snapshot as `bom.json`: current git SHA, Python version, installed pip packages,
and a list of failed tests.

**Arguments:** Optional output path (default: `bom.json`).

**Examples:**
```
py scripts/bom.py
py scripts/bom.py build/bom.json
```

---

## hooks/lib/ Utilities

These are importable modules, not standalone scripts. They can also be invoked from the CLI
for testing and integration use.

### model_selector.py

Recommends a model tier (`haiku` | `sonnet` | `opus`) for a given skill based on historical
telemetry from `~/.dream-studio/state/studio.db`.

**Decision rules (in priority order):**
1. No history → return `--default` (respecting floor)
2. Haiku success rate ≥ 95% → recommend haiku
3. Current most-used tier success rate < 80% → upgrade one tier
4. Skills in `{think, secure, analyze, review}` → always recommend opus
5. Otherwise → return the most-used tier

**CLI:**
```
py hooks/lib/model_selector.py --skill=<name> [--default=sonnet]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--skill` | required | Skill name to look up |
| `--default` | `sonnet` | Fallback tier when no history exists (`haiku`/`sonnet`/`opus`) |

**Output:** Exactly one word on stdout: `haiku`, `sonnet`, or `opus`.

**Module API:**
```python
from hooks.lib.model_selector import recommend_model
tier = recommend_model("build", default="sonnet")  # → "sonnet"
```

**Examples:**
```
py hooks/lib/model_selector.py --skill=build
py hooks/lib/model_selector.py --skill=think --default=opus
```

---

### context_compiler.py

Compiles a minimal, deterministic prompt for a specific skill mode. Used to produce
byte-identical static context for Claude prompt caching.

Reads from:
- `skills/<pack>/modes/<skill>/SKILL.md` — extracts Rules, Process, Output Format, Anti-patterns sections
- `skills/<pack>/modes/<skill>/gotchas.yml` — injects high/critical severity entries only
- `skills/core/orchestration.md` — injects Model Selection and Response Handling sections
- Optional repo-context JSON — inlined as a `Project Context` block

Drops sections matching: "example usage", "examples", "template", "trigger",
"used by", "integration", "mode dispatch", "shared resources".

**CLI:**
```
py hooks/lib/context_compiler.py --skill=<mode> --pack=<pack> \
    [--repo-context=<path>] [--project-root=.]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--skill` | required | Skill mode name (e.g. `build`, `debug`) |
| `--pack` | required | Pack name (e.g. `core`, `quality`) |
| `--repo-context` | none | Path to a JSON repo-context file |
| `--project-root` | `.` | Root of the dream-studio project |

**Output:** Compiled markdown on stdout, UTF-8 encoded.

**Module API:**
```python
from hooks.lib.context_compiler import compile_context
text = compile_context("build", "core", repo_context_path=None, project_root=".")
```

**Examples:**
```
py hooks/lib/context_compiler.py --skill=build --pack=core
py hooks/lib/context_compiler.py --skill=debug --pack=quality --project-root=.
py hooks/lib/context_compiler.py --skill=think --pack=core --repo-context=.planning/repo_context.json
```

---

### prompt_assembler.py

Cache-optimized prompt builder for subagent dispatch. Combines a static context file
(output of `context_compiler.py`) with a role template and dynamic task content.

The static context becomes the byte-identical prefix (maximizes cache hits).
Dynamic content (task description, decisions) is appended after a separator.

**Templates:** `implementer` | `reviewer` | `auditor` | `explorer`

Template files live in `hooks/lib/prompt_templates/<name>.md`.

**CLI:**
```
py hooks/lib/prompt_assembler.py --template=<name> --static-context=<path> \
    [--task-text=<text>] [--task-file=<path>] [--decisions=<text>]
```

| Flag | Description |
|------|-------------|
| `--template` | required. Agent role: `implementer`, `reviewer`, `auditor`, `explorer` |
| `--static-context` | required. Path to compiled context file (output of `context_compiler.py`) |
| `--task-text` | Inline task description |
| `--task-file` | Path to a file containing the task description |
| `--decisions` | Relevant decisions or constraints for the agent |

**Output:** Assembled prompt on stdout, UTF-8 encoded.

**Module API:**
```python
from hooks.lib.prompt_assembler import assemble_prompt
text = assemble_prompt("implementer", "compiled.md", task_text="Build the API endpoint")
```

**Examples:**
```
py hooks/lib/prompt_assembler.py --template=implementer --static-context=compiled.md --task-text="Build the API endpoint"
py hooks/lib/prompt_assembler.py --template=reviewer --static-context=compiled.md --task-file=review-scope.md
py hooks/lib/prompt_assembler.py --template=auditor --static-context=compiled.md --task-text="Audit security" --decisions="Use OWASP top 10"
```

---

## Integration with Skills

### Typical subagent dispatch pipeline

The three `hooks/lib/` utilities chain together:

```
context_compiler.py   →   prompt_assembler.py   →   Claude subagent
  (static context)          (assembled prompt)
```

`model_selector.py` is called first to pick the appropriate Claude tier before dispatch.

### Skill → script mapping

| Skill / pack | Scripts used |
|---|---|
| `dream-studio:core think` | `spec_risk_check.py`, `source_ranker.py`, `research_cache.py` |
| `dream-studio:core handoff` | `resume_from_handoff.py` (output consumed in standup) |
| `dream-studio:quality learn` | `lesson_queue.py` (promote/reject cycle) |
| Research (domains pack) | `research_cache.py` (get before research, save after), `source_ranker.py` (triangulation gate) |
| `workflows/daily-standup.yaml` | `lesson_queue.py list --pending`, `resume_from_handoff.py --brief` |
| CI / `make ci-gate` | `ci_gate.py`, `lint_skills.py`, `validate_analysts.py` |
| Routing maintenance | `generate_routing.py` (after adding/renaming skills) |
| Plugin sync | `sync-cache.ps1` (after `git pull` when skills change) |
