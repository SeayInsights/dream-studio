# `ds uninstall` Contract

Status: active
Command: `ds uninstall`
Engine: `core.installed_productization.uninstall_runtime`
Preview (mandatory): `ds uninstall-check` / `ds uninstall` (no `--execute`)

## Purpose

`ds uninstall` removes Dream Studio's adapter wiring from a machine. It has three
tiers, each gated behind an explicit flag so that an accidental or default
invocation can never delete anything. `ds uninstall-check` (and `ds uninstall`
with no `--execute`) is the mandatory non-destructive preview: it inventories
what *would* be removed and mutates nothing.

## Flags

| Flag | Effect |
|------|--------|
| _(none)_ | Dry-run. Prints the inventory and the removed-vs-preserved plan. Mutates nothing. |
| `--execute` | Integration teardown: remove `.claude` hook wiring + global launchers. State is preserved. |
| `--purge-state` | Request the state-tier wipe. Inert unless combined with `--execute` **and** `--force`. |
| `--force` | The mandatory **second confirmation** for `--purge-state`. |
| `--backup-dir <dir>` | Where the automatic pre-purge backup is written (default: outside the home). |
| `--command-dir <dir>` | Launcher directory to clear (default: `~/.local/bin`). |
| `--claude-settings-path <path>` | Override the settings.json copies to clear (repeatable). |

## Tiers, removed vs preserved targets

### Tier 0 — Dry-run (default)
- **Removed:** nothing.
- **Preserved:** everything.
- Output: inventory + plan, `status: planned`.

### Tier 1 — Integration teardown (`--execute`)
- **Removed:**
  - Dream-Studio hook entries in **both** generated `.claude/settings.json` copies
    (the detected scope copy and the user-global `~/.claude/settings.json`) — the
    hook-projection model means both fire, so both must be cleared.
  - Global launchers `ds.cmd` and `ds.ps1` in the command directory.
- **Preserved:**
  - The `~/.dream-studio` **state tier**: `state/studio.db` (the SQLite authority),
    `config/`, `adapters/`, `router/`, `meta/`, `context-packets/`, `logs/`, `backups/`.
- **Reversibility:** a reinstall re-wires hooks and launchers against the preserved
  state. Tier 1 is fully reversible.

### Tier 2 — State purge (`--execute --purge-state --force`)
- Everything in Tier 1, **plus**:
  - **Removed:** the entire `~/.dream-studio` state tier.
  - **Safety:** refuses unless `--force` (the second confirmation) is present, and
    always takes an **automatic backup first**, written **outside** the home
    directory so the wipe cannot destroy it.
- Output: `status: purged`, with `backup_path` pointing at the pre-purge backup.

## Invariants

1. Default invocation mutates nothing (`--execute` required to apply).
2. `--purge-state` without `--force` is refused with no mutation (`status: refused`).
3. A state purge always backs up before deleting.
4. Foreign (non-Dream-Studio) hook entries in settings.json are never removed.
5. Both `.claude` settings.json copies are cleared — nothing left hanging.
