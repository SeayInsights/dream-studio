---
dream_studio:
  skill_id: ds-quality
  pack: quality
  mode: groom
  mode_type: remediation
  inputs: [promoted_knowledge, gotcha_entries]
  outputs: [skill_edit, groom_pull_request, applied_lessons]
  capabilities_required: [Read, Write, Edit, Grep, Bash]
  model_preference: sonnet
  estimated_duration: 20-40min
  write_posture: hitl
  lifecycle: published
---

# Groom — Drain Promoted Lessons Into the Skill Text

## Trigger
`groom:`, `groom lessons:`, `apply lessons:`

## Why this mode exists

The learning loop captured and never landed. `insert_lesson()` writes to `raw_lessons`,
`on-agent-correction` feeds it, `lesson_threshold` counts per-skill pressure and says the
skill's SKILL.md or gotchas.yml wants review — and then nothing edited a skill. Measured
2026-09-18: 73 lessons, 40 pending, **21 promoted, 0 applied**. `promote` set a row's status
and a target and stopped there, so a promoted lesson and a landed one were indistinguishable
and `lesson_threshold` kept re-escalating skills whose lessons had already been read.

This mode is the terminus. It turns promoted lessons into an edit to the skill they name,
opens a pull request, and records arrival with `lesson_queue apply`.

## Posture

`hitl`. Opening the pull request is this mode's job and needs no approval — it is reversible
(close it, delete the branch). Merging it is the operator's. Skill text steers every later
session, so a self-merged edit to it compounds without anyone having read it once.

## Steps

1. **Pick the target.** Read the queue:
   ```
   py -m interfaces.cli.lesson_queue list --promoted
   py -m interfaces.cli.lesson_queue stats
   ```
   Group by the skill each lesson names. Take the skill with the most promoted lessons unless
   the operator named one. `core/learning/lesson_threshold.get_escalation_candidates()` gives
   the same ranking from the pending side.

2. **Read both sides.** The lesson rows (`title`, `what_happened`, `lesson`, `evidence`,
   `confidence`) and the skill's current text — its `SKILL.md`, and its `gotchas.yml` where
   one exists. A lesson whose guidance the text already carries is a duplicate.

3. **Classify each lesson.**
   - *already covered* — the text says it; skip, and apply it anyway so it stops re-escalating.
   - *gotcha* — a trap with a concrete symptom; it belongs in `gotchas.yml`.
   - *instruction* — changes what the mode does; it belongs in `SKILL.md` body text.
   - *too thin* — no evidence, or a single occurrence with low confidence; reject it with
     `lesson_queue reject` rather than carrying it forward.

4. **Draft the edit.** One edit per lesson, in the words the skill already uses. Keep the
   prose lowercase: `canonical/skills` carries a shouted-normative ceiling that the
   normative-baseline gate enforces, and a new capitalised rule there raises the count.

5. **Branch, commit, open the PR.**
   ```
   git checkout -b chore/groom-<skill>-lessons origin/main
   git commit -m "chore(skills): land <n> promoted lessons into <skill>"
   gh pr create --base main --fill
   ```
   Say in the body which lessons landed, which were rejected and why, and cite the lesson ids.
   The evidence-backed-output gate reads commit messages, so name the count and the ids there.

6. **Record arrival.** For each lesson that landed:
   ```
   py -m interfaces.cli.lesson_queue apply <lesson_id> --to <file>@<sha>
   ```
   This is what closes the loop. A lesson left at `promoted` after its edit shipped keeps
   inflating the queue and re-escalating a skill that was already updated.

7. **Hand the merge to the operator.** Report the PR number and stop. Do not merge.

## Guardrails

- The pull request stays open for review; merging it is the operator's call.
- A lesson is applied when its edit has shipped, not when it has been drafted.
- Regenerate the projections when a `SKILL.md` changes, so `skills/` and `.claude/` do not
  drift from `canonical/`.
- Lessons that say the same thing collapse into one edit, and each id is still applied.

## Done when

`lesson_queue list --promoted` is shorter than it was, every lesson the PR covers reads
`applied`, and the PR is open with the operator named as its reviewer.
