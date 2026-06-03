# ds-quality:learn:expand

Phase 19.4 — Guided Expansion with Example Compilation.

Compiles extension content from observed operator behavior stored in
ds_friction_signals and ds_user_extensions. Invoked after the operator
confirms a classification in `ds learn review`.

## Phase 19.4a: Personalization path only

Personalizations are compiled from the operator's actual dismissal patterns
in the `findings` table. Zero LLM. Zero speculation. The compiled content IS
the observed preference — not a description of the preference.

## The SkillsBench defense

SkillsBench (2026): LLM-authored skills +0.0pp vs human-curated +16.2pp.
This skill's defense: extension content is compiled from `finding_ids` the
operator actually dismissed. `compiled_from` must contain real source IDs.
If the compiler cannot find supporting evidence, compilation fails —
no content is written, and the signal returns to deferred state.

## Invocation

```
ds learn expand [--all] [extension_id]
```

## Paths implemented (19.4a)

- **personalization** — threshold_override or option_override derived from
  dismissed findings. Pure SQL. No LLM.

## Paths deferred

- **capability** — 19.4b. Requires LLM with strict event-sequence grounding.
- **onboarding** — 19.4c. LLM-authored docs only.

## Output

Compiled content written to `ds_user_extensions.content` (JSON).
Extension `status` remains `proposed` — 19.5 validates before promotion.
Canonical skills are never modified.
