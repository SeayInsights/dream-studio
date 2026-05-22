# TA3 Marker File Investigation

**Date:** 2026-05-22  
**Gating:** STOP — operator must choose marker creation approach before TA3 implementation proceeds.

---

## 1. Is `.dream-studio-project` created anywhere in production code?

**No.** The marker file is read in one place and never written by production code:

| Location | Role |
|----------|------|
| `emitters/claude_code/project.py:read_project_id()` | **Reader only** — reads first line as plain UUID |
| `tests/unit/test_skill_invoke.py:107` | Test fixture creates marker manually |
| `tests/unit/test_project_spine_wiring.py:68,82` | Test fixtures create marker manually |

No CLI command, no mutation function, and no hook writes this file.

---

## 2. Does any existing CLI command create a marker?

**No.** `ds project register` (in `interfaces/cli/ds.py:1293`) calls `core/projects/mutations.py:register_project()`, which:
- Inserts a row into `ds_projects`
- Emits a `project.created` canonical event
- Does **not** write any marker file

---

## 3. Do the existing registered projects have markers in their directories?

Checked `C:\Users\Dannis Seay\builds\` recursively (depth 3):

| Directory | Marker present? | Contents | Registered in DB? |
|-----------|----------------|----------|------------------|
| `builds/dream-cmd/` | **Yes** | `a4befdce-bfb6-40ed-9e83-ace93edac44b` (plain UUID) | Yes — Dream Command |
| `builds/torii/` | **Yes** | `916e8925-a62d-4599-80ba-60317a3ec180` (plain UUID) | **Not in active projects list** |
| `builds/dream-studio-clean/` | **No** | — | N/A (this IS the Dream Studio repo) |

Both existing markers are **plain text files** (first line = UUID, no JSON). They were created manually.

---

## 4. Current marker format vs. TA3 spec format

**Current format** (as read by `read_project_id()`):
```
a4befdce-bfb6-40ed-9e83-ace93edac44b
```
A plain text file. First line is a UUID string. Nothing else is required.

**TA3 spec format** (from the operator's instructions):
```json
{
  "schema_version": 1,
  "project_id": "<uuid>",
  "project_name": "<from ds_projects>",
  "created_at": "<iso timestamp>",
  "metadata": {
    "git_remote_url": "<from git config at creation time>",
    "registered_from_path": "<absolute path at creation, informational only>"
  }
}
```
A JSON file with structured fields. The `cwd_resolver` would parse this to return `CWDProjectContext(project_id, project_name, marker_path)`.

**This is a format change.** The existing plain-UUID markers in `dream-cmd` and `torii` are not valid JSON and cannot be parsed as the new format.

---

## 5. Format compatibility question

The TA3 `cwd_resolver.py` needs to know what to do with **old-format markers** (plain UUID):

- **Option C-1 (strict):** New JSON format only. Old markers return `None` from `resolve_project_from_cwd()`. Operator must re-run the marker creation command to upgrade existing markers.
- **Option C-2 (backward-compat):** Try JSON parse first; if that fails, fall back to reading first line as UUID. `project_name` would be `None` in the `CWDProjectContext` for old-format markers.

---

## 6. Options for marker creation (the main gating question)

### Option A — Extend `ds project register`

Extend the `register` command with an optional `--path <dir>` argument:

```
py -m interfaces.cli.ds project register --name "Dream Command" --path C:\Users\Dannis Seay\builds\dream-cmd
```

When `--path` is provided:
- Write the JSON marker to `<path>/.dream-studio-project`
- Register as normal in `ds_projects`

When `--path` is omitted:
- Register in `ds_projects` only (no marker, same behavior as today)

**Tradeoffs:**
- Natural: register + mark in one step
- Requires re-registering existing projects to get a marker, OR a separate backfill command
- `--path` is optional so existing callsites don't break
- The two existing markers (`dream-cmd`, `torii`) still need upgrading to JSON format

### Option B — New `ds project init` command

New command that an operator runs in the project directory after registration:

```
cd C:\Users\Dannis Seay\builds\dream-cmd
py -m interfaces.cli.ds project init <project_id>
```

- Writes the JSON marker in the current directory
- Does not modify `ds_projects` (project is already registered)
- Works for existing projects: operator runs `init` in each project dir to create/upgrade the marker

**Tradeoffs:**
- Clean separation of concerns (register = DB; init = filesystem)
- Operator must run two commands instead of one for new projects
- Handles existing registered projects naturally: `init` in each repo upgrades the marker
- `torii` (not in active DB) gets a marker when operator wants it; otherwise it stays orphaned

### Option B-2 — `ds project marker write` (more explicit naming)

Same as Option B but named to make the intent explicit. Not a distinct option, just a naming variant.

---

## 7. Summary of open questions requiring operator decision

**Q1 (required):** Option A (extend `register --path`) or Option B (new `init` command)?

**Q2 (required):** For `cwd_resolver` backward compat — Option C-1 (strict JSON only, existing plain-UUID markers return None) or Option C-2 (try JSON first, fall back to UUID-only format)?

**Q3 (informational):** The `torii` marker at `builds/torii` points to project `916e8925-a62d-4599-80ba-60317a3ec180` which is not in the active `ds_projects` list. Is this project registered in the DB under a different identity, or is the marker stale/orphaned? This affects what the CWD resolver should do when it finds a marker whose `project_id` doesn't exist in `ds_projects` — return the ID anyway (resolve by marker alone) or validate against DB and return None?

---

**STOPPED. Waiting for operator response on Q1, Q2, Q3 before any code is written.**
