-- Migration 161: security_events.confidence / coverage / limitations -- a finding can say
-- how much of its check was real.
--
-- WHY. The unified Finding read model (core/findings/model.py) carries three honesty
-- fields: confidence (how sure the producer is), coverage (whether the check examined
-- everything it claims to) and limitations (what it cannot establish). Nothing could
-- store them, so every finding read from security_events was "unknown" whatever the
-- producer knew. A scan that skipped a step looked identical to a complete one.
--
-- NULL IS UNKNOWN. All three columns are nullable with no default, and a reader maps NULL
-- (and every row written before this migration) to "unknown" / "not recorded", never to
-- high or complete. A writer stores NULL for a value it does not have, or does not
-- recognise, rather than a certain-looking one.
--
-- THE VOCABULARY IS CLOSED, by CHECK, and mirrors CONFIDENCE_VALUES / COVERAGE_VALUES in
-- core/findings/model.py (tests/unit/test_finding_honesty_storage.py fails if the two
-- drift). limitations is a JSON array of strings: '[]' records "none exist", which is a
-- different statement from NULL, "not recorded".
--
-- ADDITIVE ONLY: three nullable columns on an existing append-only table. No row is
-- touched, no table is dropped, and no existing reader or writer changes shape: the
-- finding.recorded INSERTs that name their columns keep working unchanged.

ALTER TABLE security_events
    ADD COLUMN confidence TEXT
    CHECK (confidence IS NULL OR confidence IN ('high', 'medium', 'low', 'unknown'));

ALTER TABLE security_events
    ADD COLUMN coverage TEXT
    CHECK (coverage IS NULL OR coverage IN ('complete', 'partial', 'unknown'));

ALTER TABLE security_events
    ADD COLUMN limitations TEXT
    CHECK (limitations IS NULL OR json_valid(limitations));
