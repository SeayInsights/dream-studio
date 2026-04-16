# Session Context

Rolling log of session-end snapshots. The `on-meta-review` hook appends entries here when a session closes. The hook reads this file on the next session-end trigger to draft retrospective prompts.

Keep this file trimmed — delete entries older than 30 days unless they're flagged as architecture decisions. Format below is just a reference; the hook writes its own format.

---

<!--
Example entry (written automatically by on-meta-review):

## Session End — 2026-04-16T12:00:00+00:00
**Session:** <uuid>
**Tokens used:** <n>
**Summary:** <one-line summary>

### Retrospective prompts
1. **What worked?** — What did this session produce that was clean, fast, or reusable?
2. **What slowed us down?** — Where did ambiguity, tool failure, or missing context cause friction?
3. **What should be a pattern?** — Is there a reusable approach here worth saving?
4. **What should change?** — Agent routing, tool choice, prompt structure — anything that should be different next time?
-->
