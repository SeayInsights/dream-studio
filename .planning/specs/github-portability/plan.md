# GitHub Portability — Plan

## Summary
Remove hardcoded user-specific paths from skill files so dream-studio works for any GitHub user who clones the repo. Skills now read user config from `~/.dream-studio/config.json` at runtime instead of embedding absolute paths.

## Approach (Option C)
Skills read from `~/.dream-studio/config.json` directly. No build-time substitution needed. Missing config produces a clear actionable error pointing to `workflow: run studio-onboard`.

## Files Changed
- `skills/learn/config.yml` — cleared `harvest.projects_root` (was `C:\Users\Dannis Seay\builds`)
- `skills/learn/SKILL.md` — Step 4 reads `claude_memory_path` from config.json; added `### Config check` gate before scan protocol
- `skills/handoff/SKILL.md` — added `project_root` field to JSON schema; Step 6 captures absolute CWD as `project_root`

## Remaining Note
`skills/STRUCTURE.md` contains two example `cd` paths with the old username — these are documentation examples, not functional paths. Not in scope for this fix.
