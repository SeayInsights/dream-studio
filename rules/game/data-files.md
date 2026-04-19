---
description: Rules for game data files — balance, items, levels, dialogue, config
globs:
  - "**/data/**/*.json"
  - "**/assets/data/**"
  - "**/design/balance/**"
  - "**/balance.json"
  - "**/config/**/*.json"
  - "**/gamedata/**/*.json"
  - "**/resources/**/*.json"
  - "**/src/data/**/*.json"
  - "**/*_data.json"
  - "**/items.json"
  - "**/levels.json"
  - "**/dialogue.json"
  - "**/factions.json"
---

# Data Files Rules

## JSON Validity
- All JSON files must be valid. Use `python -m json.tool <file>` to verify before commit.
- No trailing commas, no comments in JSON. Use JSONC only if the engine explicitly supports it.

## Schema Compliance
- Every data file type has an implicit schema. If `balance.json` has a `units` array, every unit must have the same fields.
- New fields get default values documented in the GDD — don't add undocumented keys.
- Numeric values must have reasonable bounds. A unit speed of 999999 is a data bug.

## Naming
- Files: `snake_case.json` — no spaces, no capitals.
- Keys: `snake_case` — consistent with GDScript convention.
- Arrays of entities: plural key (`"units"`, `"items"`, `"factions"`).

## Organization
- One file per concern: `balance.json` for gameplay numbers, `items.json` for item definitions, `dialogue.json` for NPC text.
- Don't nest deeper than 3 levels. If you need more, split into separate files.
- Large datasets (100+ entries): consider splitting by category (`items_weapons.json`, `items_armor.json`).

## Change Safety
- Data changes affect gameplay — treat balance file edits like code changes.
- Document the reason for numeric changes in the commit message (e.g., "reduce archer damage 15→12: too dominant in early game").
