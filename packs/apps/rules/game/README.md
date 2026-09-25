# Game Development Rules

Path-scoped coding rules for Godot 4 game projects. Claude applies these automatically when editing files matching the glob patterns in each rule's frontmatter.

## Rules

| File | Applies To | Key Constraint |
|------|-----------|----------------|
| `gameplay-code.md` | `scripts/gameplay/`, `scripts/systems/`, `scripts/mechanics/` | No hardcoded values; signals up, never call siblings |
| `networking-code.md` | `scripts/networking/`, `scripts/multiplayer/` | Server-authoritative; never trust client state |
| `ai-code.md` | `scripts/ai/`, `scripts/npc/`, `scripts/enemies/` | Timer-based updates, not per-frame; debuggable state |
| `ui-code.md` | `scripts/ui/`, `scenes/ui/`, `scenes/hud/` | No game state ownership; localization-ready |
| `shader-code.md` | `shaders/`, `*.gdshader` | Performance budgets; uniform for all tunables |
| `data-files.md` | `data/**/*.json`, `balance.json` | Valid JSON; schema-consistent; documented changes |

## Usage

These rules are referenced by the `game-dev` skill. When building a game project, the skill instructs Claude to apply rules matching the current file path. The rules also work standalone if placed in a project's `.claude/rules/` directory.
