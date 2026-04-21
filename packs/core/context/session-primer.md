# Session Primer

This file is updated at the end of significant sessions. It is NOT loaded automatically at session start — it is read only when the Director asks for context from a previous session, or when an agent needs orientation on active work.

Last updated: _(date)_

---

## How to use this file

**Agents:** Read this file only when the Director asks for session context or references past work. Do not read it proactively.

**At session end:** Update this file when significant decisions were made, new systems were built, or active projects changed state. Keep it lean — 400 tokens max. Delete stale entries older than 2 weeks.

**Director:** If you want to orient a new session to past work, say: "load context" or "what was I working on?" The agent will then read this file and surface what's relevant.

---

## Active projects

_(Add your active projects here — status, repo, local path, last commit, next step. Example:)_

### _(Project name)_
- Status: _(active development / paused / shipped)_
- Repo: _(url)_
- Local: _(path)_
- Last commit: _(sha — short description)_
- Next: _(single-sentence next step)_

---

## Recent significant decisions

_(Dated entries. Delete anything older than 14 days unless it's a lasting architecture decision.)_

---

## System state

- Dream-studio install: _(path)_
- Config: `~/.dream-studio/config.json`
- State: `~/.dream-studio/state/` + `~/.dream-studio/meta/`

---

## Instructions for updating this file

At the end of a session where any of the following happened, update this file:
- A new agent, MCP server, or system was built
- A significant architecture decision was made
- An active project changed state
- A hard limit was hit or an escalation occurred

Update rules:
- Keep total file under 400 tokens
- Add new entries under the appropriate section
- Date every entry
- Remove entries older than 14 days unless they're architecture decisions
- Never include secrets, tokens, or PII
