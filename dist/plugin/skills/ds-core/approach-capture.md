# Approach Capture — Core Module

Reusable "what did we try, and how did it go" capture, shared by any mode that
records per-skill approach data for the Improvement Loop. Extracted from
`handoff` and `recap`, which both wrote the same structured record and gating
language independently — this is the one copy.

## Usage

When a mode needs to capture approach data, reference this module in the skill's SKILL.md with:
```
## Imports
- ../../approach-capture.md — approach/outcome capture for the Improvement Loop
```

## What gets recorded

For each skill invoked during the session, capture a structured entry:

- **skill** — the skill ID invoked (e.g. `core:build`, `quality:debug`)
- **approach** — one-line description of the approach taken
- **outcome** — one of `success`, `failure`, `partial`, `correction`
- **why** — why it worked or didn't (root cause, or the Director's stated reason
  for a correction)

## Persistence

Persist each entry through the maintained approach-history interface when one is
available in this checkout. When unavailable, keep the entries in the calling
mode's own file output instead of dropping them — never invent a separate,
undeclared store for this data.

## What stays with the caller

This module is the shared record shape and the persistence gating language only.
Each caller still owns:
- **When** in its own step sequence this runs (a mid-work mode captures before
  it writes its resumable state; a post-completion mode captures after writing
  its own record, once the session's outcome is known).
- **Where** the entries land in its own output (a field inside a JSON handoff
  document vs. a section of a markdown recap).
- **What it's for on the reading side** — a mid-work mode's caller reads these
  entries to resume; a post-completion mode's caller reads them to find patterns
  across sessions, so it also queries prior approaches before adding new ones.

## Used by
handoff, recap
