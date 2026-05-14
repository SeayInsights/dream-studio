# Token Overhead

## Methodology

Each session, `on-token-log.py` records prompt, completion, and hook I/O byte counts.
`benchmark_tokens.py` groups rows by run label and computes the per-category overhead delta
(hooks, routing table, memories, skills) relative to a bare-prompt baseline.

Categories measured:

| Category | What it covers |
|---|---|
| hooks | All pre/post-tool and lifecycle hook output injected into context |
| routing_table | Skill routing table lines loaded from CLAUDE.md |
| memories | MEMORY.md entries loaded at session start |
| skills | Skill prompt text injected on invocation |

## Regenerate this report

```
py scripts/benchmark_tokens.py --run-label <label> --publish
```

This reads `~/.dream-studio/meta/token-log.md`, computes the overhead table, and overwrites this file.

## No data yet?

The token log is written by `on-token-log.py` during live Claude Code sessions.
Run a few sessions with dream-studio active, then re-run the benchmark command above.
The `~/.dream-studio/meta/token-log.md` file is local to your machine and not committed to the repo.
