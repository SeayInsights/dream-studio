# Adapter Templates

Each `.j2` template in this directory generates a platform-specific adapter file from dream-studio's skill definitions.

## Required Template Variables

Every template receives these variables:

| Variable | Type | Description |
|---|---|---|
| `skill_name` | string | The skill's name from SKILL.md frontmatter |
| `triggers` | list[str] | Trigger keywords that activate the skill |
| `workflow_steps` | list[str] | Numbered workflow steps from the skill body |

## Optional Variables

| Variable | Type | Description |
|---|---|---|
| `description` | string | Skill description from frontmatter |
| `gotchas` | list[dict] | Avoid entries from gotchas.yml (`title`, `context`, `fix`) |
| `domains` | list[dict] | Domain knowledge files (`name`, `content`) — only if `include_domains: true` in config |

## Adding a New Platform

1. Create `<platform>.j2` in this directory
2. Add an entry to `scripts/adapters_config.yml`
3. Run `make adapters` — done

No script edits required (SC-005).
