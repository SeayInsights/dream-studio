# Engine Reference Verification Checklist

Use this checklist when updating the engine reference for a new Godot version.

## Before Updating

1. [ ] Note the new Godot version being targeted
2. [ ] Read the official release notes / migration guide for that version
3. [ ] Update `ENGINE_REF_MAX_VERSION` in `hooks/handlers/on-game-validate.py`
4. [ ] Update the "Target version" in `VERSION.md`

## For Each Entry in breaking-changes.md

- [ ] Check the claim against the official Godot changelog
- [ ] Verify the "Old" and "New" code samples actually compile in the target version
- [ ] Update the verification tag to `[VERIFIED]` if confirmed
- [ ] Add `Source:` line with the official doc URL
- [ ] Remove or update entries that are no longer relevant

## For Each Entry in deprecated-apis.md

- [ ] Confirm the deprecated class/method still shows a deprecation warning
- [ ] Confirm the replacement works in the target version
- [ ] Check if any previously-deprecated APIs were fully removed (upgrade from warning → error)
- [ ] Update the "Common LLM Mistakes" table with any new patterns

## For Each Entry in best-practices.md

- [ ] Verify code samples compile and run correctly
- [ ] Check if the recommended pattern has been superseded by something newer
- [ ] Update verification tags

## New APIs to Add

For each new Godot version, check these high-churn areas:
- [ ] Navigation (NavigationServer, NavigationAgent)
- [ ] Multiplayer (MultiplayerAPI, Spawner, Synchronizer)
- [ ] TileMap / TileMapLayer
- [ ] GDExtension bindings
- [ ] Rendering / Compositor
- [ ] Animation (AnimationMixer, AnimationPlayer, AnimationTree)
- [ ] Physics (PhysicsServer2D/3D)
- [ ] Audio (AudioServer)
- [ ] Input system

## After Updating

- [ ] Run `on-game-validate.py` against a sample Godot project to verify no false positives
- [ ] Update VERSION.md with new "Reference last updated" date
- [ ] Update the post-cutoff risk areas table
- [ ] Commit with message: `docs: update engine reference for Godot X.Y`
