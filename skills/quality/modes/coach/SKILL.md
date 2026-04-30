---
name: coach
description: "Claude Code workflow coach — evaluates HOW you're using Claude Code, not WHAT you're building. Surfaces non-obvious best practices for context management, PR hygiene, agent dispatch, and skill routing. Trigger on /coach or coach:."
user_invocable: true
args: mode
argument-hint: "[workflow-fit | context-health | pr-hygiene | agent-dispatch] [--quick]"
pack: quality
chain_suggests: []
---

# Coach — Claude Code Workflow Advisor

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`/coach <mode>`, `coach:`, or invoked when you want meta-feedback on your Claude Code usage patterns

## Purpose
This skill does not build things. It evaluates the process by which you build things. Spawn parallel analyst subagents that each look at one dimension of your Claude Code workflow and return a grade with specific improvements.

Use coach when:
- A session felt inefficient but you're not sure why
- You want to know if you're using the right skill for a task
- Context is getting heavy and you want to know when to rewind
- You want to audit your PR patterns or agent dispatch habits

## Modes
- `workflow-fit` — Is this task matched to the right dream-studio skill?
- `context-health` — Is context being managed well? When should you start a new session?
- `pr-hygiene` — Are PRs sized correctly? Commit message quality? Branch hygiene?
- `agent-dispatch` — Are subagents being used at the right times? Model assignments correct?
- `route-classify` — Classify ambiguous intent against all known dream-studio triggers. Decision tree:
  1. **Match against dream-studio skill triggers.**
     - Confidence ≥ 0.8 → invoke the matched skill immediately via the Skill tool (do not just name it).
     - Confidence < 0.8 → present top 3 matches with scores and ask the Director to confirm before invoking.
  2. **No dream-studio skill match → check `skills/domains/ingest-log.yml`.**
     - Find the plugin root (two directories up from `skills/coach/`).
     - Read `<plugin-root>/skills/domains/ingest-log.yml`.
     - For each entry where `persona_md_path` is not null: check if any keyword in `keywords[]` matches the user's intent.
     - **Match found:** (a) check if `<plugin-root>/<persona_md_path>` exists locally; (b) if yes, output: `cp <plugin-root>/<persona_md_path> ~/.claude/agents/<filename>`; (c) tell the user "Once installed, Claude Code will auto-invoke this agent for matching tasks." Do NOT dispatch the agent yourself.
     - **No match:** fall through to generic coach guidance and offer: "Run `workflow: domain-ingest domain: <detected-domain>` to synthesize a specialist for this domain."
  3. **`ingest-log.yml` missing or malformed** → skip the check, fall through to generic guidance.
  Invoked automatically by the CLAUDE.md routing fallback when no trigger keyword matched.
- `zoom-out` — Scope health check: are we still solving the right problem? Detects scope creep, goal drift, and solution-problem mismatch. Run when a build feels larger than the original spec, or when you suspect the original goal has shifted. Dispatches the `analysts/zoom-out.yml` analyst.
- `--quick` flag — Run the single most relevant analyst based on context

## Signal Scale

| Signal | Workflow quality meaning |
|--------|--------------------------|
| strong-accept | Excellent practice — doing this well |
| accept | Good, with minor improvements available |
| neutral | Mixed — doing some things well, others not |
| reject | Needs improvement — this pattern is costing efficiency |
| strong-reject | Anti-pattern detected — fix this before continuing |

## Analyst Output Schema

Every analyst returns exactly this JSON:
```json
{
  "signal": "strong-accept|accept|neutral|reject|strong-reject",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences on what's working and what isn't",
  "key_factors": [
    "specific improvement or confirmation",
    "specific improvement or confirmation",
    "specific improvement or confirmation"
  ]
}
```

`key_factors` must be actionable: not "context is high" but "Session is at ~280k tokens — rewind before the next complex build task to preserve synthesis quality."

---

## Usage Examples

```
/coach workflow-fit
About to fix a bug in the payment flow — should I use debug, build, or just edit inline?

/coach context-health
This session is 2 hours in, built the full auth module. Should I start a new session?

/coach pr-hygiene
Just opened a PR with 340 lines touching 8 files across auth and payment. Too large?

/coach agent-dispatch
I ran 3 agents sequentially when they could have been parallel. How often am I doing this?

/coach full-audit
Three builds today, all inline without think or plan first. Session at ~250k tokens.
```

## Orchestration Steps

### Step 0: Parse Arguments

- `mode` — if absent: run `workflow-fit` by default (most useful starting point)
- `--quick` — single-analyst mode
- `input` — description of the current session, task, or workflow you want evaluated. If no input: use the current conversation context as the subject.

### Step 1: Validation Gate (BP1)

Read `skills/coach/modes.yml`. Validate analyst YAMLs exist and have required fields.

### Step 2: Concurrency Guard (BP9)

Read `~/.dream-studio/coach/checkpoint.json`. If `status: "reviewing"`: offer Resume/Restart/Cancel.

### Step 3: Input Summary (BP8)

Summarize what's being evaluated:
- Current session state (approximate token count if known, what has been done)
- The specific workflow or decision being reviewed
- Any context about recent patterns or recurring issues

### Step 4: Dispatch Analyst Subagents

Standard dispatch pattern. Each analyst evaluates one dimension of workflow quality.

All analysts use the same 5-point signal scale. A `reject` from any analyst is a flag to address before continuing.

Validate responses (BP3). Write checkpoint after each wave.

For `zoom-out` mode: dispatch `analysts/zoom-out.yml`. It asks 5 scope-health questions against the current session context and returns a signal (strong-accept = scope clean, strong-reject = fundamental misalignment, stop and re-align with Director).

### Step 5: Quorum Check (BP2)

Coach uses low quorum (1-2) since modes are narrow. Short-circuit if single-analyst mode.

### Step 6: Scoring and Synthesis

Coach does not use the "any-reject" strategy — a reject on pr-hygiene doesn't block workflow-fit.

Instead: present each analyst's grade independently. Synthesize only if multiple analysts return contested signals on the same dimension.

### Step 7: Write Report

```markdown
# Coach Session: {mode} — {session_summary}
**Date:** {ISO-8601}

## Workflow Grades

| Dimension | Signal | Confidence |
|-----------|--------|------------|
| {analyst} | {signal} | {confidence} |

## Findings

{For each analyst:}
### {analyst-name}: {signal}
{reasoning}

**Actions:**
{key_factors as bulleted list}
```

Write to: `~/.dream-studio/coach/reports/coach-{mode}-{YYYY-MM-DD}.md`

### Step 8: Update State

Checkpoint: `status: "complete"`, `report_path`.
Feed `~/.dream-studio/feeds/coach.json`: increment `sessions_completed`, set `last_session`.

### Step 9: Present Results

1. **Grades table:** analyst → signal → one-line summary
2. **Top 3 actions:** the highest-priority improvements across all analysts
3. **Report path** for full detail

Keep presentation tight. Coach is meta — it shouldn't take longer than the work it's reviewing.

---

## Anti-patterns

- **Running coach instead of fixing** — coach identifies problems, it doesn't fix them. After running coach, go implement the changes.
- **Using coach for every session** — run it when something felt off, not as a ritual. If everything is green, that's information too — you're doing well.
- **Ignoring strong-reject signals** — a strong-reject from any analyst means stop and fix that pattern before continuing. Don't carry technical debt in your workflow.
- **Stale workflow-fit analyst** — after adding a new dream-studio skill, update `coach/analysts/workflow-fit.yml` skill list or the routing guidance will be wrong. See the comment at the top of that file.
