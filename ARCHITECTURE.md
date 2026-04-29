# dream-studio Architecture

## Two-Layer Design

dream-studio has two distinct layers. They serve different purposes and must not be confused.

### Layer 1 — Python Hook Runtime (`packs/`)

Python hooks that execute in response to Claude Code events. These are live, running code.

```
packs/
├── core/hooks/        # on-changelog-nudge, on-milestone-end, on-stop-handoff
├── meta/hooks/        # on-pulse, on-meta-review, on-context-threshold, on-tool-activity
├── quality/hooks/     # on-agent-correction, on-quality-score, on-security-scan
├── domains/hooks/     # on-game-validate
└── core/context/      # Context docs injected by hooks (director-preferences, session-primer)
```

**Rules:**
- Never edit a hook without running its tests
- Hooks read from `~/.dream-studio/` (config.json, meta/, draft-lessons/)
- Hooks are registered via the `dream-studio@dream-studio` plugin entry in settings.json
- `packs/core/context/` docs are injected as session context — keep them current

### Layer 2 — Claude Skill Guidance (`skills/`)

Markdown instruction files that Claude reads when a skill is invoked. Not executable code.

```
skills/
├── */SKILL.md         # Instructions Claude follows when the skill is triggered
├── */gotchas.yml      # Known failure patterns — Claude reads at skill start
├── */config.yml       # Skill-specific config (thresholds, model defaults)
├── core/              # Shared modules imported by multiple skills
└── domains/           # Domain knowledge YAMLs (BI, security, design, etc.)
```

**Rules:**
- `on-skill-load.py` reads SKILL.md when a skill is triggered via the Skill tool
- Adding a new skill requires BOTH a SKILL.md in `skills/<name>/` AND registration in the global routing table (CLAUDE.md)
- Skill config.yml values are read by Claude at runtime — they do not affect Python hooks
- `sync-cache.ps1` runs after every skills/ edit to push changes to the plugin cache

## How They Connect

```
User triggers skill → guard-skills.sh + track-skill-usage.sh (PreToolUse hooks)
                    → on-skill-load.py reads skills/<name>/SKILL.md
                    → Claude follows SKILL.md instructions
                    → PostToolUse hooks fire (on-quality-score, on-tool-activity, etc.)
                    → sync-cache.ps1 syncs skills/ if any SKILL.md was edited
```

## Adding a New Skill

1. Create `skills/<name>/` with: `SKILL.md`, `gotchas.yml`, `config.yml`, `metadata.yml`, `changelog.md`
2. Add the skill's trigger to the routing table in `~/.claude/CLAUDE.md`
3. Add to `dream-studio/CLAUDE.md` routing table
4. Run `scripts/sync-cache.ps1` to push to plugin cache
5. If the skill needs a custom hook, add it to `packs/<pack>/hooks/` and register in plugin manifest

## Key Paths

| Purpose | Path |
|---------|------|
| Global config | `~/.dream-studio/config.json` |
| Draft lessons | `~/.dream-studio/meta/draft-lessons/` |
| Promoted lessons | `~/.dream-studio/meta/lessons/` |
| Pulse snapshots | `~/.dream-studio/meta/pulse-latest.json` |
| Claude memory | `~/.claude/projects/C--Users-Dannis-Seay/memory/` |
| Skill cache | synced by `scripts/sync-cache.ps1` after edits |
