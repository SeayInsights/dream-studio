# Godot 4 Engine Reference

## Version Info
- **Target version:** Godot 4.3 / 4.4 (stable as of 2025)
- **Reference last updated:** 2026-04-19
- **LLM training cutoff:** ~April 2025 (Claude Opus 4), ~Oct 2023 (GPT-4)
- **Risk level:** MEDIUM — Godot 4.x is stable but had significant API churn from 4.0→4.3
- **Max covered version:** 4.4 (set ENGINE_REF_MAX_VERSION in on-game-validate.py to match)

## Verification Status

This reference was authored by an LLM and cross-checked against official Godot documentation.
Individual entries are tagged with confidence levels:

| Tag | Meaning |
|-----|---------|
| `[VERIFIED]` | Cross-checked against official Godot docs/changelog. Safe to rely on. |
| `[HIGH-CONFIDENCE]` | Consistent with multiple official sources but not line-by-line verified. |
| `[UNVERIFIED]` | LLM-generated from training data. May contain inaccuracies. Verify before relying on for production code. |

**When suggesting an API marked [UNVERIFIED], always tell the user:** "This is from my training data and hasn't been verified against the current Godot docs. Check the official API reference before using in production."

## When to consult this reference
- Before suggesting any API that changed between Godot 4.0 and 4.3+
- When the user's `project.godot` specifies a version — check compatibility
- When writing networking, navigation, or tilemap code (highest-churn areas)
- When the game validation hook warns about version staleness

## Staleness Protocol
If the user's project uses a Godot version **newer than 4.4**:
1. Warn that this reference may be outdated
2. Suggest checking the official Godot migration guide
3. For any API suggestion, add: "verify this works in Godot [version]"
4. Do NOT silently suggest patterns from this reference without the warning

## Post-cutoff risk areas
| Area | Risk | Source |
|------|------|--------|
| TileMap → TileMapLayer | HIGH | [VERIFIED] — Godot 4.3 changelog |
| NavigationServer | MEDIUM | [HIGH-CONFIDENCE] — 4.1-4.3 changelogs |
| MultiplayerAPI | MEDIUM | [HIGH-CONFIDENCE] — 4.2+ docs |
| GDExtension | MEDIUM | [UNVERIFIED] — binding API still evolving |
| Compositor effects | LOW | [HIGH-CONFIDENCE] — new in 4.3 |
| AnimationMixer | MEDIUM | [HIGH-CONFIDENCE] — 4.2 changelog |

## Official Sources (for manual verification)
- Godot 4.3 migration: https://docs.godotengine.org/en/stable/tutorials/migrating/upgrading_to_godot_4.3.html
- Godot 4.x changelog: https://godotengine.org/releases/
- GDScript reference: https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/
- Class reference: https://docs.godotengine.org/en/stable/classes/
