# Canonical Event Reconciliation

Legacy `canonical_events` rows from an external backup are historical evidence, not active authority in the fresh installed runtime.

The reconciliation pipeline:

- opens the backup SQLite database in read-only mode;
- profiles event types and payload shapes;
- classifies each event into a taxonomy;
- maps only high-confidence events into current authority tables;
- writes an idempotent import map to `legacy_canonical_event_import_map`;
- records `backup:canonical_events:<event_id>` source refs for imported rows;
- routes low-confidence, stale, duplicated, or schema-weak events to retention or manual review;
- never recreates `canonical_events` as an active dashboard source.

Current high-confidence mappings are intentionally narrow:

- skill lifecycle events -> `execution_events` and `skill_invocations`;
- workflow lifecycle events -> `execution_events` and `workflow_invocations`;
- hook execution events -> `execution_events` and `hook_invocations`;
- security scan lifecycle events -> `execution_events`;
- source-ref-safe token usage events -> `token_usage_records`;
- existing security finding events -> duplicate-skipped against `security_findings`.

Token-usage import requires stable raw id or session context, nonnegative token counts, model, timestamp, and source refs in `token_usage_records`. Legacy raw token rows do not include cost, so imported records preserve token counts and mark cost as unavailable instead of inventing estimated spend. High-volume legacy validation failures remain `retention_only` unless a current dashboard or release gate explicitly needs them.
