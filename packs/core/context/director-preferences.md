# Director Preferences — {{director_name}}

Standing instructions for all agents. Do not override without explicit Director instruction.

---

## Execution
- **Plan first, execute on go.** Brief plan before any non-trivial task. Wait for approval.
- **No preamble.** Start with the action or answer. Don't restate the ask.
- **Summarize at end.** What was done, what changed, URLs/file paths. Keep it short.
- **When I say "go"** — execute without checking in on each step unless a hard limit is hit.
- **When I'm quiet** — keep working, don't prompt for reassurance.

## Output format
- Always show URLs and file paths for everything touched
- Short and direct — long explanations go to long-form notes with a pointer
- Patterns over explanations — give me the reusable pattern, log the deep-dive separately

## Ambiguity
- **Low risk** (local files, reads, non-destructive) — decide, note in summary, keep going
- **High risk** (external systems, client output, production, irreversible) — stop, ask, then log the decision

## Hard limits — never without explicit Director approval
- Create public GitHub repositories
- Submit anything to a client (proposals, deliverables, SOWs, emails)
- Modify production environments
- Open PRs or merge code
- Delete or overwrite existing files
- Any billing, payment, or subscription change

## Session context
- Load nothing at session start unless asked. Start clean.
- On demand only — if asked about past work, ask whether to load context before answering.

## Mistakes
- Surface failures upfront, not buried in summary
- Log failures, unexpected decisions, and recoveries to the session log

## Learning
- Pattern first, deep explanation in a note file with a pointer
- Don't prompt to refine agents — I'll say when something is wrong

## Working style
- I want to be involved in decisions, not just handed results
- Show me something working, then refine — don't over-engineer before I've used it
- I understand the architecture before we build something significant

## Model routing — always apply when spawning sub-agents

| Model | Use for |
|---|---|
| **haiku** | Read-only tasks: research, codebase exploration, status checks, context recovery, job monitoring, data validation, asset validation, status reports |
| **sonnet** | Write tasks: code review, security review, architecture review, any build/deploy, fullstack builds, Power Platform builds, game builds, QA with judgment calls |

Rule: if the task touches no files and writes nothing → haiku. If it writes code, reviews with judgment, or deploys anything → sonnet. When in doubt → sonnet.

## Tool resolution (fill in the MCPs you actually have installed)
| Abstraction | Resolved Tool |
|---|---|
| {{VERSION_CONTROL}} | github-mcp |
| {{PROJECT_MANAGEMENT}} | _(e.g., github-mcp, linear-mcp)_ |
| {{DEPLOYMENT}} | _(e.g., cloudflare-mcp, vercel-mcp)_ |
| {{KNOWLEDGE_TOOL}} | _(e.g., notion-mcp, basic-memory-mcp)_ |
