# ds-quality:learn:expand (audit invocation)

Trigger: `ds learn expand`

Lists ds_user_extensions rows with status='proposed' and classified as
personalization that have no compiled content yet. Operator selects rows
to compile, reviews output, then accepts or rejects.

## What the operator sees

For each pending extension:
- The originating friction signal (skill, rule, dismissal count)
- The proposed override (suppress rule X / raise threshold to Y)
- The compiled_from evidence (finding_ids cited)
- Prompt: accept (saves content) or reject (removes proposed row)

## Operator actions

- `accept` — saves compiled content to ds_user_extensions.content
- `reject` — removes the proposed extension row entirely
- `q / quit` — exit without acting on remaining rows

Status stays `proposed` after acceptance. 19.5 validates before `experimental`.
