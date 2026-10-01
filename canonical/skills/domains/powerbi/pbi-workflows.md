# Power BI Workflows

End-to-end build / dev / deploy flows for Power BI work: file formats, the PBIP edit cycle, git
conventions, performance debugging, version pinning, and sharing.

## File format glossary

| Extension | What it is | When you see it |
|---|---|---|
| `.pbip` | Power BI Project — the modern source-control-friendly format (since April 2024). Folder structure with TMDL + JSON. | Active development. |
| `.pbix` | Power BI Desktop file — the legacy single-file binary. | Published reports, end-user files. |
| `.pbit` | Power BI Template — `.pbix` minus the data, plus metadata. Used to start new reports from a known starting point. | A pre-branded template, if the engagement has one. |
| `.bim` | Legacy semantic model JSON, pre-PBIP. | Old reports. Convert before substantive edits — see `quality-tiers-antipatterns.md`. |
| `.tmdl` | TMDL source files inside `.SemanticModel/definition/`. | Hand-edit these for model changes. |
| `.pbism` | Compiled binary semantic model manifest. | Inside `.SemanticModel/`. **Never hand-edit.** |
| `.pbir` | Report manifest. | Inside `.Report/`. |
| `.pbiviz` | Packaged custom visual. | Output of `npm run package` (see `custom-visuals.md`). |

## Editing a PBIP project

1. **Edit TMDL/JSON** in your editor (a TMDL syntax extension is recommended if available).
2. **Open the `.pbip`** in Power BI Desktop. It reads the source files, builds the in-memory
   model, and renders the report.
3. **Save in Power BI Desktop** to regenerate `.pbism` and any other compiled artifacts. Desktop
   will also reformat TMDL slightly on save — that's expected.
4. **Test changes** by interacting with the report.
5. **Commit** the changed `.tmdl` and `.json` files (and the regenerated `.pbism` — yes, even
   though it's binary; git tracks it as a binary diff).

### What to commit / ignore

```gitignore
# Inside .SemanticModel/
.pbi/                   # Power BI Desktop cache, machine-specific
*.bim.bak                # Backup files
diagramLayout.json.bak
```

For custom-visual repo `.gitignore` patterns, see `custom-visuals.md`'s "What to commit / ignore"
section.

## Applying the active brand profile's theme to a report

1. Resolve the active brand profile (see `brand-profile.md`) and its `theme_file`.
2. Open the report in Power BI Desktop.
3. View tab → Themes dropdown → **Browse for themes**.
4. Pick the active profile's `theme_file`.
5. Power BI applies the theme — chart colors, fonts, table styles update.
6. **Save the report.** The theme is now embedded; sharing the file shares the theme.

Starting a brand-new report from a pre-branded template, if the engagement has one, is a
template-specific step outside this skill's generic workflow — follow that template's own
instructions, then apply the active brand profile's theme as above if the template doesn't
already carry it.

## Git conventions

Commit messages: `feat:`, `fix:`, `chore:`, `docs:` prefix. Reference the report or visual in
scope.

Examples:
- `feat(scorecard): add Quintile Axis sort column to Brand dimension`
- `fix(measures): add DIVIDE guard to POS $ Sales - % Change`
- `chore(theme): bump dataColors[] to lead with the active brand profile's primary color`
- `docs: update report-visual-json notes for new Section Divider page`

For multi-file PBIP edits, prefer atomic commits — one logical change per commit, even if it
spans several TMDL files. Power BI Desktop tends to touch many files on save (lineageTag
regeneration, etc.), so review the diff before committing and exclude noise.

## Performance debugging

When a measure is slow:

1. **Performance Analyzer** (View tab → Performance Analyzer → Start recording → interact with
   the visual). Shows DAX query time, visual render time, other.
2. Copy the DAX query from Performance Analyzer.
3. Open **DAX Studio** (free download). Connect to the running Power BI Desktop instance.
4. Paste the query, run with **Server Timings** enabled.
5. Look for high formula-engine time relative to storage-engine time → likely poor DAX (nested
   `CALCULATE` without `VAR`s, expensive iterators, missing indices).

Common fixes:
- Replace nested `CALCULATE` with `VAR` blocks.
- Switch `IF` + `SUMX` to `CALCULATE` + filter where possible.
- Materialize intermediate aggregates as columns at refresh time.
- Reduce cardinality of related columns.

## Power BI Desktop version pinning

The PBIP format and TMDL schema evolve. Pin the team to a single Power BI Desktop version to
avoid drift across a shared repo. Major upgrades happen periodically; coordinate with the team
before upgrading, and record the pinned version wherever the team keeps its tooling conventions.

Symptoms of a version mismatch in a shared PBIP repo:
- TMDL files re-formatted on every save with whitespace-only diffs.
- New annotations appearing that older Desktop versions don't recognize.
- Custom visual API mismatches (see `custom-visuals.md` Gotcha #9/#10).

## Sharing a PBIP / PBIX

- **Internal review:** push the PBIP to the team's repo; reviewers clone and open in Power BI
  Desktop. Don't commit the `.pbi/` cache (gitignored).
- **Client delivery:** save as `.pbix` (File → Save As → Power BI Desktop file). Send the `.pbix`
  only — the client shouldn't see the source.
- **Organization rollout via Power BI Service:** publish from Power BI Desktop → File → Publish
  → choose workspace. Configure refresh in the Service.

## Pre-commit sanity checklist

- Open the report in Power BI Desktop. Does it load without errors? (Schema mismatches show as
  red banners.)
- Click each page. Do all visuals render? (Empty visuals mean broken bindings.)
- Hover over a few visuals. Does the tooltip show data?
- Apply each top-level slicer/filter. Does the data update?
- Check Performance Analyzer for any single visual taking over 2 seconds.
- Save → close → reopen. Does it still load?

If all green, commit. If any red, fix before committing.
