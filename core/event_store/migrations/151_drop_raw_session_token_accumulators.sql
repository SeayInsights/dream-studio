-- Migration 151: drop raw_session_token_accumulators — derived-data duplicate (WO-FILESDB-REVET)
--
-- raw_session_token_accumulators (migration 145, WO-FILESDB-P2) held per-session token
-- running totals so normalize_stop could emit a token.consumption.recorded rollup at Stop.
-- That rollup is a denormalized SUM of the per-tool token.consumed events already in the
-- canonical substrate — and verified noise (~2,300 near-empty rollup events carrying ~4k
-- tokens, vs the real ~9.2M-token cost in token.consumed). The accumulator + the rollup
-- emission are retired; per-session totals now derive from token.consumed via the DuckDB
-- token_usage_records view (derived -> DuckDB, not a raw authority table + no disk fallback).
--
-- Migration 145 was never released to a live authority DB (released_version stayed 143), so
-- this DROP only keeps fresh-install / CI schema clean. Additive-safe: no table references it.

DROP TABLE IF EXISTS raw_session_token_accumulators;
