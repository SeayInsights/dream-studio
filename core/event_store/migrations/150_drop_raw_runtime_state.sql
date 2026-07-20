-- Migration 150: drop raw_runtime_state — ds_config duplicate (WO-FILESDB-REVET)
--
-- raw_runtime_state (migration 146, WO-FILESDB-P2) has the identical
-- (key, value, updated_at) schema as the pre-existing ds_config table and served the
-- same purpose: singleton key -> JSON runtime state (active_skill / active_task /
-- platform). core/runtime_state.py now stores those singletons in ds_config under a
-- `runtime.` key namespace, so the dedicated table is a redundant duplicate.
--
-- Migration 146 was never released to a live authority DB (released_version stayed at
-- 143), so this DROP only keeps fresh-install / CI schema clean; no live data is
-- affected. Additive-safe: no other table references raw_runtime_state.

DROP TABLE IF EXISTS raw_runtime_state;
